"""Tool registry — register, discover, and retrieve agent tools.

Tools are Python functions that agents can call.  This registry provides
a central catalog so tools are discoverable, categorisable, and easy to
add or remove.

Two ways to register a tool:

1. **Decorator** (preferred for new tools)::

        from agents.tools import agent_tool

        @agent_tool(category="search")
        def web_search(query: str) -> str:
            '''Search the web for information.'''
            return results

2. **Function call** (for existing LangChain tools)::

        from agents.tools import register_tool
        register_tool(existing_tool, category="search")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from Logging import get_logger

logger = get_logger("agents.tools.registry")


# ── Data structures ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolEntry:
    """Metadata about a registered tool."""

    name: str
    category: str
    description: str
    tool: Any  # BaseTool or wrapped callable


# ── Registry storage ─────────────────────────────────────────────────

_TOOL_REGISTRY: dict[str, ToolEntry] = {}


# ── Registration ─────────────────────────────────────────────────────


def register_tool(tool_obj: Any, *, category: str = "general") -> None:
    """Register an existing LangChain tool or callable.

    Args:
        tool_obj: A LangChain ``BaseTool``, ``@tool``-decorated function,
            or any callable with ``name`` and ``description`` attributes.
        category: Grouping category (e.g. ``"search"``, ``"interaction"``).
    """
    name = getattr(tool_obj, "name", getattr(tool_obj, "__name__", str(tool_obj)))
    desc = getattr(tool_obj, "description", getattr(tool_obj, "__doc__", ""))

    _TOOL_REGISTRY[name] = ToolEntry(
        name=name,
        category=category,
        description=desc,
        tool=tool_obj,
    )
    logger.info("Registered tool  name=%s  category=%s", name, category)


def agent_tool(*, category: str = "general"):
    """Decorator: create a LangChain tool AND register it in one step.

    Usage::

        @agent_tool(category="interaction")
        def ask_human(question: str) -> str:
            '''Ask the user a question.'''
            return input(question)

    The decorated function becomes a LangChain ``StructuredTool`` and is
    automatically added to the tool registry.
    """

    def decorator(func):  # noqa: ANN001
        from langchain_core.tools import tool as lc_tool

        wrapped = lc_tool(func)
        register_tool(wrapped, category=category)
        return wrapped

    return decorator


# ── Discovery ────────────────────────────────────────────────────────


def get_tool(name: str) -> Any:
    """Get a registered tool by name.

    Raises:
        KeyError: If the tool name is not registered.
    """
    if name not in _TOOL_REGISTRY:
        available = ", ".join(list_tools()) or "(none)"
        raise KeyError(f"Unknown tool: {name!r}. Registered: {available}")
    return _TOOL_REGISTRY[name].tool


def get_tools_by_category(category: str) -> list[Any]:
    """Get all tools in a given category.

    Returns:
        List of LangChain tool objects.
    """
    return [
        entry.tool for entry in _TOOL_REGISTRY.values() if entry.category == category
    ]


def list_tools(category: str | None = None) -> list[str]:
    """List registered tool names, optionally filtered by category.

    Args:
        category: If provided, only return tools in this category.

    Returns:
        Sorted list of tool names.
    """
    if category:
        return sorted(
            name for name, entry in _TOOL_REGISTRY.items() if entry.category == category
        )
    return sorted(_TOOL_REGISTRY.keys())


def get_tool_info(name: str) -> ToolEntry:
    """Get full metadata for a registered tool.

    Raises:
        KeyError: If the tool name is not registered.
    """
    if name not in _TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name!r}")
    return _TOOL_REGISTRY[name]


def list_categories() -> list[str]:
    """List all unique tool categories."""
    return sorted({entry.category for entry in _TOOL_REGISTRY.values()})
