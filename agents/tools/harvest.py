"""Reusable harvesting tools for search and browser-backed link discovery."""

from __future__ import annotations

import json

from utils import (
    crawlbase_fetch_url,
    create_firecrawl_browser_session,
    delete_firecrawl_browser,
    execute_firecrawl_browser,
    search_firecrawl,
)

from ._registry import agent_tool


@agent_tool(category="search")
def firecrawl_search_results(query: str, max_results: int = 10) -> str:
    """Search the web with Firecrawl and return result metadata as JSON."""
    try:
        data = search_firecrawl(query, limit=max_results, sources=["web", "news"])
        return json.dumps(data, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc), "query": query}, ensure_ascii=False)


@agent_tool(category="browser")
def firecrawl_browser_collect_links(url: str, max_links: int = 40) -> str:
    """Open a remote Firecrawl browser session and extract links from a page."""
    session = create_firecrawl_browser_session(ttl=180, activity_ttl=90)
    session_id = str(session.get("id", ""))
    if not session_id:
        return json.dumps({"success": False, "error": "Browser session creation failed."}, ensure_ascii=False)

    code = """
        await page.goto(%s, { waitUntil: 'domcontentloaded', timeout: 90000 });
        await page.waitForTimeout(1200);
        const anchors = await page.$$eval('a', (els) =>
          els.slice(0, %d).map((el, index) => ({
            href: el.href || '',
            text: (el.innerText || '').trim(),
            title: el.title || '',
            position: index + 1,
          }))
        );
        return JSON.stringify(anchors);
    """ % (json.dumps(url), max(1, min(int(max_links), 100)))
    try:
        result = execute_firecrawl_browser(session_id, code=code, language="node")
        return json.dumps({"success": True, "url": url, "result": result.get("result", "[]")}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc), "url": url}, ensure_ascii=False)
    finally:
        delete_firecrawl_browser(session_id)


@agent_tool(category="browser")
def crawlbase_fetch_page(url: str, javascript: bool = True) -> str:
    """Fetch a page through Crawlbase and return headers plus body length."""
    try:
        payload = crawlbase_fetch_url(url, javascript=javascript)
        return json.dumps(
            {
                "success": True,
                "url": url,
                "status_code": payload.get("status_code"),
                "headers": payload.get("headers", {}),
                "content_length": len(payload.get("content", "")),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc), "url": url}, ensure_ascii=False)