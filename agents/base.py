"""Base agent abstraction for the sentiment analysis pipeline.

Every agent inherits from ``BaseAgent``.  Subclasses set a few class
attributes and optionally override ``_register_tools()``.  The base class
handles LLM initialization, prompt loading, graph building, execution,
and tool-wrapping.

Two execution modes:
    • **react** — has tools → LangGraph ReAct agent (tool-calling loop)
    • **direct** — no tools → single LLM call with system prompt

Pattern mirrors ``BaseLLM/adapter.py``: set class attrs, implement one
method, get the full public API for free.

Usage::

    from agents.base import BaseAgent
    from agents._registry import register_agent

    @register_agent
    class MyAgent(BaseAgent):
        _name = "my_agent"
        _description = "Does something useful"
        _system_prompt_file = "system.txt"

        def _register_tools(self) -> list:
            return [my_tool_function]
"""

from __future__ import annotations

import asyncio
import time
import inspect
from abc import ABC
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Callable, Generator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from BaseLLM import get_llm
from BaseLLM.adapter import BaseLLMAdapter
from Logging import context_logger
from env import config


class BaseAgent(ABC):
    """Abstract base class every agent must inherit from.

    Subclasses **must** set:
        ``_name``            – unique agent identifier (e.g. ``"orchestrator"``)
        ``_description``     – what this agent does (shown as tool description)

    Subclasses **may** set:
        ``_system_prompt_file`` – filename in agent's ``prompts/`` dir
        ``_llm_provider``       – default LLM provider for this agent
        ``_llm_model``          – default model name

    Subclasses **may** override:
        ``_register_tools()``   – return tools list (empty → direct mode)
        ``_demo_invoke()``      – custom demo-mode logic (static data)
        ``invoke()``            – custom execution logic

    **Demo mode**: When ``llm_provider="dummy"`` (or the ``--demo`` CLI
    flag is used), the agent skips the LLM entirely and returns static
    data via ``_demo_invoke()``.  The full pipeline still runs — only
    the data is synthetic.
    """

    # ── Subclass settings ────────────────────────────────────────────
    _name: str = ""
    _description: str = ""
    _system_prompt_file: str = "system.txt"
    _llm_provider: str = "google"
    _llm_model: str | None = None
    _timeout_seconds: int | None = None
    _max_retries: int | None = None
    _circuit_breaker_threshold: int | None = None
    _circuit_breaker_cooldown_seconds: int | None = None
    _mcp_enabled: bool = False
    _mcp_server_names: list[str] | None = None
    _mcp_strict: bool = False

    def __init__(
        self,
        llm_provider: str | None = None,
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_tools: list | None = None,
        mcp_enabled: bool | None = None,
        mcp_server_names: list[str] | None = None,
        mcp_strict: bool | None = None,
        system_prompt: str | None = None,
        **llm_kwargs: Any,
    ) -> None:
        """Initialise the agent.

        Args:
            llm_provider: Override the default LLM provider.
            model: Override the default model.
            temperature: LLM sampling temperature.
            max_tokens: Maximum tokens for LLM generation.
            extra_tools: Additional tools beyond ``_register_tools()``.
            mcp_enabled: Whether to load MCP tools for this agent.
            mcp_server_names: Optional subset of MCP server names to load.
            mcp_strict: If true, MCP load failures raise instead of warning.
            system_prompt: Override system prompt (skip file loading).
            **llm_kwargs: Forwarded to ``get_llm()``.
        """
        provider = llm_provider or self._llm_provider
        model_name = model or self._llm_model

        self._llm_adapter: BaseLLMAdapter = get_llm(
            provider,
            model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            **llm_kwargs,
        )
        self._extra_tools = extra_tools or []
        self._mcp_enabled = self._mcp_enabled if mcp_enabled is None else mcp_enabled
        self._mcp_server_names = (
            self._mcp_server_names if mcp_server_names is None else mcp_server_names
        )
        self._mcp_strict = self._mcp_strict if mcp_strict is None else mcp_strict
        self._system_prompt_override = system_prompt
        self._resolved_timeout_seconds = self._resolve_int_setting(
            key_name="TIMEOUT_SECONDS",
            explicit=self._timeout_seconds,
            default=300,
        )
        self._resolved_max_retries = self._resolve_int_setting(
            key_name="MAX_RETRIES",
            explicit=self._max_retries,
            default=1,
        )
        self._resolved_circuit_breaker_threshold = self._resolve_int_setting(
            key_name="CIRCUIT_BREAKER_THRESHOLD",
            explicit=self._circuit_breaker_threshold,
            default=3,
        )
        self._resolved_circuit_breaker_cooldown_seconds = self._resolve_int_setting(
            key_name="CIRCUIT_BREAKER_COOLDOWN_SECONDS",
            explicit=self._circuit_breaker_cooldown_seconds,
            default=600,
        )
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._log = context_logger(
            f"agents.{self._name}",
            actor=self._name,
            phase="AGENT",
        )

        # Resolve prompt
        self._system_prompt: str = self._resolve_system_prompt()

        # Demo mode: provider == "dummy" → skip graph, use static data
        self._demo: bool = self._llm_adapter._provider == "dummy"

        if self._demo:
            self._mode = "demo"
            self._graph = None
            all_tools: list = []
        else:
            all_tools = self._collect_tools()
            self._mode = "react" if all_tools else "direct"
            self._graph = None
            if self._mode == "react":
                self._graph = self._build_react_graph(
                    all_tools,
                    self._system_prompt,
                )

        self._log.info(
            "Agent ready  name=%s  mode=%s  tools=%d",
            self._name,
            self._mode,
            len(all_tools),
            action="agent_init",
            meta={
                "name": self._name,
                "mode": self._mode,
                "provider": provider,
                "model": model_name or "default",
                "tool_count": len(all_tools),
                "tool_names": [getattr(t, "name", str(t)) for t in all_tools],
                "demo": self._demo,
                "timeout_seconds": self._resolved_timeout_seconds,
                "max_retries": self._resolved_max_retries,
                "circuit_breaker_threshold": self._resolved_circuit_breaker_threshold,
                "circuit_breaker_cooldown_seconds": self._resolved_circuit_breaker_cooldown_seconds,
                "mcp_enabled": self._mcp_enabled,
                "mcp_servers": self._mcp_server_names or "all",
            },
        )

    # ── Tools ────────────────────────────────────────────────────────

    def _register_tools(self) -> list:
        """Return agent-specific tools.  Override in subclass.

        Return an empty list for direct-mode agents (no tool loop).
        """
        return []

    def _collect_tools(self) -> list:
        """Merge registered tools with extra tools passed at init."""
        tools = list(self._register_tools()) + list(self._extra_tools)
        if self._mcp_enabled:
            tools.extend(self._load_mcp_tools())
        return tools

    def _load_mcp_tools(self) -> list:
        """Load MCP tools if enabled."""
        try:
            from agents.tools.mcp import load_mcp_tools

            return load_mcp_tools(
                server_names=self._mcp_server_names,
                strict=self._mcp_strict,
                register=True,
            )
        except Exception as exc:
            self._log.warning(
                "MCP tools unavailable: %s",
                exc,
                action="mcp_load_failed",
            )
            if self._mcp_strict:
                raise
            return []

    # ── Prompt resolution ────────────────────────────────────────────

    def _resolve_system_prompt(self) -> str:
        """Load system prompt: override → agent-local file → fallback."""
        if self._system_prompt_override:
            return self._system_prompt_override

        if self._system_prompt_file:
            content = self._load_local_prompt(self._system_prompt_file)
            if content:
                return content

        return f"You are the {self._name} agent. {self._description}"

    def _load_local_prompt(self, filename: str) -> str | None:
        """Load a prompt file from this agent's ``prompts/`` directory."""
        agent_dir = Path(inspect.getfile(self.__class__)).resolve().parent
        path = agent_dir / "prompts" / filename
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return None

    def _get_prompt(self, name: str, **kwargs: Any) -> str:
        """Load a named prompt: agent-local first, then global.

        Args:
            name: Prompt name (without ``.txt``).
            **kwargs: ``str.format()`` placeholders.
        """
        content = self._load_local_prompt(f"{name}.txt")
        if content:
            if kwargs:
                try:
                    return content.format(**kwargs)
                except Exception:
                    return content
            return content

        # Fall back to global prompt manager
        from prompts import get_prompt

        return get_prompt(name, **kwargs)

    # ── Graph building ───────────────────────────────────────────────

    def _build_react_graph(
        self,
        tools: list,
        prompt: str,
    ) -> CompiledStateGraph:
        """Build a LangGraph agent with tools."""
        chat_model = self._llm_adapter.chat_model

        # Some LLM implementations (e.g. langchain-copilot) provide their own
        # tool binding mechanism. Use it if available so the model can drive
        # tool invocation natively.
        if hasattr(chat_model, "bind_tools") and callable(
            getattr(chat_model, "bind_tools")
        ):
            try:
                chat_model = chat_model.bind_tools(tools)
                tools = []
            except Exception as exc:
                self._log.warning(
                    "Tool binding failed (falling back to LangChain tool loop): %s",
                    exc,
                    action="bind_tools_failed",
                )

        # LangChain's type signatures expect a BaseChatModel or model name string.
        # Copilot's bind_tools returns a Runnable, which is compatible at runtime
        # but triggers type checkers. Cast to Any to keep typing clean.
        return create_agent(
            chat_model,  # type: ignore[arg-type]
            tools=tools,
            system_prompt=prompt,
            name=self._name,
        )

    # ── Execution ────────────────────────────────────────────────────

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Demo mode — return static placeholder response.

        Override in subclass for realistic demo data.  The default
        implementation returns a simple echo.

        Args:
            message: The user's input message / topic.

        Returns:
            Dict with ``messages`` (list) and ``output`` (str), same
            shape as ``invoke()``.
        """
        output = f"[DEMO:{self._name}] Processed topic: {message.strip()[:200]}"
        self._log.info(
            "demo invoke  agent=%s",
            self._name,
            action="demo_invoke",
        )
        return {"messages": [], "output": output}

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Run the agent synchronously.

        Returns:
            Dict with ``messages`` (list) and ``output`` (str).
        """
        self._log.info(
            "invoke  len=%d  mode=%s",
            len(message),
            self._mode,
            action="invoke",
        )
        self._checkpoint_topic_input(message)
        self._checkpoint_agent_status(message, status="working", mark_started=True)

        if self._demo:
            result = self._demo_invoke(message, **kwargs)
            self._checkpoint_artifact(
                topic=message,
                artifact_type="agent_output",
                value=result.get("output", ""),
                meta={"mode": "demo", "call": "invoke"},
            )
            self._checkpoint_agent_status(
                message,
                status="completed",
                retries=0,
                mark_completed=True,
            )
            return result

        return self._invoke_with_resilience(
            call_name="invoke",
            message=message,
            core_call=self._invoke_core,
            **kwargs,
        )

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Run the agent asynchronously."""
        self._log.info(
            "ainvoke  len=%d  mode=%s",
            len(message),
            self._mode,
            action="ainvoke",
        )
        self._checkpoint_topic_input(message)
        self._checkpoint_agent_status(message, status="working", mark_started=True)

        if self._demo:
            result = self._demo_invoke(message, **kwargs)
            self._checkpoint_artifact(
                topic=message,
                artifact_type="agent_output",
                value=result.get("output", ""),
                meta={"mode": "demo", "call": "ainvoke"},
            )
            self._checkpoint_agent_status(
                message,
                status="completed",
                retries=0,
                mark_completed=True,
            )
            return result

        return await self._ainvoke_with_resilience(
            call_name="ainvoke",
            message=message,
            core_call=self._ainvoke_core,
            **kwargs,
        )

    def stream(self, message: str, **kwargs: Any) -> Generator:
        """Stream agent execution steps."""
        self._checkpoint_topic_input(message)
        self._checkpoint_agent_status(message, status="working", mark_started=True)
        if self._demo:
            result = self._demo_invoke(message, **kwargs)
            self._checkpoint_artifact(
                topic=message,
                artifact_type="agent_output",
                value=result.get("output", ""),
                meta={"mode": "demo", "call": "stream"},
            )
            self._checkpoint_agent_status(
                message,
                status="completed",
                retries=0,
                mark_completed=True,
            )
            yield result
            return

        self._check_circuit_breaker()
        start = time.monotonic()
        if self._mode == "react" and self._graph:
            try:
                for step in self._graph.stream(
                    {"messages": [{"role": "user", "content": message}]},
                    **kwargs,
                ):
                    self._enforce_stream_timeout(start)
                    yield step
                self._on_attempt_success()
                self._checkpoint_agent_status(
                    message,
                    status="completed",
                    mark_completed=True,
                )
            except Exception as exc:
                retries = self._checkpoint_increment_retry(message, error=str(exc))
                self._checkpoint_agent_status(
                    message,
                    status="failed",
                    retries=retries,
                    last_error=str(exc),
                    mark_completed=True,
                )
                raise
        else:
            result = self._invoke_with_resilience(
                call_name="stream_direct",
                message=message,
                core_call=lambda m, **k: self._invoke_direct(m, **k),
                **kwargs,
            )
            yield result

    def _invoke_core(self, message: str, **kwargs: Any) -> dict[str, Any]:
        if self._mode == "react" and self._graph:
            result = self._graph.invoke(
                {"messages": [{"role": "user", "content": message}]},
                **kwargs,
            )
            output = self._extract_last_message(result)
            self._log.success(
                "invoke OK",
                action="invoke",
                meta={"output_len": len(output)},
            )
            return {"messages": result["messages"], "output": output}

        return self._invoke_direct(message, **kwargs)

    async def _ainvoke_core(self, message: str, **kwargs: Any) -> dict[str, Any]:
        if self._mode == "react" and self._graph:
            result = await self._graph.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                **kwargs,
            )
            output = self._extract_last_message(result)
            return {"messages": result["messages"], "output": output}

        return self._invoke_direct(message, **kwargs)

    def _invoke_with_resilience(
        self,
        *,
        call_name: str,
        message: str,
        core_call: Callable[..., dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self._check_circuit_breaker()
        max_attempts = self._resolved_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = self._run_with_timeout(
                    lambda: core_call(message, **kwargs),
                    timeout_seconds=self._resolved_timeout_seconds,
                )
                self._on_attempt_success()
                self._checkpoint_agent_status(
                    message,
                    status="completed",
                    retries=attempt - 1,
                    mark_completed=True,
                )
                self._checkpoint_artifact(
                    topic=message,
                    artifact_type="agent_output",
                    value=result.get("output", ""),
                    meta={"attempt": attempt, "call": call_name},
                )
                return result
            except Exception as exc:
                last_error = exc
                self._on_attempt_failure(exc)
                retries = self._checkpoint_increment_retry(message, error=str(exc))
                self._checkpoint_agent_status(
                    message,
                    status="retrying" if attempt < max_attempts else "failed",
                    retries=retries,
                    last_error=str(exc),
                    mark_completed=attempt >= max_attempts,
                )
                self._checkpoint_artifact(
                    topic=message,
                    artifact_type="agent_attempt_error",
                    value=str(exc),
                    meta={"attempt": attempt, "call": call_name},
                )
                if attempt >= max_attempts:
                    break
                self._log.warning(
                    "%s retrying  attempt=%d/%d",
                    call_name,
                    attempt + 1,
                    max_attempts,
                    action="agent_retry",
                    reason=type(exc).__name__,
                    meta={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "timeout_seconds": self._resolved_timeout_seconds,
                    },
                )

        assert last_error is not None
        raise RuntimeError(
            f"{self._name} failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    async def _ainvoke_with_resilience(
        self,
        *,
        call_name: str,
        message: str,
        core_call: Callable[..., Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self._check_circuit_breaker()
        max_attempts = self._resolved_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = await asyncio.wait_for(
                    core_call(message, **kwargs),
                    timeout=self._resolved_timeout_seconds,
                )
                self._on_attempt_success()
                self._checkpoint_agent_status(
                    message,
                    status="completed",
                    retries=attempt - 1,
                    mark_completed=True,
                )
                self._checkpoint_artifact(
                    topic=message,
                    artifact_type="agent_output",
                    value=result.get("output", ""),
                    meta={"attempt": attempt, "call": call_name},
                )
                return result
            except Exception as exc:
                last_error = exc
                self._on_attempt_failure(exc)
                retries = self._checkpoint_increment_retry(message, error=str(exc))
                self._checkpoint_agent_status(
                    message,
                    status="retrying" if attempt < max_attempts else "failed",
                    retries=retries,
                    last_error=str(exc),
                    mark_completed=attempt >= max_attempts,
                )
                self._checkpoint_artifact(
                    topic=message,
                    artifact_type="agent_attempt_error",
                    value=str(exc),
                    meta={"attempt": attempt, "call": call_name},
                )
                if attempt >= max_attempts:
                    break
                self._log.warning(
                    "%s retrying  attempt=%d/%d",
                    call_name,
                    attempt + 1,
                    max_attempts,
                    action="agent_retry",
                    reason=type(exc).__name__,
                    meta={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "timeout_seconds": self._resolved_timeout_seconds,
                    },
                )

        assert last_error is not None
        raise RuntimeError(
            f"{self._name} failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _run_with_timeout(
        fn: Callable[[], dict[str, Any]],
        *,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn)
            try:
                return future.result(timeout=timeout_seconds)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Agent call timed out after {timeout_seconds}s"
                ) from exc

    def _check_circuit_breaker(self) -> None:
        if self._circuit_open_until <= 0:
            return

        now = time.monotonic()
        if now >= self._circuit_open_until:
            self._circuit_open_until = 0.0
            self._consecutive_failures = 0
            self._log.info(
                "Circuit breaker reset",
                action="circuit_breaker_reset",
            )
            return

        remaining = int(self._circuit_open_until - now)
        raise RuntimeError(
            f"Circuit breaker open for agent '{self._name}'. Retry after {remaining}s."
        )

    def _on_attempt_success(self) -> None:
        if self._consecutive_failures > 0:
            self._log.info(
                "Agent recovered after failures",
                action="agent_recovered",
                meta={"failures_before_success": self._consecutive_failures},
            )
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _on_attempt_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        should_open = (
            self._consecutive_failures >= self._resolved_circuit_breaker_threshold
        )

        if should_open:
            self._circuit_open_until = (
                time.monotonic() + self._resolved_circuit_breaker_cooldown_seconds
            )
            self._log.error(
                "Circuit breaker opened",
                action="circuit_breaker_open",
                reason=type(exc).__name__,
                meta={
                    "consecutive_failures": self._consecutive_failures,
                    "threshold": self._resolved_circuit_breaker_threshold,
                    "cooldown_seconds": self._resolved_circuit_breaker_cooldown_seconds,
                },
            )
            return

        self._log.warning(
            "Agent attempt failed",
            action="agent_attempt_failed",
            reason=type(exc).__name__,
            meta={
                "consecutive_failures": self._consecutive_failures,
                "threshold": self._resolved_circuit_breaker_threshold,
            },
        )

    def _enforce_stream_timeout(self, started_at: float) -> None:
        elapsed = time.monotonic() - started_at
        if elapsed <= self._resolved_timeout_seconds:
            return
        exc = TimeoutError(f"Stream timed out after {self._resolved_timeout_seconds}s")
        self._on_attempt_failure(exc)
        raise exc

    def _resolve_int_setting(
        self,
        *,
        key_name: str,
        explicit: int | None,
        default: int,
    ) -> int:
        if explicit is not None:
            return max(1, int(explicit))

        specific_key = f"AGENT_{self._name.upper()}_{key_name}"
        shared_key = f"AGENT_{key_name}"

        raw_specific = config.get(specific_key)
        if raw_specific:
            return self._parse_int(raw_specific, default=default)

        raw_shared = config.get(shared_key)
        if raw_shared:
            return self._parse_int(raw_shared, default=default)

        return default

    @staticmethod
    def _parse_int(value: str, *, default: int) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    def _checkpoint_topic_input(self, message: str) -> None:
        topic = message.strip()
        if not topic:
            return

        try:
            from agents.services import save_topic_input

            save_topic_input(
                topic,
                topic,
                input_type="agent_input",
                source_agent=self._name,
            )
        except Exception as exc:
            self._log.warning(
                "Checkpoint topic input failed: %s",
                exc,
                action="checkpoint_warn",
            )

    def _checkpoint_artifact(
        self,
        *,
        topic: str,
        artifact_type: str,
        value: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        normalized_topic = topic.strip()
        if not normalized_topic:
            return

        try:
            from agents.services import save_pipeline_artifact

            save_pipeline_artifact(
                normalized_topic,
                source_agent=self._name,
                artifact_type=artifact_type,
                value=value[:20000],
                meta=meta,
            )
        except Exception as exc:
            self._log.warning(
                "Checkpoint artifact failed: %s",
                exc,
                action="checkpoint_warn",
            )

    def _checkpoint_agent_status(
        self,
        topic: str,
        *,
        status: str,
        retries: int | None = None,
        last_error: str | None = None,
        mark_started: bool = False,
        mark_completed: bool = False,
    ) -> None:
        normalized_topic = topic.strip()
        if not normalized_topic:
            return

        try:
            from agents.services import upsert_agent_status

            upsert_agent_status(
                normalized_topic,
                agent_name=self._name,
                status=status,
                retries=retries,
                last_error=last_error,
                mark_started=mark_started,
                mark_completed=mark_completed,
            )
        except Exception as exc:
            self._log.warning(
                "Checkpoint agent status failed: %s",
                exc,
                action="checkpoint_warn",
            )

    def _checkpoint_increment_retry(self, topic: str, *, error: str) -> int:
        normalized_topic = topic.strip()
        if not normalized_topic:
            return 0

        try:
            from agents.services import increment_agent_retry

            return increment_agent_retry(
                normalized_topic,
                agent_name=self._name,
                error=error,
            )
        except Exception as exc:
            self._log.warning(
                "Checkpoint retry increment failed: %s",
                exc,
                action="checkpoint_warn",
            )
            return 0

    def _invoke_direct(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Direct LLM call with system prompt (no tool loop)."""
        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=message),
        ]
        response = self._llm_adapter.chat_model.invoke(messages)
        output = response.content if hasattr(response, "content") else str(response)
        self._log.success(
            "direct OK",
            action="invoke_direct",
            meta={"output_len": len(output)},
        )
        return {"messages": messages + [response], "output": output}

    # ── Tool wrapping ────────────────────────────────────────────────

    def as_tool(self) -> StructuredTool:
        """Wrap this agent as a LangChain tool for a parent agent.

        The parent agent calls this tool with a natural-language request,
        and receives the sub-agent's final output as a string.
        """
        agent_ref = self

        def _run(request: str) -> str:
            result = agent_ref.invoke(request)
            return result["output"]

        async def _arun(request: str) -> str:
            result = await agent_ref.ainvoke(request)
            return result["output"]

        return StructuredTool.from_function(
            func=_run,
            coroutine=_arun,
            name=f"delegate_to_{self._name}",
            description=self._description,
        )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_last_message(result: dict) -> str:
        """Pull text from the last message in a graph result."""
        msgs = result.get("messages", [])
        if not msgs:
            return ""
        last = msgs[-1]
        return last.content if hasattr(last, "content") else str(last)

    @property
    def name(self) -> str:
        """Unique agent name."""
        return self._name

    @property
    def description(self) -> str:
        """Agent description (used as tool description for parent agents)."""
        return self._description

    @property
    def graph(self) -> CompiledStateGraph | None:
        """Underlying LangGraph (None for direct-mode agents)."""
        return self._graph

    @property
    def llm(self) -> BaseLLMAdapter:
        """The LLM adapter this agent uses."""
        return self._llm_adapter

    @property
    def mode(self) -> str:
        """Execution mode: ``'react'``, ``'direct'``, or ``'demo'``."""
        return self._mode

    @property
    def is_demo(self) -> bool:
        """Whether this agent is running in demo mode (static data)."""
        return self._demo

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self._name!r} "
            f"mode={self._mode!r} tools={len(self._collect_tools())}>"
        )
