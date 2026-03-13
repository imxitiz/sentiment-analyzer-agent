"""
BaseLLM – The single entry point for every LLM interaction in this project.

Instead of importing ``langchain_google_genai``, ``langchain_ollama``, or
``langchain_openai`` directly, **always** go through this module::

    from BaseLLM import get_llm

    # ── Simple text generation ───────────────────────────────────────
    llm = get_llm("google", model="gemini-2.5-flash")
    print(llm.generate("Explain AI in one sentence."))

    # ── Per-agent model assignment (different model per agent) ───────
    orchestrator_llm = get_llm("google",  model="gemini-2.5-pro")
    clarifier_llm    = get_llm("openai",  model="gpt-4o")
    analyzer_llm     = get_llm("ollama",  model="llama3.2")
    reporter_llm     = get_llm("google",  model="gemini-2.5-flash-lite")

    # ── Use the raw LangChain ChatModel in LangGraph agents ─────────
    workflow.add_node("orchestrator", make_node(orchestrator_llm.chat_model))
    workflow.add_node("clarifier",    make_node(clarifier_llm.chat_model))

    # ── List available models ────────────────────────────────────────
    from BaseLLM import models_for, all_providers
    all_providers()        # → ["google", "ollama", "openai"]
    models_for("openai")   # → ["gpt-4o", "gpt-4o-mini", …]

Providers
---------
    google (aliases: gemini, genai, google_genai)
    ollama
    openai (aliases: chatgpt, gpt)
    dummy  – zero-dependency stub for tests
"""

from __future__ import annotations

from typing import Any, Optional

from Logging import get_logger

from .adapter import BaseLLMAdapter
from ._registry import (
    PROVIDERS,
    PROVIDER_DEFAULTS,
    GEMINI_MODELS,
    OLLAMA_MODELS,
    OPENAI_MODELS,
    resolve_provider,
    models_for,
    default_model,
    all_providers,
)

logger = get_logger("BaseLLM")


# =====================================================================
# DUMMY ADAPTER  (always available, zero-dependency)
# =====================================================================


class DummyAdapter(BaseLLMAdapter):
    """Deterministic, zero-dependency adapter for development / testing."""

    _provider = "dummy"
    _default_model = "dummy-model"
    _registry_models = ("dummy-model",)

    def _build_llm(self) -> None:  # noqa: D102
        # No real LLM – self._llm stays None
        pass

    @property
    def chat_model(self):  # type: ignore[override]
        """Dummy has no real chat model – raises if someone tries to use it."""
        raise NotImplementedError(
            "DummyAdapter does not provide a LangChain ChatModel. "
            "Switch to a real provider (google, ollama, openai) for agent use."
        )

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> str:  # noqa: D102
        snippet = prompt.strip().replace("\n", " ")[: max(40, max_tokens)]
        return f"[DUMMY-LLM] {snippet}"

    async def agenerate(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> str:  # noqa: D102
        return self.generate(prompt, max_tokens=max_tokens, **kwargs)


# =====================================================================
# FACTORY
# =====================================================================


def get_llm(
    provider: str = "google",
    model: Optional[str] = None,
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    **kwargs: Any,
) -> BaseLLMAdapter:
    """Create an LLM adapter for *provider* and *model*.

    This is the **only** function the rest of the codebase needs.

    Parameters
    ----------
    provider:
        ``"google"`` | ``"ollama"`` | ``"openai"`` | ``"dummy"``
        (plus aliases like ``"gemini"``, ``"chatgpt"``, ``"gpt"``).
    model:
        Model name.  ``None`` → provider default.
    temperature:
        Sampling temperature (0.0 – 2.0).
    max_tokens:
        Maximum tokens to generate.
    **kwargs:
        Any extra keyword arguments forwarded to the provider adapter
        (e.g. ``api_key``, ``base_url``).

    Returns
    -------
    BaseLLMAdapter
        Ready-to-use adapter instance.

    Examples
    --------
    >>> llm = get_llm("google")
    >>> llm = get_llm("openai", model="gpt-4o", temperature=0.0)
    >>> llm = get_llm("ollama", model="llama3.2")
    >>> llm = get_llm("dummy")
    """
    # Handle dummy first (no dependency needed)
    if provider.lower() == "dummy":
        logger.info("Creating DummyAdapter (no LLM calls)")
        return DummyAdapter()

    canonical = resolve_provider(provider)
    model = model or default_model(canonical)

    logger.info(
        "Creating LLM adapter  provider=%s  model=%s  temperature=%.2f  max_tokens=%d",
        canonical,
        model,
        temperature,
        max_tokens,
    )

    if canonical == "google":
        from .genai_adapter import GeminiAdapter

        return GeminiAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    if canonical == "ollama":
        from .ollama_adapter import OllamaAdapter

        return OllamaAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    if canonical == "openai":
        from .openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    # Should never reach here thanks to resolve_provider, but just in case…
    raise ValueError(f"No adapter implemented for provider {canonical!r}")


# =====================================================================
# CONVENIENCE HELPERS
# =====================================================================


def get_gemini_llm(model: str | None = None, **kwargs: Any) -> BaseLLMAdapter:
    """Shortcut: ``get_llm("google", model=…)``."""
    return get_llm("google", model=model, **kwargs)


def get_ollama_llm(model: str | None = None, **kwargs: Any) -> BaseLLMAdapter:
    """Shortcut: ``get_llm("ollama", model=…)``."""
    return get_llm("ollama", model=model, **kwargs)


def get_openai_llm(model: str | None = None, **kwargs: Any) -> BaseLLMAdapter:
    """Shortcut: ``get_llm("openai", model=…)``."""
    return get_llm("openai", model=model, **kwargs)


# =====================================================================
# SELF-TEST
# =====================================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("BaseLLM self-test")
    logger.info("=" * 60)

    logger.info("\nAvailable providers: %s", all_providers())
    for p in all_providers():
        logger.info("  %s models: %s", p, models_for(p))

    logger.info("\n── 1) DummyAdapter (always works) ──")
    d = get_llm("dummy")
    logger.info("  %r", d)
    logger.info("  → %s", d.generate("Say hi in one sentence."))

    logger.info("\n── 2) Google Gemini ──")
    try:
        g = get_llm("google")
        logger.info("  %r", g)
        logger.info("  → %s", g.generate("Explain AI in one sentence."))
    except Exception as e:
        logger.warning("  Gemini not available: %s", e)

    logger.info("\n── 3) Ollama ──")
    try:
        o = get_llm("ollama")
        logger.info("  %r", o)
        logger.info("  → %s", o.generate("Explain AI in one sentence."))
    except Exception as e:
        logger.warning("  Ollama not available: %s", e)

    logger.info("\n── 4) OpenAI / ChatGPT ──")
    try:
        c = get_llm("openai")
        logger.info("  %r", c)
        logger.info("  → %s", c.generate("Explain AI in one sentence."))
    except Exception as e:
        logger.warning("  OpenAI not available: %s", e)

    logger.info("\n── 5) Per-agent model demo ──")
    logger.info("  orchestrator → get_llm('google', model='gemini-2.5-pro')")
    logger.info("  clarifier    → get_llm('openai', model='gpt-4o')")
    logger.info("  analyzer     → get_llm('ollama', model='llama3.2')")
    logger.info("  (each agent gets its own independent adapter instance)")

    logger.info("\nDone.")
