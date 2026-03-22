"""
SentimentAnalyzer – The single entry point for every sentiment analysis in this project.

Instead of importing ``transformers`` or other sentiment libraries directly,
**always** go through this module::

    from SentimentAnalyzer import get_sentiment_analyzer, analyze_sentiment

Quick-start
-----------

    # Simple sentiment analysis
    analyzer = get_sentiment_analyzer()                    # default model
    result = analyzer.analyze("I love this product!")      # → SentimentResult
    print(f"Score: {result.score:.3f}, Label: {result.label}")

    # Get score only (0→1 continuous)
    score = analyzer.get_score("This is amazing!")         # → 0.92

    # Batch analysis
    results = analyzer.analyze_batch(["Great!", "Terrible!", "Okay"])

    # Pick a specific model
    analyzer = get_sentiment_analyzer(model="cardiffnlp/twitter-roberta-base-sentiment-latest")

    # Use dummy adapter for testing (no dependencies)
    analyzer = get_sentiment_analyzer("dummy")

Available providers
-------------------
    • ``huggingface`` – HuggingFace Transformers (default)
    • ``dummy`` – Zero-dependency testing stub

Architecture
------------
    SentimentAnalyzer uses an adapter pattern similar to BaseLLM:
    - ``BaseSentimentAdapter`` – Abstract base class
    - ``HuggingFaceAdapter`` – HuggingFace Transformers implementation
    - ``DummySentimentAdapter`` – Testing stub

    Sentiment scores are continuous (0→1) where:
    - 0.0 = very negative
    - 0.5 = neutral
    - 1.0 = very positive
"""

from __future__ import annotations

from typing import Any, Optional

from Logging import get_logger

from .adapter import BaseSentimentAdapter, SentimentResult
from ._registry import (
    SENTIMENT_MODELS,
    resolve_provider,
    models_for,
    default_model,
    all_models,
)

logger = get_logger("SentimentAnalyzer")


# =====================================================================
# DUMMY ADAPTER  (always available, zero-dependency)
# =====================================================================


class DummySentimentAdapter(BaseSentimentAdapter):
    """Deterministic, zero-dependency adapter for development / testing."""

    _provider = "dummy"
    _default_model = "dummy-model"
    _registry_models = ("dummy-model",)

    def _build_model(self) -> None:  # noqa: D102
        # No real model – self._pipeline stays None
        pass

    def _predict(self, text: str) -> dict[str, Any]:
        """Deterministic sentiment prediction for testing.

        Returns a score based on simple keyword matching:
        - Positive words → high score (0.7-0.9)
        - Negative words → low score (0.1-0.3)
        - Neutral → 0.5
        """
        text_lower = text.lower()

        # Positive keywords
        positive_words = [
            "love",
            "great",
            "amazing",
            "excellent",
            "good",
            "wonderful",
            "fantastic",
            "awesome",
            "happy",
            "best",
            "perfect",
            "beautiful",
            "brilliant",
            "outstanding",
            "superb",
            "delightful",
            "joy",
        ]

        # Negative keywords
        negative_words = [
            "hate",
            "terrible",
            "awful",
            "bad",
            "worst",
            "horrible",
            "disgusting",
            "poor",
            "disappointing",
            "sad",
            "angry",
            "ugly",
            "boring",
            "annoying",
            "frustrating",
            "useless",
            "broken",
        ]

        # Count matches
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        # Calculate score
        if positive_count > negative_count:
            score = 0.7 + (positive_count * 0.05)
            label = "positive"
        elif negative_count > positive_count:
            score = 0.3 - (negative_count * 0.05)
            label = "negative"
        else:
            score = 0.5
            label = "neutral"

        # Clamp to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        return {
            "score": score,
            "label": label,
            "confidence": 0.8,  # Dummy confidence
            "raw": {
                "text": text,
                "positive_count": positive_count,
                "negative_count": negative_count,
            },
        }

    def _predict_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Batch prediction for testing."""
        return [self._predict(text) for text in texts]


# =====================================================================
# FACTORY
# =====================================================================


def get_sentiment_analyzer(
    provider: str = "huggingface",
    model: Optional[str] = None,
    *,
    device: str | None = None,
    batch_size: int = 8,
    **kwargs: Any,
) -> BaseSentimentAdapter:
    """Create a sentiment analyzer for *provider* and *model*.

    This is the **only** function the rest of the codebase needs.

    Parameters
    ----------
    provider:
        ``"huggingface"`` | ``"dummy"``
        (plus aliases like ``"hf"``).
    model:
        Model name.  ``None`` → provider default.
    device:
        Device to use ("cpu", "cuda", "mps"). Defaults to auto-detection.
    batch_size:
        Batch size for batch predictions. Defaults to 8.
    **kwargs:
        Any extra keyword arguments forwarded to the provider adapter.

    Returns
    -------
    BaseSentimentAdapter
        Ready-to-use adapter instance.

    Examples
    --------
    >>> analyzer = get_sentiment_analyzer()
    >>> analyzer = get_sentiment_analyzer("huggingface", model="cardiffnlp/twitter-roberta-base-sentiment-latest")
    >>> analyzer = get_sentiment_analyzer("dummy")
    """
    # Handle dummy first (no dependency needed)
    if provider.lower() == "dummy":
        logger.info("Creating DummySentimentAdapter (no model calls)")
        return DummySentimentAdapter()

    canonical = resolve_provider(provider)
    model = model or default_model(canonical)

    logger.info(
        "Creating sentiment analyzer  provider=%s  model=%s  device=%s  batch_size=%d",
        canonical,
        model,
        device or "auto",
        batch_size,
    )

    if canonical == "huggingface":
        from .huggingface_adapter import HuggingFaceAdapter

        return HuggingFaceAdapter(
            model=model,
            device=device,
            batch_size=batch_size,
            **kwargs,
        )

    # Should never reach here thanks to resolve_provider, but just in case…
    raise ValueError(f"No adapter implemented for provider {canonical!r}")


# =====================================================================
# CONVENIENCE HELPERS
# =====================================================================


def analyze_sentiment(
    text: str,
    provider: str = "huggingface",
    model: Optional[str] = None,
    **kwargs: Any,
) -> SentimentResult:
    """Analyze sentiment of a single text (convenience function).

    This is a shortcut for ``get_sentiment_analyzer(provider, model).analyze(text)``.

    Parameters
    ----------
    text : str
        The text to analyze.
    provider : str
        Sentiment provider ("huggingface" or "dummy").
    model : str, optional
        Model name. Defaults to provider default.
    **kwargs
        Extra arguments passed to the adapter.

    Returns
    -------
    SentimentResult
        Sentiment analysis result.

    Examples
    --------
    >>> result = analyze_sentiment("I love this!")
    >>> print(f"Score: {result.score:.3f}, Label: {result.label}")
    """
    analyzer = get_sentiment_analyzer(provider, model, **kwargs)
    return analyzer.analyze(text)


# =====================================================================
# SELF-TEST
# =====================================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("SentimentAnalyzer self-test")
    logger.info("=" * 60)

    logger.info("\nAvailable models: %s", all_models())

    logger.info("\n── 1) DummySentimentAdapter (always works) ──")
    d = get_sentiment_analyzer("dummy")
    logger.info("  %r", d)
    result = d.analyze("I love this product!")
    logger.info("  → Score: %.3f, Label: %s", result.score, result.label)

    logger.info("\n── 2) HuggingFace (default model) ──")
    try:
        h = get_sentiment_analyzer()
        logger.info("  %r", h)
        result = h.analyze("This is amazing!")
        logger.info("  → Score: %.3f, Label: %s", result.score, result.label)
    except Exception as e:
        logger.warning("  HuggingFace not available: %s", e)

    logger.info("\n── 3) Batch analysis ──")
    try:
        h = get_sentiment_analyzer()
        results = h.analyze_batch(["Great!", "Terrible!", "Okay"])
        for r in results:
            logger.info("  → Score: %.3f, Label: %s", r.score, r.label)
    except Exception as e:
        logger.warning("  Batch analysis failed: %s", e)

    logger.info("\n── 4) Convenience function ──")
    try:
        result = analyze_sentiment("This is wonderful!")
        logger.info("  → Score: %.3f, Label: %s", result.score, result.label)
    except Exception as e:
        logger.warning("  Convenience function failed: %s", e)

    logger.info("\nDone.")
