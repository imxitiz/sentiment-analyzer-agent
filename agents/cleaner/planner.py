"""Planner sub-agent for adaptive cleaner runtime tuning."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.cleaner.models import CleanerPlan


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

        structured_llm = self._llm_adapter.chat_model.with_structured_output(
            CleanerPlan
        )
        result = structured_llm.invoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=message),
            ]
        )
        plan = (
            result
            if isinstance(result, CleanerPlan)
            else CleanerPlan.model_validate(result)
        )
        return {
            "messages": [],
            "output": plan.model_dump_json(indent=2),
            "plan": plan,
        }

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
