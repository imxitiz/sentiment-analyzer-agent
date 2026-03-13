"""Open WebSearch MCP server registration."""

from __future__ import annotations

from agents.tools.mcp.registry import register_mcp_server


def register_open_websearch_servers() -> None:
    """Register Open WebSearch MCP server configs (disabled by default)."""
    register_mcp_server(
        "open_websearch_stdio",
        {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "open-websearch@latest"],
            "env": {"MODE": "stdio"},
            "description": (
                "Open WebSearch MCP (stdio) via npx open-websearch@latest."
            ),
        },
        enabled=False,
    )

    register_mcp_server(
        "open_websearch_http",
        {
            "transport": "http",
            "url": "http://localhost:3000/mcp",
            "description": "Open WebSearch MCP (http) at /mcp.",
        },
        enabled=False,
    )
