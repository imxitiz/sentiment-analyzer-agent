"""Scraper agent — phase 3 deep extraction from harvested URLs."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base import BaseAgent
from agents._registry import register_agent
from agents.scraper.models import RecoveryPlan, ScrapeRuntimeConfig, ScrapeTarget
from agents.scraper.recovery import ScraperRecoveryAgent
from agents.services import (
    bootstrap_scrape_targets,
    build_document_store,
    build_scrape_runtime_config,
    finish_scrape_run,
    get_latest_run_id,
    init_scraper_tables,
    load_scrape_targets,
    record_orchestrator_event,
    save_pipeline_artifact,
    scrape_status_counts,
    scrape_target_with_backend,
    start_scrape_run,
    update_scrape_target,
)
from agents.services.scraper_sources import build_backend_plan
from Logging import get_logger

logger = get_logger("agents.scraper")


@register_agent
class ScraperAgent(BaseAgent):
    """Fetch raw content for harvested links and persist it for later phases."""

    _name = "scraper"
    _description = (
        "Fetch raw documents and rich metadata for harvested URLs, route each "
        "URL through the best scraping backend, and persist reusable raw data "
        "for later cleaning and sentiment analysis."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"
    _timeout_seconds = 1800
    _max_retries = 2

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        if not topic:
            raise ValueError("ScraperAgent requires a non-empty topic.")
        if self._demo:
            return self._demo_invoke(topic, **kwargs)
        return asyncio.run(self.ainvoke(topic, **kwargs))

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        if self._demo:
            return self._demo_invoke(topic, **kwargs)

        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        runtime = self._runtime_config()
        init_scraper_tables(topic)
        bootstrapped = bootstrap_scrape_targets(topic)
        targets = load_scrape_targets(topic, limit=runtime.max_targets_per_run)

        run_id = str(uuid.uuid4())
        start_scrape_run(
            topic,
            run_id=run_id,
            source_agent=self._name,
            config_data=asdict(runtime),
        )

        document_store = build_document_store()
        document_store.start_run(
            topic=topic,
            run_id=run_id,
            source_agent=self._name,
            config_data=asdict(runtime),
        )
        synced = document_store.sync_targets(
            topic=topic, run_id=run_id, targets=targets
        )

        latest_run_id = get_latest_run_id(topic)
        if latest_run_id:
            record_orchestrator_event(
                latest_run_id,
                event_type="scrape_started",
                agent=self._name,
                status="running",
                message="Scraper started deep extraction",
                meta={
                    "scrape_run_id": run_id,
                    "targets": len(targets),
                },
            )

        recovery_agent = ScraperRecoveryAgent(
            llm_provider=getattr(self.llm, "_provider", "dummy"),
        )
        stats: dict[str, Any] = {
            "bootstrapped_targets": bootstrapped,
            "queued_targets": len(targets),
            "synced_targets": synced,
            "completed": 0,
            "reused": 0,
            "failed": 0,
            "backend_usage": {},
        }

        semaphore = asyncio.Semaphore(runtime.max_concurrency)

        async def _worker(target: ScrapeTarget) -> dict[str, Any]:
            async with semaphore:
                return await self._process_target(
                    topic=topic,
                    run_id=run_id,
                    target=target,
                    runtime=runtime,
                    recovery_agent=recovery_agent,
                    document_store=document_store,
                )

        try:
            results = await asyncio.gather(
                *[_worker(target) for target in targets], return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    stats["failed"] += 1
                    continue
                assert isinstance(result, dict)
                status = str(result.get("status") or "failed")
                backend = result.get("backend")
                if backend:
                    stats["backend_usage"][backend] = (
                        int(stats["backend_usage"].get(backend, 0)) + 1
                    )
                if status == "completed":
                    stats["completed"] += 1
                elif status == "reused":
                    stats["reused"] += 1
                else:
                    stats["failed"] += 1

            stats["queue_status"] = scrape_status_counts(topic)
            finish_scrape_run(topic, run_id=run_id, status="completed", stats=stats)
            document_store.finish_run(run_id=run_id, status="completed", stats=stats)
            self._checkpoint_agent_status(
                topic,
                status="completed",
                retries=0,
                mark_completed=True,
            )
            summary = self._format_summary(topic, stats)
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="scraper_summary",
                value=summary,
                meta=stats,
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="scrape_complete",
                    agent=self._name,
                    status="completed",
                    message="Scraper completed deep extraction",
                    meta=stats,
                )
            return {"messages": [], "output": summary, "stats": stats}
        except Exception as exc:
            error = str(exc)
            stats["queue_status"] = scrape_status_counts(topic)
            finish_scrape_run(
                topic, run_id=run_id, status="failed", stats=stats, error=error
            )
            document_store.finish_run(
                run_id=run_id, status="failed", stats=stats, error=error
            )
            self._checkpoint_agent_status(
                topic,
                status="failed",
                last_error=error,
                mark_completed=True,
            )
            save_pipeline_artifact(
                topic,
                source_agent=self._name,
                artifact_type="scraper_error",
                value=error,
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="scrape_error",
                    agent=self._name,
                    status="failed",
                    message=error,
                    meta=stats,
                )
            raise

    async def _process_target(
        self,
        *,
        topic: str,
        run_id: str,
        target: ScrapeTarget,
        runtime: ScrapeRuntimeConfig,
        recovery_agent: ScraperRecoveryAgent,
        document_store: Any,
    ) -> dict[str, Any]:
        existing = document_store.find_document(target.normalized_url)
        if existing and self._can_reuse_document(existing, runtime):
            attached = document_store.attach_existing_document(
                topic=topic,
                run_id=run_id,
                target=target,
                existing_document=existing,
            )
            document_id = str(
                attached.get("document_id")
                or existing.get("document_id")
                or target.unique_id
            )
            update_scrape_target(
                topic,
                normalized_url=target.normalized_url,
                status="completed",
                attempts=target.attempts,
                selected_backend="reused_document",
                document_id=document_id,
                mark_completed=True,
            )
            document_store.mark_target_status(
                topic=topic,
                normalized_url=target.normalized_url,
                status="completed",
                run_id=run_id,
                backend="reused_document",
                document_id=document_id,
                attempts=target.attempts,
                extra={"reused": True},
            )
            return {
                "status": "reused",
                "backend": "reused_document",
                "document_id": document_id,
            }

        backend_plan = build_backend_plan(target, runtime)
        if not backend_plan:
            update_scrape_target(
                topic,
                normalized_url=target.normalized_url,
                status="failed",
                attempts=target.attempts,
                last_error="No scraping backend is enabled for this target.",
                mark_completed=True,
            )
            return {"status": "failed", "error": "no_backend"}

        remaining = backend_plan.copy()
        attempts = target.attempts
        while remaining and attempts < runtime.max_retries_per_target:
            backend = remaining.pop(0)
            attempts += 1
            update_scrape_target(
                topic,
                normalized_url=target.normalized_url,
                status="pending",
                attempts=attempts,
                selected_backend=backend,
                mark_started=True,
            )
            document_store.mark_target_status(
                topic=topic,
                normalized_url=target.normalized_url,
                status="pending",
                run_id=run_id,
                backend=backend,
                attempts=attempts,
            )
            try:
                scraped = await scrape_target_with_backend(
                    target, backend=backend, runtime=runtime
                )
                updated_target = dataclasses.replace(target, attempts=attempts)
                saved = document_store.save_document(
                    topic=topic,
                    run_id=run_id,
                    target=updated_target,
                    document=scraped,
                )
                update_scrape_target(
                    topic,
                    normalized_url=target.normalized_url,
                    status="completed",
                    attempts=attempts,
                    selected_backend=backend,
                    document_id=str(saved.get("document_id") or target.unique_id),
                    mark_completed=True,
                )
                return {
                    "status": "completed",
                    "backend": backend,
                    "document_id": str(saved.get("document_id") or target.unique_id),
                }
            except Exception as exc:
                error_text = str(exc)
                recovery = self._run_recovery_agent(
                    recovery_agent=recovery_agent,
                    target=target,
                    backend=backend,
                    error_text=error_text,
                    remaining_backends=remaining,
                )
                save_pipeline_artifact(
                    topic,
                    source_agent=self._name,
                    artifact_type="scraper_backend_error",
                    value=error_text,
                    meta={
                        "url": target.normalized_url,
                        "backend": backend,
                        "recovery": recovery.model_dump(),
                    },
                )
                update_scrape_target(
                    topic,
                    normalized_url=target.normalized_url,
                    status="failed"
                    if recovery.mark_terminal or not recovery.should_retry
                    else "pending",
                    attempts=attempts,
                    selected_backend=backend,
                    last_error=error_text,
                    mark_completed=recovery.mark_terminal
                    or (not recovery.should_retry and not remaining),
                )
                document_store.mark_target_status(
                    topic=topic,
                    normalized_url=target.normalized_url,
                    status="failed"
                    if recovery.mark_terminal or not recovery.should_retry
                    else "pending",
                    run_id=run_id,
                    backend=backend,
                    error=error_text,
                    attempts=attempts,
                    extra={"recovery_reason": recovery.reason},
                )
                if recovery.mark_terminal:
                    break
                if (
                    recovery.recommended_backend
                    and recovery.recommended_backend in remaining
                ):
                    remaining.remove(recovery.recommended_backend)
                    remaining.insert(0, recovery.recommended_backend)
                if not recovery.should_retry and not remaining:
                    break

        update_scrape_target(
            topic,
            normalized_url=target.normalized_url,
            status="failed",
            attempts=attempts,
            selected_backend=None,
            last_error="All scraping backends failed or recovery marked the URL terminal.",
            mark_completed=True,
        )
        document_store.mark_target_status(
            topic=topic,
            normalized_url=target.normalized_url,
            status="failed",
            run_id=run_id,
            attempts=attempts,
            error="All scraping backends failed or recovery marked the URL terminal.",
        )
        return {"status": "failed"}

    def _run_recovery_agent(
        self,
        *,
        recovery_agent: ScraperRecoveryAgent,
        target: ScrapeTarget,
        backend: str,
        error_text: str,
        remaining_backends: list[str],
    ) -> RecoveryPlan:
        payload = {
            "url": target.url,
            "normalized_url": target.normalized_url,
            "platform": target.platform,
            "failed_backend": backend,
            "error": error_text,
            "remaining_backends": remaining_backends,
        }
        try:
            result = recovery_agent.invoke(json.dumps(payload, ensure_ascii=False))
            plan = result.get("recovery_plan")
            if isinstance(plan, RecoveryPlan):
                return plan
        except Exception as exc:
            logger.warning(
                "Recovery agent failed, falling back to deterministic handling: %s",
                exc,
                action="scraper_recovery_fallback",
            )

        if remaining_backends:
            return RecoveryPlan(
                should_retry=True,
                recommended_backend=remaining_backends[0],
                mark_terminal=False,
                reason="Fallback recovery selected the next backend in order.",
            )
        return RecoveryPlan(
            should_retry=False,
            recommended_backend=None,
            mark_terminal=True,
            reason="No backends remain after the failure.",
        )

    def _can_reuse_document(
        self, document: dict[str, Any], runtime: ScrapeRuntimeConfig
    ) -> bool:
        if not runtime.allow_existing_reuse:
            return False
        last_scraped_at = document.get("last_scraped_at")
        if not last_scraped_at:
            return False
        try:
            scraped_at = datetime.fromisoformat(str(last_scraped_at))
        except ValueError:
            return False
        if scraped_at.tzinfo is None:
            scraped_at = scraped_at.replace(tzinfo=timezone.utc)
        return scraped_at >= datetime.now(timezone.utc) - timedelta(
            days=runtime.reuse_existing_days
        )

    def _runtime_config(self) -> ScrapeRuntimeConfig:
        return build_scrape_runtime_config()

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        output = (
            f"Scraper demo completed for {message}. Collected raw documents, metadata, "
            "and reusable document references for downstream cleaning."
        )
        return {
            "messages": [],
            "output": output,
            "stats": {
                "queued_targets": 42,
                "completed": 31,
                "reused": 7,
                "failed": 4,
                "backend_usage": {
                    "reddit_json": 8,
                    "generic_http": 14,
                    "firecrawl": 6,
                    "camoufox": 3,
                },
            },
        }

    def _format_summary(self, topic: str, stats: dict[str, Any]) -> str:
        return (
            f"Scraping completed for {topic}. "
            f"Queued {stats.get('queued_targets', 0)} URLs, completed {stats.get('completed', 0)}, "
            f"reused {stats.get('reused', 0)} existing documents, and failed {stats.get('failed', 0)}."
        )
