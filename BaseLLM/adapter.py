"""Abstract base adapter for all LLM providers.

Every provider adapter (Gemini, Ollama, OpenAI, …) must inherit from
``BaseLLMAdapter`` and implement a small set of abstract methods.  The
base class then provides the **full public API** (sync generate, async
generate, structured logging, error handling) so individual adapters
stay tiny and consistent.

Contract
--------
    Subclasses **must** implement:
        ``_provider``         – class-level str
        ``_default_model``    – class-level str
        ``_registry_models``  – class-level tuple
        ``_build_llm()``      – create the LangChain ``BaseChatModel``

    Everything else (``generate``, ``agenerate``, ``chat_model``,
    ``models``, logging, error handling) is handled here.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from Logging import get_logger, context_logger


class BaseLLMAdapter(ABC):
    """Abstract base class every LLM adapter must implement.

    Subclasses only need to set three class attributes and implement
    ``_build_llm()``.  The rest is inherited.
    """

    # ── Subclass must override these ─────────────────────────────────
    _provider: str = ""  # e.g. "google"
    _default_model: str = ""  # e.g. "gemini-2.5-flash-lite"
    _registry_models: tuple[str, ...] = ()
    _supports_structured_output: bool = True

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> None:
        self._model = model or self._default_model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra: dict[str, Any] = kwargs
        self._llm: BaseChatModel | None = None

        # Each adapter instance gets a context-bound logger
        self._log = context_logger(
            f"BaseLLM.{self._provider}",
            actor=f"{self._provider}_adapter",
            phase="LLM",
        )

        self._log.info(
            "Initialising %s  model=%s  temperature=%.2f  max_tokens=%d",
            self.__class__.__name__,
            self._model,
            self._temperature,
            self._max_tokens,
            action="adapter_init",
            meta={
                "provider": self._provider,
                "model": self._model,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "extra_keys": list(kwargs.keys()),
            },
        )
        self._build_llm()

    # ── Abstract: subclass must implement ─────────────────────────────

    @abstractmethod
    def _build_llm(self) -> None:
        """Create ``self._llm`` – the LangChain ``BaseChatModel`` instance.

        Must set ``self._llm``.  Should raise ``ImportError`` with a
        helpful message if the provider package is missing.
        """
        ...

    # ── Identity (concrete – derived from class attrs) ────────────────

    @property
    def provider(self) -> str:
        """Canonical provider key."""
        return self._provider

    @property
    def model_name(self) -> str:
        """Currently-selected model name."""
        return self._model

    @property
    def supports_structured_output(self) -> bool:
        """Whether this provider should use native structured output paths."""
        return self._supports_structured_output

    # ── Core capabilities (concrete) ──────────────────────────────────

    @property
    def chat_model(self) -> BaseChatModel:
        """Return the underlying LangChain ``BaseChatModel``.

        Use this directly in LangGraph nodes, chains, agent executors::

            workflow.add_node("analyst", make_node(llm.chat_model))
        """
        if self._llm is None:
            self._build_llm()
        assert self._llm is not None
        return self._llm

    def models(self) -> list[str]:
        """Return the list of model names from the registry for this provider."""
        return list(self._registry_models)

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> str:
        """Send *prompt* and return the model's text response (synchronous).

        All logging, timing, and error handling is done here so that
        individual adapters don't have to repeat it.
        """
        self._log.info(
            "generate called  prompt_len=%d  max_tokens=%d",
            len(prompt),
            max_tokens,
            action="generate",
            meta={"prompt_len": len(prompt), "max_tokens": max_tokens},
        )

        messages = [HumanMessage(content=prompt)]
        t0 = time.perf_counter()
        try:
            response = self.chat_model.invoke(messages, **kwargs)
            text = self._extract_text(response)
            elapsed = time.perf_counter() - t0

            self._log.success(
                "generate OK  response_len=%d  elapsed=%.3fs",
                len(text),
                elapsed,
                action="generate",
                meta={
                    "response_len": len(text),
                    "elapsed_s": round(elapsed, 3),
                },
            )
            return text

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._log.error(
                "generate FAILED  error=%s  elapsed=%.3fs",
                exc,
                elapsed,
                action="generate",
                reason=type(exc).__name__,
                meta={"error": str(exc), "elapsed_s": round(elapsed, 3)},
                exc_info=True,
            )
            raise RuntimeError(
                f"{self.__class__.__name__} generation failed ({self._model}): {exc}"
            ) from exc

    async def agenerate(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> str:
        """Async version of ``generate``.

        Uses the LangChain model's native ``ainvoke`` so it doesn't block
        the event loop – critical for concurrent agent pipelines.
        """
        self._log.info(
            "agenerate called  prompt_len=%d  max_tokens=%d",
            len(prompt),
            max_tokens,
            action="agenerate",
            meta={"prompt_len": len(prompt), "max_tokens": max_tokens},
        )

        messages = [HumanMessage(content=prompt)]
        t0 = time.perf_counter()
        try:
            response = await self.chat_model.ainvoke(messages, **kwargs)
            text = self._extract_text(response)
            elapsed = time.perf_counter() - t0

            self._log.success(
                "agenerate OK  response_len=%d  elapsed=%.3fs",
                len(text),
                elapsed,
                action="agenerate",
                meta={
                    "response_len": len(text),
                    "elapsed_s": round(elapsed, 3),
                },
            )
            return text

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._log.error(
                "agenerate FAILED  error=%s  elapsed=%.3fs",
                exc,
                elapsed,
                action="agenerate",
                reason=type(exc).__name__,
                meta={"error": str(exc), "elapsed_s": round(elapsed, 3)},
                exc_info=True,
            )
            raise RuntimeError(
                f"{self.__class__.__name__} async generation failed "
                f"({self._model}): {exc}"
            ) from exc

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the text content from a LangChain response object."""
        content = response.content if hasattr(response, "content") else response
        # Some Ollama models return list content
        if isinstance(content, list):
            return str(content[0]) if content else ""
        return str(content)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} provider={self._provider!r} "
            f"model={self._model!r}>"
        )


# ── Backward-compat alias ────────────────────────────────────────────
LLMAdapter = BaseLLMAdapter
