"""Built-in MCP server registrations."""

from __future__ import annotations

_BUILTINS_REGISTERED = False


def register_builtin_mcp_servers() -> None:
    """Register built-in MCP servers once."""
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return
    _BUILTINS_REGISTERED = True

    from .open_websearch import register_open_websearch_servers

    register_open_websearch_servers()


__all__ = ["register_builtin_mcp_servers"]
