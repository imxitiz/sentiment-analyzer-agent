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

import inspect
from abc import ABC
from pathlib import Path
from typing import Any, Generator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from BaseLLM import get_llm
from BaseLLM.adapter import BaseLLMAdapter
from Logging import context_logger


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

    def __init__(
        self,
        llm_provider: str | None = None,
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_tools: list | None = None,
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
            system_prompt: Override system prompt (skip file loading).
            **llm_kwargs: Forwarded to ``get_llm()``.
        """
        provider = llm_provider or self._llm_provider
        model_name = model or self._llm_model

        self._llm_adapter: BaseLLMAdapter = get_llm(
            provider, model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            **llm_kwargs,
        )
        self._extra_tools = extra_tools or []
        self._system_prompt_override = system_prompt
        self._log = context_logger(
            f"agents.{self._name}", actor=self._name, phase="AGENT",
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
                    all_tools, self._system_prompt,
                )

        self._log.info(
            "Agent ready  name=%s  mode=%s  tools=%d",
            self._name, self._mode, len(all_tools),
            action="agent_init",
            meta={
                "name": self._name,
                "mode": self._mode,
                "provider": provider,
                "model": model_name or "default",
                "tool_count": len(all_tools),
                "tool_names": [getattr(t, "name", str(t)) for t in all_tools],
                "demo": self._demo,
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
        return self._register_tools() + self._extra_tools

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
        return create_agent(
            self._llm_adapter.chat_model,
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
        output = (
            f"[DEMO:{self._name}] Processed topic: "
            f"{message.strip()[:200]}"
        )
        self._log.info(
            "demo invoke  agent=%s", self._name, action="demo_invoke",
        )
        return {"messages": [], "output": output}

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Run the agent synchronously.

        Returns:
            Dict with ``messages`` (list) and ``output`` (str).
        """
        self._log.info(
            "invoke  len=%d  mode=%s", len(message), self._mode,
            action="invoke",
        )

        # Demo mode — skip LLM entirely
        if self._demo:
            return self._demo_invoke(message, **kwargs)

        if self._mode == "react" and self._graph:
            result = self._graph.invoke(
                {"messages": [{"role": "user", "content": message}]},
                **kwargs,
            )
            output = self._extract_last_message(result)
            self._log.success(
                "invoke OK", action="invoke",
                meta={"output_len": len(output)},
            )
            return {"messages": result["messages"], "output": output}

        return self._invoke_direct(message, **kwargs)

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Run the agent asynchronously."""
        self._log.info(
            "ainvoke  len=%d  mode=%s", len(message), self._mode,
            action="ainvoke",
        )

        if self._demo:
            return self._demo_invoke(message, **kwargs)

        if self._mode == "react" and self._graph:
            result = await self._graph.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                **kwargs,
            )
            output = self._extract_last_message(result)
            return {"messages": result["messages"], "output": output}

        return self._invoke_direct(message, **kwargs)

    def stream(self, message: str, **kwargs: Any) -> Generator:
        """Stream agent execution steps."""
        if self._demo:
            yield self._demo_invoke(message, **kwargs)
            return

        if self._mode == "react" and self._graph:
            yield from self._graph.stream(
                {"messages": [{"role": "user", "content": message}]},
                **kwargs,
            )
        else:
            yield self._invoke_direct(message, **kwargs)

    def _invoke_direct(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Direct LLM call with system prompt (no tool loop)."""
        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=message),
        ]
        response = self._llm_adapter.chat_model.invoke(messages)
        output = response.content if hasattr(response, "content") else str(response)
        self._log.success(
            "direct OK", action="invoke_direct",
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
