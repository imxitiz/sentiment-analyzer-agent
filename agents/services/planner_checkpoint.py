"""SQLite checkpoint service for topic inputs and planner artifacts.

This module persists per-topic execution data so planner outputs and
agent responses can be resumed/debugged after failures.

Storage model:
    - one SQLite database per topic under ``data/scrapes/<topic>.db``
    - table ``topic_inputs`` for user topic + clarifications
    - table ``pipeline_artifacts`` for planner outputs and agent events
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Logging import get_logger

logger = get_logger("agents.services.planner_checkpoint")

_DB_DIR = Path("data/scrapes")


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:80].strip("-") or "untitled-topic"


def db_path_for_topic(topic: str) -> Path:
    """Return per-topic SQLite path, creating parent directory if needed."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    return _DB_DIR / f"{_slugify(topic)}.db"


def _connect(topic: str) -> sqlite3.Connection:
    path = db_path_for_topic(topic)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_topic_db(topic: str) -> Path:
    """Ensure checkpoint tables exist for a topic database."""
    with _connect(topic) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                input_type TEXT NOT NULL,
                source_agent TEXT NOT NULL,
                content TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_agent TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                value TEXT NOT NULL,
                meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_status (
                agent_name TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_type
            ON pipeline_artifacts(artifact_type, created_at)
            """
        )
    return db_path_for_topic(topic)


def save_topic_input(
    topic: str,
    content: str,
    *,
    input_type: str,
    source_agent: str = "user",
) -> None:
    """Insert user-provided topic or clarification row."""
    init_topic_db(topic)
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect(topic) as conn:
        conn.execute(
            """
            INSERT INTO topic_inputs(created_at, input_type, source_agent, content)
            VALUES (?, ?, ?, ?)
            """,
            (created_at, input_type, source_agent, content.strip()),
        )


def save_pipeline_artifact(
    topic: str,
    *,
    source_agent: str,
    artifact_type: str,
    value: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Insert planner/agent artifact as append-only event row."""
    init_topic_db(topic)
    created_at = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
    with _connect(topic) as conn:
        conn.execute(
            """
            INSERT INTO pipeline_artifacts(created_at, source_agent, artifact_type, value, meta_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (created_at, source_agent, artifact_type, value, meta_json),
        )


def save_planner_plan(
    topic: str,
    *,
    plan: Any,
    raw_output: str,
    source_agent: str = "planner",
) -> None:
    """Persist planner result as row-wise artifacts for recovery/debugging."""
    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else dict(plan)

    save_pipeline_artifact(
        topic,
        source_agent=source_agent,
        artifact_type="planner_raw_output",
        value=raw_output,
    )

    for key in ("topic_summary", "estimated_volume", "stop_condition", "reasoning"):
        value = str(plan_dict.get(key, "")).strip()
        if not value:
            continue
        save_pipeline_artifact(
            topic,
            source_agent=source_agent,
            artifact_type=f"planner_{key}",
            value=value,
        )

    for keyword in plan_dict.get("keywords", []):
        if not keyword:
            continue
        save_pipeline_artifact(
            topic,
            source_agent=source_agent,
            artifact_type="planner_keyword",
            value=str(keyword),
        )

    for hashtag in plan_dict.get("hashtags", []):
        if not hashtag:
            continue
        save_pipeline_artifact(
            topic,
            source_agent=source_agent,
            artifact_type="planner_hashtag",
            value=str(hashtag),
        )

    for query in plan_dict.get("search_queries", []):
        if not query:
            continue
        save_pipeline_artifact(
            topic,
            source_agent=source_agent,
            artifact_type="planner_query",
            value=str(query),
        )

    for platform in plan_dict.get("platforms", []):
        if not platform:
            continue

        if hasattr(platform, "model_dump"):
            platform_dict = platform.model_dump()
        elif isinstance(platform, dict):
            platform_dict = platform
        else:
            platform_dict = {"name": str(platform)}

        save_pipeline_artifact(
            topic,
            source_agent=source_agent,
            artifact_type="planner_platform",
            value=str(platform_dict.get("name", "unknown")),
            meta={
                "priority": platform_dict.get("priority", ""),
                "reason": platform_dict.get("reason", ""),
            },
        )

    logger.info(
        "Planner plan checkpointed  topic=%s",
        topic,
        action="planner_checkpoint",
        meta={
            "keywords": len(plan_dict.get("keywords", [])),
            "hashtags": len(plan_dict.get("hashtags", [])),
            "queries": len(plan_dict.get("search_queries", [])),
            "platforms": len(plan_dict.get("platforms", [])),
        },
    )


def upsert_agent_status(
    topic: str,
    *,
    agent_name: str,
    status: str,
    retries: int | None = None,
    last_error: str | None = None,
    mark_started: bool = False,
    mark_completed: bool = False,
    meta: dict[str, Any] | None = None,
) -> None:
    """Upsert status row for an agent in a topic DB."""
    init_topic_db(topic)
    now = datetime.now(timezone.utc).isoformat()

    with _connect(topic) as conn:
        row = conn.execute(
            """
            SELECT retries, started_at, meta_json
            FROM agent_status
            WHERE agent_name = ?
            """,
            (agent_name,),
        ).fetchone()

        if row:
            existing_retries = int(row[0] or 0)
            started_at = row[1] or (now if mark_started else None)
            existing_meta = json.loads(row[2]) if row[2] else {}
            merged_meta = {**existing_meta, **(meta or {})}

            conn.execute(
                """
                UPDATE agent_status
                SET status = ?, retries = ?, last_error = ?, started_at = ?,
                    updated_at = ?, completed_at = ?, meta_json = ?
                WHERE agent_name = ?
                """,
                (
                    status,
                    retries if retries is not None else existing_retries,
                    last_error,
                    started_at,
                    now,
                    now if mark_completed else None,
                    json.dumps(merged_meta, ensure_ascii=False)
                    if merged_meta
                    else None,
                    agent_name,
                ),
            )
            return

        conn.execute(
            """
            INSERT INTO agent_status(
                agent_name, status, retries, last_error,
                started_at, updated_at, completed_at, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_name,
                status,
                retries or 0,
                last_error,
                now if mark_started else None,
                now,
                now if mark_completed else None,
                json.dumps(meta, ensure_ascii=False) if meta else None,
            ),
        )


def increment_agent_retry(topic: str, *, agent_name: str, error: str) -> int:
    """Increment retry count for an agent and return the updated value."""
    init_topic_db(topic)
    with _connect(topic) as conn:
        row = conn.execute(
            "SELECT retries FROM agent_status WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        retries = int(row[0] or 0) + 1 if row else 1

    upsert_agent_status(
        topic,
        agent_name=agent_name,
        status="retrying",
        retries=retries,
        last_error=error,
    )
    return retries
