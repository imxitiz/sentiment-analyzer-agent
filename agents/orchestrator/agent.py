"""Orchestrator agent — the central coordinator of the pipeline.

The orchestrator receives a topic from the user, optionally clarifies it,
delegates to sub-agents (planner, searcher, scraper, …), and synthesises
results.  Sub-agents are exposed as tools so the LLM decides when to
delegate.

**Demo mode**: When ``llm_provider="dummy"``, the orchestrator runs the
full pipeline with static data — each sub-agent is invoked (also in demo
mode) and results are formatted into a cohesive summary.  The output
matches the production format exactly.

Usage::

    from agents.orchestrator import OrchestratorAgent
    from agents.planner import PlannerAgent

    planner = PlannerAgent(llm_provider="google")
    orchestrator = OrchestratorAgent(
        sub_agents=[planner],
        llm_provider="google",
        model="gemini-2.5-pro",
    )

    result = orchestrator.invoke("Nepal elections 2026")
    print(result["output"])

    # Demo mode:
    orchestrator = OrchestratorAgent(llm_provider="dummy")
    result = orchestrator.invoke("Tesla stock")
"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents._registry import register_agent
from agents.services import (
    bootstrap_topic,
    record_orchestrator_event,
    update_topic_run,
)


@register_agent
class OrchestratorAgent(BaseAgent):
    """Main orchestrator — coordinates all analysis sub-agents.

    Accepts a list of sub-agents at init.  Each sub-agent is wrapped as
    a tool via ``agent.as_tool()`` so the orchestrator LLM can decide
    when and how to delegate.
    """

    _name = "orchestrator"
    _description = (
        "Main orchestrator that coordinates the full sentiment analysis "
        "pipeline: clarification, planning, search, scraping, cleaning, "
        "and analysis."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-pro"

    def __init__(
        self,
        sub_agents: list[BaseAgent] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialise the orchestrator.

        Args:
            sub_agents: List of sub-agent instances.  Each is auto-wrapped
                as a tool.  If ``None``, a default PlannerAgent is created.
            **kwargs: Forwarded to ``BaseAgent.__init__``.
        """
        if sub_agents is None:
            from agents.harvester.agent import HarvesterAgent
            from agents.planner.agent import PlannerAgent
            from agents.scraper.agent import ScraperAgent
            forwarded = {
                k: v for k, v in kwargs.items()
                if k in ("llm_provider",)
            }
            sub_agents = [
                PlannerAgent(**forwarded),
                HarvesterAgent(**forwarded),
                ScraperAgent(**forwarded),
            ]

        self._sub_agents = sub_agents
        super().__init__(**kwargs)

    def _register_tools(self) -> list:
        """Sub-agent tools + built-in interaction tools."""
        tools = []

        # Wrap each sub-agent as a tool
        for agent in self._sub_agents:
            tools.append(agent.as_tool())

        # Built-in tools
        from agents.tools.human import ask_human
        from agents.tools.browser import (
            camoufox_click_browser,
            camoufox_close_all_browser_sessions,
            camoufox_close_browser_session,
            camoufox_evaluate_browser,
            camoufox_extract_links_browser,
            camoufox_extract_text_browser,
            camoufox_list_browser_sessions,
            camoufox_navigate_browser,
            camoufox_open_browser,
            camoufox_type_browser,
        )

        tools.append(ask_human)
        tools.extend(
            [
                camoufox_open_browser,
                camoufox_navigate_browser,
                camoufox_click_browser,
                camoufox_type_browser,
                camoufox_extract_text_browser,
                camoufox_extract_links_browser,
                camoufox_evaluate_browser,
                camoufox_list_browser_sessions,
                camoufox_close_browser_session,
                camoufox_close_all_browser_sessions,
            ]
        )

        return tools

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Bootstrap topic DB + orchestrator DB before running pipeline."""
        topic = message.strip()
        run = bootstrap_topic(topic)
        run_id = run["run_id"]
        update_topic_run(
            run_id,
            status="running",
            active_agent=self._name,
            meta={"mode": self.mode},
        )

        try:
            result = super().invoke(message, **kwargs)
            update_topic_run(
                run_id,
                status="completed",
                active_agent=self._name,
            )
            record_orchestrator_event(
                run_id,
                event_type="pipeline_complete",
                agent=self._name,
                status="completed",
                message="Orchestrator completed successfully",
            )
            return result
        except Exception as exc:
            update_topic_run(
                run_id,
                status="failed",
                active_agent=self._name,
                error=str(exc),
            )
            record_orchestrator_event(
                run_id,
                event_type="pipeline_error",
                agent=self._name,
                status="failed",
                message=str(exc),
            )
            raise

    # ── Demo mode ────────────────────────────────────────────────────

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Run the full pipeline in demo mode with static data.

        Each sub-agent is invoked (also in demo mode).  Their outputs
        are assembled into a formatted summary that mirrors the
        production orchestrator output.
        """
        topic = message.strip()
        self._log.info(
            "Demo orchestration  topic=%s", topic,
            action="demo_orchestrate",
        )

        # Phase 1: Assess topic clarity (demo: always clear)
        sections = [
            "# Sentiment Analysis Pipeline\n",
            f"**Topic**: {topic}\n",
            "**Mode**: Demo (static data)\n",
            "---\n",
            "## 1. Topic Assessment\n",
            f"The topic **\"{topic}\"** is clear and specific enough to "
            f"proceed directly without clarification.\n",
        ]

        # Phase 2: Delegate to sub-agents
        sub_results: dict[str, dict] = {}
        for agent in self._sub_agents:
            self._log.info(
                "Delegating to %s", agent.name, action="demo_delegate",
            )
            result = agent.invoke(topic)
            sub_results[agent.name] = result

        # Phase 3: Format planner output (if present)
        if "planner" in sub_results:
            planner_result = sub_results["planner"]
            plan = planner_result.get("plan")

            sections.append("## 2. Research Plan\n")

            if plan:
                sections.append(f"**Summary**: {plan.topic_summary}\n")

                sections.append("### Keywords\n")
                for kw in plan.keywords:
                    sections.append(f"- {kw}")
                sections.append("")

                sections.append("### Hashtags\n")
                sections.append(", ".join(plan.hashtags) + "\n")

                sections.append("### Platform Strategy\n")
                for p in plan.platforms:
                    sections.append(
                        f"- **{p.name}** ({p.priority}): {p.reason}"
                    )
                sections.append("")

                sections.append("### Search Queries\n")
                for i, q in enumerate(plan.search_queries, 1):
                    sections.append(f"{i}. `{q}`")
                sections.append("")

                sections.append("### Data Volume\n")
                sections.append(f"{plan.estimated_volume}\n")

                sections.append("### Stop Condition\n")
                sections.append(f"{plan.stop_condition}\n")
            else:
                # Fallback: raw output
                sections.append(f"```\n{planner_result['output']}\n```\n")

        # Phase 4: Any other sub-agent outputs
        for name, result in sub_results.items():
            if name == "planner":
                continue
            sections.append(f"## {name.title()} Output\n")
            sections.append(result["output"] + "\n")

        # Phase 5: Next steps
        sections.extend(
            [
                "---\n",
                "## Next Steps\n",
                "1. **Clean**: Deduplicate, filter spam, normalise text",
                "2. **Analyse**: Run sentiment model on cleaned data",
                "3. **Visualise**: Push results to dashboard\n",
                "*[DEMO MODE] This is a static demonstration run. "
                "Use a real LLM provider (gemini/openai/ollama) for "
                "production analysis.*",
            ]
        )

        output = "\n".join(sections)
        self._log.success(
            "Demo orchestration complete",
            action="demo_orchestrate",
            meta={"topic": topic, "sub_agents": list(sub_results.keys())},
        )
        return {"messages": [], "output": output}
