"""Document-store abstraction for phase-3 scraped content.

The scraper runtime depends on this interface rather than on MongoDB
directly so the underlying store can be replaced later without changing the
agent or source adapters.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pymongo import ReturnDocument

from Logging import context_logger, get_logger

from .planner_checkpoint import db_path_for_topic
from utils.mongodb import get_mongo_database

if TYPE_CHECKING:
    from agents.scraper.models import ScrapedContent, ScrapeTarget

logger = get_logger("agents.services.document_store")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _hash_url(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_document_id(normalized_url: str) -> str:
    return f"doc_{_hash_url(normalized_url)[:24]}"


def _extract_reference_url(item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    candidates = [
        item.get("source_url"),
        item.get("url"),
        metadata.get("url"),
        metadata.get("link"),
        metadata.get("permalink"),
        metadata.get("story_url"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _normalize_content_items(
    *, normalized_url: str, document: ScrapedContent
) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(document.content_items):
        if not isinstance(raw_item, dict):
            continue
        metadata = raw_item.get("metadata") if isinstance(raw_item.get("metadata"), dict) else {}
        item_url = _extract_reference_url(raw_item)
        text = str(raw_item.get("text") or "").strip()
        title = str(raw_item.get("title") or "").strip()
        kind = str(raw_item.get("kind") or "content")
        author_name = raw_item.get("author")
        author = {"name": author_name} if author_name else None
        fingerprint_source = item_url or f"{kind}:{title}:{text[:160]}:{index}"
        normalized_items.append(
            {
                "item_id": _hash_text(f"{normalized_url}:{fingerprint_source}")
                or f"item_{index}",
                "position": index,
                "kind": kind,
                "url": item_url,
                "title": title or None,
                "text": text or None,
                "excerpt": text[:280] if text else None,
                "author": author,
                "published_at": raw_item.get("published_at"),
                "depth": raw_item.get("depth"),
                "geo": raw_item.get("geo") or metadata.get("geo") or {},
                "metrics": {
                    key: value
                    for key, value in metadata.items()
                    if key
                    in {
                        "score",
                        "num_comments",
                        "reply_count",
                        "repost_count",
                        "like_count",
                        "quote_count",
                        "descendants",
                        "upvote_ratio",
                    }
                },
                "references": [
                    {
                        "kind": "source",
                        "url": item_url,
                        "label": title or item_url,
                    }
                ]
                if item_url
                else [],
                "metadata": metadata,
            }
        )
    return normalized_items


def _summarize_authors(document: ScrapedContent, content_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    authors: dict[str, dict[str, Any]] = {}
    for raw_author in document.authors:
        if not isinstance(raw_author, dict):
            continue
        name = str(raw_author.get("name") or raw_author.get("handle") or "").strip()
        if name:
            authors[name] = dict(raw_author)

    primary_author = str(document.author or "").strip()
    if primary_author and primary_author not in authors:
        authors[primary_author] = {"name": primary_author}

    for item in content_items:
        author = item.get("author") if isinstance(item.get("author"), dict) else None
        if not author:
            continue
        name = str(author.get("name") or "").strip()
        if name and name not in authors:
            authors[name] = dict(author)
    return list(authors.values())


def _collect_references(
    *, target: ScrapeTarget, document: ScrapedContent, content_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    references: list[dict[str, Any]] = []

    def _push(reference: dict[str, Any]) -> None:
        url = reference.get("url")
        if not isinstance(url, str) or not url.strip() or url in seen:
            return
        seen.add(url)
        references.append(reference)

    _push(
        {
            "kind": "canonical",
            "url": document.final_url or target.url,
            "label": document.title or target.title or target.url,
        }
    )
    for reference in document.references:
        if isinstance(reference, dict):
            _push(reference)
    for item in content_items:
        for reference in item.get("references") or []:
            if isinstance(reference, dict):
                _push(reference)
    return references


def _build_topic_ref(
    *, topic: str, topic_slug: str, run_id: str, target: ScrapeTarget, status: str, document_id: str | None = None
) -> dict[str, Any]:
    payload = {
        "topic": topic,
        "topic_slug": topic_slug,
        "run_id": run_id,
        "status": status,
        "quality_score": target.quality_score,
        "relevance_score": target.relevance_score,
        "source_name": target.source_name,
        "discovered_link_id": target.discovered_link_id,
        "target_id": target.unique_id,
        "attempts": target.attempts,
        "last_seen_at": _utc_now(),
    }
    if target.published_at:
        payload["published_at"] = target.published_at
    if document_id:
        payload["document_id"] = document_id
    return payload


def _build_document_payload(
    *,
    topic: str,
    topic_slug: str,
    run_id: str,
    target: ScrapeTarget,
    document: ScrapedContent,
    document_id: str,
) -> dict[str, Any]:
    now = _utc_now()
    content_hash = _hash_text(document.content_text or document.raw_text or "")
    content_items = _normalize_content_items(
        normalized_url=target.normalized_url,
        document=document,
    )
    authors = _summarize_authors(document, content_items)
    references = _collect_references(
        target=target,
        document=document,
        content_items=content_items,
    )
    return {
        "schema_version": 2,
        "document_id": document_id,
        "target_id": target.unique_id,
        "run_id": run_id,
        "topic": topic,
        "topic_slug": topic_slug,
        "canonical_url": document.final_url or target.url,
        "normalized_url": target.normalized_url,
        "normalized_url_hash": _hash_url(target.normalized_url),
        "domain": document.domain or target.domain,
        "platform": document.platform or target.platform,
        "entity_type": document.entity_type,
        "fetch_backend": document.fetch_backend,
        "http_status": document.http_status,
        "title": document.title or target.title,
        "description": document.description or target.description,
        "author": document.author or target.author,
        "authors": authors,
        "published_at": document.published_at or target.published_at,
        "language": document.language,
        "site_name": document.site_name,
        "geo": document.geo,
        "engagement": document.engagement,
        "references": references,
        "provenance": {
            "source_name": target.source_name,
            "discovered_link_id": target.discovered_link_id,
            "backend": document.fetch_backend,
            **document.provenance,
        },
        "content_text": document.content_text,
        "excerpt": document.excerpt,
        "raw_text": document.raw_text,
        "raw_html": document.raw_html,
        "markdown": document.markdown,
        "content_items": content_items,
        "metadata": document.metadata,
        "raw_payload": document.raw_payload,
        "content_hash": content_hash,
        "analysis_state": {
            "cleaning": "not_started",
            "sentiment": "not_started",
        },
        "updated_at": now,
        "last_scraped_at": now,
        "topic_refs": {
            topic_slug: _build_topic_ref(
                topic=topic,
                topic_slug=topic_slug,
                run_id=run_id,
                target=target,
                status="completed",
                document_id=document_id,
            )
        },
    }


class BaseDocumentStore(ABC):
    """Abstract storage contract for scraped targets and raw documents."""

    @abstractmethod
    def ensure_indexes(self) -> None:
        """Prepare the backing store for efficient writes and lookups."""

    @abstractmethod
    def start_run(
        self,
        *,
        topic: str,
        run_id: str,
        source_agent: str,
        config_data: dict[str, Any],
    ) -> None:
        """Record the start of a scraper run."""

    @abstractmethod
    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        stats: dict[str, Any],
        error: str | None = None,
    ) -> None:
        """Finalize a scraper run."""

    @abstractmethod
    def sync_targets(
        self, *, topic: str, run_id: str, targets: list[ScrapeTarget]
    ) -> int:
        """Mirror topic-scoped scrape targets into the document store."""

    @abstractmethod
    def find_document(self, normalized_url: str) -> dict[str, Any] | None:
        """Return an existing scraped document if already present."""

    @abstractmethod
    def mark_target_status(
        self,
        *,
        topic: str,
        normalized_url: str,
        status: str,
        run_id: str,
        backend: str | None = None,
        error: str | None = None,
        document_id: str | None = None,
        attempts: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Update per-target scrape status in the backing store."""

    @abstractmethod
    def save_document(
        self,
        *,
        topic: str,
        run_id: str,
        target: ScrapeTarget,
        document: ScrapedContent,
    ) -> dict[str, Any]:
        """Persist a scraped raw document and link it back to its target."""

    @abstractmethod
    def attach_existing_document(
        self,
        *,
        topic: str,
        run_id: str,
        target: ScrapeTarget,
        existing_document: dict[str, Any],
    ) -> dict[str, Any]:
        """Attach an existing raw document to a new topic/target reference."""


class MongoDocumentStore(BaseDocumentStore):
    """MongoDB-backed implementation of the scraper document store."""

    def __init__(self) -> None:
        self._db = get_mongo_database(app_name="sentiment-analyzer-agent-scraper")
        self._targets = self._db["scrape_targets"]
        self._documents = self._db["scraped_documents"]
        self._runs = self._db["scrape_runs"]
        self._log = context_logger(
            "agents.services.document_store.mongo",
            actor="document_store",
            phase="SCRAPER",
        )

    def ensure_indexes(self) -> None:
        self._targets.create_index("normalized_url", unique=True)
        self._targets.create_index("normalized_url_hash")
        self._targets.create_index("target_ids")
        self._targets.create_index("topic_slugs")
        self._targets.create_index("scrape_status.state")
        self._targets.create_index("scrape_status.last_attempt_at")
        self._targets.create_index([("platform", 1), ("domain", 1)])

        self._documents.create_index("document_id", unique=True)
        self._documents.create_index("normalized_url", unique=True)
        self._documents.create_index("normalized_url_hash")
        self._documents.create_index("topic_slugs")
        self._documents.create_index("analysis_state.cleaning")
        self._documents.create_index("analysis_state.sentiment")
        self._documents.create_index("content_hash")
        self._documents.create_index("authors.name")
        self._documents.create_index("references.url")
        self._documents.create_index("content_items.item_id")
        self._documents.create_index([("platform", 1), ("published_at", -1)])
        self._documents.create_index([("topic_slugs", 1), ("platform", 1), ("published_at", -1)])

        self._runs.create_index("run_id", unique=True)
        self._runs.create_index("topic")

    def start_run(
        self,
        *,
        topic: str,
        run_id: str,
        source_agent: str,
        config_data: dict[str, Any],
    ) -> None:
        now = _utc_now()
        self._runs.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "topic": topic,
                    "topic_slug": db_path_for_topic(topic).stem,
                    "source_agent": source_agent,
                    "status": "running",
                    "updated_at": now,
                    "config": config_data,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        stats: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self._runs.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": _utc_now(),
                    "stats": stats,
                    "error": error,
                }
            },
        )

    def sync_targets(
        self, *, topic: str, run_id: str, targets: list[ScrapeTarget]
    ) -> int:
        topic_slug = db_path_for_topic(topic).stem
        now = _utc_now()
        synced = 0
        for target in targets:
            topic_ref = _build_topic_ref(
                topic=topic,
                topic_slug=topic_slug,
                run_id=run_id,
                target=target,
                status=target.status,
            )

            self._targets.update_one(
                {"normalized_url": target.normalized_url},
                {
                    "$set": {
                        "target_id": target.unique_id,
                        "canonical_url": target.url,
                        "normalized_url": target.normalized_url,
                        "normalized_url_hash": _hash_url(target.normalized_url),
                        "domain": target.domain,
                        "platform": target.platform,
                        "title": target.title,
                        "description": target.description,
                        "author": target.author,
                        "published_at": target.published_at,
                        "updated_at": now,
                        "last_seen_at": now,
                        "latest_run_id": run_id,
                        f"topic_refs.{topic_slug}": topic_ref,
                    },
                    "$setOnInsert": {
                        "created_at": now,
                        "first_seen_at": now,
                        "scrape_status": {
                            "state": target.status,
                            "attempts": target.attempts,
                        },
                    },
                    "$addToSet": {
                        "topics": topic,
                        "topic_slugs": topic_slug,
                        "target_ids": target.unique_id,
                    },
                },
                upsert=True,
            )
            synced += 1
        return synced

    def find_document(self, normalized_url: str) -> dict[str, Any] | None:
        return self._documents.find_one({"normalized_url": normalized_url})

    def mark_target_status(
        self,
        *,
        topic: str,
        normalized_url: str,
        status: str,
        run_id: str,
        backend: str | None = None,
        error: str | None = None,
        document_id: str | None = None,
        attempts: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        topic_slug = db_path_for_topic(topic).stem
        now = _utc_now()
        update_fields: dict[str, Any] = {
            "updated_at": now,
            "latest_run_id": run_id,
            "scrape_status.state": status,
            "scrape_status.last_attempt_at": now,
            f"topic_refs.{topic_slug}.status": status,
            f"topic_refs.{topic_slug}.last_attempt_at": now,
        }
        if backend:
            update_fields["scrape_status.backend"] = backend
            update_fields[f"topic_refs.{topic_slug}.backend"] = backend
        if error is not None:
            update_fields["scrape_status.last_error"] = error
            update_fields[f"topic_refs.{topic_slug}.last_error"] = error
        if document_id:
            update_fields["scrape_status.document_id"] = document_id
            update_fields[f"topic_refs.{topic_slug}.document_id"] = document_id
        if attempts is not None:
            update_fields["scrape_status.attempts"] = attempts
            update_fields[f"topic_refs.{topic_slug}.attempts"] = attempts
        if extra:
            for key, value in extra.items():
                update_fields[f"scrape_status.meta.{key}"] = value
                update_fields[f"topic_refs.{topic_slug}.meta.{key}"] = value

        self._targets.update_one(
            {"normalized_url": normalized_url},
            {"$set": update_fields},
            upsert=True,
        )

    def attach_existing_document(
        self,
        *,
        topic: str,
        run_id: str,
        target: ScrapeTarget,
        existing_document: dict[str, Any],
    ) -> dict[str, Any]:
        topic_slug = db_path_for_topic(topic).stem
        now = _utc_now()
        document_id = str(
            existing_document.get("document_id")
            or _stable_document_id(target.normalized_url)
        )
        topic_ref = _build_topic_ref(
            topic=topic,
            topic_slug=topic_slug,
            run_id=run_id,
            target=target,
            status="completed",
            document_id=document_id,
        )
        saved = self._documents.find_one_and_update(
            {"normalized_url": target.normalized_url},
            {
                "$set": {
                    "updated_at": now,
                    "last_reused_at": now,
                    f"topic_refs.{topic_slug}": topic_ref,
                },
                "$addToSet": {
                    "topics": topic,
                    "topic_slugs": topic_slug,
                    "target_ids": target.unique_id,
                },
                "$inc": {"reuse_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return saved or {"document_id": document_id}

    def save_document(
        self,
        *,
        topic: str,
        run_id: str,
        target: ScrapeTarget,
        document: ScrapedContent,
    ) -> dict[str, Any]:
        topic_slug = db_path_for_topic(topic).stem
        now = _utc_now()
        existing = self.find_document(target.normalized_url) or {}
        document_id = str(
            existing.get("document_id") or _stable_document_id(target.normalized_url)
        )
        payload = _build_document_payload(
            topic=topic,
            topic_slug=topic_slug,
            run_id=run_id,
            target=target,
            document=document,
            document_id=document_id,
        )
        topic_ref = dict(payload.pop("topic_refs", {})).get(topic_slug, {})

        saved = self._documents.find_one_and_update(
            {"normalized_url": target.normalized_url},
            {
                "$set": {
                    **payload,
                    f"topic_refs.{topic_slug}": topic_ref,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
                "$addToSet": {
                    "topics": topic,
                    "topic_slugs": topic_slug,
                    "target_ids": target.unique_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        self.mark_target_status(
            topic=topic,
            normalized_url=target.normalized_url,
            status="completed",
            run_id=run_id,
            backend=document.fetch_backend,
            document_id=document_id,
            attempts=target.attempts,
        )
        self._log.info(
            "Saved scraped document  url=%s backend=%s",
            target.normalized_url,
            document.fetch_backend,
            action="save_document",
            meta={
                "document_id": document_id,
                "platform": document.platform,
                "content_items": len(document.content_items),
            },
        )
        return saved or {"document_id": document_id}


def build_document_store() -> BaseDocumentStore:
    """Return the active document-store implementation."""
    store = MongoDocumentStore()
    store.ensure_indexes()
    return store


__all__ = ["BaseDocumentStore", "MongoDocumentStore", "build_document_store"]
