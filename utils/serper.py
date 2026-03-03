"""Serper API utility adapter.

Centralized integration point for Google search via Serper so agents/tools
can reuse one implementation.
"""

from __future__ import annotations

from typing import Any

import requests

from env import config
from Logging import get_logger

logger = get_logger("utils.serper")


def send_serper_request(
    query: str,
    *,
    api_key: str | None = None,
    type: str = "google",
    max_results: int = 10,
    gl: str = "us",
    hl: str = "en",
    page: int = 1,
    autocorrect: bool = True,
) -> dict[str, Any]:
    """Send a search request to Serper API and return the response as a dict."""
    api_key = api_key or config.get("SERPER_API_KEY")
    if not api_key:
        raise ValueError("SERPER_API_KEY is not configured.")
    payload = {
        "q": query,
        "num": max(1, min(int(max_results), 10)),
        "gl": gl,
        "hl": hl,
        "page": page,
        "autocorrect": autocorrect,
    }
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    response = requests.post(
        f"https://{type}.serper.dev/search",
        headers=headers,
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    data["ok"] = True
    data["demo"] = False
    return data


def exception_to_str(exc: Exception) -> str:
    """Convert an exception to a concise string for logging."""
    return f"{exc.__class__.__name__}: {str(exc)}"


def search_google_serper(
    query: str,
    *,
    api_key: str | None = None,
    type: str = "google",
    max_results: int = 10,
    gl: str = "us",
    hl: str = "en",
    page: int = 1,
    autocorrect: bool = True,
    include_demo_on_error: bool = True,
) -> dict[str, Any]:
    """Search Google via Serper and return normalized response.

    Returns a dict compatible with Serper-style fields. When API key is missing
    or request fails and ``include_demo_on_error`` is true, returns a realistic
    demo payload under the same shape with ``demo=true`` and ``error`` fields.
    """
    top_n = max(1, min(int(max_results), 10))
    try:
        return send_serper_request(
            query,
            api_key=api_key,
            type=type,
            max_results=top_n,
            gl=gl,
            hl=hl,
            page=page,
            autocorrect=autocorrect,
        )
    except Exception as exc:
        logger.warning(
            "Serper request failed: %s",
            exc,
            action="serper_search",
            reason=exception_to_str(exc),
            meta={"query": query},
        )
        if include_demo_on_error:
            demo = _demo_response(query, gl=gl, hl=hl, page=page, top_n=top_n)
            demo["demo"] = True
            demo["error"] = str(exc)
            return demo
        return {
            "ok": False,
            "error": str(exc),
            "query": query,
        }


def _demo_response(
    query: str,
    *,
    gl: str,
    hl: str,
    page: int,
    top_n: int,
) -> dict[str, Any]:
    normalized = query.strip() or "apple inc"

    generic_organic = [
        {
            "title": f"{normalized} - Overview",
            "link": f"https://example.com/search/{normalized.replace(' ', '-').lower()}",
            "snippet": f"Overview and recent updates related to {normalized}.",
            "position": 1,
        },
        {
            "title": f"{normalized} discussions",
            "link": "https://www.reddit.com/",
            "snippet": f"Community discussion threads and sentiment around {normalized}.",
            "position": 2,
        },
        {
            "title": f"{normalized} news",
            "link": "https://news.google.com/",
            "snippet": f"Latest news and analysis for {normalized}.",
            "position": 3,
        },
    ]

    return {
        "ok": True,
        "searchParameters": {
            "q": normalized,
            "gl": gl,
            "hl": hl,
            "autocorrect": True,
            "page": page,
            "type": "search",
        },
        "knowledgeGraph": {
            "title": normalized,
            "type": "Topic",
            "description": f"Demo knowledge summary for {normalized}.",
            "descriptionSource": "Demo",
        },
        "organic": generic_organic[:top_n],
        "peopleAlsoAsk": [
            {
                "question": f"What is {normalized}?",
                "snippet": f"High-level context and ongoing public conversation around {normalized}.",
                "title": "Demo context",
                "link": "https://example.com/",
            }
        ],
        "relatedSearches": [
            {"query": f"{normalized} sentiment"},
            {"query": f"{normalized} public opinion"},
            {"query": f"{normalized} social media"},
        ],
    }
