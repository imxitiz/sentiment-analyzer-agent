"""Harvester agent — Phase 2 link collection coordinator."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import nullcontext
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
    backfill_harvest_metadata,
    build_fallback_harvest_tasks,
    collect_camoufox_agentic_results,
    collect_firecrawl_browser_results,
    collect_firecrawl_results,
    collect_serper_results,
    finish_harvest_run,
    init_harvest_tables,
    load_research_brief,
    record_orchestrator_event,
    save_pipeline_artifact,
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
        "queries, multiple search providers, and browser discovery. "
        "Writes deduplicated links into the topic "
        "SQLite database."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"
    _timeout_seconds = 1200
    _max_retries = 2

    _SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
        "serper": (
            "serper",
            "search",
            "web",
            "news",
            "social",
            "reddit",
            "twitter",
            "x",
            "facebook",
            "youtube",
        ),
        "firecrawl_search": ("firecrawl_search", "firecrawl", "firecrawl-news"),
        "firecrawl_browser": ("firecrawl_browser", "browser", "rendered_browser"),
        "camoufox_browser": ("camoufox_browser", "camoufox", "camoufox_rendered"),
        "camoufox_agentic": ("camoufox_agentic", "agentic_browser", "agentic_camoufox"),
        "serpapi": ("serpapi",),
    }

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        if not topic:
            raise ValueError("HarvesterAgent requires a non-empty topic.")
        try:
            from agents.services import llm_trace_context
        except Exception:
            llm_trace_context = None

        context_manager = (
            llm_trace_context(topic, self._name)
            if llm_trace_context is not None
            else nullcontext()
        )
        with context_manager:
            return asyncio.run(self.ainvoke(topic, **kwargs))

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        topic = message.strip()
        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        try:
            from agents.services import llm_trace_context
        except Exception:
            llm_trace_context = None

        context_manager = (
            llm_trace_context(topic, self._name)
            if llm_trace_context is not None
            else nullcontext()
        )

        with context_manager:
            brief = load_research_brief(topic)
            runtime = self._runtime_config()
            init_harvest_tables(topic)
            backfill_stats = backfill_harvest_metadata(topic)
            plan = await self._build_harvest_plan(topic, brief, runtime)
            plan_json = plan.model_dump_json(indent=2)

        self._checkpoint_artifact(
            topic=topic,
            artifact_type="harvester_plan",
            value=plan_json,
            meta={
                "task_count": len(plan.tasks),
                "source_order": plan.source_order,
                "platform_backfill": backfill_stats,
            },
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

            await writer.close()
            stats = writer.stats | {
                "tasks_executed": len(plan.tasks),
                "sources_used": list(
                    dict.fromkeys(batch.source_name for batch in collected_batches)
                ),
                "platform_backfill": backfill_stats,
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
            if runtime.enable_camoufox_agentic:
                available_sources.append("camoufox_agentic")

        prompt_input = {
            "topic": topic,
            "planner_brief": self._compact_planner_brief(brief),
            "available_sources": available_sources,
            "max_links": runtime.max_links,
            "per_query_limit": runtime.per_query_limit,
            "min_quality_score": runtime.min_quality_score,
            "target_task_count": min(14, max(6, len(brief.search_queries[:14]))),
            "schema_contract": {
                "summary": "string",
                "source_order": "array<string>",
                "max_links": "integer",
                "min_quality_score": "float",
                "tasks": [
                    {
                        "query": "string",
                        "platform_hint": "string",
                        "source_names": "array<string>",
                        "target_results": "integer",
                        "rationale": "string",
                    }
                ],
                "reasoning": "string",
            },
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
                    "Return exactly one valid JSON object for the HarvestPlan schema.\n"
                    "Use EXACT top-level keys: summary, source_order, max_links, min_quality_score, tasks, reasoning.\n"
                    "Each tasks item MUST contain only: query, platform_hint, source_names, target_results, rationale.\n"
                    "Do not include markdown, commentary, code fences, or trailing text.\n"
                    "Do not add any extra keys.\n\n"
                    f"{json.dumps(prompt_input, ensure_ascii=False, indent=2)}"
                )
            ),
        ]

        def _fallback_text_getter() -> str:
            response = self._llm_adapter.invoke_messages(
                messages,
                call_kind="harvester_plan_fallback_invoke",
            )
            content = response.content if hasattr(response, "content") else response
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)
            return str(content)

        recovery = invoke_model_with_structured_recovery(
            llm_adapter=self._llm_adapter,
            schema_model=HarvestPlan,
            messages=messages,
            supports_structured=self._llm_adapter.supports_structured_output,
            structured_invoke_kwargs=self._structured_invoke_kwargs(),
            fallback_text_getter=_fallback_text_getter,
            normalize_payload=lambda payload: self._normalize_harvest_plan_payload(
                payload,
                available_sources=available_sources,
                per_query_limit=runtime.per_query_limit,
            ),
            repair_prompt_builder=(
                lambda raw: self._build_harvest_plan_repair_prompt(
                    raw_text=raw,
                    available_sources=available_sources,
                    per_query_limit=runtime.per_query_limit,
                )
            ),
            max_reasks=1,
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
            normalized_plan = self._normalize_harvest_plan(
                plan=plan,
                available_sources=available_sources,
                runtime=runtime,
            )
            if normalized_plan is not None and normalized_plan.tasks:
                return normalized_plan

            self._checkpoint_artifact(
                topic=topic,
                artifact_type="harvester_plan_non_executable",
                value="LLM plan parsed but had no executable tasks after source normalization",
                meta={
                    "mode": recovery.mode,
                    "available_sources": available_sources,
                },
            )

        self._checkpoint_artifact(
            topic=topic,
            artifact_type="harvester_plan_fallback",
            value="Structured recovery failed or returned empty tasks; using deterministic fallback plan",
            meta={"mode": recovery.mode, "reask_attempts": recovery.reask_attempts},
        )
        return self._demo_plan(brief, runtime)

    @staticmethod
    def _build_harvest_plan_repair_prompt(
        raw_text: str,
        available_sources: list[str],
        per_query_limit: int,
    ) -> str:
        return (
            "Convert the following harvester planning output into strict JSON for HarvestPlan. "
            "Return JSON object only with keys: summary, source_order, max_links, "
            "min_quality_score, tasks, reasoning. "
            "Each tasks item must include: query, platform_hint, source_names, target_results, rationale. "
            f"source_names entries must be selected only from: {available_sources}. "
            f"target_results must be an integer between 1 and {max(1, int(per_query_limit))}. "
            "No markdown, no extra text.\n\n"
            "Raw output:\n"
            f"{raw_text}"
        )

    def _normalize_source_name(
        self, source: str, available_sources: list[str]
    ) -> str | None:
        candidate = str(source or "").strip().lower().replace("-", "_")
        if not candidate:
            return None
        if candidate in available_sources:
            return candidate
        for canonical, aliases in self._SOURCE_ALIASES.items():
            if candidate == canonical or candidate in aliases:
                return canonical if canonical in available_sources else None
        return None

    @staticmethod
    def _compact_planner_brief(brief: Any) -> dict[str, Any]:
        """Trim planner context so structured planning prompt stays concise and robust."""
        platforms: list[dict[str, str]] = []
        for item in brief.platforms[:6]:
            platforms.append(
                {
                    "name": str(item.get("name", "")).strip(),
                    "priority": str(item.get("priority", "")).strip(),
                    "reason": str(item.get("reason", "")).strip()[:180],
                }
            )

        return {
            "topic_summary": str(brief.topic_summary or "")[:400],
            "keywords": [str(item) for item in brief.keywords[:12]],
            "hashtags": [str(item) for item in brief.hashtags[:8]],
            "platforms": platforms,
            "search_queries": [str(item) for item in brief.search_queries[:14]],
            "estimated_volume": str(brief.estimated_volume or "")[:300],
            "stop_condition": str(brief.stop_condition or "")[:300],
            "reasoning": str(brief.reasoning or "")[:500],
        }

    def _structured_invoke_kwargs(self) -> dict[str, Any]:
        """Provider-tuned structured invocation kwargs.

        Ollama structured outputs are more reliable with JSON schema mode
        on newer servers/models. If unsupported, adapter falls back safely.
        """
        provider = str(getattr(self._llm_adapter, "_provider", "")).lower()
        if provider == "ollama":
            return {"method": "json_schema"}
        if provider in {"google", "openai"}:
            return {"method": "json_schema", "strict": True}
        return {}

    def _normalize_harvest_plan(
        self,
        *,
        plan: HarvestPlan,
        available_sources: list[str],
        runtime: HarvesterRuntimeConfig,
    ) -> HarvestPlan | None:
        normalized_tasks: list[HarvestTaskPlan] = []
        fallback_source = available_sources[0] if available_sources else "serper"

        for task in plan.tasks:
            query = str(task.query or "").strip()
            if not query:
                continue

            normalized_sources: list[str] = []
            for source_name in task.source_names:
                normalized = self._normalize_source_name(source_name, available_sources)
                if normalized and normalized not in normalized_sources:
                    normalized_sources.append(normalized)

            if not normalized_sources:
                normalized_sources = [fallback_source]

            target_results = max(
                1, min(int(task.target_results), runtime.per_query_limit)
            )
            platform_hint = str(task.platform_hint or "web").strip() or "web"
            rationale = str(
                task.rationale or "Harvest candidate links for sentiment analysis"
            ).strip()

            normalized_tasks.append(
                HarvestTaskPlan(
                    query=query,
                    platform_hint=platform_hint,
                    source_names=normalized_sources,
                    target_results=target_results,
                    rationale=rationale,
                )
            )

        if not normalized_tasks:
            return None

        source_order: list[str] = []
        for source_name in plan.source_order:
            normalized = self._normalize_source_name(source_name, available_sources)
            if normalized and normalized not in source_order:
                source_order.append(normalized)
        if not source_order:
            source_order = list(dict.fromkeys(available_sources))

        return HarvestPlan(
            summary=str(plan.summary or "Harvest links for sentiment pipeline"),
            source_order=source_order,
            max_links=runtime.max_links,
            min_quality_score=runtime.min_quality_score,
            tasks=normalized_tasks,
            reasoning=str(plan.reasoning or "Normalized from recovered plan"),
        )

    def _normalize_harvest_plan_payload(
        self,
        payload: Any,
        *,
        available_sources: list[str],
        per_query_limit: int,
    ) -> Any:
        """Normalize loose model JSON into HarvestPlan-compatible payload.

        This improves first-pass schema recovery for providers that emit mostly
        correct JSON but miss a few required fields.
        """
        if not isinstance(payload, dict):
            return payload

        normalized: dict[str, Any] = dict(payload)
        normalized["summary"] = str(normalized.get("summary") or "Harvest plan")
        normalized["reasoning"] = str(
            normalized.get("reasoning") or "Recovered from partial structured output"
        )

        source_order = normalized.get("source_order")
        if isinstance(source_order, str):
            normalized["source_order"] = [source_order]
        elif isinstance(source_order, list):
            normalized["source_order"] = [
                str(item) for item in source_order if str(item).strip()
            ]
        else:
            normalized["source_order"] = list(available_sources)

        max_links = normalized.get("max_links")
        try:
            # Provide default of 0 before int() to handle None case properly
            normalized["max_links"] = max(
                1, int(max_links if max_links is not None else 0)
            )
        except (TypeError, ValueError):
            normalized["max_links"] = 1000

        min_quality_score = normalized.get("min_quality_score")
        try:
            # Provide default of 0.0 before float() to handle None case properly
            normalized["min_quality_score"] = max(
                0.0, float(min_quality_score if min_quality_score is not None else 0.0)
            )
        except (TypeError, ValueError):
            normalized["min_quality_score"] = 0.35

        fallback_source = available_sources[0] if available_sources else "serper"
        tasks = normalized.get("tasks")
        normalized_tasks: list[dict[str, Any]] = []
        if isinstance(tasks, list):
            for item in tasks:
                if not isinstance(item, dict):
                    continue

                query = str(item.get("query") or "").strip()
                if not query:
                    continue

                source_names = item.get("source_names")
                if source_names is None:
                    legacy_source = item.get("source") or item.get("source_name")
                    source_names = (
                        [legacy_source] if legacy_source else [fallback_source]
                    )
                if isinstance(source_names, str):
                    source_names = [source_names]
                if not isinstance(source_names, list):
                    source_names = [fallback_source]

                normalized_sources: list[str] = []
                for source_name in source_names:
                    normalized_source = self._normalize_source_name(
                        str(source_name),
                        available_sources,
                    )
                    if (
                        normalized_source
                        and normalized_source not in normalized_sources
                    ):
                        normalized_sources.append(normalized_source)
                if not normalized_sources:
                    normalized_sources = [fallback_source]

                target_results = item.get("target_results")
                if target_results is None:
                    target_results = item.get("desired_count")
                # Provide default of 0 before int() to handle None case properly
                try:
                    target_results_int = int(
                        target_results if target_results is not None else 0
                    )
                except (TypeError, ValueError):
                    target_results_int = 10
                target_results_int = max(1, min(target_results_int, per_query_limit))

                platform_hint = str(item.get("platform_hint") or "web").strip() or "web"
                rationale = str(
                    item.get("rationale") or "Harvest candidate links"
                ).strip()

                normalized_tasks.append(
                    {
                        "query": query,
                        "platform_hint": platform_hint,
                        "source_names": normalized_sources,
                        "target_results": target_results_int,
                        "rationale": rationale,
                    }
                )

        normalized["tasks"] = normalized_tasks
        return normalized

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
            source_timeout_seconds=_as_int("HARVESTER_SOURCE_TIMEOUT_SECONDS", 300),
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
            enable_crawlbase=_as_bool("HARVESTER_ENABLE_CRAWLBASE", False),
            enable_serpapi=_as_bool("HARVESTER_ENABLE_SERPAPI", False),
            enable_camoufox=_as_bool("HARVESTER_ENABLE_CAMOUFOX", False),
            enable_camoufox_agentic=_as_bool("HARVESTER_ENABLE_CAMOUFOX_AGENTIC", True),
            camoufox_agentic_max_seed_pages=_as_int(
                "HARVESTER_CAMOUFOX_AGENTIC_MAX_SEED_PAGES", 10
            ),
            camoufox_agentic_max_hops=_as_int("HARVESTER_CAMOUFOX_AGENTIC_MAX_HOPS", 2),
            camoufox_agentic_links_per_page=_as_int(
                "HARVESTER_CAMOUFOX_AGENTIC_LINKS_PER_PAGE", 25
            ),
            camoufox_agentic_extract_chars=_as_int(
                "HARVESTER_CAMOUFOX_AGENTIC_EXTRACT_CHARS", 1200
            ),
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
            if runtime.enable_camoufox_agentic:
                source_map["camoufox_agentic"] = collect_camoufox_agentic_results

        semaphore = asyncio.Semaphore(runtime.max_concurrency)
        camoufox_semaphore = asyncio.Semaphore(1)
        results: list[Any] = []

        async def _run_task(task: HarvestTaskPlan, source_name: str) -> None:
            collector = source_map.get(source_name)
            if collector is None or writer.is_full:
                return
            active_semaphore = (
                camoufox_semaphore if source_name.startswith("camoufox_") else semaphore
            )
            async with active_semaphore:
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
