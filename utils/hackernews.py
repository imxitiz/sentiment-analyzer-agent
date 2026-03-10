"""Hacker News API adapter for scraper backends."""

from __future__ import annotations

from typing import Any

import requests

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


def get_hn_item(item_id: int, *, timeout_seconds: float = 20.0) -> dict[str, Any]:
    """Fetch one Hacker News item."""
    response = requests.get(
        f"{HN_API_BASE}/item/{int(item_id)}.json",
        timeout=max(5.0, timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Unexpected Hacker News item payload.")


__all__ = ["get_hn_item"]
