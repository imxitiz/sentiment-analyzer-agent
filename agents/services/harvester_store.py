"""Persistence layer for Phase 2 harvesting.

This module owns:
  - harvest-specific SQLite schema
  - reconstruction of planner context from the topic database
  - URL normalization and quality scoring helpers
  - an async writer queue that serializes writes safely into SQLite
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from Logging import context_logger, get_logger

from agents.harvester.models import HarvestedLink, HarvesterRuntimeConfig, ResearchBrief
from .planner_checkpoint import db_path_for_topic, init_topic_db

logger = get_logger("agents.services.harvester_store")

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
    "si",
    "utm_campaign",
    "utm_content",
    "utm_id",
    "utm_medium",
    "utm_name",
    "utm_source",
    "utm_term",
}
_LOW_VALUE_PATTERNS = (
    "/login",
    "/signup",
    "/privacy",
    "/terms",
    "/share",
    "/intent/",
    "/sharer",
)
_LOW_VALUE_DOMAINS = (
    "duckduckgo.com",
    "bing.com",
    "search.yahoo.com",
    "accounts.google.com",
    "news.google.com",
)
_LOW_SIGNAL_QUERY_KEYS = {
    "ia",
    "iax",
    "iaxm",
    "assist",
    "ceid",
    "hl",
    "gl",
}
_LOW_SIGNAL_TITLES = {
    "all",
    "images",
    "videos",
    "news",
    "maps",
    "home",
    "sign in",
    "search assist",
    "duck.ai",
    "learn more",
}
_SENTIMENT_EVIDENCE_TERMS = (
    "opinion",
    "reaction",
    "react",
    "debate",
    "support",
    "oppose",
    "critic",
    "criticism",
    "praise",
    "concern",
    "comment",
    "comments",
    "discussion",
    "thread",
    "public sentiment",
)
_NEUTRAL_INFO_TERMS = (
    "date",
    "calendar",
    "time and date",
    "holiday list",
    "office holidays",
)
_PLATFORM_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit.com",),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "news": ("news.google.com",),
    "wiki": ("wikipedia.org", "wikidata.org", "wikimedia.org"),
    "hackernews": ("news.ycombinator.com",),
    "bluesky": ("bsky.app",),
    "medium": ("medium.com",),
    "substack": ("substack.com",),
}
_PLATFORM_HINT_ALIASES: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit", "subreddit", "r/"),
    "x": ("twitter", "x", "tweet", "hashtag"),
    "facebook": ("facebook", "fb"),
    "instagram": ("instagram", "insta"),
    "youtube": ("youtube", "yt", "video"),
    "tiktok": ("tiktok",),
    "wiki": ("wikipedia", "wiki", "wikidata"),
    "news_site": ("news site", "news", "editorial", "article", "newspaper"),
}
_NEWS_DOMAIN_KEYWORDS = (
    "news",
    "post",
    "times",
    "herald",
    "journal",
    "tribune",
    "republic",
    "republica",
    "khabar",
    "kantipur",
    "himalayan",
    "aljazeera",
    "bbc",
    "npr",
    "livemint",
    "economictimes",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(topic: str) -> sqlite3.Connection:
    path = db_path_for_topic(topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_harvest_tables(topic: str) -> Path:
    """Ensure harvesting tables exist in the topic database."""
    init_topic_db(topic)
    with _connect(topic) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS harvest_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                source_agent TEXT NOT NULL,
                llm_provider TEXT,
                llm_model TEXT,
                plan_json TEXT,
                config_json TEXT,
                stats_json TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discovered_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                discovery_query TEXT,
                discovered_at TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                quality_score REAL NOT NULL DEFAULT 0.0,
                relevance_score REAL NOT NULL DEFAULT 0.0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                extra_meta_json TEXT,
                raw_payload_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS link_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                unique_id TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                url TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                discovery_query TEXT,
                position INTEGER,
                domain TEXT,
                platform TEXT,
                title TEXT,
                description TEXT,
                author TEXT,
                published_at TEXT,
                quality_score REAL NOT NULL DEFAULT 0.0,
                relevance_score REAL NOT NULL DEFAULT 0.0,
                accepted INTEGER NOT NULL DEFAULT 0,
                rejection_reason TEXT,
                extra_meta_json TEXT,
                raw_payload_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_discovered_links_status
            ON discovered_links(status, platform, quality_score DESC, last_seen_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_discovered_links_domain_platform
            ON discovered_links(domain, platform)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_link_observations_lookup
            ON link_observations(normalized_url, observed_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_link_observations_domain_platform
            ON link_observations(domain, platform)
            """
        )
    return db_path_for_topic(topic)


def backfill_platform_labels(topic: str) -> dict[str, int]:
    """Backfill platform labels for known domains in harvested tables.

    This keeps historical rows useful for downstream routing when platform
    support expands (for example wiki-specific scraping paths).
    """
    init_harvest_tables(topic)
    updated_discovered = 0
    updated_observations = 0

    with _connect(topic) as conn:
        discovered_rows = conn.execute(
            """
            SELECT id, url, domain, platform
            FROM discovered_links
            """
        ).fetchall()
        for row_id, url, domain, platform in discovered_rows:
            normalized_domain = str(domain or "").lower().strip()
            candidate_url = (
                f"https://{normalized_domain}" if normalized_domain else str(url or "")
            )
            inferred = infer_platform(candidate_url, None)
            if not inferred:
                continue
            current = str(platform or "").strip().lower()
            if current == inferred:
                continue
            conn.execute(
                "UPDATE discovered_links SET platform = ? WHERE id = ?",
                (inferred, int(row_id)),
            )
            updated_discovered += 1

        observation_rows = conn.execute(
            """
            SELECT id, url, domain, platform
            FROM link_observations
            """
        ).fetchall()
        for row_id, url, domain, platform in observation_rows:
            normalized_domain = str(domain or "").lower().strip()
            candidate_url = (
                f"https://{normalized_domain}" if normalized_domain else str(url or "")
            )
            inferred = infer_platform(candidate_url, None)
            if not inferred:
                continue
            current = str(platform or "").strip().lower()
            if current == inferred:
                continue
            conn.execute(
                "UPDATE link_observations SET platform = ? WHERE id = ?",
                (inferred, int(row_id)),
            )
            updated_observations += 1

    return {
        "discovered_links": updated_discovered,
        "link_observations": updated_observations,
    }


def backfill_published_dates(topic: str) -> dict[str, int]:
    """Backfill missing published_at values from raw payload JSON."""
    init_harvest_tables(topic)
    discovered_updates = 0
    observation_updates = 0

    with _connect(topic) as conn:
        discovered_rows = conn.execute(
            """
            SELECT id, published_at, raw_payload_json
            FROM discovered_links
            WHERE COALESCE(TRIM(published_at), '') = ''
              AND COALESCE(TRIM(raw_payload_json), '') != ''
            """
        ).fetchall()
        for row_id, published_at, raw_payload_json in discovered_rows:
            try:
                payload = json.loads(raw_payload_json) if raw_payload_json else {}
            except json.JSONDecodeError:
                payload = {}
            resolved = _resolve_published_at(published_at, payload)
            if not resolved:
                continue
            conn.execute(
                "UPDATE discovered_links SET published_at = ? WHERE id = ?",
                (resolved, int(row_id)),
            )
            discovered_updates += 1

        observation_rows = conn.execute(
            """
            SELECT id, published_at, raw_payload_json
            FROM link_observations
            WHERE COALESCE(TRIM(published_at), '') = ''
              AND COALESCE(TRIM(raw_payload_json), '') != ''
            """
        ).fetchall()
        for row_id, published_at, raw_payload_json in observation_rows:
            try:
                payload = json.loads(raw_payload_json) if raw_payload_json else {}
            except json.JSONDecodeError:
                payload = {}
            resolved = _resolve_published_at(published_at, payload)
            if not resolved:
                continue
            conn.execute(
                "UPDATE link_observations SET published_at = ? WHERE id = ?",
                (resolved, int(row_id)),
            )
            observation_updates += 1

    return {
        "discovered_links": discovered_updates,
        "link_observations": observation_updates,
    }


def backfill_harvest_metadata(topic: str) -> dict[str, dict[str, int]]:
    """Apply metadata backfills needed by scraping routing logic."""
    platform_stats = backfill_platform_labels(topic)
    published_stats = backfill_published_dates(topic)
    return {
        "platform": platform_stats,
        "published_at": published_stats,
    }


def load_research_brief(topic: str) -> ResearchBrief:
    """Reconstruct planner output from append-only artifacts."""
    init_topic_db(topic)
    brief = ResearchBrief(topic=topic)
    with _connect(topic) as conn:
        rows = conn.execute(
            """
            SELECT artifact_type, value, meta_json
            FROM pipeline_artifacts
            WHERE source_agent = 'planner'
            ORDER BY id ASC
            """
        ).fetchall()

    for artifact_type, value, meta_json in rows:
        if artifact_type == "planner_topic_summary":
            brief.topic_summary = value
        elif artifact_type == "planner_estimated_volume":
            brief.estimated_volume = value
        elif artifact_type == "planner_stop_condition":
            brief.stop_condition = value
        elif artifact_type == "planner_reasoning":
            brief.reasoning = value
        elif artifact_type == "planner_keyword" and value not in brief.keywords:
            brief.keywords.append(value)
        elif artifact_type == "planner_hashtag" and value not in brief.hashtags:
            brief.hashtags.append(value)
        elif artifact_type == "planner_query" and value not in brief.search_queries:
            brief.search_queries.append(value)
        elif artifact_type == "planner_platform":
            meta = json.loads(meta_json) if meta_json else {}
            brief.platforms.append(
                {
                    "name": value,
                    "priority": str(meta.get("priority", "medium")),
                    "reason": str(meta.get("reason", "")),
                }
            )

    if not brief.search_queries:
        base_queries = [topic]
        if brief.keywords:
            base_queries.extend(brief.keywords[:4])
        brief.search_queries = list(dict.fromkeys(base_queries))

    return brief


def start_harvest_run(
    topic: str,
    *,
    run_id: str,
    source_agent: str,
    llm_provider: str,
    llm_model: str | None,
    plan_json: str,
    config_data: dict[str, Any],
) -> None:
    """Insert or replace a harvest run record."""
    init_harvest_tables(topic)
    now = _utc_now()
    with _connect(topic) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO harvest_runs(
                run_id, created_at, updated_at, status, source_agent,
                llm_provider, llm_model, plan_json, config_json, stats_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now,
                now,
                "running",
                source_agent,
                llm_provider,
                llm_model,
                plan_json,
                json.dumps(config_data, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                None,
            ),
        )


def finish_harvest_run(
    topic: str,
    *,
    run_id: str,
    status: str,
    stats: dict[str, Any],
    error: str | None = None,
) -> None:
    """Finalize a harvest run record."""
    with _connect(topic) as conn:
        conn.execute(
            """
            UPDATE harvest_runs
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


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication without losing semantic identity."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in _TRACKING_QUERY_KEYS
    ]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        params="",
        query=urlencode(query_items, doseq=True),
        fragment="",
    )
    return str(urlunparse(normalized))


def url_unique_id(normalized_url: str) -> str:
    """Stable unique ID for a normalized URL."""
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:24]


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _normalize_platform_hint(hinted_platform: str | None) -> str | None:
    hint = (hinted_platform or "").strip().lower()
    if not hint or hint in {"web", "generic"}:
        return None

    if hint in _PLATFORM_DOMAIN_HINTS:
        return hint
    if hint == "news":
        return "news_site"

    for canonical, aliases in _PLATFORM_HINT_ALIASES.items():
        if any(alias in hint for alias in aliases):
            return canonical
    return None


def _looks_like_news_domain(domain: str) -> bool:
    lowered = (domain or "").lower()
    if not lowered:
        return False
    # any(token in lowered for token in _NEWS_DOMAIN_KEYWORDS)
    matches_domain_keywords = any(token in lowered for token in _NEWS_DOMAIN_KEYWORDS)

    # or if ends with or starts with "news" or "post" or "times" etc
    matches_generic_news_patterns = bool(
        re.search(r"(news|post|times|herald|journal|tribune|republic|khabar)", lowered)
    )

    return matches_domain_keywords or matches_generic_news_patterns


def _parse_published_at(raw_value: Any) -> str | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, (int, float)):
        if raw_value <= 0:
            return None
        try:
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc).isoformat()
        except Exception:
            return None

    if not isinstance(raw_value, str):
        return None

    value = raw_value.strip()
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    for fmt in (
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None


def _resolve_published_at(
    published_at: str | None,
    raw_payload: dict[str, Any],
) -> str | None:
    parsed = _parse_published_at(published_at)
    if parsed:
        return parsed

    primary_keys = (
        "published_at",
        "publishedAt",
        "published",
        "date",
        "datetime",
        "pubDate",
        "publication_date",
        "published_date",
        "article_date",
        "created_at",
        "createdAt",
        "created",
        "timestamp",
        "unix_timestamp",
        "epoch",
        "time",
    )

    for key in primary_keys:
        parsed = _parse_published_at(raw_payload.get(key))
        if parsed:
            return parsed

    stack: list[Any] = [raw_payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                key_l = str(key).lower()
                if any(
                    token in key_l
                    for token in ("date", "time", "published", "created", "timestamp")
                ):
                    parsed = _parse_published_at(value)
                    if parsed:
                        return parsed
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    stack.append(item)
    return None


def infer_platform(url: str, hinted_platform: str | None = None) -> str:
    domain = extract_domain(url)
    for platform, domain_hints in _PLATFORM_DOMAIN_HINTS.items():
        if any(domain.endswith(item) for item in domain_hints):
            return platform
    if _looks_like_news_domain(domain):
        return "news_site"

    # Use planner/LLM hints only as a last resort when domain routing cannot
    # classify the URL.
    normalized_hint = _normalize_platform_hint(hinted_platform)
    if normalized_hint:
        return normalized_hint

    return "web"


def is_probably_low_value_url(url: str) -> bool:
    normalized = normalize_url(url)
    if not normalized:
        return True
    lowered = normalized.lower()
    parsed = urlparse(normalized)
    domain = (parsed.netloc or "").lower()

    if any(
        domain == item or domain.endswith(f".{item}") for item in _LOW_VALUE_DOMAINS
    ):
        return True

    if any(
        pattern in parsed.path.lower() for pattern in ("/search", "/topics/", "/home")
    ):
        return True

    query_keys = {
        key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    }
    if query_keys.intersection(_LOW_SIGNAL_QUERY_KEYS):
        return True

    if any(pattern in lowered for pattern in _LOW_VALUE_PATTERNS):
        return True
    if lowered.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js")):
        return True
    return False


def score_link(
    link: HarvestedLink, brief: ResearchBrief
) -> tuple[float, float, str | None]:
    """Return quality score, relevance score, and optional rejection reason."""
    normalized_url = normalize_url(link.url)
    if not normalized_url:
        return 0.0, 0.0, "invalid_url"
    if is_probably_low_value_url(normalized_url):
        return 0.05, 0.05, "low_value_url"

    text = " ".join(
        part
        for part in [
            link.title,
            link.description,
            link.discovery_query,
            link.metadata.get("anchor_text", ""),
        ]
        if part
    ).lower()
    cleaned_title = (link.title or "").strip().lower()
    if cleaned_title in _LOW_SIGNAL_TITLES:
        return 0.05, 0.05, "navigation_link"

    terms = {
        item.lower().strip("# ")
        for item in [brief.topic, *brief.keywords[:25], *brief.hashtags[:15]]
        if item
    }

    matched_terms = sum(1 for term in terms if term and term in text)
    evidence_matches = sum(1 for term in _SENTIMENT_EVIDENCE_TERMS if term in text)
    neutral_matches = sum(1 for term in _NEUTRAL_INFO_TERMS if term in text)

    relevance = min(
        1.0,
        0.15
        + matched_terms * 0.12
        + evidence_matches * 0.04
        + max(0.0, link.relevance_signal),
    )

    quality = 0.2
    if link.title:
        quality += 0.12
    if link.description:
        quality += 0.10
    if link.author:
        quality += 0.05
    if link.published_at:
        quality += 0.05
    if link.position is not None:
        quality += max(0.0, (20 - min(link.position, 20)) * 0.01)
    inferred_platform = infer_platform(link.url, None)
    if inferred_platform != "web":
        quality += 0.08
    quality += min(0.18, evidence_matches * 0.03)
    quality -= min(0.2, neutral_matches * 0.05)

    # Camoufox browser discovery can emit search/navigation links; down-rank
    # low-evidence web pages aggressively so they don't dominate the queue.
    if link.source_name in {"camoufox_browser", "camoufox_agentic"}:
        if inferred_platform == "web" and evidence_matches == 0:
            quality -= 0.25

    quality += max(0.0, link.quality_signal)
    quality += relevance * 0.35
    quality = min(1.0, max(0.0, quality))

    return quality, relevance, None


@dataclass(slots=True)
class WriterStats:
    queued: int = 0
    observations_written: int = 0
    links_inserted: int = 0
    links_updated: int = 0
    duplicates_seen: int = 0
    rejected_low_quality: int = 0
    rejected_invalid: int = 0
    write_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class AsyncLinkWriter:
    """Single-writer async queue for SQLite ingestion.

    All concurrent harvester tasks submit records here. A single consumer flushes
    batched writes through SQLite in a thread, which avoids write races while
    preserving high parallelism in the source collectors.
    """

    def __init__(
        self,
        *,
        topic: str,
        brief: ResearchBrief,
        config: HarvesterRuntimeConfig,
        run_id: str,
        actor: str = "harvester",
    ) -> None:
        self._topic = topic
        self._brief = brief
        self._config = config
        self._run_id = run_id
        self._queue: asyncio.Queue[HarvestedLink | None] = asyncio.Queue(
            maxsize=config.writer_queue_size
        )
        self._stop_event = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._stats = WriterStats()
        self._log = context_logger(
            "agents.services.harvester_writer",
            actor=actor,
            phase="HARVESTER",
            topic=topic,
        )

    @property
    def stats(self) -> dict[str, int]:
        return self._stats.as_dict()

    @property
    def is_full(self) -> bool:
        return (
            self._stats.links_inserted >= self._config.max_links
            or self._stop_event.is_set()
        )

    async def start(self) -> None:
        init_harvest_tables(self._topic)
        self._worker = asyncio.create_task(
            self._run(), name=f"harvest-writer:{self._topic}"
        )

    async def submit(self, link: HarvestedLink) -> bool:
        if self.is_full:
            return False
        self._stats.queued += 1
        await self._queue.put(link)
        return True

    async def submit_many(self, links: list[HarvestedLink]) -> int:
        accepted = 0
        for link in links:
            if self.is_full:
                break
            stored = await self.submit(link)
            accepted += int(stored)
        return accepted

    async def close(self) -> None:
        await self._queue.put(None)
        if self._worker is not None:
            await self._worker

    async def _run(self) -> None:
        batch: list[HarvestedLink] = []
        while True:
            item = await self._queue.get()
            if item is None:
                if batch:
                    await asyncio.to_thread(self._write_batch_sync, batch)
                    batch = []
                self._queue.task_done()
                break

            batch.append(item)
            self._queue.task_done()
            if len(batch) >= self._config.writer_batch_size:
                await asyncio.to_thread(self._write_batch_sync, batch)
                batch = []

        self._stop_event.set()

    def _write_batch_sync(self, batch: list[HarvestedLink]) -> None:
        with _connect(self._topic) as conn:
            for link in batch:
                try:
                    self._write_one_sync(conn, link)
                except Exception as exc:
                    self._stats.write_errors += 1
                    self._log.error(
                        "Link write failed: %s",
                        exc,
                        action="link_write_error",
                        reason=type(exc).__name__,
                        meta={"url": link.url, "source": link.source_name},
                    )

    def _write_one_sync(self, conn: sqlite3.Connection, link: HarvestedLink) -> None:
        link.published_at = _resolve_published_at(link.published_at, link.raw_payload)
        normalized_url = normalize_url(link.url)
        quality_score, relevance_score, rejection_reason = score_link(link, self._brief)
        unique_id = url_unique_id(normalized_url) if normalized_url else ""
        domain = extract_domain(normalized_url) if normalized_url else ""
        platform = infer_platform(normalized_url or link.url, None)
        observed_at = _utc_now()
        accepted = bool(
            normalized_url
            and quality_score >= self._config.min_quality_score
            and not self.is_full
        )
        if not normalized_url:
            self._stats.rejected_invalid += 1
            rejection_reason = rejection_reason or "invalid_url"
        elif not accepted:
            self._stats.rejected_low_quality += 1
            rejection_reason = rejection_reason or "below_quality_threshold"

        conn.execute(
            """
            INSERT INTO link_observations(
                run_id, observed_at, unique_id, normalized_url, url,
                source_name, source_type, discovery_query, position,
                domain, platform, title, description, author, published_at,
                quality_score, relevance_score, accepted, rejection_reason,
                extra_meta_json, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._run_id,
                observed_at,
                unique_id,
                normalized_url,
                link.url,
                link.source_name,
                link.source_type,
                link.discovery_query,
                link.position,
                domain,
                platform,
                link.title,
                link.description,
                link.author,
                link.published_at,
                quality_score,
                relevance_score,
                int(accepted),
                rejection_reason,
                json.dumps(link.metadata, ensure_ascii=False),
                json.dumps(link.raw_payload, ensure_ascii=False, default=str),
            ),
        )
        self._stats.observations_written += 1

        if not accepted:
            return

        row = conn.execute(
            """
            SELECT id, duplicate_count, quality_score, relevance_score, extra_meta_json
            FROM discovered_links
            WHERE normalized_url = ?
            """,
            (normalized_url,),
        ).fetchone()

        payload_meta = json.dumps(link.metadata, ensure_ascii=False)
        payload_raw = json.dumps(link.raw_payload, ensure_ascii=False, default=str)
        if row:
            existing_meta = json.loads(row[4]) if row[4] else {}
            merged_meta = {**existing_meta, **link.metadata}
            conn.execute(
                """
                UPDATE discovered_links
                SET url = ?, domain = ?, platform = ?,
                    title = CASE WHEN LENGTH(COALESCE(title, '')) >= LENGTH(?) THEN title ELSE ? END,
                    description = CASE WHEN LENGTH(COALESCE(description, '')) >= LENGTH(?) THEN description ELSE ? END,
                    author = COALESCE(author, ?),
                    published_at = COALESCE(published_at, ?),
                    source_name = ?,
                    source_type = ?,
                    discovery_query = ?,
                    last_seen_at = ?,
                    quality_score = MAX(quality_score, ?),
                    relevance_score = MAX(relevance_score, ?),
                    duplicate_count = duplicate_count + 1,
                    extra_meta_json = ?,
                    raw_payload_json = ?
                WHERE normalized_url = ?
                """,
                (
                    normalized_url,
                    domain,
                    platform,
                    link.title,
                    link.title,
                    link.description,
                    link.description,
                    link.author,
                    link.published_at,
                    link.source_name,
                    link.source_type,
                    link.discovery_query,
                    observed_at,
                    quality_score,
                    relevance_score,
                    json.dumps(merged_meta, ensure_ascii=False),
                    payload_raw,
                    normalized_url,
                ),
            )
            self._stats.links_updated += 1
            self._stats.duplicates_seen += 1
            return

        conn.execute(
            """
            INSERT INTO discovered_links(
                unique_id, normalized_url, url, topic, domain, platform,
                title, description, author, published_at,
                source_name, source_type, discovery_query, discovered_at,
                first_seen_at, last_seen_at, status, quality_score,
                relevance_score, duplicate_count, extra_meta_json, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id,
                normalized_url,
                normalized_url,
                self._topic,
                domain,
                platform,
                link.title,
                link.description,
                link.author,
                link.published_at,
                link.source_name,
                link.source_type,
                link.discovery_query,
                observed_at,
                observed_at,
                observed_at,
                "PENDING",
                quality_score,
                relevance_score,
                0,
                payload_meta,
                payload_raw,
            ),
        )
        self._stats.links_inserted += 1
        if self._stats.links_inserted >= self._config.max_links:
            self._stop_event.set()
