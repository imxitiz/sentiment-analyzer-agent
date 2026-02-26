"""OpenAI / ChatGPT adapter – wraps ``langchain-openai``.

Install:  ``pip install langchain-openai``
Env var:  ``OPENAI_API_KEY``

Usage::

    from BaseLLM import get_llm

    llm = get_llm("openai", model="gpt-4o-mini")
    llm.generate("Explain AI in one sentence.")
    llm.chat_model   # raw LangChain ChatModel for agents / chains
"""

from __future__ import annotations

from typing import Any, Optional

from .adapter import BaseLLMAdapter
from ._registry import OPENAI_MODELS, OPENAI_DEFAULT


class OpenAIAdapter(BaseLLMAdapter):
    """LLM adapter for OpenAI / ChatGPT via ``langchain-openai``."""

    _provider = "openai"
    _default_model = OPENAI_DEFAULT
    _registry_models = OPENAI_MODELS

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _build_llm(self) -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError(
                "langchain-openai is required. "
                "Install with:  pip install langchain-openai"
            ) from exc

        init_kwargs: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            **self._extra,
        }
        if self._api_key is not None:
            init_kwargs["api_key"] = self._api_key
        if self._base_url is not None:
            init_kwargs["base_url"] = self._base_url

        self._llm = ChatOpenAI(**init_kwargs)
