"""Ollama adapter – wraps ``langchain-ollama``.

Install:  ``pip install langchain-ollama``
Server:   ``ollama serve`` must be running (default http://localhost:11434)

Usage::

    from BaseLLM import get_llm

    llm = get_llm("ollama", model="llama3.2")
    llm.generate("Explain AI in one sentence.")
    llm.chat_model   # raw LangChain ChatModel for agents / chains
"""

from __future__ import annotations

from typing import Any

from .adapter import BaseLLMAdapter
from ._registry import OLLAMA_MODELS, OLLAMA_DEFAULT


class OllamaAdapter(BaseLLMAdapter):
    """LLM adapter for Ollama models via ``langchain-ollama``."""

    _provider = "ollama"
    _default_model = OLLAMA_DEFAULT
    _registry_models = OLLAMA_MODELS

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        self._base_url = base_url
        # Pass remaining to the base (which calls _build_llm)
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _build_llm(self) -> None:
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ImportError(
                "langchain-ollama is required. "
                "Install with:  pip install langchain-ollama"
            ) from exc

        self._llm = ChatOllama(
            model=self._model,
            temperature=self._temperature,
            num_predict=self._max_tokens,
            base_url=self._base_url,
            **self._extra,
        )
