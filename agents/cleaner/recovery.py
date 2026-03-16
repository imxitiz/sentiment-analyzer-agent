"""Recovery sub-agent for cleaner fallback and sampled QA review."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.cleaner.models import CleanerRecoveryPlan
from utils.structured_output import invoke_model_with_structured_recovery


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

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=message),
        ]

        def _fallback_text_getter() -> str:
            response = self._llm_adapter.chat_model.invoke(messages)
            content = response.content if hasattr(response, "content") else response
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)
            return str(content)

        recovery = invoke_model_with_structured_recovery(
            llm_adapter=self._llm_adapter,
            schema_model=CleanerRecoveryPlan,
            messages=messages,
            supports_structured=self._llm_adapter.supports_structured_output,
            fallback_text_getter=_fallback_text_getter,
            repair_prompt_builder=self._build_repair_prompt,
            max_reasks=2,
            repair_max_tokens=1024,
        )
        plan = (
            recovery.value if recovery.value is not None else self._demo_plan(message)
        )
        return {
            "messages": messages,
            "output": plan.model_dump_json(indent=2),
            "recovery_plan": plan,
        }

    @staticmethod
    def _build_repair_prompt(raw_text: str) -> str:
        return (
            "Convert the following cleaner recovery output into strict JSON with only these keys: "
            "status, cleaned_text, reason, quality_score. "
            "Return JSON object only, no markdown.\n\n"
            "Raw output:\n"
            f"{raw_text}"
        )

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
