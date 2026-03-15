"""Sentiment analyzer agent — phase 5 sentiment scoring for cleaned documents.

This agent takes cleaned documents from the CleanerAgent and runs sentiment
analysis using the SentimentAnalyzer module. It produces sentiment scores
(0→1 continuous) for each document and stores results in MongoDB.

Pipeline position:
    Topic → Keywords → Harvest → Scrape → Clean → **Sentiment** → Dashboard

Features:
    - Fully async batch processing with semaphore-controlled concurrency
    - Topic-aware sentiment analysis (understands topic context)
    - Planner sub-agent for adaptive model selection
    - Recovery sub-agent for failed/low-confidence cases
    - Progress tracking and checkpointing
    - MongoDB persistence for sentiment results
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import Counter
from dataclasses import asdict
from typing import Any, Iterable

from agents.base import BaseAgent
from agents._registry import register_agent
from agents.sentiment.models import (
    SentimentPlan,
    SentimentRecoveryPlan,
    SentimentRuntimeConfig,
)
from agents.sentiment.planner import SentimentPlannerAgent
from agents.sentiment.recovery import SentimentRecoveryAgent
from agents.services import (
    build_sentiment_runtime_config,
    build_sentiment_store,
    get_latest_run_id,
    record_orchestrator_event,
)
from Logging import get_logger

logger = get_logger("agents.sentiment")


@register_agent
class SentimentAnalyzerAgent(BaseAgent):
    """Analyze sentiment of cleaned documents using HuggingFace models.

    This agent:
    1. Loads cleaned documents from MongoDB
    2. Invokes planner for adaptive configuration
    3. Runs sentiment analysis using SentimentAnalyzer (async batch)
    4. Uses recovery agent for failed/low-confidence cases
    5. Stores sentiment results back to MongoDB
    6. Provides summary statistics

    Sentiment scores are continuous (0→1):
    - 0.0 = very negative
    - 0.5 = neutral
    - 1.0 = very positive
    """

    _name = "sentiment"
    _description = (
        "Analyze sentiment of cleaned documents using HuggingFace models. "
        "Produces continuous sentiment scores (0→1) for each document with "
        "async batch processing, planner for adaptive config, and recovery for failures."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"
    _timeout_seconds = 1800
    _max_retries = 1

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke the sentiment analyzer agent.

        Parameters
        ----------
        message : str
            Topic name to analyze.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Sentiment analysis results including scores and statistics.
        """
        topic = message.strip()
        if not topic:
            raise ValueError("SentimentAnalyzerAgent requires a non-empty topic.")
        if self._demo:
            return self._demo_invoke(topic, **kwargs)
        return asyncio.run(self.ainvoke(topic, **kwargs))

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Async invocation of the sentiment analyzer agent.

        Parameters
        ----------
        message : str
            Topic name to analyze.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Sentiment analysis results including scores and statistics.
        """
        topic = message.strip()
        if self._demo:
            return self._demo_invoke(topic, **kwargs)

        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        runtime = self._build_runtime_config()
        store = build_sentiment_store()
        run_id = str(uuid.uuid4())
        pending = store.load_pending_documents(
            topic=topic, limit=runtime.max_documents_per_run
        )

        plan = None
        if runtime.llm_plan_enabled and pending:
            plan = self._invoke_planner(topic, pending, runtime)
            if plan:
                runtime = self._apply_plan_to_runtime(runtime, plan)
                self._checkpoint_artifact(
                    topic=topic,
                    artifact_type="sentiment_plan",
                    value=plan.model_dump_json(indent=2),
                    meta={
                        "confidence": plan.confidence,
                        "model": plan.model,
                        "sample_size": min(runtime.llm_plan_sample_size, len(pending)),
                    },
                )

        store.start_run(topic=topic, run_id=run_id, runtime=runtime, plan=plan)

        stats: dict[str, Any] = {
            "queued_documents": len(pending),
            "total_documents": len(pending),
            "analyzed": 0,
            "failed": 0,
            "recovered": 0,
            "avg_score": 0.0,
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "plan_enabled": bool(plan is not None),
            "plan_confidence": float(plan.confidence) if plan is not None else 0.0,
            "llm_fallback_budget": runtime.llm_fallback_sample_size
            if runtime.llm_fallback_enabled
            else 0,
        }

        latest_run_id = get_latest_run_id(topic)
        if latest_run_id:
            record_orchestrator_event(
                latest_run_id,
                event_type="sentiment_started",
                agent=self._name,
                status="running",
                message=f"Starting sentiment analysis for {len(pending)} documents",
                meta={
                    "sentiment_run_id": run_id,
                    "total_documents": len(pending),
                    "plan_enabled": bool(plan is not None),
                },
            )

        if not pending:
            summary = "Sentiment analyzer found no cleaned documents to process."
            store.finish_run(run_id=run_id, status="completed", stats=stats)
            self._checkpoint_agent_status(
                topic, status="completed", mark_completed=True
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="sentiment_completed",
                    agent=self._name,
                    status="completed",
                    message=summary,
                    meta=stats,
                )
            return {"status": "completed", "summary": summary, "stats": stats}

        llm_provider = getattr(self.llm, "_provider", "dummy")

        try:
            from SentimentAnalyzer import get_sentiment_analyzer

            analyzer = get_sentiment_analyzer(
                provider=runtime.provider,
                model=runtime.model,
                device=runtime.device,
                batch_size=runtime.batch_size,
            )

            max_concurrency = runtime.max_concurrency
            if runtime.device and runtime.device.lower() in {"cuda", "mps"}:
                if max_concurrency > 1:
                    logger.info(
                        "Reducing sentiment concurrency for GPU device: %s → 1",
                        max_concurrency,
                    )
                max_concurrency = 1

            recovery_agent = SentimentRecoveryAgent(llm_provider=llm_provider)
            results = await self._process_documents_batched(
                topic=topic,
                documents=pending,
                analyzer=analyzer,
                runtime=runtime,
                recovery_agent=recovery_agent,
                max_concurrency=max_concurrency,
            )

            scores: list[float] = []
            for result in results:
                if not isinstance(result, dict):
                    stats["failed"] += 1
                    continue

                store.save_result(
                    topic=topic,
                    run_id=run_id,
                    result=result,
                    model=runtime.model,
                    provider=runtime.provider,
                )

                if result.get("status") != "analyzed":
                    stats["failed"] += 1
                    continue

                if result.get("recovered"):
                    stats["recovered"] += 1

                score = float(result.get("score", 0.5))
                scores.append(score)
                stats["analyzed"] += 1

                label = result.get("label")
                if label == "positive":
                    stats["positive_count"] += 1
                elif label == "negative":
                    stats["negative_count"] += 1
                else:
                    stats["neutral_count"] += 1

            if scores:
                stats["avg_score"] = sum(scores) / len(scores)

            store.save_summary(topic=topic, run_id=run_id, stats=stats)
            store.finish_run(run_id=run_id, status="completed", stats=stats)
            summary = (
                f"Sentiment analysis completed: {stats['analyzed']} documents analyzed, "
                f"{stats['recovered']} recovered. Average score: {stats['avg_score']:.3f}. "
                f"Positive: {stats['positive_count']}, "
                f"Neutral: {stats['neutral_count']}, "
                f"Negative: {stats['negative_count']}."
            )

            self._checkpoint_artifact(
                topic=topic,
                artifact_type="sentiment_summary",
                value=summary,
                meta=stats,
            )
            self._checkpoint_agent_status(
                topic, status="completed", mark_completed=True
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="sentiment_completed",
                    agent=self._name,
                    status="completed",
                    message=summary,
                    meta=stats,
                )

            return {
                "status": "completed",
                "summary": summary,
                "stats": stats,
                "run_id": run_id,
            }

        except Exception as exc:
            logger.error(
                "Sentiment analysis failed  topic=%s  error=%s",
                topic,
                exc,
                exc_info=True,
            )
            store.finish_run(
                run_id=run_id,
                status="failed",
                stats=stats,
                error=str(exc),
            )
            self._checkpoint_agent_status(topic, status="failed", last_error=str(exc))
            raise RuntimeError(
                f"Sentiment analysis failed for topic '{topic}': {exc}"
            ) from exc

    def _invoke_planner(
        self,
        topic: str,
        documents: list[dict[str, Any]],
        runtime: SentimentRuntimeConfig,
    ) -> SentimentPlan | None:
        """Invoke the planner sub-agent to generate adaptive configuration.

        Parameters
        ----------
        topic : str
            Topic name.
        documents : list[dict[str, Any]]
            Sample documents for planning.
        runtime : SentimentRuntimeConfig
            Current runtime configuration.

        Returns
        -------
        SentimentPlan | None
            Generated plan or None if planning fails.
        """
        sample_size = min(runtime.llm_plan_sample_size, len(documents))
        samples = documents[:sample_size]
        platform_counts = Counter(
            str(doc.get("platform") or "unknown").lower() for doc in samples
        )

        payload = {
            "topic": topic,
            "sample_documents": [
                {
                    "document_id": doc.get("document_id"),
                    "text_preview": (
                        doc.get("sentiment_text") or doc.get("cleaned_text") or ""
                    )[:500],
                    "platform": doc.get("platform"),
                }
                for doc in samples
            ],
            "platform_distribution": dict(platform_counts),
        }

        planner = SentimentPlannerAgent(
            llm_provider=getattr(self.llm, "_provider", "dummy")
        )
        try:
            result = planner.invoke(json.dumps(payload, ensure_ascii=False))
            plan = result.get("plan")
            if isinstance(plan, SentimentPlan):
                return plan
            if isinstance(plan, dict):
                return SentimentPlan.model_validate(plan)
            return None
        except Exception as exc:
            logger.warning(
                "Sentiment planner fallback to baseline runtime: %s",
                exc,
                action="sentiment_plan_failed",
                meta={"topic": topic, "sample_size": sample_size},
            )
            return None

    def _apply_plan_to_runtime(
        self,
        runtime: SentimentRuntimeConfig,
        plan: SentimentPlan,
    ) -> SentimentRuntimeConfig:
        """Apply planner configuration overrides to runtime config.

        Parameters
        ----------
        runtime : SentimentRuntimeConfig
            Base runtime configuration.
        plan : SentimentPlan
            Plan with configuration overrides.

        Returns
        -------
        SentimentRuntimeConfig
            Updated runtime configuration.
        """
        updated = asdict(runtime)
        updated["custom_keywords_positive"] = tuple(runtime.custom_keywords_positive)
        updated["custom_keywords_negative"] = tuple(runtime.custom_keywords_negative)

        if plan.model:
            updated["model"] = plan.model
        elif plan.language_override:
            updated["model"] = self._resolve_language_override(
                plan.language_override, updated["model"]
            )
        if plan.positive_threshold is not None:
            updated["positive_threshold"] = plan.positive_threshold
        if plan.negative_threshold is not None:
            updated["negative_threshold"] = plan.negative_threshold
        if plan.include_topic_context is not None:
            updated["include_topic_context"] = plan.include_topic_context
        if plan.topic_context_weight is not None:
            updated["topic_context_weight"] = plan.topic_context_weight
        if plan.min_confidence_threshold is not None:
            updated["min_confidence_threshold"] = plan.min_confidence_threshold
        if plan.auto_retry_low_confidence is not None:
            updated["auto_retry_low_confidence"] = plan.auto_retry_low_confidence
        if plan.custom_keywords_positive:
            merged = list(updated.get("custom_keywords_positive") or ())
            merged.extend(plan.custom_keywords_positive)
            updated["custom_keywords_positive"] = tuple(
                dict.fromkeys(kw.strip().lower() for kw in merged if kw.strip())
            )
        if plan.custom_keywords_negative:
            merged = list(updated.get("custom_keywords_negative") or ())
            merged.extend(plan.custom_keywords_negative)
            updated["custom_keywords_negative"] = tuple(
                dict.fromkeys(kw.strip().lower() for kw in merged if kw.strip())
            )

        return SentimentRuntimeConfig(**updated)

    @staticmethod
    def _resolve_language_override(language_override: str, current: str) -> str:
        normalized = language_override.strip().lower()
        if normalized in {"multilingual", "multi", "non_english"}:
            return "nlptown/bert-base-multilingual-uncased-sentiment"
        if normalized in {"twitter", "social", "social_media"}:
            return "cardiffnlp/twitter-roberta-base-sentiment-latest"
        return current

    async def _process_documents_batched(
        self,
        topic: str,
        documents: list[dict[str, Any]],
        analyzer: Any,
        runtime: SentimentRuntimeConfig,
        recovery_agent: SentimentRecoveryAgent,
        max_concurrency: int = 1,
    ) -> list[dict[str, Any]]:
        batches = list(self._chunked(documents, max(1, runtime.batch_size)))
        semaphore = asyncio.Semaphore(max(1, max_concurrency))
        fallback_state = {
            "remaining": runtime.llm_fallback_sample_size
            if runtime.llm_fallback_enabled
            else 0
        }
        fallback_lock = asyncio.Lock()

        async def _run_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
            async with semaphore:
                return await self._analyze_batch(
                    topic=topic,
                    batch=batch,
                    analyzer=analyzer,
                    runtime=runtime,
                    recovery_agent=recovery_agent,
                    fallback_state=fallback_state,
                    fallback_lock=fallback_lock,
                )

        results: list[dict[str, Any]] = []
        batch_results = await asyncio.gather(
            *[_run_batch(batch) for batch in batches], return_exceptions=True
        )

        for batch, batch_result in zip(batches, batch_results):
            if isinstance(batch_result, BaseException):
                logger.warning(
                    "Batch sentiment failed  reason=%s",
                    batch_result,
                )
                for document in batch:
                    results.append(
                        self._failure_result(
                            document,
                            reason="batch_failed",
                            error=str(batch_result),
                        )
                    )
                continue
            results.extend(batch_result)

        return results

    async def _analyze_batch(
        self,
        *,
        topic: str,
        batch: list[dict[str, Any]],
        analyzer: Any,
        runtime: SentimentRuntimeConfig,
        recovery_agent: SentimentRecoveryAgent,
        fallback_state: dict[str, int],
        fallback_lock: asyncio.Lock,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        doc_refs: list[tuple[dict[str, Any], str]] = []

        for document in batch:
            text = self._prepare_text(document, runtime)
            if not text:
                results.append(
                    self._failure_result(
                        document,
                        reason="empty_text",
                        error="No sentiment_text or cleaned_text available",
                    )
                )
                continue
            doc_refs.append((document, text))

        if not doc_refs:
            return results

        texts = [text for _, text in doc_refs]
        try:
            base_results = await asyncio.to_thread(analyzer.analyze_batch, texts)
        except Exception as exc:
            logger.warning(
                "Batch analysis failed; falling back to single  error=%s",
                exc,
            )
            for document, text in doc_refs:
                results.append(
                    await self._analyze_single(
                        topic=topic,
                        document=document,
                        text=text,
                        analyzer=analyzer,
                        runtime=runtime,
                        recovery_agent=recovery_agent,
                        fallback_state=fallback_state,
                        fallback_lock=fallback_lock,
                        failure_reason=str(exc),
                    )
                )
            return results

        for (document, text), base in zip(doc_refs, base_results):
            results.append(
                await self._finalize_result(
                    topic=topic,
                    document=document,
                    text=text,
                    base_result=base,
                    runtime=runtime,
                    recovery_agent=recovery_agent,
                    fallback_state=fallback_state,
                    fallback_lock=fallback_lock,
                )
            )
        return results

    async def _analyze_single(
        self,
        *,
        topic: str,
        document: dict[str, Any],
        text: str,
        analyzer: Any,
        runtime: SentimentRuntimeConfig,
        recovery_agent: SentimentRecoveryAgent,
        fallback_state: dict[str, int],
        fallback_lock: asyncio.Lock,
        failure_reason: str,
    ) -> dict[str, Any]:
        try:
            base = await asyncio.to_thread(analyzer.analyze, text)
            return await self._finalize_result(
                topic=topic,
                document=document,
                text=text,
                base_result=base,
                runtime=runtime,
                recovery_agent=recovery_agent,
                fallback_state=fallback_state,
                fallback_lock=fallback_lock,
            )
        except Exception as exc:
            logger.warning(
                "Single sentiment failed  doc_id=%s  error=%s",
                document.get("document_id"),
                exc,
            )
            if runtime.llm_fallback_enabled:
                return await self._recover_with_llm(
                    topic=topic,
                    document=document,
                    original_result=None,
                    failure_reason=failure_reason or str(exc),
                    runtime=runtime,
                    recovery_agent=recovery_agent,
                    fallback_state=fallback_state,
                    fallback_lock=fallback_lock,
                )
            return self._failure_result(
                document,
                reason="analysis_failed",
                error=str(exc),
            )

    async def _finalize_result(
        self,
        *,
        topic: str,
        document: dict[str, Any],
        text: str,
        base_result: Any,
        runtime: SentimentRuntimeConfig,
        recovery_agent: SentimentRecoveryAgent,
        fallback_state: dict[str, int],
        fallback_lock: asyncio.Lock,
    ) -> dict[str, Any]:
        score = float(getattr(base_result, "score", 0.5))
        confidence = float(getattr(base_result, "confidence", 0.0))
        score = self._apply_keyword_adjustment(
            score,
            text=text,
            runtime=runtime,
        )
        label = self._label_from_score(score, runtime)
        result = {
            "document_id": document.get("document_id"),
            "score": score,
            "label": label,
            "confidence": confidence,
            "status": "analyzed",
            "recovered": False,
        }

        if (
            confidence < runtime.min_confidence_threshold
            and runtime.auto_retry_low_confidence
            and runtime.llm_fallback_enabled
        ):
            return await self._recover_with_llm(
                topic=topic,
                document=document,
                original_result=result,
                failure_reason="low_confidence",
                runtime=runtime,
                recovery_agent=recovery_agent,
                fallback_state=fallback_state,
                fallback_lock=fallback_lock,
            )

        if (
            confidence < runtime.min_confidence_threshold
            and runtime.auto_retry_low_confidence
        ):
            result["low_confidence"] = True
        return result

    async def _recover_with_llm(
        self,
        *,
        topic: str,
        document: dict[str, Any],
        original_result: dict[str, Any] | None,
        failure_reason: str,
        runtime: SentimentRuntimeConfig,
        recovery_agent: SentimentRecoveryAgent,
        fallback_state: dict[str, int],
        fallback_lock: asyncio.Lock,
    ) -> dict[str, Any]:
        """Use LLM recovery agent for failed/low-confidence cases.

        Parameters
        ----------
        topic : str
            Topic name.
        document : dict[str, Any]
            Document to recover.
        original_result : dict[str, Any] | None
            Original sentiment result if available.
        failure_reason : str
            Reason for recovery.
        runtime : SentimentRuntimeConfig
            Runtime configuration.
        recovery_agent : SentimentRecoveryAgent
            Recovery agent.

        Returns
        -------
        dict[str, Any]
            Recovered sentiment result.
        """
        allowed = await self._consume_fallback_budget(
            fallback_state=fallback_state, fallback_lock=fallback_lock
        )
        if not allowed:
            if original_result:
                original_result["fallback_skipped"] = "budget_exhausted"
                original_result["low_confidence"] = True
                return original_result
            return self._failure_result(
                document,
                reason="fallback_budget_exhausted",
                error="LLM fallback budget exhausted",
            )

        payload = {
            "topic": topic,
            "document_text": (
                document.get("sentiment_text") or document.get("cleaned_text") or ""
            )[: runtime.llm_fallback_max_chars],
            "original_score": original_result.get("score") if original_result else None,
            "original_confidence": original_result.get("confidence")
            if original_result
            else None,
            "failure_reason": failure_reason,
        }

        try:
            response = await asyncio.to_thread(
                recovery_agent.invoke, json.dumps(payload, ensure_ascii=False)
            )
            recovery_plan = response.get("recovery_plan")

            if recovery_plan and isinstance(recovery_plan, SentimentRecoveryPlan):
                if recovery_plan.status == "accepted":
                    return {
                        "document_id": document.get("document_id"),
                        "score": recovery_plan.score,
                        "label": recovery_plan.label,
                        "confidence": recovery_plan.confidence,
                        "status": "analyzed",
                        "recovered": True,
                        "recovery_reason": recovery_plan.reason,
                    }

            if original_result:
                original_result["fallback_error"] = "Recovery rejected"
                return original_result

            return self._failure_result(
                document,
                reason="recovery_rejected",
                error="Recovery rejected",
            )

        except Exception as exc:
            logger.warning(
                "Recovery agent failed  doc_id=%s  error=%s",
                document.get("document_id"),
                exc,
            )
            if original_result:
                original_result["fallback_error"] = str(exc)
                return original_result
            return self._failure_result(
                document,
                reason="recovery_failed",
                error=str(exc),
            )

    async def _consume_fallback_budget(
        self,
        *,
        fallback_state: dict[str, int],
        fallback_lock: asyncio.Lock,
    ) -> bool:
        async with fallback_lock:
            remaining = int(fallback_state.get("remaining", 0))
            if remaining <= 0:
                return False
            fallback_state["remaining"] = remaining - 1
            return True

    def _prepare_text(
        self, document: dict[str, Any], runtime: SentimentRuntimeConfig
    ) -> str:
        text = (
            document.get("sentiment_text")
            or document.get("cleaned_text")
            or document.get("text")
            or ""
        ).strip()
        if not text:
            return ""
        if runtime.max_text_chars:
            return text[: runtime.max_text_chars]
        return text

    def _apply_keyword_adjustment(
        self,
        score: float,
        *,
        text: str,
        runtime: SentimentRuntimeConfig,
    ) -> float:
        if not runtime.include_topic_context:
            return score
        delta = self._keyword_adjustment(
            text=text,
            positive_keywords=runtime.custom_keywords_positive,
            negative_keywords=runtime.custom_keywords_negative,
        )
        if delta == 0:
            return score
        adjusted = score + (runtime.topic_context_weight * delta)
        return max(0.0, min(1.0, adjusted))

    @staticmethod
    def _keyword_adjustment(
        *,
        text: str,
        positive_keywords: Iterable[str],
        negative_keywords: Iterable[str],
    ) -> float:
        if not text:
            return 0.0
        text_lower = text.lower()
        pos_count = sum(
            1 for kw in positive_keywords if kw and kw.lower() in text_lower
        )
        neg_count = sum(
            1 for kw in negative_keywords if kw and kw.lower() in text_lower
        )
        if pos_count == neg_count:
            return 0.0
        delta = (pos_count - neg_count) * 0.02
        return max(-0.2, min(0.2, delta))

    @staticmethod
    def _label_from_score(score: float, runtime: SentimentRuntimeConfig) -> str:
        if score >= runtime.positive_threshold:
            return "positive"
        if score <= runtime.negative_threshold:
            return "negative"
        return "neutral"

    @staticmethod
    def _failure_result(
        document: dict[str, Any], *, reason: str, error: str | None = None
    ) -> dict[str, Any]:
        return {
            "document_id": document.get("document_id"),
            "score": 0.5,
            "label": "neutral",
            "confidence": 0.0,
            "status": "failed",
            "recovered": False,
            "error": error or reason,
        }

    @staticmethod
    def _chunked(
        items: list[dict[str, Any]], size: int
    ) -> Iterable[list[dict[str, Any]]]:
        for idx in range(0, len(items), max(1, size)):
            yield items[idx : idx + size]

    def _build_runtime_config(self) -> SentimentRuntimeConfig:
        """Build runtime configuration for sentiment analysis."""
        return build_sentiment_runtime_config()

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Demo mode implementation with static sentiment data.

        Parameters
        ----------
        message : str
            Topic name.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Demo sentiment analysis results.
        """
        import random

        topic = message.strip()
        random.seed(hash(topic))

        # Generate demo statistics
        total_docs = random.randint(50, 200)
        analyzed = total_docs - random.randint(0, 5)
        failed = total_docs - analyzed
        recovered = random.randint(0, min(5, failed))

        # Generate realistic distribution
        positive_ratio = random.uniform(0.3, 0.5)
        negative_ratio = random.uniform(0.2, 0.4)
        neutral_ratio = 1.0 - positive_ratio - negative_ratio

        positive_count = int(analyzed * positive_ratio)
        negative_count = int(analyzed * negative_ratio)
        neutral_count = int(analyzed * neutral_ratio)

        # Calculate average score
        avg_score = (
            ((positive_count * 0.75) + (neutral_count * 0.5) + (negative_count * 0.25))
            / analyzed
            if analyzed > 0
            else 0.5
        )

        stats = {
            "total_documents": total_docs,
            "analyzed": analyzed,
            "failed": failed,
            "recovered": recovered,
            "avg_score": avg_score,
            "positive_count": positive_count,
            "neutral_count": neutral_count,
            "negative_count": negative_count,
        }

        summary = (
            f"Sentiment analysis completed (demo): {analyzed} documents analyzed, "
            f"{recovered} recovered. Average score: {avg_score:.3f}. "
            f"Positive: {positive_count}, "
            f"Neutral: {neutral_count}, "
            f"Negative: {negative_count}."
        )

        return {
            "status": "completed",
            "summary": summary,
            "stats": stats,
            "run_id": f"demo-{uuid.uuid4().hex[:8]}",
        }
