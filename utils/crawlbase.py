"""Crawlbase API adapter.

Provides a minimal wrapper for the Crawlbase Crawling API so the harvester can
expand candidate pages with rendered HTML when browser-style retrieval is
needed.
"""

from __future__ import annotations

from typing import Any

import requests

from env import config

_BASE_URL = "https://api.crawlbase.com/"


def crawlbase_fetch_url(
    url: str,
    *,
    token: str | None = None,
    javascript: bool = True,
    timeout_seconds: float = 90.0,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch a URL through Crawlbase Crawling API."""
    resolved_token = token
    if not resolved_token:
        resolved_token = config.get("CRAWLBASE_JS_TOKEN" if javascript else "CRAWLBASE_TOKEN")
    if not resolved_token:
        raise ValueError("Crawlbase token is not configured.")

    params: dict[str, Any] = {
        "token": resolved_token,
        "url": url,
    }
    if extra_params:
        params.update(extra_params)

    response = requests.get(
        _BASE_URL,
        params=params,
        headers={"Accept-Encoding": "gzip"},
        timeout=max(10.0, timeout_seconds),
    )
    response.raise_for_status()

    return {
        "status_code": response.status_code,
        "url": url,
        "content": response.text,
        "headers": dict(response.headers),
    }


__all__ = ["crawlbase_fetch_url"]