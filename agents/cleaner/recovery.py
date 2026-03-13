"""Recovery sub-agent for cleaner fallback and sampled QA review."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.cleaner.models import CleanerRecoveryPlan


class CleanerRecoveryAgent(BaseAgent):
    """LLM-only fallback used when deterministic cleaning fails or is uncertain."""

    _name = "cleaner_recovery"
    _description = (
        "Review deterministic cleaning output, recover failed cases, and return "
        "a quality decision with improved cleaned text when needed."
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

        structured_llm = self._llm_adapter.chat_model.with_structured_output(CleanerRecoveryPlan)
        result = structured_llm.invoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=message),
            ]
        )
        plan = result if isinstance(result, CleanerRecoveryPlan) else CleanerRecoveryPlan.model_validate(result)
        return {
            "messages": [],
            "output": plan.model_dump_json(indent=2),
            "recovery_plan": plan,
        }

    def _demo_plan(self, message: str) -> CleanerRecoveryPlan:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            payload = {}

        cleaned = str(payload.get("deterministic_cleaned_text") or "").strip()
        if len(cleaned) >= 30:
            return CleanerRecoveryPlan(
                status="accepted",
                cleaned_text=cleaned,
                reason="Deterministic output is sufficient in demo mode.",
                quality_score=0.8,
            )

        raw_preview = str(payload.get("raw_text_preview") or "").strip()
        recovered = raw_preview[:500]
        if recovered:
            return CleanerRecoveryPlan(
                status="accepted",
                cleaned_text=recovered,
                reason="Fallback used raw preview because deterministic text was empty.",
                quality_score=0.6,
            )

        return CleanerRecoveryPlan(
            status="rejected",
            cleaned_text="",
            reason="No text was available to recover in demo mode.",
            quality_score=0.0,
        )
