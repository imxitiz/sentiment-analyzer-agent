"""Single source of truth for every model the project knows about.

Add or remove models here and the rest of the codebase picks them up
automatically.  Each provider maps to a tuple of model name strings.

Usage::

    from BaseLLM._registry import PROVIDERS, models_for

    models_for("google")   # → ["gemini-2.5-flash", …]
    models_for("openai")   # → ["gpt-4o", …]
"""

from __future__ import annotations

from typing import Sequence

# ── Google Gemini ────────────────────────────────────────────────────────
GEMINI_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
)

GEMINI_DEFAULT: str = "gemini-2.5-flash-lite"

# ── Ollama (local) ──────────────────────────────────────────────────────
OLLAMA_MODELS: tuple[str, ...] = (
    "llama3.2",
    "llama3.1",
    "llama3",
    "llama2",
    "qwen2.5",
    "qwen2",
    "mistral",
    "mixtral",
    "codellama",
    "deepseek-coder",
    "deepseek-r1",
    "phi3",
    "gemma2",
    "gemma",
)

OLLAMA_DEFAULT: str = "llama3.2"

# ── OpenAI / ChatGPT ────────────────────────────────────────────────────
OPENAI_MODELS: tuple[str, ...] = (
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3-mini",
)

OPENAI_DEFAULT: str = "gpt-4o-mini"

# ── GitHub Copilot (langchain-copilot) ──────────────────────────────────
COPILOT_MODELS: tuple[str, ...] = (
    "gpt-4ogpt-4.1",
    "gpt-5-mini",
)

COPILOT_DEFAULT: str = "gpt-4.1"

# ── Provider → models mapping ───────────────────────────────────────────

PROVIDERS: dict[str, tuple[str, ...]] = {
    "google": GEMINI_MODELS,
    "ollama": OLLAMA_MODELS,
    "openai": OPENAI_MODELS,
    "copilot": COPILOT_MODELS,
}

PROVIDER_DEFAULTS: dict[str, str] = {
    "google": GEMINI_DEFAULT,
    "ollama": OLLAMA_DEFAULT,
    "openai": OPENAI_DEFAULT,
    "copilot": COPILOT_DEFAULT,
}

# Aliases → canonical provider key
_PROVIDER_ALIASES: dict[str, str] = {
    "google": "google",
    "google_genai": "google",
    "gemini": "google",
    "genai": "google",
    "ollama": "ollama",
    "openai": "openai",
    "chatgpt": "openai",
    "gpt": "openai",
    "copilot": "copilot",
    "github": "copilot",
}


def resolve_provider(name: str) -> str:
    """Resolve a provider alias to its canonical key.

    Raises ``ValueError`` for unknown providers.
    """
    canonical = _PROVIDER_ALIASES.get(name.lower())
    if canonical is None:
        known = ", ".join(sorted(_PROVIDER_ALIASES))
        raise ValueError(f"Unknown provider {name!r}. Known aliases: {known}")
    return canonical


def models_for(provider: str) -> list[str]:
    """Return the model list for *provider* (accepts aliases)."""
    return list(PROVIDERS.get(resolve_provider(provider), ()))


def default_model(provider: str) -> str:
    """Return the default model name for *provider*."""
    return PROVIDER_DEFAULTS[resolve_provider(provider)]


def all_providers() -> list[str]:
    """Return canonical provider keys."""
    return list(PROVIDERS)
