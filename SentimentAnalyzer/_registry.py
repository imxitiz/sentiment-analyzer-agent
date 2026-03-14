"""Sentiment model registry – single source of truth for all sentiment models.

This module defines:
- Available sentiment models and their metadata
- Provider-to-model mapping
- Helper functions to query the registry

Usage
-----
    from SentimentAnalyzer._registry import (
        SENTIMENT_MODELS,
        MODEL_INFO,
        models_for,
        default_model,
        all_models,
        get_model_info,
    )

    all_models()                    # → ["distilroberta-base", "cardiffnlp/twitter-roberta-base-sentiment-latest", ...]
    models_for("huggingface")       # → ["distilroberta-base", "cardiffnlp/twitter-roberta-base-sentiment-latest", ...]
    default_model("huggingface")    # → "distilroberta-base"
    get_model_info("distilroberta-base")  # → {"name": ..., "provider": ..., "description": ...}
"""

from __future__ import annotations

from typing import Any

# ── Model definitions ────────────────────────────────────────────────

SENTIMENT_MODELS: dict[str, list[str]] = {
    "huggingface": [
        "distilroberta-base",
        "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "nlptown/bert-base-multilingual-uncased-sentiment",
    ],
    "dummy": ["dummy-model"],
}

MODEL_INFO: dict[str, dict[str, Any]] = {
    "distilroberta-base": {
        "name": "distilroberta-base",
        "provider": "huggingface",
        "description": "Fast, lightweight sentiment model based on DistilRoBERTa",
        "default": True,
        "labels": ["negative", "neutral", "positive"],
        "score_range": [0.0, 1.0],
    },
    "cardiffnlp/twitter-roberta-base-sentiment-latest": {
        "name": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "provider": "huggingface",
        "description": "Twitter-optimized sentiment model from Cardiff NLP",
        "default": False,
        "labels": ["negative", "neutral", "positive"],
        "score_range": [0.0, 1.0],
    },
    "nlptown/bert-base-multilingual-uncased-sentiment": {
        "name": "nlptown/bert-base-multilingual-uncased-sentiment",
        "provider": "huggingface",
        "description": "Multilingual sentiment model (1-5 stars)",
        "default": False,
        "labels": ["1 star", "2 stars", "3 stars", "4 stars", "5 stars"],
        "score_range": [1.0, 5.0],  # Will be normalized to [0.0, 1.0]
    },
    "dummy-model": {
        "name": "dummy-model",
        "provider": "dummy",
        "description": "Zero-dependency testing stub",
        "default": True,
        "labels": ["negative", "neutral", "positive"],
        "score_range": [0.0, 1.0],
    },
}

# ── Provider aliases ─────────────────────────────────────────────────

PROVIDER_ALIASES: dict[str, str] = {
    "hf": "huggingface",
    "hugging": "huggingface",
    "transformers": "huggingface",
}


# ── Helper functions ─────────────────────────────────────────────────


def all_models() -> list[str]:
    """Return list of all available model names."""
    models = []
    for provider_models in SENTIMENT_MODELS.values():
        models.extend(provider_models)
    return models


def models_for(provider: str) -> list[str]:
    """Return list of model names for a given provider.

    Parameters
    ----------
    provider : str
        Provider name (e.g., "huggingface", "dummy").

    Returns
    -------
    list[str]
        List of model names for the provider.
    """
    canonical = resolve_provider(provider)
    return SENTIMENT_MODELS.get(canonical, [])


def default_model(provider: str) -> str:
    """Return the default model name for a given provider.

    Parameters
    ----------
    provider : str
        Provider name (e.g., "huggingface", "dummy").

    Returns
    -------
    str
        Default model name.

    Raises
    ------
    ValueError
        If no default model is found for the provider.
    """
    canonical = resolve_provider(provider)
    provider_models = SENTIMENT_MODELS.get(canonical, [])

    for model_name in provider_models:
        info = MODEL_INFO.get(model_name, {})
        if info.get("default", False):
            return model_name

    # Fallback to first model if no default is marked
    if provider_models:
        return provider_models[0]

    raise ValueError(f"No models found for provider {canonical!r}")


def get_model_info(model_name: str) -> dict[str, Any]:
    """Get metadata for a specific model.

    Parameters
    ----------
    model_name : str
        Model name (e.g., "distilroberta-base").

    Returns
    -------
    dict[str, Any]
        Model metadata including name, provider, description, labels, etc.

    Raises
    ------
    ValueError
        If the model is not found in the registry.
    """
    if model_name not in MODEL_INFO:
        raise ValueError(
            f"Model {model_name!r} not found in registry. "
            f"Available models: {all_models()}"
        )
    return MODEL_INFO[model_name]


def resolve_provider(provider: str) -> str:
    """Resolve provider name to canonical form.

    Parameters
    ----------
    provider : str
        Provider name or alias (e.g., "hf", "hugging", "huggingface").

    Returns
    -------
    str
        Canonical provider name.

    Raises
    ------
    ValueError
        If the provider is not recognized.
    """
    canonical = PROVIDER_ALIASES.get(provider.lower(), provider.lower())

    if canonical not in SENTIMENT_MODELS:
        available = list(SENTIMENT_MODELS.keys())
        raise ValueError(
            f"Unknown sentiment provider {provider!r}. "
            f"Available providers: {available}"
        )

    return canonical
