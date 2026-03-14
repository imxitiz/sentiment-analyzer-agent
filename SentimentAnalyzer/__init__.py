"""
SentimentAnalyzer – One place for all sentiment analysis in this project.
=========================================================================

Every time you need sentiment analysis – whether for the agent pipeline, batch
processing, or simple text scoring – import from here::

    from SentimentAnalyzer import get_sentiment_analyzer, analyze_sentiment

Quick-start
-----------

    # Simple sentiment analysis
    analyzer = get_sentiment_analyzer()                    # default model
    result = analyzer.analyze("I love this product!")      # → {'score': 0.95, 'label': 'positive'}

    # Pick a specific model
    analyzer = get_sentiment_analyzer(model="cardiffnlp/twitter-roberta-base-sentiment-latest")

    # Batch analysis
    results = analyzer.analyze_batch(["Great!", "Terrible!", "Okay"])

    # Get sentiment score only (0→1 continuous)
    score = analyzer.get_score("This is amazing!")         # → 0.92

Available models
----------------
    • ``distilroberta-base`` – Fast, lightweight (default)
    • ``cardiffnlp/twitter-roberta-base-sentiment-latest`` – Twitter-optimized
    • ``nlptown/bert-base-multilingual-uncased-sentiment`` – Multilingual (1-5 stars)
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

# ── Abstract base class (for type hints) ─────────────────────────────
from .adapter import BaseSentimentAdapter

# ── Model registry ───────────────────────────────────────────────────
from ._registry import (
    SENTIMENT_MODELS,
    MODEL_INFO,
    models_for,
    default_model,
    all_models,
    get_model_info,
)

# ── Factory & helpers ────────────────────────────────────────────────
from .main import (
    get_sentiment_analyzer,
    analyze_sentiment,
    DummySentimentAdapter,
)

# ── Concrete adapters (import when you need explicit typing) ─────────
from .huggingface_adapter import HuggingFaceAdapter

__all__ = [
    # Abstract base
    "BaseSentimentAdapter",
    # Factory (the main thing you need)
    "get_sentiment_analyzer",
    "analyze_sentiment",
    # Dummy
    "DummySentimentAdapter",
    # Concrete adapters
    "HuggingFaceAdapter",
    # Registry
    "SENTIMENT_MODELS",
    "MODEL_INFO",
    "models_for",
    "default_model",
    "all_models",
    "get_model_info",
]
