"""Planner sub-agent for adaptive cleaner runtime tuning."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.cleaner.models import CleanerPlan
from utils.structured_output import invoke_model_with_structured_recovery


class CleanerPlannerAgent(BaseAgent):
    """Generate per-topic cleaning plans from sampled raw document previews."""

    _name = "cleaner_planner"
    _description = (
        "Analyze sampled raw scraped documents and generate adaptive cleaning "
        "configuration overrides for better extraction, normalization, and filtering."
    )
    _system_prompt_file = "planner.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        if self._demo:
            plan = self._demo_plan(message)
            return {
                "messages": [],
                "output": plan.model_dump_json(indent=2),
                "plan": plan,
            }

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=message),
        ]

        fallback_result: dict[str, Any] = {"messages": messages, "output": ""}

        def _fallback_text_getter() -> str:
            nonlocal fallback_result
            fallback_result = self._invoke_direct(message, **kwargs)
            return str(fallback_result.get("output", ""))

        recovery = invoke_model_with_structured_recovery(
            llm_adapter=self._llm_adapter,
            schema_model=CleanerPlan,
            messages=messages,
            supports_structured=self._llm_adapter.supports_structured_output,
            fallback_text_getter=_fallback_text_getter,
            repair_prompt_builder=self._build_repair_prompt,
            repair_max_tokens=2048,
        )

        if recovery.value is None:
            raise RuntimeError(
                "Cleaner planner structured recovery failed"
                f" (structured_error={recovery.structured_error},"
                f" parse_error={recovery.parse_error},"
                f" repair_error={recovery.repair_error})"
            )

        plan = recovery.value
        return {
            "messages": fallback_result.get("messages", messages),
            "output": recovery.output_text,
            "plan": plan,
        }

    def _build_repair_prompt(self, raw_text: str) -> str:
        return (
            "Convert the following cleaner planning output into strict JSON with "
            "only these keys: strategy_summary, min_clean_chars, max_clean_chars, "
            "min_alpha_ratio, max_url_ratio, max_symbol_ratio, enable_fuzzy_dedupe, "
            "fuzzy_dedupe_threshold, preferred_languages, reject_non_preferred_languages, "
            "custom_noise_patterns, extra_remove_regexes, replacement_rules, confidence. "
            "Return JSON object only. No markdown, no extra text.\n\n"
            "Raw output:\n"
            f"{raw_text}"
        )

    def _demo_plan(self, message: str) -> CleanerPlan:
        try:
            payload = json.loads(message)
            topic = str(payload.get("topic") or "")
        except json.JSONDecodeError:
            topic = ""
        return CleanerPlan(
            strategy_summary=(
                "Demo adaptive plan: preserve sentiment cues, keep punctuation removal "
                "on, and tighten link-heavy junk rejection."
            ),
            min_clean_chars=30,
            max_clean_chars=12000,
            min_alpha_ratio=0.35,
            max_url_ratio=0.3,
            max_symbol_ratio=0.35,
            enable_fuzzy_dedupe=True,
            fuzzy_dedupe_threshold=93.0,
            preferred_languages=["en"],
            reject_non_preferred_languages=False,
            custom_noise_patterns=[
                r"cookie(s)?\\s+policy",
                r"subscribe\\s+for\\s+more",
                r"sponsored\\s+content",
            ],
            extra_remove_regexes=[],
            replacement_rules={},
            confidence=0.62 if topic else 0.55,
        )
