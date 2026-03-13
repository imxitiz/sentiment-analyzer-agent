"""Cleaner agent — phase 4 preprocessing for sentiment-ready text."""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from dataclasses import asdict
from typing import Any

from agents._registry import register_agent
from agents.base import BaseAgent
from agents.cleaner.models import CleanerPlan, CleanerResult
from agents.cleaner.planner import CleanerPlannerAgent
from agents.cleaner.recovery import CleanerRecoveryAgent
from agents.services import (
    build_cleaner_store,
    build_cleaning_runtime_config,
    get_latest_run_id,
    record_orchestrator_event,
    save_pipeline_artifact,
)
from agents.services.cleaner_text import clean_document
from Logging import get_logger

logger = get_logger("agents.cleaner")


@register_agent
class CleanerAgent(BaseAgent):
    """Clean raw scraped Mongo documents into sentiment-ready payloads."""

    _name = "cleaner"
    _description = (
        "Clean scraped raw documents with adaptive extraction, configurable "
        "normalization, deduplication, and quality checks before sentiment analysis."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"
    _timeout_seconds = 1800
    _max_retries = 1

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        if not topic:
            raise ValueError("CleanerAgent requires a non-empty topic.")
        if self._demo:
            return self._demo_invoke(topic, **kwargs)
        return asyncio.run(self.ainvoke(topic, **kwargs))

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        if self._demo:
            return self._demo_invoke(topic, **kwargs)

        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        runtime = build_cleaning_runtime_config()
        store = build_cleaner_store()
        run_id = str(uuid.uuid4())
        pending = store.load_pending_documents(topic=topic, limit=runtime.max_documents_per_run)
        plan = self._build_cleaning_plan(topic=topic, runtime=runtime, pending=pending)

        store.start_run(topic=topic, run_id=run_id, runtime=runtime, plan=plan)

        stats: dict[str, Any] = {
            "queued_documents": len(pending),
            "accepted": 0,
            "duplicate": 0,
            "too_short": 0,
            "failed": 0,
            "llm_fallback_used": 0,
            "qa_reviews": 0,
            "plan_enabled": bool(plan is not None),
            "plan_confidence": float(plan.confidence) if plan is not None else 0.0,
        }

        latest_run_id = get_latest_run_id(topic)
        if latest_run_id:
            record_orchestrator_event(
                latest_run_id,
                event_type="clean_started",
                agent=self._name,
                status="running",
                message="Cleaner started document normalization",
                meta={
                    "clean_run_id": run_id,
                    "queued_documents": len(pending),
                    "plan_enabled": bool(plan is not None),
                },
            )

        if not pending:
            summary = "Cleaner found no pending documents to process."
            store.finish_run(run_id=run_id, status="completed", stats=stats)
            self._checkpoint_agent_status(topic, status="completed", mark_completed=True)
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="clean_complete",
                    agent=self._name,
                    status="completed",
                    message=summary,
                    meta=stats,
                )
            return {"messages": [], "output": summary, "stats": stats}

        recovery_agent = CleanerRecoveryAgent(
            llm_provider=getattr(self.llm, "_provider", "dummy"),
        )
        sample_ids = self._sample_document_ids(pending, runtime.sample_review_rate, runtime.max_sample_reviews)
        semaphore = asyncio.Semaphore(runtime.max_concurrency)

        async def _worker(document: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self._process_document(
                    topic=topic,
                    run_id=run_id,
                    document=document,
                    store=store,
                    runtime=runtime,
                    plan=plan,
                    recovery_agent=recovery_agent,
                    do_sample_review=str(document.get("document_id") or "") in sample_ids,
                )

        try:
            results = await asyncio.gather(*[_worker(doc) for doc in pending], return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    stats["failed"] += 1
                    continue
                if not isinstance(result, dict):
                    stats["failed"] += 1
                    continue
                status = str(result.get("status") or "failed")
                if status not in stats:
                    stats["failed"] += 1
                else:
                    stats[status] = int(stats.get(status, 0)) + 1
                if bool(result.get("fallback_used")):
                    stats["llm_fallback_used"] += 1
                if bool(result.get("reviewed")):
                    stats["qa_reviews"] += 1

            summary = self._format_summary(topic, stats)
            store.finish_run(run_id=run_id, status="completed", stats=stats)
            self._checkpoint_agent_status(topic, status="completed", mark_completed=True)
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="cleaner_summary",
                value=summary,
                meta=stats,
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="clean_complete",
                    agent=self._name,
                    status="completed",
                    message="Cleaner completed preprocessing",
                    meta=stats,
                )
            return {"messages": [], "output": summary, "stats": stats}
        except Exception as exc:
            error = str(exc)
            stats["error"] = error
            store.finish_run(run_id=run_id, status="failed", stats=stats, error=error)
            self._checkpoint_agent_status(
                topic,
                status="failed",
                last_error=error,
                mark_completed=True,
            )
            save_pipeline_artifact(
                topic,
                source_agent=self._name,
                artifact_type="cleaner_error",
                value=error,
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="clean_error",
                    agent=self._name,
                    status="failed",
                    message=error,
                    meta=stats,
                )
            raise

    async def _process_document(
        self,
        *,
        topic: str,
        run_id: str,
        document: dict[str, Any],
        store: Any,
        runtime: Any,
        plan: CleanerPlan | None,
        recovery_agent: CleanerRecoveryAgent,
        do_sample_review: bool,
    ) -> dict[str, Any]:
        document_id = str(document.get("document_id") or "")
        if not document_id:
            return {"status": "failed", "reason": "missing_document_id"}

        deterministic = await asyncio.to_thread(clean_document, document, runtime, plan=plan)
        fallback_used = False

        if deterministic.status == "accepted" and store.has_duplicate(
            topic=topic,
            cleaned_hash=deterministic.cleaned_hash,
            document_id=document_id,
        ):
            deterministic = CleanerResult(
                status="duplicate",
                cleaned_text=deterministic.cleaned_text,
                sentiment_text=deterministic.sentiment_text,
                cleaned_hash=deterministic.cleaned_hash,
                source_text=deterministic.source_text,
                reason="Duplicate cleaned text hash already exists for this topic.",
                quality_flags=[*deterministic.quality_flags, "duplicate_hash"],
                metrics=deterministic.metrics,
                features=deterministic.features,
            )

        if (
            deterministic.status == "accepted"
            and runtime.enable_fuzzy_dedupe
            and deterministic.cleaned_text.strip()
        ):
            near_match = store.find_near_duplicate(
                topic=topic,
                cleaned_text=deterministic.cleaned_text,
                document_id=document_id,
                threshold=runtime.fuzzy_dedupe_threshold,
                candidate_limit=runtime.fuzzy_candidate_limit,
            )
            if near_match is not None:
                score_value = float(near_match.get("score", 0.0))
                deterministic = CleanerResult(
                    status="duplicate",
                    cleaned_text=deterministic.cleaned_text,
                    sentiment_text=deterministic.sentiment_text,
                    cleaned_hash=deterministic.cleaned_hash,
                    source_text=deterministic.source_text,
                    reason=(
                        "Near-duplicate detected against recent cleaned record "
                        f"(score={score_value:.2f})."
                    ),
                    quality_flags=[*deterministic.quality_flags, "duplicate_fuzzy"],
                    metrics=deterministic.metrics,
                    features={
                        **deterministic.features,
                        "near_duplicate": near_match,
                    },
                )

        final = deterministic
        if runtime.llm_fallback_enabled and deterministic.status in {"failed", "too_short"}:
            recovered = await asyncio.to_thread(
                self._recover_with_llm,
                topic,
                recovery_agent,
                document,
                deterministic,
                "fallback_on_failure",
                runtime,
            )
            if recovered is not None:
                final = recovered
                fallback_used = True

        reviewed = False
        if runtime.llm_fallback_enabled and do_sample_review and final.status == "accepted":
            reviewed = True
            reviewed_result = await asyncio.to_thread(
                self._recover_with_llm,
                topic,
                recovery_agent,
                document,
                final,
                "sample_quality_review",
                runtime,
            )
            if reviewed_result is not None and reviewed_result.status == "accepted":
                final = reviewed_result

        source = "llm_fallback" if fallback_used else "deterministic"
        store.save_clean_result(
            topic=topic,
            run_id=run_id,
            document=document,
            result=final,
            source=source,
        )
        return {
            "document_id": document_id,
            "status": final.status,
            "fallback_used": fallback_used,
            "reviewed": reviewed,
        }

    def _build_cleaning_plan(
        self,
        *,
        topic: str,
        runtime: Any,
        pending: list[dict[str, Any]],
    ) -> CleanerPlan | None:
        if not runtime.llm_plan_enabled or not pending:
            return None

        sample_size = min(len(pending), max(1, runtime.llm_plan_sample_size))
        sampled = random.sample(pending, sample_size)
        payload = {
            "topic": topic,
            "runtime": asdict(runtime),
            "samples": [
                {
                    "document_id": str(doc.get("document_id") or ""),
                    "platform": doc.get("platform"),
                    "title": str(doc.get("title") or "")[:300],
                    "description": str(doc.get("description") or "")[:300],
                    "content_text_preview": str(doc.get("content_text") or "")[: runtime.llm_plan_max_chars_per_sample],
                    "raw_text_preview": str(doc.get("raw_text") or "")[: runtime.llm_plan_max_chars_per_sample],
                    "raw_html_preview": str(doc.get("raw_html") or "")[: runtime.llm_plan_max_chars_per_sample],
                }
                for doc in sampled
            ],
        }

        planner = CleanerPlannerAgent(llm_provider=getattr(self.llm, "_provider", "dummy"))
        try:
            result = planner.invoke(json.dumps(payload, ensure_ascii=False))
            plan = result.get("plan")
            if isinstance(plan, CleanerPlan):
                return plan
            if isinstance(plan, dict):
                return CleanerPlan.model_validate(plan)
            return None
        except Exception as exc:
            logger.warning(
                "Cleaner planner fallback to baseline runtime: %s",
                exc,
                action="cleaner_plan_failed",
                meta={"topic": topic, "sample_size": sample_size},
            )
            return None

    def _recover_with_llm(
        self,
        topic: str,
        recovery_agent: CleanerRecoveryAgent,
        document: dict[str, Any],
        deterministic: CleanerResult,
        review_reason: str,
        runtime: Any,
    ) -> CleanerResult | None:
        payload = {
            "topic": topic,
            "document_id": document.get("document_id"),
            "platform": document.get("platform"),
            "title": document.get("title"),
            "raw_text_preview": deterministic.source_text[: runtime.llm_fallback_max_chars],
            "deterministic_cleaned_text": deterministic.cleaned_text[: runtime.llm_fallback_max_chars],
            "failure_reason": deterministic.reason,
            "quality_flags": deterministic.quality_flags,
            "metrics": deterministic.metrics,
            "features": deterministic.features,
            "review_reason": review_reason,
            "force_full_rewrite": runtime.llm_force_full_rewrite,
        }
        try:
            response = recovery_agent.invoke(json.dumps(payload, ensure_ascii=False))
            plan = response.get("recovery_plan")
            if plan is None:
                return None
            cleaned_text = str(plan.cleaned_text or "").strip() or deterministic.cleaned_text
            if plan.status == "accepted" and cleaned_text:
                clean_hash = deterministic.cleaned_hash
                if not clean_hash and cleaned_text:
                    import hashlib

                    clean_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
                return CleanerResult(
                    status="accepted",
                    cleaned_text=cleaned_text,
                    sentiment_text=cleaned_text,
                    cleaned_hash=clean_hash,
                    source_text=deterministic.source_text,
                    reason=f"LLM review: {plan.reason}",
                    quality_flags=[*deterministic.quality_flags, "llm_reviewed"],
                    metrics=deterministic.metrics,
                    features={
                        **deterministic.features,
                        "llm_quality_score": float(plan.quality_score),
                        "recommended_plan_adjustments": plan.recommended_plan_adjustments,
                    },
                )
            if plan.status == "rejected":
                return CleanerResult(
                    status="failed",
                    cleaned_text=deterministic.cleaned_text,
                    sentiment_text=deterministic.sentiment_text,
                    cleaned_hash=deterministic.cleaned_hash,
                    source_text=deterministic.source_text,
                    reason=f"LLM rejected cleaning output: {plan.reason}",
                    quality_flags=[*deterministic.quality_flags, "llm_rejected"],
                    metrics=deterministic.metrics,
                    features=deterministic.features,
                )
            return None
        except Exception as exc:
            logger.warning(
                "Cleaner LLM fallback failed: %s",
                exc,
                action="cleaner_llm_fallback_failed",
                meta={"topic": topic, "document_id": document.get("document_id")},
            )
            return None

    @staticmethod
    def _sample_document_ids(
        documents: list[dict[str, Any]],
        rate: float,
        max_reviews: int,
    ) -> set[str]:
        ids = [str(doc.get("document_id") or "") for doc in documents if doc.get("document_id")]
        if not ids:
            return set()
        sample_size = min(len(ids), max(0, max_reviews), max(1, int(len(ids) * rate)))
        return set(random.sample(ids, sample_size)) if sample_size else set()

    @staticmethod
    def _format_summary(topic: str, stats: dict[str, Any]) -> str:
        return (
            f"Cleaner completed for '{topic}'. "
            f"Accepted={stats.get('accepted', 0)}, "
            f"Duplicate={stats.get('duplicate', 0)}, "
            f"TooShort={stats.get('too_short', 0)}, "
            f"Failed={stats.get('failed', 0)}, "
            f"FallbackUsed={stats.get('llm_fallback_used', 0)}, "
            f"QAReviews={stats.get('qa_reviews', 0)}, "
            f"PlanEnabled={stats.get('plan_enabled', False)}, "
            f"PlanConfidence={stats.get('plan_confidence', 0.0):.2f}."
        )

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        runtime = build_cleaning_runtime_config()
        summary = (
            f"[DEMO:cleaner] Topic={topic} "
            f"runtime={json.dumps(asdict(runtime), ensure_ascii=False)}"
        )
        return {
            "messages": [],
            "output": summary,
            "stats": {
                "queued_documents": 20,
                "accepted": 16,
                "duplicate": 2,
                "too_short": 1,
                "failed": 1,
                "llm_fallback_used": 2,
                "qa_reviews": 3,
                "plan_enabled": True,
                "plan_confidence": 0.62,
            },
        }
