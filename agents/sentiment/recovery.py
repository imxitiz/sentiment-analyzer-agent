"""Recovery sub-agent for sentiment analysis fallback and QA review.

This sub-agent handles cases where:
1. The primary sentiment model fails (error, timeout, etc.)
2. Confidence is below threshold (needs retry or LLM fallback)
3. Edge cases that the deterministic model can't handle well
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.sentiment.models import SentimentRecoveryPlan


class SentimentRecoveryAgent(BaseAgent):
    """LLM-only fallback used when primary sentiment analysis fails or is uncertain.

    This agent:
    1. Receives failed/low-confidence sentiment analysis cases
    2. Uses LLM to produce a sentiment score and label
    3. Provides reasoning for the decision
    4. Suggests plan adjustments for future cases
    """

    _name = "sentiment_recovery"
    _description = (
        "Analyze failed or low-confidence sentiment cases using LLM fallback. "
        "Produces reliable sentiment scores with explanations."
    )
    _system_prompt_file = "recovery.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke the recovery agent for a failed sentiment analysis.

        Parameters
        ----------
        message : str
            JSON payload with document text, original score, failure reason.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Contains 'recovery_plan' (SentimentRecoveryPlan) and 'output' (JSON string).
        """
        if self._demo:
            plan = self._demo_plan(message)
            return {
                "messages": [],
                "output": plan.model_dump_json(indent=2),
                "recovery_plan": plan,
            }

        structured_llm = self._llm_adapter.chat_model.with_structured_output(
            SentimentRecoveryPlan
        )
        result = structured_llm.invoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=message),
            ]
        )
        plan = (
            result
            if isinstance(result, SentimentRecoveryPlan)
            else SentimentRecoveryPlan.model_validate(result)
        )
        return {
            "messages": [],
            "output": plan.model_dump_json(indent=2),
            "recovery_plan": plan,
        }

    def _demo_plan(self, message: str) -> SentimentRecoveryPlan:
        """Generate a demo recovery plan for testing without LLM.

        Parameters
        ----------
        message : str
            JSON payload with document and failure info.

        Returns
        -------
        SentimentRecoveryPlan
            Demo recovery plan.
        """
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            payload = {}

        # Extract available info
        text = str(payload.get("text") or payload.get("document_text") or "").strip()
        # Note: original_score and failure_reason available for future use in demo

        # If we have text, do basic keyword-based demo analysis
        if len(text) > 10:
            text_lower = text.lower()
            positive_words = ["good", "great", "excellent", "love", "best", "amazing", "happy"]
            negative_words = ["bad", "terrible", "worst", "hate", "awful", "sad", "angry"]

            pos_count = sum(1 for w in positive_words if w in text_lower)
            neg_count = sum(1 for w in negative_words if w in text_lower)

            if pos_count > neg_count:
                score = 0.75
                label = "positive"
            elif neg_count > pos_count:
                score = 0.25
                label = "negative"
            else:
                score = 0.5
                label = "neutral"

            return SentimentRecoveryPlan(
                status="accepted",
                score=score,
                label=label,
                confidence=0.6,
                reason="Demo mode: keyword-based fallback analysis.",
                alternative_models_tried=["keyword_fallback"],
                recommended_plan_adjustments={},
            )

        # No text available
        return SentimentRecoveryPlan(
            status="rejected",
            score=0.5,
            label="neutral",
            confidence=0.0,
            reason="No text available for analysis in demo mode.",
            alternative_models_tried=[],
            recommended_plan_adjustments={},
        )
