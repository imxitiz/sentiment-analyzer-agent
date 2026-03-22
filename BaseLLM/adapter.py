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

import json
import re
import time
import uuid
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

    def invoke_messages(
        self,
        messages: list[Any],
        *,
        call_kind: str = "chat_invoke",
        **kwargs: Any,
    ) -> Any:
        """Invoke chat model with trace persistence and timing metadata."""
        trace_id = str(uuid.uuid4())
        started = time.perf_counter()
        input_messages = self._serialize_messages(messages)
        input_text = "\n".join(
            str(m.get("content", "")) for m in input_messages if m.get("content")
        )
        try:
            response = self.chat_model.invoke(messages, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            output_text = self._extract_text(response)
            self._record_trace(
                request_id=trace_id,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=input_text,
                output_text=output_text,
                latency_ms=elapsed_ms,
            )
            return response
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self._record_trace(
                request_id=trace_id,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=input_text,
                error_text=str(exc),
                latency_ms=elapsed_ms,
            )
            raise

    async def ainvoke_messages(
        self,
        messages: list[Any],
        *,
        call_kind: str = "chat_ainvoke",
        **kwargs: Any,
    ) -> Any:
        """Async invoke with trace persistence and timing metadata."""
        trace_id = str(uuid.uuid4())
        started = time.perf_counter()
        input_messages = self._serialize_messages(messages)
        input_text = "\n".join(
            str(m.get("content", "")) for m in input_messages if m.get("content")
        )
        try:
            response = await self.chat_model.ainvoke(messages, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            output_text = self._extract_text(response)
            self._record_trace(
                request_id=trace_id,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=input_text,
                output_text=output_text,
                latency_ms=elapsed_ms,
            )
            return response
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self._record_trace(
                request_id=trace_id,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=input_text,
                error_text=str(exc),
                latency_ms=elapsed_ms,
            )
            raise

    def invoke_structured(
        self,
        messages: list[Any],
        *,
        schema_model: Any,
        call_kind: str = "structured_invoke",
        structured_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke with structured-output binding and persist trace rows."""
        trace_id = str(uuid.uuid4())
        started = time.perf_counter()
        input_messages = self._serialize_messages(messages)
        input_text = "\n".join(
            str(m.get("content", "")) for m in input_messages if m.get("content")
        )
        effective_structured_kwargs = (
            dict(structured_kwargs)
            if structured_kwargs is not None
            else self._default_structured_kwargs()
        )
        try:
            used_include_raw = False
            if effective_structured_kwargs:
                try:
                    structured_llm = self.chat_model.with_structured_output(
                        schema_model,
                        include_raw=True,
                        **effective_structured_kwargs,
                    )
                    used_include_raw = True
                except TypeError:
                    try:
                        structured_llm = self.chat_model.with_structured_output(
                            schema_model,
                            include_raw=True,
                        )
                        used_include_raw = True
                    except TypeError:
                        structured_llm = self.chat_model.with_structured_output(
                            schema_model,
                            **effective_structured_kwargs,
                        )
            else:
                try:
                    structured_llm = self.chat_model.with_structured_output(
                        schema_model,
                        include_raw=True,
                    )
                    used_include_raw = True
                except TypeError:
                    structured_llm = self.chat_model.with_structured_output(
                        schema_model
                    )

            result = structured_llm.invoke(messages, **kwargs)
            trace_meta: dict[str, Any] = {
                "schema": getattr(schema_model, "__name__", str(schema_model)),
                "structured_kwargs": effective_structured_kwargs,
                "include_raw": used_include_raw,
            }
            parsed_result = result

            if isinstance(result, dict) and (
                "parsed" in result or "raw" in result or "parsing_error" in result
            ):
                parsed_result = result.get("parsed")
                raw_message = result.get("raw")
                parsing_error = result.get("parsing_error")

                if raw_message is not None:
                    raw_text = self._extract_text(raw_message)
                    if raw_text:
                        trace_meta["raw_preview"] = raw_text[:2000]

                if parsing_error:
                    raise RuntimeError(
                        "Structured parsing failed: "
                        f"{parsing_error}. Raw output: {trace_meta.get('raw_preview', '')}"
                    )

            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if hasattr(parsed_result, "model_dump_json"):
                output_text = parsed_result.model_dump_json(indent=2)
            else:
                output_text = json.dumps(parsed_result, ensure_ascii=False, default=str)
            self._record_trace(
                request_id=trace_id,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=input_text,
                output_text=output_text,
                latency_ms=elapsed_ms,
                meta=trace_meta,
            )
            return parsed_result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            error_text = str(exc)
            extracted_output = self._extract_completion_from_error(error_text)
            self._record_trace(
                request_id=trace_id,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=input_text,
                output_text=extracted_output,
                error_text=error_text,
                latency_ms=elapsed_ms,
                meta={
                    "schema": getattr(schema_model, "__name__", str(schema_model)),
                    "structured_kwargs": effective_structured_kwargs,
                },
            )
            raise

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
            response = self.invoke_messages(
                messages,
                call_kind="generate_invoke",
                **kwargs,
            )
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
            response = await self.ainvoke_messages(
                messages,
                call_kind="agenerate_invoke",
                **kwargs,
            )
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

    @staticmethod
    def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for msg in messages:
            role = getattr(msg, "type", None) or getattr(msg, "role", None) or "message"
            content = getattr(msg, "content", msg)
            if isinstance(content, list):
                content_text = "\n".join(str(item) for item in content)
            else:
                content_text = str(content)
            serialized.append({"role": str(role), "content": content_text})
        return serialized

    def _default_structured_kwargs(self) -> dict[str, Any]:
        """Return provider-tuned defaults for native structured output.

        These defaults reduce schema drift without requiring each agent to pass
        provider-specific kwargs explicitly.
        """
        provider = str(self._provider or "").lower()
        if provider == "ollama":
            return {"method": "json_schema"}
        if provider in {"google", "openai"}:
            return {"method": "json_schema", "strict": True}
        return {}

    @staticmethod
    def _extract_completion_from_error(error_text: str) -> str | None:
        """Try to recover raw completion text from provider parse errors.

        Some LangChain/provider exceptions include the model completion inline
        (for example: ``Failed to parse ... from completion {...}``).
        """
        if not error_text:
            return None

        patterns = (
            r"from completion\s+([\s\S]+)$",
            r"completion:\s*([\s\S]+)$",
            r"raw output:\s*([\s\S]+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, error_text, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).strip()
            if candidate:
                return candidate

        # Last resort: capture the largest balanced JSON object in the error text.
        start = error_text.find("{")
        end = error_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return error_text[start : end + 1]
        return None

    def _record_trace(
        self,
        *,
        request_id: str,
        call_kind: str,
        input_messages: list[dict[str, Any]] | None = None,
        input_text: str | None = None,
        output_text: str | None = None,
        error_text: str | None = None,
        latency_ms: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        try:
            from agents.services import (
                get_llm_trace_context,
                save_llm_trace,
            )
            from agents.services.planner_checkpoint import init_topic_db

            topic, source_agent = get_llm_trace_context()
            if not topic:
                return

            init_topic_db(topic)

            save_llm_trace(
                topic,
                provider=self._provider,
                model=self._model,
                call_kind=call_kind,
                input_messages=input_messages,
                input_text=(input_text or "")[:50000],
                output_text=(output_text or "")[:50000] if output_text else None,
                error_text=(error_text or "")[:5000] if error_text else None,
                latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
                source_agent=source_agent,
                request_id=request_id,
                meta=meta,
            )
        except Exception as exc:
            self._log.warning(
                "LLM trace persistence failed: %s",
                exc,
                action="llm_trace_warn",
            )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} provider={self._provider!r} "
            f"model={self._model!r}>"
        )


# ── Backward-compat alias ────────────────────────────────────────────
LLMAdapter = BaseLLMAdapter
