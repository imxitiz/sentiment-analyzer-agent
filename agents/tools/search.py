"""Search tools for agents.

Provides Google search snippets via Serper API so agents can gather
fresh context before planning.
"""

from __future__ import annotations

import json
from typing import Any

from Logging import get_logger
from utils import search_google_serper

from ._registry import agent_tool

logger = get_logger("agents.tools.search")


@agent_tool(category="search")
def google_search_snippets(query: str, engine: str = "google", max_results: int = 10) -> str:
    """Search the web and return top result snippets.

    Args:
        query: Search keyword/query string.
        engine: Search engine name (currently only ``google`` is supported).
        max_results: Number of result snippets to return (1-10).

    Returns:
        JSON string with query metadata and top organic results.
    """
    normalized_engine = engine.lower().strip()
    if normalized_engine != "google":
        return json.dumps(
            {
                "ok": False,
                "error": f"Unsupported engine: {engine}. Only 'google' is available.",
            },
            ensure_ascii=False,
        )
    data = search_google_serper(query, max_results=max_results)
    organic = data.get("organic", [])[: max(1, min(int(max_results), 10))]

    items: list[dict[str, Any]] = []
    for item in organic:
        items.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )

    result = {
        "ok": bool(data.get("ok", False)),
        "demo": bool(data.get("demo", False)),
        "engine": "google",
        "query": query,
        "count": len(items),
        "results": items,
        "relatedSearches": data.get("relatedSearches", []),
        "peopleAlsoAsk": data.get("peopleAlsoAsk", []),
        "knowledgeGraph": data.get("knowledgeGraph", {}),
    }
    if data.get("error"):
        result["error"] = data["error"]

    logger.info(
        "Search snippets fetched  query=%s results=%d demo=%s",
        query,
        len(items),
        bool(data.get("demo", False)),
        action="tool_search",
        meta={"engine": "google", "count": len(items), "demo": bool(data.get("demo", False))},
    )
    return json.dumps(result, ensure_ascii=False)
