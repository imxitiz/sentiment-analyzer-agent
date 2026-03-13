"""Reusable utility layer for external service adapters."""

from .crawlbase import crawlbase_fetch_url
from .firecrawl import (
    create_firecrawl_browser_session,
    delete_firecrawl_browser,
    execute_firecrawl_browser,
    scrape_firecrawl,
    search_firecrawl,
)
from .serper import search_google_serper
from .serpapi import search_serpapi
from .camoufox import (
    camoufox_click,
    camoufox_close_all_browsers,
    camoufox_close_browser,
    camoufox_evaluate,
    camoufox_extract_links,
    camoufox_extract_text,
    camoufox_fetch_anchors,
    camoufox_is_available,
    camoufox_list_sessions,
    camoufox_navigate,
    camoufox_start_browser,
    camoufox_type,
)

__all__ = [
    "crawlbase_fetch_url",
    "create_firecrawl_browser_session",
    "delete_firecrawl_browser",
    "execute_firecrawl_browser",
    "scrape_firecrawl",
    "search_firecrawl",
    "search_google_serper",
    "search_serpapi",
    "camoufox_click",
    "camoufox_close_all_browsers",
    "camoufox_close_browser",
    "camoufox_evaluate",
    "camoufox_extract_links",
    "camoufox_extract_text",
    "camoufox_fetch_anchors",
    "camoufox_is_available",
    "camoufox_list_sessions",
    "camoufox_navigate",
    "camoufox_start_browser",
    "camoufox_type",
]
