"""YouTube utility adapter for lightweight metadata extraction."""

from __future__ import annotations

from typing import Any

import requests


def get_youtube_oembed(video_url: str, *, timeout_seconds: float = 20.0) -> dict[str, Any]:
    """Fetch video metadata through YouTube oEmbed endpoint."""
    response = requests.get(
        "https://www.youtube.com/oembed",
        params={"url": video_url, "format": "json"},
        timeout=max(5.0, timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Unexpected YouTube oEmbed payload.")


__all__ = ["get_youtube_oembed"]
