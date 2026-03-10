"""RSS parsing utility adapter for scraper backends."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

import requests


def fetch_rss_feed(url: str, *, timeout_seconds: float = 25.0, max_items: int = 30) -> dict[str, Any]:
    """Fetch and parse an RSS/Atom feed into a normalized structure."""
    response = requests.get(url, timeout=max(5.0, timeout_seconds))
    response.raise_for_status()
    raw_xml = response.text
    root = ET.fromstring(raw_xml)

    channel = root.find("./channel")
    if channel is not None:
        title = (channel.findtext("title") or "").strip()
        description = (channel.findtext("description") or "").strip()
        feed_link = (channel.findtext("link") or "").strip()
        nodes = channel.findall("item")
        items: list[dict[str, Any]] = []
        for node in nodes[: max(1, max_items)]:
            items.append(
                {
                    "title": (node.findtext("title") or "").strip(),
                    "link": (node.findtext("link") or "").strip(),
                    "description": (node.findtext("description") or "").strip(),
                    "author": (node.findtext("author") or "").strip() or None,
                    "published_at": (node.findtext("pubDate") or "").strip() or None,
                    "guid": (node.findtext("guid") or "").strip() or None,
                }
            )
        return {
            "format": "rss",
            "title": title,
            "description": description,
            "link": feed_link,
            "items": items,
            "raw_xml": raw_xml,
        }

    # Atom fallback
    atom_ns = {"a": "http://www.w3.org/2005/Atom"}
    title = (root.findtext("a:title", default="", namespaces=atom_ns) or "").strip()
    feed_link = ""
    first_link = root.find("a:link", atom_ns)
    if first_link is not None:
        feed_link = (first_link.get("href") or "").strip()
    entries = root.findall("a:entry", atom_ns)
    items = []
    for entry in entries[: max(1, max_items)]:
        link_node = entry.find("a:link", atom_ns)
        items.append(
            {
                "title": (entry.findtext("a:title", default="", namespaces=atom_ns) or "").strip(),
                "link": ((link_node.get("href") if link_node is not None else "") or "").strip(),
                "description": (entry.findtext("a:summary", default="", namespaces=atom_ns) or "").strip(),
                "author": (entry.findtext("a:author/a:name", default="", namespaces=atom_ns) or "").strip() or None,
                "published_at": (entry.findtext("a:published", default="", namespaces=atom_ns) or "").strip() or None,
                "guid": (entry.findtext("a:id", default="", namespaces=atom_ns) or "").strip() or None,
            }
        )
    return {
        "format": "atom",
        "title": title,
        "description": "",
        "link": feed_link,
        "items": items,
        "raw_xml": raw_xml,
    }


__all__ = ["fetch_rss_feed"]
