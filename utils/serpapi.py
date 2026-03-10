"""SerpAPI adapter helper.

Lightweight wrapper around the SerpAPI web search endpoint so that the
harvester and other components can call it without embedding HTTP logic.

See https://serpapi.com/ for details.  This module is intentionally minimal;
most callers simply need the JSON payload produced by SerpAPI.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from env import config


_BASE_URL = "https://serpapi.com/search"


def search_serpapi(
    query: str,
    *,
    api_key: Optional[str] = None,
    max_results: int = 10,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run a SerpAPI search and return the parsed JSON response.

    Args:
        query: Search query string.
        api_key: Optional override; falls back to ``SERPAPI_API_KEY``.
        max_results: ``num`` parameter to limit results.
        **kwargs: Additional query parameters forwarded to SerpAPI.

    Raises:
        requests.HTTPError on failure.
    """
    key = api_key or config.get("SERPAPI_API_KEY")
    if not key:
        raise ValueError("SerpAPI key is not configured")

    params: Dict[str, Any] = {
        "q": query,
        "api_key": key,
        "num": max_results,
    }
    params.update(kwargs)
    response = requests.get(_BASE_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


__all__ = ["search_serpapi"]
