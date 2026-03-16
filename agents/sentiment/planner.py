"""Planner sub-agent for adaptive sentiment analysis configuration.

This sub-agent analyzes sample cleaned documents and generates a SentimentPlan
that optimizes the sentiment analysis for the specific topic and document types.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.sentiment.models import SentimentPlan
from utils.structured_output import invoke_model_with_structured_recovery


class SentimentPlannerAgent(BaseAgent):
    """Generate per-topic sentiment analysis plans from sampled document previews.

    The planner analyzes:
    - Topic content and domain (e.g., political, product reviews, social media)
    - Sample document characteristics (length, language, platform)
    - Common sentiment patterns in the domain

    And produces:
    - Optimal model selection
    - Threshold tuning
    - Topic context configuration
    - Custom keyword lists
    """

    _name = "sentiment_planner"
    _description = (
        "Analyze sampled cleaned documents and generate adaptive sentiment "
        "configuration for better accuracy on specific topics and domains."
    )
    _system_prompt_file = "planner.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke the planner to generate a sentiment plan.

        Parameters
        ----------
        message : str
            JSON payload with topic and sample documents.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Contains 'plan' (SentimentPlan) and 'output' (JSON string).
        """
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
            schema_model=SentimentPlan,
            messages=messages,
            supports_structured=self._llm_adapter.supports_structured_output,
            fallback_text_getter=_fallback_text_getter,
            repair_prompt_builder=self._build_repair_prompt,
            repair_max_tokens=2048,
        )

        if recovery.value is None:
            raise RuntimeError(
                "Sentiment planner structured recovery failed"
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
            "Convert the following sentiment planning output into strict JSON with only these keys: "
            "strategy_summary, model, positive_threshold, negative_threshold, include_topic_context, "
            "topic_context_weight, min_confidence_threshold, auto_retry_low_confidence, "
            "custom_keywords_positive, custom_keywords_negative, language_override, confidence. "
            "Return JSON object only. No markdown, no extra text.\n\n"
            "Raw output:\n"
            f"{raw_text}"
        )

    def _demo_plan(self, message: str) -> SentimentPlan:
        """Generate a demo plan for testing without LLM.

        Parameters
        ----------
        message : str
            JSON payload or topic string.

        Returns
        -------
        SentimentPlan
            Demo sentiment plan.
        """
        try:
            payload = json.loads(message)
            topic = str(payload.get("topic") or "")
        except json.JSONDecodeError:
            topic = message.strip()

        # Demo plan with reasonable defaults
        return SentimentPlan(
            strategy_summary=(
                "Demo adaptive plan: use default model with standard thresholds. "
                "For social media content, consider lowering confidence threshold."
            ),
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            positive_threshold=0.6,
            negative_threshold=0.4,
            include_topic_context=True,
            topic_context_weight=0.3,
            min_confidence_threshold=0.5,
            auto_retry_low_confidence=True,
            custom_keywords_positive=[],
            custom_keywords_negative=[],
            language_override=None,
            confidence=0.7 if topic else 0.6,
        )
