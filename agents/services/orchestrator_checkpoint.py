"""Orchestrator-level checkpoint service.

Stores topic intake metadata in a central orchestrator database and
links each run to a per-topic SQLite database path.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Logging import get_logger

from .planner_checkpoint import (
    db_path_for_topic,
    init_topic_db,
    save_pipeline_artifact,
    save_topic_input,
)

logger = get_logger("agents.services.orchestrator_checkpoint")

_ORCHESTRATOR_DB = Path("data/scrapes/orchestrator.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect_orchestrator() -> sqlite3.Connection:
    _ORCHESTRATOR_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_ORCHESTRATOR_DB)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_orchestrator_db() -> Path:
    """Create central orchestrator checkpoint DB schema if missing."""
    with _connect_orchestrator() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                topic_slug TEXT NOT NULL,
                topic_db_path TEXT NOT NULL,
                status TEXT NOT NULL,
                active_agent TEXT,
                retries INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orchestrator_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                agent TEXT,
                status TEXT,
                message TEXT,
                meta_json TEXT,
                FOREIGN KEY (run_id) REFERENCES topic_runs(run_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orchestrator_events_run
            ON orchestrator_events(run_id, created_at)
            """
        )
    return _ORCHESTRATOR_DB


def create_topic_run(topic: str) -> dict[str, str]:
    """Create a new run row for the incoming topic."""
    topic = topic.strip()
    init_orchestrator_db()

    run_id = str(uuid.uuid4())
    topic_db = init_topic_db(topic)
    topic_slug = topic_db.stem
    now = _utc_now()

    with _connect_orchestrator() as conn:
        conn.execute(
            """
            INSERT INTO topic_runs(
                run_id, created_at, updated_at, topic, topic_slug,
                topic_db_path, status, active_agent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now,
                now,
                topic,
                topic_slug,
                str(topic_db),
                "received",
                "orchestrator",
            ),
        )

    record_orchestrator_event(
        run_id,
        event_type="topic_received",
        agent="orchestrator",
        status="received",
        message=f"Topic received: {topic}",
        meta={"topic_db": str(topic_db)},
    )

    return {
        "run_id": run_id,
        "topic": topic,
        "topic_slug": topic_slug,
        "topic_db_path": str(topic_db),
    }


def record_orchestrator_event(
    run_id: str,
    *,
    event_type: str,
    agent: str,
    status: str,
    message: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Append orchestrator event for audit/debug purposes."""
    init_orchestrator_db()
    with _connect_orchestrator() as conn:
        conn.execute(
            """
            INSERT INTO orchestrator_events(
                run_id, created_at, event_type, agent, status, message, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _utc_now(),
                event_type,
                agent,
                status,
                message,
                json.dumps(meta, ensure_ascii=False) if meta else None,
            ),
        )


def update_topic_run(
    run_id: str,
    *,
    status: str,
    active_agent: str | None = None,
    retries: int | None = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Update central run status and append a status event."""
    init_orchestrator_db()

    with _connect_orchestrator() as conn:
        existing = conn.execute(
            "SELECT retries, meta_json FROM topic_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if not existing:
            return

        next_retries = retries if retries is not None else int(existing[0] or 0)
        existing_meta = json.loads(existing[1]) if existing[1] else {}
        merged_meta = {**existing_meta, **(meta or {})}

        conn.execute(
            """
            UPDATE topic_runs
            SET updated_at = ?, status = ?, active_agent = ?, retries = ?, error = ?, meta_json = ?
            WHERE run_id = ?
            """,
            (
                _utc_now(),
                status,
                active_agent,
                next_retries,
                error,
                json.dumps(merged_meta, ensure_ascii=False) if merged_meta else None,
                run_id,
            ),
        )

    record_orchestrator_event(
        run_id,
        event_type="status_update",
        agent=active_agent or "orchestrator",
        status=status,
        message=f"Run status updated to {status}",
        meta={"retries": next_retries, "error": error} | (meta or {}),
    )


def bootstrap_topic(topic: str) -> dict[str, str]:
    """Initialize run metadata + per-topic DB immediately on topic intake."""
    run = create_topic_run(topic)
    topic_text = topic.strip()

    save_topic_input(
        topic_text,
        topic_text,
        input_type="topic",
        source_agent="orchestrator",
    )
    save_pipeline_artifact(
        topic_text,
        source_agent="orchestrator",
        artifact_type="topic_received",
        value=topic_text,
        meta={
            "run_id": run["run_id"],
            "topic_db_path": run["topic_db_path"],
        },
    )

    logger.info(
        "Topic bootstrapped  run_id=%s topic=%s",
        run["run_id"],
        topic_text,
        action="topic_bootstrap",
        meta={
            "topic_slug": run["topic_slug"],
            "topic_db_path": run["topic_db_path"],
        },
    )
    return run


def get_latest_run_id(topic: str) -> str | None:
    """Return latest run_id for a topic, if any."""
    init_orchestrator_db()
    with _connect_orchestrator() as conn:
        row = conn.execute(
            """
            SELECT run_id
            FROM topic_runs
            WHERE topic = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (topic.strip(),),
        ).fetchone()
    return str(row[0]) if row else None


def topic_db_for(topic: str) -> str:
    """Return deterministic topic DB path string."""
    return str(db_path_for_topic(topic.strip()))
