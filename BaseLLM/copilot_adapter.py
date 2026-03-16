"""GitHub Copilot adapter – wraps ``langchain-copilot``.

Install:  ``pip install langchain-copilot``

Usage::

    from BaseLLM import get_llm

    llm = get_llm("copilot", model="gpt-4o")
    llm.generate("Explain AI in one sentence.")
    llm.chat_model   # raw LangChain ChatModel for agents / chains
"""

from __future__ import annotations

from typing import Any, Optional

from .adapter import BaseLLMAdapter
from ._registry import COPILOT_MODELS, COPILOT_DEFAULT


class CopilotAdapter(BaseLLMAdapter):
    """LLM adapter for GitHub Copilot via ``langchain-copilot``."""

    _provider = "copilot"
    _default_model = COPILOT_DEFAULT
    _registry_models = COPILOT_MODELS
    _supports_structured_output = False

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        cli_path: Optional[str] = None,
        cli_url: Optional[str] = None,
        streaming: bool = False,
        **kwargs: Any,
    ) -> None:
        self._cli_path = cli_path
        self._cli_url = cli_url
        self._streaming = streaming
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _build_llm(self) -> None:
        try:
            from langchain_copilot import CopilotChatModel
        except ImportError as exc:
            raise ImportError(
                "langchain-copilot is required. Install with: pip install langchain-copilot",
                "LangChain integration for GitHub Copilot SDK - Use GitHub Copilot models in your LangChain applications.",
                "https://github.com/imxitiz/github-copilot-langchain",
            ) from exc

        self._llm = CopilotChatModel(
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            streaming=self._streaming,
            cli_path=self._cli_path,
            cli_url=self._cli_url,
            **self._extra,
        )
