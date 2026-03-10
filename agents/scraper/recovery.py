"""Recovery sub-agent used by the scraper on extraction failures."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.scraper.models import RecoveryPlan


class ScraperRecoveryAgent(BaseAgent):
    """AI-assisted fallback selector for scraper backend failures."""

    _name = "scraper_recovery"
    _description = (
        "Analyse scraper failures, decide whether a URL should be retried, "
        "and pick the next backend to try when recovery is possible."
    )
    _system_prompt_file = "recovery.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        if self._demo:
            plan = self._demo_plan(message)
            return {
                "messages": [],
                "output": plan.model_dump_json(indent=2),
                "recovery_plan": plan,
            }

        structured_llm = self._llm_adapter.chat_model.with_structured_output(RecoveryPlan)
        result = structured_llm.invoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=message),
            ]
        )
        plan = result if isinstance(result, RecoveryPlan) else RecoveryPlan.model_validate(result)
        return {
            "messages": [],
            "output": plan.model_dump_json(indent=2),
            "recovery_plan": plan,
        }

    def _demo_plan(self, message: str) -> RecoveryPlan:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            payload = {}
        remaining = payload.get("remaining_backends") or []
        error_text = str(payload.get("error") or "").lower()
        http_status = payload.get("http_status")

        if http_status in {404, 410} or "not found" in error_text:
            return RecoveryPlan(
                should_retry=False,
                recommended_backend=None,
                mark_terminal=True,
                reason="The URL appears to be gone, so further retries are low value.",
            )

        if remaining:
            return RecoveryPlan(
                should_retry=True,
                recommended_backend=str(remaining[0]),
                mark_terminal=False,
                reason="Try the next available backend before marking the URL as failed.",
            )

        return RecoveryPlan(
            should_retry=False,
            recommended_backend=None,
            mark_terminal=True,
            reason="No backends remain, so this target should be marked failed.",
        )

