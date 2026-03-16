"""Provides Google search snippets via Serper API so agents can gather
fresh context before planning.
"""

from __future__ import annotations

import json
from typing import Any

from Logging import get_logger
from utils import search_google_serper

logger = get_logger("agents.services.search_searchengine")


def search_searchengine(
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
    normalized_engine = engine.lower().strip()

    top_n = max(1, min(int(max_results), 10))

    if normalized_engine == "google":
        data = search_google_serper(query, max_results=top_n)
        organic = data.get("organic", [])[:top_n]

        items: list[dict[str, Any]] = []
        for item in organic:
            items.append(
                {
                    "attributes": item.get("attributes", {}),
                    "date": item.get("date", ""),
                    "link": item.get("link", ""),
                    "position": item.get("position", 0),
                    "sitelinks": item.get("sitelinks", []),
                    "snippet": item.get("snippet", ""),
                    "title": item.get("title", ""),
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
            "searchParameters": data.get("searchParameters", {}),
        }
        if data.get("error"):
            result["error"] = data["error"]

        logger.info(
            "Search snippets fetched  query=%s results=%d demo=%s",
            query,
            len(items),
            bool(data.get("demo", False)),
            action="tool_search",
            meta={
                "engine": "google",
                "count": len(items),
                "demo": bool(data.get("demo", False)),
            },
        )
        return json.dumps(result, ensure_ascii=False)

    if normalized_engine in ("duckduckgo", "ddg"):
        # Attempt to use the community DuckDuckGo integration.  If the
        # dependency is missing or the request fails we fall back to a tiny
        # demo payload so that agents can still function offline or during
        # tests.
        items: list[dict[str, Any]] = []
        demo_mode = False
        err_msg: str | None = None
        try:
            from langchain_community.tools import DuckDuckGoSearchRun

            # DuckDuckGoSearchRun returns a comma separated key:value string by
            # default; we just want a list of the top titles/links/snippets.
            runner = DuckDuckGoSearchRun(output_format="json")
            raw = runner.invoke(query)  # this is a JSON string if output_format=json
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            # parsed is expected to be a list of dicts
            for item in parsed[:top_n]:
                items.append(
                    {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    }
                )
        except Exception as exc:  # pragma: no cover - network/dependency issues
            logger.warning(
                "DuckDuckGo search failed: %s",
                exc,
                action="tool_search",
                reason=str(exc),
                meta={"query": query},
            )
            demo_mode = True
            err_msg = str(exc)
            # simple demo response so tool output is still valid
            items = [
                {
                    "title": f"{query} (demo)",
                    "link": f"https://duckduckgo.com/?q={query}",
                    "snippet": f"Demo search result for {query}.",
                }
            ]
        result = {
            "ok": not demo_mode,
            "demo": demo_mode,
            "engine": "duckduckgo",
            "query": query,
            "count": len(items),
            "results": items,
        }
        if err_msg:
            result["error"] = err_msg
        logger.info(
            "Search snippets fetched  query=%s results=%d demo=%s",
            query,
            len(items),
            demo_mode,
            action="tool_search",
            meta={"engine": "duckduckgo", "count": len(items), "demo": demo_mode},
        )
        return json.dumps(result, ensure_ascii=False)

    # unsupported engine
    return json.dumps(
        {
            "ok": False,
            "error": f"Unsupported engine: {engine}. Only 'google' and 'duckduckgo' are available.",
        },
        ensure_ascii=False,
    )
