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
)
from .search import google_search_snippets

__all__ = [
    "ToolEntry",
    "agent_tool",
    "crawlbase_fetch_page",
    "firecrawl_browser_collect_links",
    "firecrawl_search_results",
    "register_tool",
    "get_tool",
    "get_tool_info",
    "get_tools_by_category",
    "list_tools",
    "list_categories",
    "google_search_snippets",
]
