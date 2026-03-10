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
from .search import google_search_snippets

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
    "google_search_snippets",
]
