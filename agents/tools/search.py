"""Search tools for agents.

Provides Google search snippets via Serper API so agents can gather
fresh context before planning.
"""

from __future__ import annotations

import json
from Logging import get_logger
from agents.services import search_searchengine

from ._registry import agent_tool

logger = get_logger("agents.tools.search")


@agent_tool(category="search")
def search_engine_snippets(
    query: str, engine: str = "google", max_results: int = 10
) -> str:
    """Search the web and return top result snippets.

    The original helper was built around Google/Serper, but we now support
    additional engines (DuckDuckGo) so that agents can perform lightweight
    internet searches without relying solely on Serper. Callers can
    pass ``engine="duckduckgo"`` or ``engine="ddg"`` to exercise the
    alternate backend.

    Args:
        query: Search keyword/query string.
        engine: Search engine name (``google`` or ``duckduckgo``).
        max_results: Number of result snippets to return (1-10).

    Returns:
        JSON string with query metadata and top organic results.  The shape is
        identical regardless of engine so that callers do not need conditional
        logic when processing the output.
    """

    try:
        return search_searchengine(query, engine, max_results)
    except Exception as e:
        logger.error(f"Error in search_engine_snippets: {e}")
        return json.dumps({"ok": False, "error": str(e)})
