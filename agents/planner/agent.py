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
from typing import Any

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents._registry import register_agent
from Logging import get_logger

logger = get_logger("agents.planner")


# ── Structured output schema ─────────────────────────────────────────

class PlatformStrategy(BaseModel):
    """A platform to search and why."""

    name: str = Field(description="Platform name (e.g. reddit, twitter, facebook)")
    priority: str = Field(description="high, medium, or low")
    reason: str = Field(description="Why this platform matters for this topic")


class ResearchPlan(BaseModel):
    """Structured output from the planner agent."""

    topic_summary: str = Field(
        description="One-line summary of the research topic",
    )
    keywords: list[str] = Field(
        description="Search keywords to find relevant content (10-20)",
    )
    hashtags: list[str] = Field(
        description="Social media hashtags for this topic (10-15)",
    )
    platforms: list[PlatformStrategy] = Field(
        description="Platforms to search with priority and reasoning",
    )
    search_queries: list[str] = Field(
        description="Ready-to-use search queries (5-10)",
    )
    estimated_volume: str = Field(
        description="Expected data volume and recommended sample size",
    )
    stop_condition: str = Field(
        description="When to stop collecting data",
    )
    reasoning: str = Field(
        description="Brief explanation of the overall strategy",
    )


# ── Agent ─────────────────────────────────────────────────────────────

@register_agent
class PlannerAgent(BaseAgent):
    """Research planner — generates keywords, hashtags, and search strategy.

    Runs in direct mode (no tools).  Uses structured output when the LLM
    supports it, falls back to plain text otherwise.
    """

    _name = "planner"
    _description = (
        "Generate a comprehensive research plan for sentiment analysis on "
        "a given topic.  Returns keywords, hashtags, platform strategies, "
        "and ready-to-use search queries as structured JSON."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Generate a research plan for the given topic.

        Attempts structured output first; falls back to plain text if the
        LLM doesn't support ``with_structured_output``.  In demo mode,
        returns a static plan immediately.

        Returns:
            Dict with ``output`` (JSON string), ``messages``, and
            optionally ``plan`` (``ResearchPlan`` instance).
        """
        self._log.info(
            "Planning for topic  len=%d", len(message),
            action="plan", meta={"topic_preview": message[:100]},
        )

        # Demo mode — skip LLM entirely
        if self._demo:
            return self._demo_invoke(message, **kwargs)

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=f"Create a research plan for: {message}"),
        ]

        # Try structured output first
        try:
            plan = self._invoke_structured(messages)
            output = plan.model_dump_json(indent=2)
            self._log.success(
                "Plan generated (structured)  keywords=%d  queries=%d",
                len(plan.keywords), len(plan.search_queries),
                action="plan",
                meta={
                    "keyword_count": len(plan.keywords),
                    "hashtag_count": len(plan.hashtags),
                    "platform_count": len(plan.platforms),
                    "query_count": len(plan.search_queries),
                },
            )
            return {
                "messages": messages,
                "output": output,
                "plan": plan,
            }

        except Exception as exc:
            self._log.warning(
                "Structured output failed, falling back to text: %s", exc,
                action="plan_fallback",
            )

        # Fallback: plain text response
        result = self._invoke_direct(message, **kwargs)
        self._log.success("Plan generated (text fallback)", action="plan")
        return result

    def _invoke_structured(self, messages: list) -> ResearchPlan:
        """Call LLM with structured output binding."""
        structured_llm = self._llm_adapter.chat_model.with_structured_output(
            ResearchPlan,
        )
        result = structured_llm.invoke(messages)
        if isinstance(result, ResearchPlan):
            return result
        # Handle dict response from some providers
        return ResearchPlan.model_validate(result)

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
            len(plan.keywords), len(plan.search_queries),
            action="demo_plan",
            meta={"topic": topic, "demo": True},
        )
        return {
            "messages": [],
            "output": output,
            "plan": plan,
        }
