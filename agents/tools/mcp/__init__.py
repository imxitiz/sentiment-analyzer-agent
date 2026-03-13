"""MCP tool integration helpers."""

from __future__ import annotations

from .registry import (
    MCPServerConfig,
    disable_mcp_server,
    enable_mcp_server,
    ensure_mcp_config_loaded,
    get_mcp_server,
    list_mcp_servers,
    load_mcp_servers_from_file,
    normalize_mcp_server_config,
    register_mcp_server,
    register_mcp_servers,
)
from .loader import (
    load_mcp_prompts,
    load_mcp_prompts_async,
    load_mcp_resources,
    load_mcp_resources_async,
    load_mcp_tools,
    load_mcp_tools_async,
)
from .servers import register_builtin_mcp_servers

register_builtin_mcp_servers()

__all__ = [
    "MCPServerConfig",
    "disable_mcp_server",
    "enable_mcp_server",
    "ensure_mcp_config_loaded",
    "get_mcp_server",
    "list_mcp_servers",
    "load_mcp_prompts",
    "load_mcp_prompts_async",
    "load_mcp_resources",
    "load_mcp_resources_async",
    "load_mcp_tools",
    "load_mcp_tools_async",
    "load_mcp_servers_from_file",
    "normalize_mcp_server_config",
    "register_mcp_server",
    "register_mcp_servers",
]
