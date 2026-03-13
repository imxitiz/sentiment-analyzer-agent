"""Firecrawl API adapter.

Provides a small, reusable wrapper over the Firecrawl REST API so agents and
tools can use search, scrape, and browser features without depending on a
specific SDK.
"""

from __future__ import annotations

from typing import Any

import requests

from env import config
from Logging import get_logger

logger = get_logger("utils.firecrawl")

_BASE_URL = "https://api.firecrawl.dev/v2"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    path: str,
    *,
    api_key: str | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 75.0,
) -> dict[str, Any]:
    token = api_key or config.get("FIRECRAWL_API_KEY")
    if not token:
        raise ValueError("FIRECRAWL_API_KEY is not configured.")

    response = requests.request(
        method,
        f"{_BASE_URL}{path}",
        headers=_headers(token),
        json=json_body,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data
    raise RuntimeError("Unexpected Firecrawl response payload.")


def search_firecrawl(
    query: str,
    *,
    api_key: str | None = None,
    limit: int = 10,
    country: str = "US",
    location: str | None = None,
    sources: list[str] | None = None,
    categories: list[dict[str, str]] | None = None,
    timeout_ms: int = 60000,
    tbs: str | None = None,
    scrape_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search Firecrawl and return the normalized JSON payload."""
    body: dict[str, Any] = {
        "query": query,
        "limit": max(1, min(int(limit), 100)),
        "country": country,
        "timeout": max(1, int(timeout_ms)),
        "sources": sources or ["web"],
    }
    if location:
        body["location"] = location
    if categories:
        body["categories"] = categories
    if tbs:
        body["tbs"] = tbs
    if scrape_options:
        body["scrapeOptions"] = scrape_options

    data = _request(
        "POST",
        "/search",
        api_key=api_key,
        json_body=body,
        timeout_seconds=max(30.0, timeout_ms / 1000.0 + 15.0),
    )
    data.setdefault("success", True)
    return data


def scrape_firecrawl(
    url: str,
    *,
    api_key: str | None = None,
    formats: list[str] | None = None,
    timeout_seconds: float = 75.0,
    only_main_content: bool = True,
) -> dict[str, Any]:
    """Scrape a single URL with Firecrawl."""
    return _request(
        "POST",
        "/scrape",
        api_key=api_key,
        json_body={
            "url": url,
            "formats": formats or ["markdown", "html", "links"],
            "onlyMainContent": only_main_content,
        },
        timeout_seconds=timeout_seconds,
    )


def create_firecrawl_browser_session(
    *,
    api_key: str | None = None,
    ttl: int = 300,
    activity_ttl: int = 120,
    profile_name: str | None = None,
    save_changes: bool = False,
) -> dict[str, Any]:
    """Launch a remote Firecrawl browser session."""
    body: dict[str, Any] = {
        "ttl": max(30, min(int(ttl), 3600)),
        "activityTtl": max(10, min(int(activity_ttl), 3600)),
    }
    if profile_name:
        body["profile"] = {
            "name": profile_name,
            "saveChanges": save_changes,
        }
    return _request(
        "POST",
        "/browser",
        api_key=api_key,
        json_body=body,
        timeout_seconds=30.0,
    )


def execute_firecrawl_browser(
    session_id: str,
    *,
    code: str,
    api_key: str | None = None,
    language: str = "node",
    timeout_seconds: float = 75.0,
) -> dict[str, Any]:
    """Execute code inside a Firecrawl browser session."""
    return _request(
        "POST",
        f"/browser/{session_id}/execute",
        api_key=api_key,
        json_body={
            "code": code,
            "language": language,
        },
        timeout_seconds=timeout_seconds,
    )


def delete_firecrawl_browser(
    session_id: str,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Close a Firecrawl browser session."""
    return _request(
        "DELETE",
        f"/browser/{session_id}",
        api_key=api_key,
        timeout_seconds=30.0,
    )


__all__ = [
    "create_firecrawl_browser_session",
    "delete_firecrawl_browser",
    "execute_firecrawl_browser",
    "scrape_firecrawl",
    "search_firecrawl",
]
