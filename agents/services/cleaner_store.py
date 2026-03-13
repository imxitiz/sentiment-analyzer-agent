"""MongoDB persistence helpers for phase-4 cleaning."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import importlib
from typing import Any

from pymongo import ReturnDocument

from agents.cleaner.models import CleanerPlan, CleanerResult, CleaningRuntimeConfig
from Logging import context_logger
from env import config
from utils.mongodb import get_mongo_database

from .planner_checkpoint import db_path_for_topic


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: str | None, default: int, *, min_value: int = 1) -> int:
    try:
        parsed = int(value or default)
        return max(min_value, parsed)
    except (TypeError, ValueError):
        return default


def _to_float(
    value: str | None, default: float, *, min_value: float = 0.0, max_value: float = 1.0
) -> float:
    try:
        parsed = float(value or default)
    except (TypeError, ValueError):
        return default
    return min(max_value, max(min_value, parsed))


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_cleaning_runtime_config() -> CleaningRuntimeConfig:
    """Build phase-4 runtime settings from environment variables."""
    preferred_languages_raw = config.get("CLEANER_PREFERRED_LANGUAGES") or "en"
    preferred_languages = tuple(
        part.strip().lower()
        for part in preferred_languages_raw.split(",")
        if part.strip()
    ) or ("en",)
    extraction_backends_raw = (
        config.get("CLEANER_EXTRACTION_BACKENDS")
        or "content_fields,trafilatura,readability,bs4"
    )
    extraction_backends = tuple(
        part.strip().lower()
        for part in extraction_backends_raw.split(",")
        if part.strip()
    ) or ("content_fields", "bs4")

    return CleaningRuntimeConfig(
        max_concurrency=_to_int(config.get("CLEANER_MAX_CONCURRENCY"), 8),
        max_documents_per_run=_to_int(config.get("CLEANER_MAX_DOCUMENTS_PER_RUN"), 500),
        sample_review_rate=_to_float(config.get("CLEANER_SAMPLE_REVIEW_RATE"), 0.05),
        max_sample_reviews=_to_int(config.get("CLEANER_MAX_SAMPLE_REVIEWS"), 20),
        min_clean_chars=_to_int(config.get("CLEANER_MIN_CLEAN_CHARS"), 30, min_value=1),
        max_clean_chars=_to_int(
            config.get("CLEANER_MAX_CLEAN_CHARS"), 12000, min_value=200
        ),
        remove_punctuation=_to_bool(config.get("CLEANER_REMOVE_PUNCTUATION"), True),
        lowercase_text=_to_bool(config.get("CLEANER_LOWERCASE_TEXT"), True),
        replace_urls_with_token=_to_bool(
            config.get("CLEANER_REPLACE_URLS_WITH_TOKEN"), True
        ),
        replace_mentions_with_token=_to_bool(
            config.get("CLEANER_REPLACE_MENTIONS_WITH_TOKEN"), True
        ),
        preserve_case_for_shouting=_to_bool(
            config.get("CLEANER_PRESERVE_CASE_FOR_SHOUTING"), False
        ),
        extraction_backends=extraction_backends,
        min_alpha_ratio=_to_float(config.get("CLEANER_MIN_ALPHA_RATIO"), 0.35),
        max_url_ratio=_to_float(config.get("CLEANER_MAX_URL_RATIO"), 0.3),
        max_symbol_ratio=_to_float(config.get("CLEANER_MAX_SYMBOL_RATIO"), 0.35),
        reject_non_preferred_languages=_to_bool(
            config.get("CLEANER_REJECT_NON_PREFERRED_LANGUAGES"), False
        ),
        preferred_languages=preferred_languages,
        enable_fuzzy_dedupe=_to_bool(config.get("CLEANER_ENABLE_FUZZY_DEDUPE"), True),
        fuzzy_dedupe_threshold=_to_float(
            config.get("CLEANER_FUZZY_DEDUPE_THRESHOLD"), 93.0, max_value=100.0
        ),
        fuzzy_candidate_limit=_to_int(config.get("CLEANER_FUZZY_CANDIDATE_LIMIT"), 250),
        llm_plan_enabled=_to_bool(config.get("CLEANER_LLM_PLAN_ENABLED"), True),
        llm_plan_sample_size=_to_int(config.get("CLEANER_LLM_PLAN_SAMPLE_SIZE"), 24),
        llm_plan_max_chars_per_sample=_to_int(
            config.get("CLEANER_LLM_PLAN_MAX_CHARS_PER_SAMPLE"), 1600
        ),
        llm_fallback_max_chars=_to_int(
            config.get("CLEANER_LLM_FALLBACK_MAX_CHARS"), 2200
        ),
        llm_force_full_rewrite=_to_bool(
            config.get("CLEANER_LLM_FORCE_FULL_REWRITE"), False
        ),
        llm_fallback_enabled=_to_bool(config.get("CLEANER_LLM_FALLBACK_ENABLED"), True),
    )


class CleanerDocumentStore:
    """Store for retrieving raw docs and saving cleaned outputs."""

    def __init__(self) -> None:
        self._db = get_mongo_database(app_name="sentiment-analyzer-agent-cleaner")
        self._raw = self._db["scraped_documents"]
        self._cleaned = self._db["cleaned_documents"]
        self._runs = self._db["clean_runs"]
        self._log = context_logger(
            "agents.services.cleaner_store",
            actor="cleaner_store",
            phase="CLEANER",
        )

    def ensure_indexes(self) -> None:
        self._raw.create_index([("analysis_state.cleaning", 1), ("updated_at", -1)])
        self._raw.create_index([("topic_slugs", 1), ("analysis_state.cleaning", 1)])
        self._raw.create_index("cleaning.cleaned_hash")
        self._raw.create_index("cleaning.cleaned_signature")
        self._cleaned.create_index("document_id", unique=True)
        self._cleaned.create_index([("topic_slug", 1), ("status", 1)])
        self._cleaned.create_index("cleaned_hash")
        self._cleaned.create_index("cleaned_signature")
        self._runs.create_index("run_id", unique=True)
        self._runs.create_index([("topic", 1), ("created_at", -1)])

    def start_run(
        self,
        *,
        topic: str,
        run_id: str,
        runtime: CleaningRuntimeConfig,
        plan: CleanerPlan | None = None,
    ) -> None:
        now = _utc_now()
        self._runs.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "topic": topic,
                    "topic_slug": db_path_for_topic(topic).stem,
                    "status": "running",
                    "updated_at": now,
                    "runtime": asdict(runtime),
                    "plan": plan.model_dump() if plan is not None else None,
                },
                "$setOnInsert": {"created_at": now},
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
                    "stats": stats,
                    "error": error,
                    "updated_at": _utc_now(),
                }
            },
        )

    def load_pending_documents(self, *, topic: str, limit: int) -> list[dict[str, Any]]:
        topic_slug = db_path_for_topic(topic).stem
        cursor = (
            self._raw.find(
                {
                    "topic_slugs": topic_slug,
                    "analysis_state.cleaning": {"$in": ["not_started", "failed"]},
                },
                {
                    "_id": 0,
                    "document_id": 1,
                    "topic": 1,
                    "topic_slugs": 1,
                    "platform": 1,
                    "canonical_url": 1,
                    "title": 1,
                    "description": 1,
                    "content_text": 1,
                    "raw_text": 1,
                    "raw_html": 1,
                    "markdown": 1,
                    "content_items": 1,
                    "updated_at": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(max(1, limit))
        )
        return list(cursor)

    def has_duplicate(
        self, *, topic: str, cleaned_hash: str | None, document_id: str
    ) -> bool:
        if not cleaned_hash:
            return False
        topic_slug = db_path_for_topic(topic).stem
        match = self._cleaned.find_one(
            {
                "topic_slug": topic_slug,
                "cleaned_hash": cleaned_hash,
                "status": "accepted",
                "document_id": {"$ne": document_id},
            },
            {"document_id": 1},
        )
        return bool(match)

    def find_near_duplicate(
        self,
        *,
        topic: str,
        cleaned_text: str,
        document_id: str,
        threshold: float,
        candidate_limit: int,
    ) -> dict[str, Any] | None:
        if not cleaned_text.strip():
            return None

        topic_slug = db_path_for_topic(topic).stem
        cursor = (
            self._cleaned.find(
                {
                    "topic_slug": topic_slug,
                    "status": "accepted",
                    "document_id": {"$ne": document_id},
                },
                {
                    "document_id": 1,
                    "cleaned_text": 1,
                    "canonical_url": 1,
                    "platform": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(max(1, candidate_limit))
        )
        candidates = list(cursor)
        if not candidates:
            return None

        try:
            rapidfuzz_process = importlib.import_module("rapidfuzz.process")
            rapidfuzz_fuzz = importlib.import_module("rapidfuzz.fuzz")
            extract_one = getattr(rapidfuzz_process, "extractOne", None)
            wratio = getattr(rapidfuzz_fuzz, "WRatio", None)
            if not callable(extract_one) or wratio is None:
                return None
        except Exception:
            return None

        index_to_doc = {
            idx: doc
            for idx, doc in enumerate(candidates)
            if isinstance(doc.get("cleaned_text"), str)
            and doc.get("cleaned_text", "").strip()
        }
        if not index_to_doc:
            return None

        choices = {idx: str(doc["cleaned_text"]) for idx, doc in index_to_doc.items()}
        best = extract_one(cleaned_text, choices, scorer=wratio)
        if not isinstance(best, tuple) or len(best) < 3:
            return None

        _, score, idx = best
        if float(score) < threshold:
            return None
        matched = index_to_doc.get(int(idx))
        if matched is None:
            return None

        return {
            "document_id": matched.get("document_id"),
            "score": float(score),
            "platform": matched.get("platform"),
            "canonical_url": matched.get("canonical_url"),
        }

    def save_clean_result(
        self,
        *,
        topic: str,
        run_id: str,
        document: dict[str, Any],
        result: CleanerResult,
        source: str,
    ) -> dict[str, Any]:
        topic_slug = db_path_for_topic(topic).stem
        now = _utc_now()
        document_id = str(document.get("document_id") or "")
        if not document_id:
            raise ValueError(
                "Document is missing document_id; cannot save clean result."
            )

        clean_payload = {
            "version": 1,
            "status": result.status,
            "reason": result.reason,
            "cleaned_text": result.cleaned_text,
            "sentiment_text": result.sentiment_text,
            "cleaned_hash": result.cleaned_hash,
            "cleaned_signature": result.cleaned_hash[:16]
            if result.cleaned_hash
            else None,
            "source_text": result.source_text,
            "metrics": result.metrics,
            "quality_flags": result.quality_flags,
            "features": result.features,
            "source": source,
            "run_id": run_id,
            "updated_at": now,
        }
        analysis_state = {
            "cleaning": "completed"
            if result.status in {"accepted", "duplicate", "too_short"}
            else "failed",
            "cleaning_updated_at": now,
        }

        saved_raw = self._raw.find_one_and_update(
            {"document_id": document_id},
            {
                "$set": {
                    "cleaning": clean_payload,
                    "analysis_state.cleaning": analysis_state["cleaning"],
                    "analysis_state.cleaning_updated_at": analysis_state[
                        "cleaning_updated_at"
                    ],
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        saved_cleaned = self._cleaned.find_one_and_update(
            {"document_id": document_id},
            {
                "$set": {
                    "document_id": document_id,
                    "topic": topic,
                    "topic_slug": topic_slug,
                    "platform": document.get("platform"),
                    "canonical_url": document.get("canonical_url"),
                    "status": result.status,
                    "reason": result.reason,
                    "cleaned_hash": result.cleaned_hash,
                    "cleaned_signature": result.cleaned_hash[:16]
                    if result.cleaned_hash
                    else None,
                    "cleaned_text": result.cleaned_text,
                    "sentiment_text": result.sentiment_text,
                    "metrics": result.metrics,
                    "quality_flags": result.quality_flags,
                    "features": result.features,
                    "source": source,
                    "run_id": run_id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        self._log.info(
            "Saved cleaned document  id=%s status=%s source=%s",
            document_id,
            result.status,
            source,
            action="save_clean_result",
            meta={
                "document_id": document_id,
                "status": result.status,
                "source": source,
            },
        )
        return {"raw": saved_raw, "cleaned": saved_cleaned}


def build_cleaner_store() -> CleanerDocumentStore:
    """Return configured cleaner store implementation."""
    store = CleanerDocumentStore()
    store.ensure_indexes()
    return store


def load_latest_clean_stats(topic: str) -> dict[str, Any] | None:
    """Load latest cleaner run stats for a topic from MongoDB."""
    topic_slug = db_path_for_topic(topic).stem
    db = get_mongo_database(app_name="sentiment-analyzer-agent-cleaner")
    run = db["clean_runs"].find_one(
        {"topic_slug": topic_slug},
        sort=[("updated_at", -1)],
    )
    if not run:
        return None
    stats = run.get("stats") if isinstance(run.get("stats"), dict) else {}
    stats["status"] = run.get("status", "unknown")
    stats["run_id"] = run.get("run_id")
    return stats


__all__ = [
    "CleanerDocumentStore",
    "build_cleaner_store",
    "build_cleaning_runtime_config",
    "load_latest_clean_stats",
]
