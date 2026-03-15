"""Sentiment package exports.

Lazy-load ``SentimentAnalyzerAgent`` to avoid circular imports when service
modules import ``agents.sentiment.models``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .agent import SentimentAnalyzerAgent

__all__ = ["SentimentAnalyzerAgent"]


def __getattr__(name: str):
	if name == "SentimentAnalyzerAgent":
		from .agent import SentimentAnalyzerAgent

		return SentimentAnalyzerAgent
	raise AttributeError(name)
