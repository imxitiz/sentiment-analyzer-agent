"""Agent tools — shared tools available to any agent.

Public API::

    from agents.tools import (
        agent_tool,          # decorator: create + register a tool
        register_tool,       # register an existing tool
        get_tool,            # look up tool by name
        list_tools,          # list registered tool names
        get_tools_by_category,
        list_categories,
    )
"""

from ._registry import (
    ToolEntry,
    agent_tool,
    register_tool,
    get_tool,
    get_tool_info,
    get_tools_by_category,
    list_tools,
    list_categories,
)
from .harvest import (
    crawlbase_fetch_page,
    firecrawl_browser_collect_links,
    firecrawl_search_results,
    serpapi_search_results,
    camoufox_browser_collect_links,
)
from .browser import (
    camoufox_click_browser,
    camoufox_close_all_browser_sessions,
    camoufox_close_browser_session,
    camoufox_evaluate_browser,
    camoufox_extract_links_browser,
    camoufox_extract_text_browser,
    camoufox_list_browser_sessions,
    camoufox_navigate_browser,
    camoufox_open_browser,
    camoufox_type_browser,
)
from .search import search_engine_snippets
from .mcp import (
    MCPServerConfig,
    disable_mcp_server,
    enable_mcp_server,
    get_mcp_server,
    list_mcp_servers,
    load_mcp_prompts,
    load_mcp_prompts_async,
    load_mcp_resources,
    load_mcp_resources_async,
    load_mcp_servers_from_file,
    load_mcp_tools,
    load_mcp_tools_async,
    normalize_mcp_server_config,
    register_mcp_server,
    register_mcp_servers,
)

__all__ = [
    "ToolEntry",
    "agent_tool",
    "crawlbase_fetch_page",
    "firecrawl_browser_collect_links",
    "firecrawl_search_results",
    "serpapi_search_results",
    "camoufox_browser_collect_links",
    "camoufox_click_browser",
    "camoufox_close_all_browser_sessions",
    "camoufox_close_browser_session",
    "camoufox_evaluate_browser",
    "camoufox_extract_links_browser",
    "camoufox_extract_text_browser",
    "camoufox_list_browser_sessions",
    "camoufox_navigate_browser",
    "camoufox_open_browser",
    "camoufox_type_browser",
    "register_tool",
    "get_tool",
    "get_tool_info",
    "get_tools_by_category",
    "list_tools",
    "list_categories",
    "MCPServerConfig",
    "disable_mcp_server",
    "enable_mcp_server",
    "get_mcp_server",
    "search_engine_snippets",
    "list_mcp_servers",
    "load_mcp_prompts",
    "load_mcp_prompts_async",
    "load_mcp_resources",
    "load_mcp_resources_async",
    "load_mcp_servers_from_file",
    "load_mcp_tools",
    "load_mcp_tools_async",
    "normalize_mcp_server_config",
    "register_mcp_server",
    "register_mcp_servers",
]
