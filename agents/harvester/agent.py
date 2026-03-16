"""Harvester agent — Phase 2 link collection coordinator."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from typing import Any, Awaitable, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents._registry import register_agent
from agents.harvester.models import (
    HarvestPlan,
    HarvestTaskPlan,
    HarvesterRuntimeConfig,
)
from agents.services import (
    AsyncLinkWriter,
    build_fallback_harvest_tasks,
    collect_firecrawl_browser_results,
    collect_firecrawl_results,
    collect_serper_results,
    expand_with_crawlbase,
    finish_harvest_run,
    init_harvest_tables,
    load_research_brief,
    record_orchestrator_event,
    save_pipeline_artifact,
    select_expansion_seeds,
    start_harvest_run,
)
from utils.structured_output import invoke_model_with_structured_recovery


CollectorFunc = Callable[..., Awaitable[Any]]


@register_agent
class HarvesterAgent(BaseAgent):
    """Collect and persist candidate links for downstream scraping."""

    _name = "harvester"
    _description = (
        "Harvest high-quality candidate links for a topic using the planner's "
        "queries, multiple search providers, browser discovery, and expansion "
        "from promising seed pages. Writes deduplicated links into the topic "
        "SQLite database."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"
    _timeout_seconds = 1200
    _max_retries = 2

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        if not topic:
            raise ValueError("HarvesterAgent requires a non-empty topic.")
        return asyncio.run(self.ainvoke(topic, **kwargs))

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        brief = load_research_brief(topic)
        runtime = self._runtime_config()
        init_harvest_tables(topic)
        plan = await self._build_harvest_plan(topic, brief, runtime)
        plan_json = plan.model_dump_json(indent=2)

        self._checkpoint_artifact(
            topic=topic,
            artifact_type="harvester_plan",
            value=plan_json,
            meta={"task_count": len(plan.tasks), "source_order": plan.source_order},
        )

        run_id = str(uuid.uuid4())
        start_harvest_run(
            topic,
            run_id=run_id,
            source_agent=self._name,
            llm_provider=self.llm._provider,
            llm_model=getattr(self.llm, "_model", None),
            plan_json=plan_json,
            config_data=asdict(runtime),
        )
        latest_run_id = None
        try:
            from agents.services import get_latest_run_id

            latest_run_id = get_latest_run_id(topic)
        except Exception:
            latest_run_id = None

        if latest_run_id:
            record_orchestrator_event(
                latest_run_id,
                event_type="harvest_started",
                agent=self._name,
                status="running",
                message="Harvester started link collection",
                meta={"harvest_run_id": run_id, "task_count": len(plan.tasks)},
            )

        writer = AsyncLinkWriter(
            topic=topic,
            brief=brief,
            config=runtime,
            run_id=run_id,
            actor=self._name,
        )
        await writer.start()

        collected_batches: list = []
        try:
            search_results = await self._collect_search_batches(
                topic, brief, plan, runtime, writer
            )
            collected_batches.extend(search_results)

            seed_links = select_expansion_seeds(
                [item for batch in search_results for item in batch.links],
                brief=brief,
                runtime=runtime,
            )
            if seed_links and not writer.is_full:
                expansion_result = await expand_with_crawlbase(
                    seed_links,
                    brief=brief,
                    runtime=runtime,
                    actor=self._name,
                )
                collected_batches.append(expansion_result)
                await writer.submit_many(expansion_result.links)
                self._checkpoint_artifact(
                    topic=topic,
                    artifact_type="harvester_source_summary",
                    value=json.dumps(
                        {
                            "source": expansion_result.source_name,
                            "count": len(expansion_result.links),
                            "warnings": expansion_result.warnings,
                        },
                        ensure_ascii=False,
                    ),
                )

            await writer.close()
            stats = writer.stats | {
                "tasks_executed": len(plan.tasks),
                "sources_used": list(
                    dict.fromkeys(batch.source_name for batch in collected_batches)
                ),
                "seed_links": len(seed_links),
            }
            finish_harvest_run(topic, run_id=run_id, status="completed", stats=stats)
            self._checkpoint_agent_status(
                topic,
                status="completed",
                retries=0,
                mark_completed=True,
            )
            summary = self._format_summary(topic, plan, stats, collected_batches)
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_summary",
                value=summary,
                meta=stats,
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="harvest_complete",
                    agent=self._name,
                    status="completed",
                    message="Harvester completed link collection",
                    meta=stats,
                )
            return {
                "messages": [],
                "output": summary,
                "plan": plan,
                "stats": stats,
            }
        except Exception as exc:
            await writer.close()
            stats = writer.stats
            finish_harvest_run(
                topic, run_id=run_id, status="failed", stats=stats, error=str(exc)
            )
            self._checkpoint_agent_status(
                topic,
                status="failed",
                last_error=str(exc),
                mark_completed=True,
            )
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_error",
                value=str(exc),
            )
            if latest_run_id:
                record_orchestrator_event(
                    latest_run_id,
                    event_type="harvest_error",
                    agent=self._name,
                    status="failed",
                    message=str(exc),
                    meta=stats,
                )
            raise

    async def _build_harvest_plan(
        self,
        topic: str,
        brief: Any,
        runtime: HarvesterRuntimeConfig,
    ) -> HarvestPlan:
        if self._demo:
            return self._demo_plan(brief, runtime)

        available_sources = ["serper"]
        from env import config

        # Add any enabled sources depending on configured API keys
        if runtime.enable_firecrawl and config.get("FIRECRAWL_API_KEY"):
            available_sources.append("firecrawl_search")
            if runtime.enable_browser_discovery:
                available_sources.append("firecrawl_browser")
        if runtime.enable_serpapi and config.get("SERPAPI_API_KEY"):
            available_sources.append("serpapi")
        # camoufox can run as a remote server, local Python package, or CLI,
        # so we don't require CAMOUFOX_ENDPOINT here; the collector itself will
        # raise if nothing is usable.  Users still must set the runtime flag.
        if runtime.enable_camoufox:
            available_sources.append("camoufox_browser")

        prompt_input = {
            "topic": topic,
            "planner_brief": {
                "topic_summary": brief.topic_summary,
                "keywords": brief.keywords,
                "hashtags": brief.hashtags,
                "platforms": brief.platforms,
                "search_queries": brief.search_queries,
                "estimated_volume": brief.estimated_volume,
                "stop_condition": brief.stop_condition,
                "reasoning": brief.reasoning,
            },
            "available_sources": available_sources,
            "max_links": runtime.max_links,
            "per_query_limit": runtime.per_query_limit,
            "min_quality_score": runtime.min_quality_score,
        }
        self._checkpoint_artifact(
            topic=topic,
            artifact_type="harvester_plan_prompt",
            value=json.dumps(prompt_input, ensure_ascii=False),
        )

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(
                content=(
                    "Build a harvesting plan for this topic and planner brief. "
                    "Return only valid JSON for the HarvestPlan schema.\n\n"
                    f"{json.dumps(prompt_input, ensure_ascii=False, indent=2)}"
                )
            ),
        ]

        def _fallback_text_getter() -> str:
            response = self._llm_adapter.chat_model.invoke(messages)
            content = response.content if hasattr(response, "content") else response
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)
            return str(content)

        recovery = invoke_model_with_structured_recovery(
            llm_adapter=self._llm_adapter,
            schema_model=HarvestPlan,
            messages=messages,
            supports_structured=self._llm_adapter.supports_structured_output,
            fallback_text_getter=_fallback_text_getter,
            repair_prompt_builder=self._build_harvest_plan_repair_prompt,
            max_reasks=2,
            repair_max_tokens=2048,
        )

        if recovery.structured_error is not None:
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_plan_structured_error",
                value=recovery.structured_error,
                meta={"mode": recovery.mode},
            )
        if recovery.parse_error is not None:
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_plan_parse_error",
                value=recovery.parse_error,
                meta={"mode": recovery.mode},
            )
        if recovery.reask_error is not None:
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_plan_reask_error",
                value=recovery.reask_error,
                meta={"mode": recovery.mode, "attempts": recovery.reask_attempts},
            )
        if recovery.repair_error is not None:
            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_plan_repair_error",
                value=recovery.repair_error,
                meta={"mode": recovery.mode},
            )

        plan = recovery.value
        if plan is not None and plan.tasks:
            return plan

        self._checkpoint_artifact(
            topic=topic,
            artifact_type="harvester_plan_fallback",
            value="Structured recovery failed or returned empty tasks; using deterministic fallback plan",
            meta={"mode": recovery.mode, "reask_attempts": recovery.reask_attempts},
        )
        return self._demo_plan(brief, runtime)

    @staticmethod
    def _build_harvest_plan_repair_prompt(raw_text: str) -> str:
        return (
            "Convert the following harvester planning output into strict JSON for HarvestPlan. "
            "Return JSON object only with keys: summary, source_order, max_links, "
            "min_quality_score, tasks. "
            "Each tasks item must include: source, query, rationale, desired_count, "
            "priority, query_type, required, tags. "
            "No markdown, no extra text.\n\n"
            "Raw output:\n"
            f"{raw_text}"
        )

    def _demo_plan(self, brief: Any, runtime: HarvesterRuntimeConfig) -> HarvestPlan:
        tasks = build_fallback_harvest_tasks(brief, runtime)
        return HarvestPlan(
            summary=f"Fallback harvesting plan for {brief.topic}",
            source_order=["serper", "firecrawl_search", "firecrawl_browser"],
            max_links=runtime.max_links,
            min_quality_score=runtime.min_quality_score,
            tasks=tasks,
            reasoning="Fallback deterministic plan built from planner search queries and platform hints.",
        )

    def _runtime_config(self) -> HarvesterRuntimeConfig:
        from env import config

        def _as_bool(key: str, default: bool) -> bool:
            raw = config.get(key)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        def _as_int(key: str, default: int) -> int:
            raw = config.get(key)
            try:
                return max(1, int(raw)) if raw is not None else default
            except (TypeError, ValueError):
                return default

        def _as_float(key: str, default: float) -> float:
            raw = config.get(key)
            try:
                return max(0.0, float(raw)) if raw is not None else default
            except (TypeError, ValueError):
                return default

        return HarvesterRuntimeConfig(
            max_links=_as_int("HARVESTER_MAX_LINKS", 1000),
            max_concurrency=_as_int("HARVESTER_MAX_CONCURRENCY", 8),
            source_timeout_seconds=_as_int("HARVESTER_SOURCE_TIMEOUT_SECONDS", 120),
            writer_batch_size=_as_int("HARVESTER_WRITER_BATCH_SIZE", 50),
            writer_queue_size=_as_int("HARVESTER_QUEUE_SIZE", 5000),
            per_query_limit=_as_int("HARVESTER_PER_QUERY_LIMIT", 25),
            min_quality_score=_as_float("HARVESTER_MIN_QUALITY_SCORE", 0.35),
            expansion_seed_limit=_as_int("HARVESTER_EXPANSION_SEED_LIMIT", 12),
            expansion_per_seed_limit=_as_int("HARVESTER_EXPANSION_PER_SEED_LIMIT", 25),
            enable_serper=_as_bool("HARVESTER_ENABLE_SERPER", True),
            enable_firecrawl=_as_bool("HARVESTER_ENABLE_FIRECRAWL", True),
            enable_browser_discovery=_as_bool(
                "HARVESTER_ENABLE_BROWSER_DISCOVERY", True
            ),
            enable_crawlbase=_as_bool("HARVESTER_ENABLE_CRAWLBASE", True),
            enable_serpapi=_as_bool("HARVESTER_ENABLE_SERPAPI", False),
            enable_camoufox=_as_bool("HARVESTER_ENABLE_CAMOUFOX", False),
        )

    async def _collect_search_batches(
        self,
        topic: str,
        brief: Any,
        plan: HarvestPlan,
        runtime: HarvesterRuntimeConfig,
        writer: AsyncLinkWriter,
    ) -> list[Any]:
        """Execute all harvesting tasks concurrently and record results."""
        source_map: dict[str, CollectorFunc] = {}
        if runtime.enable_serper:
            source_map["serper"] = collect_serper_results
        if runtime.enable_firecrawl:
            source_map["firecrawl_search"] = collect_firecrawl_results
        if runtime.enable_firecrawl and runtime.enable_browser_discovery:
            source_map["firecrawl_browser"] = collect_firecrawl_browser_results
        if runtime.enable_serpapi:
            from agents.services.harvester_sources import collect_serpapi_results

            source_map["serpapi"] = collect_serpapi_results
        if runtime.enable_camoufox:
            from agents.services.harvester_sources import (
                collect_camoufox_browser_results,
            )

            source_map["camoufox_browser"] = collect_camoufox_browser_results

        semaphore = asyncio.Semaphore(runtime.max_concurrency)
        results: list[Any] = []

        async def _run_task(task: HarvestTaskPlan, source_name: str) -> None:
            collector = source_map.get(source_name)
            if collector is None or writer.is_full:
                return
            async with semaphore:
                result = await asyncio.wait_for(
                    collector(
                        task,
                        brief=brief,
                        runtime=runtime,
                        actor=self._name,
                    ),
                    timeout=runtime.source_timeout_seconds,
                )
                results.append(result)
                await writer.submit_many(result.links)
                save_pipeline_artifact(
                    topic,
                    source_agent=self._name,
                    artifact_type="harvester_source_summary",
                    value=json.dumps(
                        {
                            "source": result.source_name,
                            "source_type": result.source_type,
                            "count": len(result.links),
                            "warnings": result.warnings,
                            "meta": result.meta,
                            "query": task.query,
                        },
                        ensure_ascii=False,
                    ),
                )

        coroutines: list[Awaitable[None]] = []
        for task in plan.tasks:
            for source_name in task.source_names:
                if source_name not in source_map or writer.is_full:
                    continue
                coroutines.append(_run_task(task, source_name))

        await asyncio.gather(*coroutines)
        return results

    def _format_summary(
        self,
        topic: str,
        plan: HarvestPlan,
        stats: dict[str, Any],
        batches: list[Any],
    ) -> str:
        source_lines = []
        for batch in batches:
            source_lines.append(
                f"- {batch.source_name}: {len(batch.links)} candidates"
                + (f" ({len(batch.warnings)} warnings)" if batch.warnings else "")
            )
        return "\n".join(
            [
                "# Link Harvest Complete",
                f"**Topic**: {topic}",
                f"**Plan Summary**: {plan.summary}",
                f"**Tasks Executed**: {stats.get('tasks_executed', 0)}",
                f"**Canonical Links Stored**: {stats.get('links_inserted', 0)}",
                f"**Updated Existing Links**: {stats.get('links_updated', 0)}",
                f"**Observations Logged**: {stats.get('observations_written', 0)}",
                f"**Duplicates Seen**: {stats.get('duplicates_seen', 0)}",
                f"**Rejected Low Quality**: {stats.get('rejected_low_quality', 0)}",
                f"**Rejected Invalid**: {stats.get('rejected_invalid', 0)}",
                "## Sources",
                *source_lines,
            ]
        )
