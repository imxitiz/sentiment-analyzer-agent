"""Planner agent — generates research plans for sentiment analysis.

The planner takes a topic and produces a structured plan with keywords,
hashtags, platform strategies, and search queries.  It uses the LLM's
structured output capability to return a ``ResearchPlan`` Pydantic model.

This agent runs in **direct mode** (no tools — pure LLM reasoning).

**Demo mode**: When ``llm_provider="dummy"``, returns a static but
realistic ``ResearchPlan`` with the topic name injected.  The plan
structure is identical to what the LLM would produce.

Usage::

    from agents.planner import PlannerAgent, ResearchPlan

    planner = PlannerAgent(llm_provider="google")
    result = planner.invoke("Nepal elections 2026")

    # Structured plan (when available):
    plan: ResearchPlan = result.get("plan")

    # Always available as JSON string:
    print(result["output"])

    # Demo mode (no LLM needed):
    demo_planner = PlannerAgent(llm_provider="dummy")
    result = demo_planner.invoke("Tesla stock")  # static data
"""

from __future__ import annotations

import re
from contextlib import nullcontext
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents._registry import register_agent
from agents.base import BaseAgent
from agents.services import (
    init_topic_db,
    save_pipeline_artifact,
    save_planner_plan,
    save_topic_input,
)

from agents.services import search_searchengine

from Logging import get_logger
from utils.structured_output import invoke_model_with_structured_recovery

logger = get_logger("agents.planner")


class PlatformStrategy(BaseModel):
    """A platform to search and why."""

    name: str = Field(description="Platform name (e.g. reddit, twitter, facebook)")
    priority: str = Field(description="high, medium, or low")
    reason: str = Field(description="Why this platform matters for this topic")


class ResearchPlan(BaseModel):
    """Structured research plan output from the planner."""

    topic_summary: str
    keywords: list[str]
    hashtags: list[str]
    platforms: list[PlatformStrategy]
    search_queries: list[str]
    estimated_volume: str
    stop_condition: str
    reasoning: str


@register_agent
class PlannerAgent(BaseAgent):
    """Create a research plan for a user topic."""

    _name = "planner"
    _description = (
        "Generate a comprehensive structured research plan for sentiment analysis on "
        "a given topic.  Returns keywords, hashtags, platform strategies, "
        "and ready-to-use search queries as structured JSON."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Generate a research plan for the given topic.

        Attempts structured output parsing to return a ResearchPlan model, but always returns the raw LLM output as a JSON string for transparency and debugging.
        In demo mode, returns a static ResearchPlan with the topic name injected immediately.
        Returns:
            dict with keys:
                - 'plan': ResearchPlan (when structured output is successful)
                - 'output': raw JSON string from LLM (always available)
            saves artifacts and checkpoints status in the database.
        """
        topic = message.strip()
        if not topic:
            raise ValueError("Topic cannot be empty")

        init_topic_db(topic)
        save_topic_input(
            topic,
            topic,
            input_type="topic",
            source_agent=self._name,
        )

        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        self._log.info(
            "Planning for topic  len=%d",
            len(topic),
            action="plan",
            meta={"topic_preview": topic[:120]},
        )

        try:
            from agents.services import llm_trace_context

            trace_context = llm_trace_context(topic, self._name)
        except Exception:
            trace_context = nullcontext()

        try:
            with trace_context:
                if self._demo:
                    result = self._demo_invoke(message, **kwargs)
                    if result.get("plan") is not None:
                        save_planner_plan(
                            topic,
                            plan=result["plan"],
                            raw_output=result.get("output", ""),
                            source_agent=self._name,
                        )
                    else:
                        save_pipeline_artifact(
                            topic,
                            source_agent=self._name,
                            artifact_type="planner_demo_output",
                            value=result.get("output", ""),
                        )
                    self._checkpoint_agent_status(
                        topic,
                        status="completed",
                        retries=0,
                        mark_completed=True,
                    )
                    return result

                web_context = self._gather_web_context(topic)
                if web_context:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_web_context",
                        value=web_context,
                    )

                messages = [
                    SystemMessage(content=self._system_prompt),
                    HumanMessage(
                        content=(
                            f"Create a research plan for: {message}\n\n"
                            f"Web context (from tool-based internet search):\n{web_context}"
                        )
                    ),
                ]

                fallback_result: dict[str, Any] = {"messages": messages, "output": ""}

                def _fallback_text_getter() -> str:
                    nonlocal fallback_result
                    response = self._llm_adapter.invoke_messages(
                        messages,
                        call_kind="planner_fallback_invoke",
                    )
                    content = (
                        response.content if hasattr(response, "content") else response
                    )
                    if isinstance(content, list):
                        output = "\n".join(str(item) for item in content)
                    else:
                        output = str(content)
                    fallback_result = {"messages": messages, "output": output}
                    self._log.success("Plan generated (text fallback)", action="plan")
                    return str(fallback_result.get("output", ""))

                recovery = invoke_model_with_structured_recovery(
                    llm_adapter=self._llm_adapter,
                    schema_model=ResearchPlan,
                    messages=messages,
                    supports_structured=self._llm_adapter.supports_structured_output,
                    structured_invoke_kwargs=self._structured_invoke_kwargs(),
                    fallback_text_getter=_fallback_text_getter,
                    normalize_payload=self._normalize_plan_payload,
                    repair_prompt_builder=lambda raw: self._build_plan_repair_prompt(
                        topic=topic,
                        raw_plan_text=raw,
                    ),
                    max_reasks=0
                    if not self._llm_adapter.supports_structured_output
                    else 1,
                    repair_max_tokens=2048,
                )

                if recovery.structured_error is not None:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_structured_error",
                        value=recovery.structured_error,
                        meta={"mode": recovery.mode},
                    )
                if recovery.structured_skipped:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_structured_skipped",
                        value="Structured output intentionally skipped for provider",
                        meta={
                            "provider": self._llm_adapter.provider,
                            "mode": recovery.mode,
                        },
                    )
                if recovery.parse_error is not None:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_parse_error",
                        value=recovery.parse_error,
                        meta={"mode": recovery.mode},
                    )
                if recovery.repair_error is not None:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_repair_error",
                        value=recovery.repair_error,
                        meta={"mode": recovery.mode},
                    )
                if recovery.reask_error is not None:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_reask_error",
                        value=recovery.reask_error,
                        meta={
                            "mode": recovery.mode,
                            "attempts": recovery.reask_attempts,
                        },
                    )
                if recovery.fallback_error is not None:
                    save_pipeline_artifact(
                        topic,
                        source_agent=self._name,
                        artifact_type="planner_fallback_error",
                        value=recovery.fallback_error,
                        meta={"mode": recovery.mode},
                    )

                if recovery.value is not None:
                    plan = recovery.value
                    self._log.success(
                        "Plan generated (%s)  keywords=%d  queries=%d",
                        recovery.mode,
                        len(plan.keywords),
                        len(plan.search_queries),
                    )
                    save_planner_plan(
                        topic,
                        plan=plan,
                        raw_output=recovery.raw_text,
                        source_agent=self._name,
                    )
                else:
                    plan = None

                output = recovery.raw_text or fallback_result.get("output", "")
                if output:
                    self._checkpoint_artifact(
                        topic=topic,
                        artifact_type="planner_output",
                        value=output,
                    )

                self._checkpoint_agent_status(
                    topic,
                    status="completed",
                    retries=0,
                    mark_completed=True,
                )
                return {"messages": messages, "output": output, "plan": plan}

        except Exception as exc:
            self._checkpoint_agent_status(
                topic,
                status="failed",
                last_error=str(exc),
                mark_completed=True,
            )
            raise

    @staticmethod
    def _flatten_string_values(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, dict):
            flattened: list[str] = []
            for item in value.values():
                flattened.extend(PlannerAgent._flatten_string_values(item))
            return flattened
        text = str(value).strip()
        return [text] if text else []

    def _normalize_plan_payload(self, payload: Any) -> Any:
        """Normalize alternate planner JSON shapes to the ResearchPlan schema."""
        if not isinstance(payload, dict):
            return payload

        normalized = dict(payload)
        if "topic_summary" not in normalized and "topic" in normalized:
            normalized["topic_summary"] = str(normalized.get("topic", "")).strip()

        if isinstance(normalized.get("keywords"), dict):
            normalized["keywords"] = PlannerAgent._flatten_string_values(
                normalized.get("keywords")
            )

        if isinstance(normalized.get("hashtags"), dict):
            normalized["hashtags"] = PlannerAgent._flatten_string_values(
                normalized.get("hashtags")
            )

        if "search_queries" not in normalized:
            for candidate_key in ("queries", "search_query", "query_list"):
                if candidate_key in normalized:
                    normalized["search_queries"] = self._flatten_string_values(
                        normalized.get(candidate_key)
                    )
                    break

        if isinstance(normalized.get("search_queries"), dict):
            normalized["search_queries"] = self._flatten_string_values(
                normalized.get("search_queries")
            )

        if "platforms" not in normalized and isinstance(
            normalized.get("platform_strategies"), dict
        ):
            platform_items = []
            entries = list(normalized["platform_strategies"].items())
            for idx, (name, details) in enumerate(entries):
                detail_dict = details if isinstance(details, dict) else {}
                approach = str(detail_dict.get("approach", "")).strip()
                if idx <= 1:
                    priority = "high"
                elif idx <= 3:
                    priority = "medium"
                else:
                    priority = "low"
                platform_items.append(
                    {
                        "name": str(name),
                        "priority": priority,
                        "reason": approach or f"Sentiment source: {name}",
                    }
                )
            normalized["platforms"] = platform_items

        if "platforms" not in normalized and isinstance(
            normalized.get("platform_strategy"), dict
        ):
            platform_items = []
            entries = list(normalized["platform_strategy"].items())
            for idx, (name, details) in enumerate(entries):
                detail_dict = details if isinstance(details, dict) else {}
                approach = str(
                    detail_dict.get("reason")
                    or detail_dict.get("rationale")
                    or detail_dict.get("approach")
                    or ""
                ).strip()
                priority_raw = detail_dict.get("priority")
                if isinstance(priority_raw, (int, float)):
                    priority_num = int(priority_raw)
                    if priority_num <= 2:
                        priority = "high"
                    elif priority_num <= 4:
                        priority = "medium"
                    else:
                        priority = "low"
                else:
                    priority_text = str(priority_raw or "").strip().lower()
                    if priority_text in {"high", "medium", "low"}:
                        priority = priority_text
                    elif idx <= 1:
                        priority = "high"
                    elif idx <= 3:
                        priority = "medium"
                    else:
                        priority = "low"

                platform_items.append(
                    {
                        "name": str(name),
                        "priority": priority,
                        "reason": approach or f"Sentiment source: {name}",
                    }
                )
            normalized["platforms"] = platform_items

        if isinstance(normalized.get("platforms"), list):
            normalized_platforms = []
            for idx, platform in enumerate(normalized["platforms"]):
                if isinstance(platform, dict):
                    name = str(
                        platform.get("name") or platform.get("platform") or "unknown"
                    )
                    priority_raw = platform.get("priority")
                    if isinstance(priority_raw, (int, float)):
                        priority_num = int(priority_raw)
                        if priority_num <= 2:
                            priority = "high"
                        elif priority_num <= 4:
                            priority = "medium"
                        else:
                            priority = "low"
                    else:
                        priority_text = str(priority_raw or "").strip().lower()
                        if priority_text in {"high", "medium", "low"}:
                            priority = priority_text
                        elif idx <= 1:
                            priority = "high"
                        elif idx <= 3:
                            priority = "medium"
                        else:
                            priority = "low"
                    reason = str(
                        platform.get("reason")
                        or platform.get("rationale")
                        or f"Sentiment source: {name}"
                    )
                    normalized_platforms.append(
                        {"name": name, "priority": priority, "reason": reason}
                    )
                else:
                    name = str(platform)
                    if idx <= 1:
                        priority = "high"
                    elif idx <= 3:
                        priority = "medium"
                    else:
                        priority = "low"
                    normalized_platforms.append(
                        {
                            "name": name,
                            "priority": priority,
                            "reason": f"Sentiment source: {name}",
                        }
                    )
            normalized["platforms"] = normalized_platforms

        normalized.setdefault("estimated_volume", "Target 2,000-5,000 posts/documents")
        normalized.setdefault(
            "stop_condition",
            "Stop when sentiment trends stabilize across platforms for 48 hours",
        )
        normalized.setdefault(
            "reasoning",
            "Blend platform-level social signals with cross-source query coverage.",
        )

        return normalized

    def _build_plan_repair_prompt(self, *, topic: str, raw_plan_text: str) -> str:
        """Build repair prompt for converting free-form plan text to strict schema."""
        return (
            "Convert the following research plan into strict JSON for this schema keys only: "
            "topic_summary, keywords, hashtags, platforms, search_queries, estimated_volume, "
            "stop_condition, reasoning. "
            "Rules: return JSON object only, no markdown, no explanation. "
            "platforms must be a list of objects with keys: name, priority, reason. "
            "keywords/hashtags/search_queries must be lists of strings. "
            f"Topic: {topic}\n\n"
            "Raw plan text:\n"
            f"{raw_plan_text}"
        )

    def _invoke_structured(self, messages: list[Any]) -> ResearchPlan:
        """Call LLM with structured output binding."""
        result = self._llm_adapter.invoke_structured(
            messages,
            schema_model=ResearchPlan,
            call_kind="planner_structured_invoke",
            structured_kwargs=self._structured_invoke_kwargs(),
        )
        if isinstance(result, ResearchPlan):
            return result
        # Handle dict response from some providers
        return ResearchPlan.model_validate(result)

    def _structured_invoke_kwargs(self) -> dict[str, Any]:
        """Provider-tuned structured output kwargs for planner schema calls."""
        provider = str(getattr(self._llm_adapter, "_provider", "")).lower()
        if provider == "ollama":
            return {"method": "json_schema"}
        if provider in {"google", "openai"}:
            return {"method": "json_schema", "strict": True}
        return {}

    def _gather_web_context(self, topic: str) -> str:
        """Get a quick search queries to gather search snippets deterministically,
        then summarize with the LLM to give to planner.
        LLM gives the search query from the user topic, and we do the search ourselves
        and give the results back to the LLM to summarize, so that from all the actual internet search,
        it makes LLM easier to make plan from the web context and
        know the popular terms to do the harvesting and sentiment analysis on given topic.

        !!! WE MIGHT AGAIN NEED TO GO BACK TO LETTING LLM DO THE SEARCHING WITH TOOL CALL IN THE FUTURE,
        THE PLANNER AGENT WILL HAVE MORE CONTROL ON HOW TO DO THE SEARCHING AND ALSO CAN KNOW BETTER,
        WHICH CAN LEAD TO BETTER SEARCH QUERIES AND ALSO BETTER WEB CONTEXT SUMMARY FOR THE PLANNER AGENT TO MAKE THE RESEARCH PLAN.
        BUT FOR NOW, THIS APPROACH GIVES US MORE CONTROL AND RELIABILITY IN TESTING.!!!
        """
        try:
            query_prompt = [
                SystemMessage(
                    content=(
                        "You are a helpful assistant for a research planner agent. "
                        "Given a research topic, generate a set of plain text, comma-separated search queries "
                        "that would be useful to gather web context for that topic. "
                        "These queries should be designed to retrieve relevant information from search engines or other web sources that can help the planner agent create a comprehensive research plan. "
                        "The queries should be specific enough to yield useful results but broad enough to cover various aspects of the topic."
                    )
                ),
                HumanMessage(content=topic),
            ]

            queries = self._llm_adapter.invoke_messages(
                query_prompt,
                call_kind="planner_web_context_queries",
            )

            content = queries.content if hasattr(queries, "content") else queries
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)

            queries = str(content)

            list_of_queries = self._extract_web_context_queries(str(queries), topic)
            queries = list_of_queries[:5]  # limit to top 5 queries

            snippet_payloads: list[str] = []
            for query in queries:
                snippet_payloads.append(
                    search_searchengine(query=query, engine="google", max_results=5)
                )

            summary_messages = [
                SystemMessage(
                    content=(
                        "You are a research assistant for a planning agent. "
                        "Summarize search snippets into concise bullets about trends, "
                        "vocabulary, and likely hashtags for sentiment analysis. "
                        "Keep output short and plain text."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Topic: {topic}\n\n"
                        "Search snippets (JSON):\n" + "\n\n".join(snippet_payloads)
                    )
                ),
            ]
            response = self._llm_adapter.invoke_messages(
                summary_messages,
                call_kind="planner_web_context_summary",
            )
            content = response.content if hasattr(response, "content") else response
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)
            return str(content)
        except Exception as exc:
            self._log.warning(
                "Web context gathering failed: %s",
                exc,
                action="plan_web_context",
                reason=type(exc).__name__,
            )
            return ""

    @staticmethod
    def _extract_web_context_queries(raw_text: str, topic: str) -> list[str]:
        """Extract query phrases robustly from LLM text.

        Prevents accidental token splitting (for example "Here are useful...")
        from becoming junk one-word search queries.
        """
        raw = str(raw_text or "").strip()
        if not raw:
            return [topic]

        # Prefer phrase separators; never split on plain whitespace.
        candidates = [
            item.strip(" \t\n\r-•*\"'`")
            for item in re.split(r"[,;\n]+", raw)
            if item.strip()
        ]

        cleaned: list[str] = []
        rejected_singletons = {
            "here",
            "are",
            "useful",
            "search",
            "queries",
            "query",
        }
        for candidate in candidates:
            candidate = re.sub(r"^\d+[\.)]\s*", "", candidate).strip()
            if not candidate:
                continue
            lower = candidate.lower()
            if lower in rejected_singletons:
                continue
            if len(candidate) < 8:
                continue
            cleaned.append(candidate)

        deduped = list(dict.fromkeys(cleaned))
        if deduped:
            return deduped

        return [
            topic,
            f"{topic} public sentiment",
            f"{topic} Nepal reactions",
        ]

    # ── Demo mode ────────────────────────────────────────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert topic to a URL-safe slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        return slug[:60].strip("-")

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Return a static but realistic research plan for demo mode.

        The plan mirrors the exact ``ResearchPlan`` schema with the
        topic name injected into keywords, hashtags, and queries.
        """
        topic = message.strip()
        slug = self._slugify(topic)
        tag = slug.replace("-", "")

        plan = ResearchPlan(
            topic_summary=f"Sentiment analysis research plan for: {topic}",
            keywords=[
                topic,
                f"{topic} opinion",
                f"{topic} sentiment",
                f"{topic} debate",
                f"{topic} controversy",
                f"{topic} support",
                f"{topic} criticism",
                f"{topic} public opinion",
                f"{topic} social media",
                f"{topic} news",
                f"why {topic}",
                f"{topic} impact",
                f"{topic} reaction",
            ],
            hashtags=[
                f"#{tag}",
                f"#{slug}",
                f"#{tag}opinion",
                f"#{tag}debate",
                f"#{tag}news",
                f"#{tag}sentiment",
                f"#{tag}analysis",
                f"#{tag}reaction",
                f"#{tag}trending",
                f"#{tag}discussion",
            ],
            platforms=[
                PlatformStrategy(
                    name="reddit",
                    priority="high",
                    reason=f"Large discussion threads and diverse opinions on {topic}",
                ),
                PlatformStrategy(
                    name="twitter",
                    priority="high",
                    reason="Real-time public opinion, trending discussions, and hashtag tracking",
                ),
                PlatformStrategy(
                    name="news",
                    priority="medium",
                    reason="Editorial perspectives, fact-based reporting, and expert commentary",
                ),
                PlatformStrategy(
                    name="facebook",
                    priority="medium",
                    reason="Community groups, public page discussions, and longer-form reactions",
                ),
                PlatformStrategy(
                    name="youtube",
                    priority="low",
                    reason="Comment sections on related video content and creator opinions",
                ),
            ],
            search_queries=[
                f"{topic} sentiment",
                f"{topic} public opinion",
                f"site:reddit.com {topic}",
                f"site:twitter.com {topic}",
                f"{topic} news analysis",
                f"{topic} debate",
                f'"{topic}" reaction OR response',
            ],
            estimated_volume=(
                f"Expected 500-2000 posts across platforms for '{topic}'. "
                f"Recommended sample: 500 for statistical significance."
            ),
            stop_condition=(
                "After 500 relevant posts collected, or when 3 consecutive "
                "searches yield <10% new unique results."
            ),
            reasoning=(
                f"[DEMO] Static research plan for '{topic}'. "
                f"In production, the LLM generates a tailored strategy "
                f"with topic-specific nuances."
            ),
        )

        output = plan.model_dump_json(indent=2)
        self._log.success(
            "Demo plan generated  keywords=%d  queries=%d",
            len(plan.keywords),
            len(plan.search_queries),
            action="demo_plan",
            meta={"topic": topic, "demo": True},
        )
        return {
            "messages": [],
            "output": output,
            "plan": plan,
        }
