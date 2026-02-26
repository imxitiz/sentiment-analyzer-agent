"""
BaseLLM – One place for all LLM access in this project.
========================================================

Every time you need an LLM – whether for a LangGraph agent, a chain, or a
simple prompt → response call – import from here::

    from BaseLLM import get_llm, models_for, all_providers

Quick-start
-----------

    # Simple generation
    llm = get_llm("google")                       # default Gemini model
    llm.generate("Explain AI in one sentence.")

    # Pick a specific model
    llm = get_llm("openai", model="gpt-4o")

    # Get the raw LangChain ChatModel for a LangGraph node / chain
    chat = llm.chat_model

    # Assign different models to different agents
    orchestrator = get_llm("google",  model="gemini-2.5-pro")
    clarifier    = get_llm("openai",  model="gpt-4o")
    analyzer     = get_llm("ollama",  model="llama3.2")

Available providers
-------------------
    • ``google``  (aliases: ``gemini``, ``genai``, ``google_genai``)
    • ``ollama``
    • ``openai``  (aliases: ``chatgpt``, ``gpt``)
    • ``dummy``   – zero-dependency testing stub

Registry helpers
----------------
    • ``all_providers()``   → ``["google", "ollama", "openai"]``
    • ``models_for("openai")``  → ``["gpt-4o", "gpt-4o-mini", …]``
"""

from __future__ import annotations

# ── Abstract base class (for type hints) ─────────────────────────────
from .adapter import BaseLLMAdapter, LLMAdapter  # LLMAdapter = compat alias

# ── Model registry ───────────────────────────────────────────────────
from ._registry import (
    GEMINI_MODELS,
    OLLAMA_MODELS,
    OPENAI_MODELS,
    PROVIDERS,
    PROVIDER_DEFAULTS,
    models_for,
    default_model,
    all_providers,
    resolve_provider,
)

# ── Factory & helpers ────────────────────────────────────────────────
from .main import (
    get_llm,
    get_gemini_llm,
    get_ollama_llm,
    get_openai_llm,
    DummyAdapter,
)

# ── Concrete adapters (import when you need explicit typing) ─────────
from .genai_adapter import GeminiAdapter, GenAIAdapter
from .ollama_adapter import OllamaAdapter
from .openai_adapter import OpenAIAdapter

__all__ = [
    # Abstract base
    "BaseLLMAdapter",
    "LLMAdapter",
    # Factory (the main thing you need)
    "get_llm",
    "get_gemini_llm",
    "get_ollama_llm",
    "get_openai_llm",
    # Dummy
    "DummyAdapter",
    # Concrete adapters
    "GeminiAdapter",
    "GenAIAdapter",
    "OllamaAdapter",
    "OpenAIAdapter",
    # Registry
    "GEMINI_MODELS",
    "OLLAMA_MODELS",
    "OPENAI_MODELS",
    "PROVIDERS",
    "PROVIDER_DEFAULTS",
    "models_for",
    "default_model",
    "all_providers",
    "resolve_provider",
]
