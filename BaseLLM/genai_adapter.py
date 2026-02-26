"""Google Gemini adapter – wraps ``langchain-google-genai``.

Install:  ``pip install langchain-google-genai``
Env var:  ``GOOGLE_API_KEY``

Usage::

    from BaseLLM import get_llm

    llm = get_llm("google", model="gemini-2.5-flash")
    llm.generate("Explain AI in one sentence.")
    llm.chat_model   # raw LangChain ChatModel for agents / chains
"""

from __future__ import annotations

from typing import Any

from .adapter import BaseLLMAdapter
from ._registry import GEMINI_MODELS, GEMINI_DEFAULT


class GeminiAdapter(BaseLLMAdapter):
    """LLM adapter for Google Gemini via ``langchain-google-genai``."""

    _provider = "google"
    _default_model = GEMINI_DEFAULT
    _registry_models = GEMINI_MODELS

    def _build_llm(self) -> None:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ImportError(
                "langchain-google-genai is required. "
                "Install with:  pip install langchain-google-genai"
            ) from exc

        self._llm = ChatGoogleGenerativeAI(
            model=self._model,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
            **self._extra,
        )


# Backward-compat alias
GenAIAdapter = GeminiAdapter
