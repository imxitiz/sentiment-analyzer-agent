"""Bluesky public API adapter for scraper backends."""

from __future__ import annotations

from typing import Any

import requests

PUBLIC_BSKY_API = "https://public.api.bsky.app/xrpc"


def _get(path: str, *, params: dict[str, Any], timeout_seconds: float = 20.0) -> dict[str, Any]:
    response = requests.get(
        f"{PUBLIC_BSKY_API}{path}",
        params=params,
        timeout=max(5.0, timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Unexpected Bluesky response payload.")


def resolve_bluesky_handle(handle: str) -> str:
    """Resolve a Bluesky handle into a DID."""
    payload = _get(
        "/com.atproto.identity.resolveHandle",
        params={"handle": handle},
    )
    did = payload.get("did")
    if not isinstance(did, str) or not did:
        raise RuntimeError("Bluesky handle resolution did not return a DID.")
    return did


def get_bluesky_post_thread(uri: str, *, depth: int = 6) -> dict[str, Any]:
    """Fetch a Bluesky post thread by AT URI."""
    return _get(
        "/app.bsky.feed.getPostThread",
        params={"uri": uri, "depth": max(1, min(depth, 12))},
        timeout_seconds=30.0,
    )


__all__ = ["get_bluesky_post_thread", "resolve_bluesky_handle"]
