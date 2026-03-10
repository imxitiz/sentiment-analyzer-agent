"""SQLite checkpoint and queue state for phase-3 deep scraping."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from Logging import get_logger

from .planner_checkpoint import db_path_for_topic, init_topic_db

if TYPE_CHECKING:
    from agents.scraper.models import ScrapeTarget

logger = get_logger("agents.services.scraper_store")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(topic: str) -> sqlite3.Connection:
    path = db_path_for_topic(topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_scraper_tables(topic: str) -> Path:
    """Ensure scraper tables exist in the per-topic SQLite database."""
    init_topic_db(topic)
    with _connect(topic) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                source_agent TEXT NOT NULL,
                config_json TEXT,
                stats_json TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discovered_link_id INTEGER,
                unique_id TEXT NOT NULL UNIQUE,
                normalized_url TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                topic TEXT NOT NULL,
                domain TEXT,
                platform TEXT,
                title TEXT,
                description TEXT,
                author TEXT,
                published_at TEXT,
                quality_score REAL NOT NULL DEFAULT 0.0,
                relevance_score REAL NOT NULL DEFAULT 0.0,
                source_name TEXT,
                status TEXT NOT NULL DEFAULT 'not_started',
                attempts INTEGER NOT NULL DEFAULT 0,
                selected_backend TEXT,
                last_error TEXT,
                document_id TEXT,
                started_at TEXT,
                completed_at TEXT,
                last_scraped_at TEXT,
                updated_at TEXT NOT NULL,
                extra_meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scrape_targets_status
            ON scrape_targets(status, attempts, quality_score DESC, relevance_score DESC)
            """
        )
    return db_path_for_topic(topic)


def bootstrap_scrape_targets(topic: str) -> int:
    """Copy discovered links into the scraper queue if not already present."""
    init_scraper_tables(topic)
    now = _utc_now()
    with _connect(topic) as conn:
        exists = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'discovered_links'
            """
        ).fetchone()
        if not exists:
            return 0

        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO scrape_targets(
                discovered_link_id,
                unique_id,
                normalized_url,
                url,
                topic,
                domain,
                platform,
                title,
                description,
                author,
                published_at,
                quality_score,
                relevance_score,
                source_name,
                status,
                attempts,
                updated_at,
                extra_meta_json
            )
            SELECT
                id,
                unique_id,
                normalized_url,
                url,
                topic,
                domain,
                COALESCE(platform, 'web'),
                title,
                description,
                author,
                published_at,
                quality_score,
                relevance_score,
                source_name,
                'not_started',
                0,
                ?,
                extra_meta_json
            FROM discovered_links
            WHERE normalized_url IS NOT NULL AND normalized_url != ''
            """,
            (now,),
        )
        return conn.total_changes - before


def start_scrape_run(
    topic: str,
    *,
    run_id: str,
    source_agent: str,
    config_data: dict[str, Any],
) -> None:
    """Insert or replace a scraper run record."""
    init_scraper_tables(topic)
    now = _utc_now()
    with _connect(topic) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scrape_runs(
                run_id, created_at, updated_at, status, source_agent,
                config_json, stats_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now,
                now,
                "running",
                source_agent,
                json.dumps(config_data, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                None,
            ),
        )


def finish_scrape_run(
    topic: str,
    *,
    run_id: str,
    status: str,
    stats: dict[str, Any],
    error: str | None = None,
) -> None:
    """Finalize a scraper run."""
    with _connect(topic) as conn:
        conn.execute(
            """
            UPDATE scrape_runs
            SET updated_at = ?, status = ?, stats_json = ?, error = ?
            WHERE run_id = ?
            """,
            (
                _utc_now(),
                status,
                json.dumps(stats, ensure_ascii=False),
                error,
                run_id,
            ),
        )


def load_scrape_targets(
    topic: str,
    *,
    statuses: Iterable[str] = ("not_started",),
    limit: int = 250,
) -> list[ScrapeTarget]:
    """Load the next batch of targets ready for scraping."""
    from agents.scraper.models import ScrapeTarget

    init_scraper_tables(topic)
    status_list = list(statuses)
    placeholders = ", ".join("?" for _ in status_list)
    query = f"""
        SELECT
            discovered_link_id,
            unique_id,
            normalized_url,
            url,
            topic,
            domain,
            platform,
            title,
            description,
            author,
            published_at,
            quality_score,
            relevance_score,
            source_name,
            status,
            attempts,
            extra_meta_json
        FROM scrape_targets
        WHERE status IN ({placeholders})
        ORDER BY quality_score DESC, relevance_score DESC, id ASC
        LIMIT ?
    """
    with _connect(topic) as conn:
        rows = conn.execute(query, [*status_list, max(1, limit)]).fetchall()

    targets: list[ScrapeTarget] = []
    for row in rows:
        extra_meta = json.loads(row[16]) if row[16] else {}
        targets.append(
            ScrapeTarget(
                discovered_link_id=row[0],
                unique_id=row[1],
                normalized_url=row[2],
                url=row[3],
                topic=row[4],
                domain=row[5],
                platform=row[6] or "web",
                title=row[7] or "",
                description=row[8] or "",
                author=row[9],
                published_at=row[10],
                quality_score=float(row[11] or 0.0),
                relevance_score=float(row[12] or 0.0),
                source_name=row[13] or "",
                status=row[14] or "not_started",
                attempts=int(row[15] or 0),
                extra_meta=extra_meta,
            )
        )
    return targets


def update_scrape_target(
    topic: str,
    *,
    normalized_url: str,
    status: str,
    attempts: int | None = None,
    selected_backend: str | None = None,
    last_error: str | None = None,
    document_id: str | None = None,
    mark_started: bool = False,
    mark_completed: bool = False,
) -> None:
    """Update target state inside the topic queue."""
    init_scraper_tables(topic)
    now = _utc_now()
    with _connect(topic) as conn:
        current = conn.execute(
            "SELECT attempts FROM scrape_targets WHERE normalized_url = ?",
            (normalized_url,),
        ).fetchone()
        next_attempts = (
            attempts if attempts is not None else int(current[0] or 0) if current else 0
        )
        conn.execute(
            """
            UPDATE scrape_targets
            SET status = ?, attempts = ?, selected_backend = ?, last_error = ?,
                document_id = COALESCE(?, document_id),
                started_at = COALESCE(started_at, ?),
                completed_at = ?,
                last_scraped_at = ?,
                updated_at = ?
            WHERE normalized_url = ?
            """,
            (
                status,
                next_attempts,
                selected_backend,
                last_error,
                document_id,
                now if mark_started else None,
                now if mark_completed else None,
                now if status == "completed" else None,
                now,
                normalized_url,
            ),
        )


def scrape_status_counts(topic: str) -> dict[str, int]:
    """Return aggregate counts by scraper queue state."""
    init_scraper_tables(topic)
    with _connect(topic) as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*)
            FROM scrape_targets
            GROUP BY status
            """
        ).fetchall()
    return {str(status): int(count) for status, count in rows}


def load_latest_scrape_stats(topic: str) -> dict[str, Any] | None:
    """Return the latest scrape run stats, if available."""
    path = db_path_for_topic(topic)
    if not path.exists():
        return None

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT stats_json, status
            FROM scrape_runs
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None

    stats_json, status = row
    stats = json.loads(stats_json) if stats_json else {}
    if isinstance(stats, dict):
        stats["status"] = status
        return stats
    return {"status": status}


__all__ = [
    "bootstrap_scrape_targets",
    "finish_scrape_run",
    "init_scraper_tables",
    "load_latest_scrape_stats",
    "load_scrape_targets",
    "scrape_status_counts",
    "start_scrape_run",
    "update_scrape_target",
]
