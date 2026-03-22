"""MongoDB persistence helpers for phase-5 sentiment analysis."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from agents.sentiment.models import SentimentPlan, SentimentRuntimeConfig
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


def _to_tuple(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip().lower() for part in value.split(",") if part.strip())


def build_sentiment_runtime_config() -> SentimentRuntimeConfig:
    """Build phase-5 runtime settings from environment variables."""
    return SentimentRuntimeConfig(
        provider=(config.get("SENTIMENT_PROVIDER") or "huggingface").strip(),
        model=(
            config.get("SENTIMENT_MODEL")
            or "cardiffnlp/twitter-roberta-base-sentiment-latest"
        ).strip(),
        device=(config.get("SENTIMENT_DEVICE") or "").strip() or None,
        batch_size=_to_int(config.get("SENTIMENT_BATCH_SIZE"), 16),
        max_concurrency=_to_int(config.get("SENTIMENT_MAX_CONCURRENCY"), 4),
        max_documents_per_run=_to_int(
            config.get("SENTIMENT_MAX_DOCUMENTS_PER_RUN"), 500
        ),
        max_text_chars=_to_int(config.get("SENTIMENT_MAX_TEXT_CHARS"), 4000),
        positive_threshold=_to_float(config.get("SENTIMENT_POSITIVE_THRESHOLD"), 0.6),
        negative_threshold=_to_float(config.get("SENTIMENT_NEGATIVE_THRESHOLD"), 0.4),
        include_topic_context=_to_bool(
            config.get("SENTIMENT_INCLUDE_TOPIC_CONTEXT"), True
        ),
        topic_context_weight=_to_float(
            config.get("SENTIMENT_TOPIC_CONTEXT_WEIGHT"), 0.3
        ),
        custom_keywords_positive=_to_tuple(
            config.get("SENTIMENT_CUSTOM_KEYWORDS_POSITIVE")
        ),
        custom_keywords_negative=_to_tuple(
            config.get("SENTIMENT_CUSTOM_KEYWORDS_NEGATIVE")
        ),
        llm_plan_enabled=_to_bool(config.get("SENTIMENT_LLM_PLAN_ENABLED"), True),
        llm_plan_sample_size=_to_int(config.get("SENTIMENT_LLM_PLAN_SAMPLE_SIZE"), 10),
        llm_fallback_enabled=_to_bool(
            config.get("SENTIMENT_LLM_FALLBACK_ENABLED"), True
        ),
        llm_fallback_sample_size=_to_int(
            config.get("SENTIMENT_LLM_FALLBACK_SAMPLE_SIZE"), 10
        ),
        llm_fallback_max_chars=_to_int(
            config.get("SENTIMENT_LLM_FALLBACK_MAX_CHARS"), 2000
        ),
        min_confidence_threshold=_to_float(
            config.get("SENTIMENT_MIN_CONFIDENCE_THRESHOLD"), 0.5
        ),
        auto_retry_low_confidence=_to_bool(
            config.get("SENTIMENT_AUTO_RETRY_LOW_CONFIDENCE"), True
        ),
    )


class SentimentDocumentStore:
    """Store for loading cleaned documents and saving sentiment outputs."""

    def __init__(self) -> None:
        self._db = get_mongo_database(app_name="sentiment-analyzer-agent-sentiment")
        self._raw = self._db["scraped_documents"]
        self._cleaned = self._db["cleaned_documents"]
        self._runs = self._db["sentiment_runs"]
        self._results = self._db["sentiment_results"]
        self._summaries = self._db["sentiment_summaries"]
        self._log = context_logger(
            "agents.services.sentiment_store",
            actor="sentiment_store",
            phase="SENTIMENT",
        )

    def ensure_indexes(self) -> None:
        self._raw.create_index("analysis_state.sentiment")
        self._cleaned.create_index([("topic_slug", 1), ("status", 1)])
        self._cleaned.create_index("analysis_state.sentiment")
        self._cleaned.create_index("sentiment_run_id")
        self._runs.create_index("run_id", unique=True)
        self._runs.create_index([("topic", 1), ("created_at", -1)])
        self._results.create_index([("topic_slug", 1), ("document_id", 1)])
        self._summaries.create_index("topic", unique=True)

    def start_run(
        self,
        *,
        topic: str,
        run_id: str,
        runtime: SentimentRuntimeConfig,
        plan: SentimentPlan | None = None,
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
        query = {
            "topic_slug": topic_slug,
            "status": "accepted",
            "$or": [
                {"analysis_state.sentiment": {"$in": ["not_started", "failed"]}},
                {"analysis_state.sentiment": {"$exists": False}},
                {"analysis_state": {"$exists": False}},
            ],
        }
        cursor = (
            self._cleaned.find(
                query,
                {
                    "_id": 0,
                    "document_id": 1,
                    "topic": 1,
                    "topic_slug": 1,
                    "platform": 1,
                    "canonical_url": 1,
                    "cleaned_text": 1,
                    "sentiment_text": 1,
                    "updated_at": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(max(1, limit))
        )
        return list(cursor)

    def save_result(
        self,
        *,
        topic: str,
        run_id: str,
        result: dict[str, Any],
        model: str,
        provider: str,
    ) -> None:
        document_id = result.get("document_id")
        if not document_id:
            return

        now = _utc_now()
        topic_slug = db_path_for_topic(topic).stem
        status = "completed" if result.get("status") == "analyzed" else "failed"
        sentiment_payload = {
            "score": result.get("score"),
            "label": result.get("label"),
            "confidence": result.get("confidence"),
            "model": model,
            "provider": provider,
            "recovered": bool(result.get("recovered")),
            "recovery_reason": result.get("recovery_reason"),
            "status": status,
        }

        self._cleaned.update_one(
            {"document_id": document_id},
            {
                "$set": {
                    "sentiment": sentiment_payload,
                    "analysis_state.sentiment": status,
                    "analysis_state.sentiment_updated_at": now,
                    "sentiment_run_id": run_id,
                    "sentiment_updated_at": now,
                    "updated_at": now,
                }
            },
        )

        self._raw.update_one(
            {"document_id": document_id},
            {
                "$set": {
                    "sentiment": sentiment_payload,
                    "analysis_state.sentiment": status,
                    "analysis_state.sentiment_updated_at": now,
                    "updated_at": now,
                }
            },
        )

        self._results.update_one(
            {"document_id": document_id, "topic": topic},
            {
                "$set": {
                    **sentiment_payload,
                    "topic": topic,
                    "topic_slug": topic_slug,
                    "document_id": document_id,
                    "sentiment_run_id": run_id,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    def save_summary(
        self,
        *,
        topic: str,
        run_id: str,
        stats: dict[str, Any],
    ) -> None:
        topic_slug = db_path_for_topic(topic).stem
        self._summaries.update_one(
            {"topic": topic},
            {
                "$set": {
                    "topic": topic,
                    "topic_slug": topic_slug,
                    "sentiment_run_id": run_id,
                    "stats": stats,
                    "total_documents": stats.get("total_documents"),
                    "analyzed": stats.get("analyzed"),
                    "avg_score": stats.get("avg_score"),
                    "updated_at": _utc_now(),
                }
            },
            upsert=True,
        )


def build_sentiment_store() -> SentimentDocumentStore:
    """Return configured sentiment store implementation."""
    store = SentimentDocumentStore()
    store.ensure_indexes()
    return store


def load_latest_sentiment_stats(topic: str) -> dict[str, Any] | None:
    """Load latest sentiment run stats for a topic from MongoDB."""
    topic_slug = db_path_for_topic(topic).stem
    db = get_mongo_database(app_name="sentiment-analyzer-agent-sentiment")
    run = db["sentiment_runs"].find_one(
        {"topic_slug": topic_slug}, sort=[("created_at", -1)]
    )
    if not run:
        return None
    return run.get("stats")


__all__ = [
    "build_sentiment_runtime_config",
    "build_sentiment_store",
    "load_latest_sentiment_stats",
]
