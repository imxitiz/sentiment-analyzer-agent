"""Scraping backends and extraction helpers for phase 3."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from Logging import context_logger, get_logger
from agents.services.scraper_runtime import available_registered_backends

from utils.camoufox import (
    camoufox_close_browser,
    camoufox_extract_text,
    camoufox_start_browser,
)
from utils.bluesky import get_bluesky_post_thread, resolve_bluesky_handle
from utils.crawlbase import crawlbase_fetch_url
from utils.firecrawl import scrape_firecrawl
from utils.hackernews import get_hn_item
from utils.rss import fetch_rss_feed
from utils.youtube import get_youtube_oembed

if TYPE_CHECKING:
    from agents.scraper.models import ScrapedContent, ScrapeRuntimeConfig, ScrapeTarget

logger = get_logger("agents.services.scraper_sources")

_PLATFORM_HINTS: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit.com",),
    "bluesky": ("bsky.app", "bsky.social"),
    "x": ("x.com", "twitter.com"),
    "twitter": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "hackernews": ("news.ycombinator.com",),
    "tiktok": ("tiktok.com",),
}
_CONTENT_TAGS = ("article", "main", "section", "body")
_DROP_SELECTORS = ("script", "style", "noscript", "svg", "nav", "footer", "header")


def available_scrape_backends(runtime: ScrapeRuntimeConfig) -> list[str]:
    """Return globally available scraping backends for the current runtime."""
    return available_registered_backends(runtime)


def classify_target_platform(target: ScrapeTarget) -> str:
    """Infer the best platform family from URL/domain hints."""
    platform = (target.platform or "").strip().lower()
    if platform and platform != "web":
        return platform

    host = (target.domain or urlparse(target.url).netloc).lower()
    path = urlparse(target.url).path.lower()
    if path.endswith(".xml") or "/feed" in path or path.endswith("/rss"):
        return "rss"
    for name, domains in _PLATFORM_HINTS.items():
        if any(domain in host for domain in domains):
            return name
    return "web"


def build_backend_plan(target: ScrapeTarget, runtime: ScrapeRuntimeConfig) -> list[str]:
    """Return an ordered list of backends to try for a target."""
    platform = classify_target_platform(target)
    available = set(available_scrape_backends(runtime))
    plan: list[str] = []

    if platform == "reddit":
        plan.append("reddit_json")
        plan.extend(["generic_http", "firecrawl", "camoufox", "crawlbase"])
    elif platform == "bluesky":
        plan.extend(["bluesky_public", "firecrawl", "camoufox", "generic_http", "crawlbase"])
    elif platform in {"youtube"}:
        plan.extend(["youtube_oembed", "generic_http", "firecrawl", "crawlbase", "camoufox"])
    elif platform == "hackernews":
        plan.extend(["hackernews_api", "generic_http", "firecrawl", "crawlbase", "camoufox"])
    elif platform == "rss":
        plan.extend(["rss_feed", "generic_http", "firecrawl", "crawlbase"])
    elif platform in {"facebook", "instagram", "tiktok", "x", "twitter"}:
        plan.extend(["firecrawl", "camoufox", "generic_http", "crawlbase"])
    else:
        plan.extend(["generic_http", "firecrawl", "crawlbase", "camoufox"])

    filtered: list[str] = []
    for backend in plan:
        if backend in {"reddit_json", "bluesky_public", "youtube_oembed", "hackernews_api", "rss_feed"} or backend in available:
            if backend not in filtered:
                filtered.append(backend)
    return filtered


async def scrape_target_with_backend(
    target: ScrapeTarget,
    *,
    backend: str,
    runtime: ScrapeRuntimeConfig,
) -> ScrapedContent:
    """Execute one scrape backend asynchronously."""
    return await asyncio.to_thread(_scrape_target_sync, target, backend, runtime)


def _scrape_target_sync(
    target: ScrapeTarget,
    backend: str,
    runtime: ScrapeRuntimeConfig,
) -> ScrapedContent:
    if backend == "reddit_json":
        return _scrape_reddit_json(target, runtime)
    if backend == "bluesky_public":
        return _scrape_bluesky_public(target, runtime)
    if backend == "youtube_oembed":
        return _scrape_youtube_oembed(target, runtime)
    if backend == "hackernews_api":
        return _scrape_hackernews_api(target, runtime)
    if backend == "rss_feed":
        return _scrape_rss_feed(target, runtime)
    if backend == "generic_http":
        return _scrape_generic_http(target, runtime)
    if backend == "firecrawl":
        return _scrape_firecrawl_backend(target, runtime)
    if backend == "crawlbase":
        return _scrape_crawlbase_backend(target, runtime)
    if backend == "camoufox":
        return _scrape_camoufox_backend(target, runtime)
    raise ValueError(f"Unknown scraping backend: {backend}")


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/133.0 Safari/537.36"
        )
    }


def _strip_text(value: str, limit: int | None = None) -> str:
    collapsed = re.sub(r"\s+", " ", value or "").strip()
    if limit is None:
        return collapsed
    return collapsed[:limit]


def _coerce_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def _extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            docs.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            docs.append(payload)
    return docs


def _meta_content(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def _extract_geo(soup: BeautifulSoup) -> dict[str, Any]:
    geo: dict[str, Any] = {}
    latitude = _meta_content(soup, "place:location:latitude")
    longitude = _meta_content(soup, "place:location:longitude")
    region = _meta_content(soup, "geo.region")
    placename = _meta_content(soup, "geo.placename")
    locale = _meta_content(soup, "og:locale")
    if latitude:
        geo["latitude"] = latitude
    if longitude:
        geo["longitude"] = longitude
    if region:
        geo["region"] = region
    if placename:
        geo["placename"] = placename
    if locale:
        geo["locale"] = locale
    return geo


def _extract_main_text(soup: BeautifulSoup) -> str:
    working = BeautifulSoup(str(soup), "html.parser")
    for selector in _DROP_SELECTORS:
        for tag in working.find_all(selector):
            tag.decompose()

    for candidate in _CONTENT_TAGS:
        node = working.find(candidate)
        if not node:
            continue
        text = _strip_text(node.get_text(" ", strip=True))
        if len(text) > 200:
            return text

    paragraphs = [
        _strip_text(tag.get_text(" ", strip=True))
        for tag in working.find_all(["p", "li", "blockquote"])
    ]
    paragraphs = [item for item in paragraphs if len(item) > 30]
    return "\n\n".join(paragraphs[:80])


def _extract_html_payload(
    *,
    url: str,
    final_url: str,
    html: str,
    backend: str,
    http_status: int | None,
    fallback_platform: str,
    raw_payload: dict[str, Any],
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    soup = BeautifulSoup(html, "html.parser")
    json_ld = _extract_json_ld(soup)
    title = _strip_text(
        _meta_content(soup, "og:title", "twitter:title")
        or (soup.title.get_text(strip=True) if soup.title else "")
    )
    description = _strip_text(
        _meta_content(soup, "description", "og:description", "twitter:description")
        or ""
    )
    author = _meta_content(soup, "author", "article:author")
    published_at = _meta_content(soup, "article:published_time", "pubdate", "date")
    language = _coerce_optional_string(
        (soup.html.get("lang") if soup.html else None) or _meta_content(soup, "og:locale")
    )
    site_name = _meta_content(soup, "og:site_name", "application-name")
    geo = _extract_geo(soup)
    main_text = _extract_main_text(soup)
    raw_text = _strip_text(soup.get_text(" ", strip=True))

    for item in json_ld:
        if not title:
            title = _strip_text(str(item.get("headline") or item.get("name") or ""))
        if not description:
            description = _strip_text(str(item.get("description") or ""))
        if not author:
            author_data = item.get("author")
            if isinstance(author_data, dict):
                author = str(author_data.get("name") or "") or None
            elif isinstance(author_data, list) and author_data:
                first = author_data[0]
                if isinstance(first, dict):
                    author = str(first.get("name") or "") or None
        if not published_at and item.get("datePublished"):
            published_at = str(item.get("datePublished"))
        if not main_text and item.get("articleBody"):
            main_text = _strip_text(str(item.get("articleBody")))

    content_items: list[dict[str, Any]] = []
    if main_text:
        content_items.append(
            {
                "kind": "article",
                "source_url": final_url,
                "title": title,
                "text": main_text,
                "author": author,
                "published_at": published_at,
                "geo": geo,
                "metadata": {
                    "site_name": site_name,
                    "language": language,
                },
            }
        )

    return ScrapedContent(
        fetch_backend=backend,
        normalized_url=url,
        final_url=final_url,
        platform=fallback_platform,
        domain=urlparse(final_url).netloc.lower(),
        title=title,
        description=description,
        author=author,
        published_at=published_at,
        language=language,
        site_name=site_name,
        content_text=main_text or raw_text,
        excerpt=(main_text or raw_text)[:400],
        raw_text=raw_text,
        raw_html=html,
        http_status=http_status,
        authors=[{"name": author}] if author else [],
        geo=geo,
        references=[
            {
                "kind": "source",
                "url": final_url,
                "label": site_name or title or final_url,
            }
        ],
        content_items=content_items,
        provenance={
            "backend": backend,
            "source_url": url,
            "final_url": final_url,
            "http_status": http_status,
        },
        metadata={
            "json_ld_count": len(json_ld),
            "title": title,
            "description": description,
        },
        raw_payload=raw_payload,
    )


def _scrape_generic_http(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    response = requests.get(
        target.url,
        headers=_request_headers(),
        timeout=max(10.0, float(runtime.source_timeout_seconds)),
        allow_redirects=True,
    )
    response.raise_for_status()
    return _extract_html_payload(
        url=target.normalized_url,
        final_url=response.url,
        html=response.text,
        backend="generic_http",
        http_status=response.status_code,
        fallback_platform=classify_target_platform(target),
        raw_payload={
            "headers": dict(response.headers),
            "status_code": response.status_code,
        },
    )


def _flatten_reddit_comments(
    nodes: list[dict[str, Any]], depth: int = 0
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for node in nodes:
        data = node.get("data", {})
        if node.get("kind") != "t1":
            continue
        body = _strip_text(str(data.get("body") or ""))
        if body:
            comments.append(
                {
                    "kind": "comment",
                    "author": data.get("author"),
                    "text": body,
                    "published_at": _utc_from_unix(data.get("created_utc")),
                    "depth": depth,
                    "metadata": {
                        "score": data.get("score"),
                        "subreddit": data.get("subreddit"),
                        "permalink": data.get("permalink"),
                    },
                }
            )
        replies = data.get("replies")
        if isinstance(replies, dict):
            child_nodes = replies.get("data", {}).get("children", [])
            comments.extend(_flatten_reddit_comments(child_nodes, depth=depth + 1))
    return comments


def _utc_from_unix(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except Exception:
        return None


def _scrape_reddit_json(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    parsed = urlparse(target.url)
    json_path = parsed.path.rstrip("/")
    if not json_path.endswith(".json"):
        json_path = f"{json_path}.json"
    json_url = f"https://www.reddit.com{json_path}"

    response = requests.get(
        json_url,
        headers={**_request_headers(), "Accept": "application/json"},
        timeout=max(10.0, float(runtime.source_timeout_seconds)),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Unexpected Reddit JSON payload.")

    post_node = payload[0].get("data", {}).get("children", [])
    if not post_node:
        raise RuntimeError("Reddit payload did not include a submission.")

    post = post_node[0].get("data", {})
    comments_root = (
        payload[1].get("data", {}).get("children", []) if len(payload) > 1 else []
    )
    comments = _flatten_reddit_comments(comments_root)
    title = _strip_text(str(post.get("title") or ""))
    body = _strip_text(str(post.get("selftext") or ""))
    content_text = "\n\n".join(item for item in [title, body] if item)

    content_items = [
        {
            "kind": "submission",
            "source_url": target.url,
            "title": title,
            "text": body or title,
            "author": post.get("author"),
            "published_at": _utc_from_unix(post.get("created_utc")),
            "metadata": {
                "subreddit": post.get("subreddit"),
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
                "permalink": post.get("permalink"),
            },
        }
    ]
    content_items.extend(comments)
    text_fragments = [
        text
        for item in content_items
        for text in [_coerce_optional_string(item.get("text"))]
        if text
    ]

    return ScrapedContent(
        fetch_backend="reddit_json",
        normalized_url=target.normalized_url,
        final_url=target.url,
        platform="reddit",
        domain="reddit.com",
        title=title,
        description=_strip_text(str(post.get("subreddit_name_prefixed") or "")),
        author=post.get("author"),
        published_at=_utc_from_unix(post.get("created_utc")),
        language="en",
        site_name="Reddit",
        content_text=content_text,
        excerpt=(body or title)[:400],
        raw_text="\n\n".join(text_fragments),
        http_status=response.status_code,
        authors=[{"name": post.get("author")}] if post.get("author") else [],
        geo={},
        engagement={
            "score": post.get("score"),
            "upvote_ratio": post.get("upvote_ratio"),
            "num_comments": post.get("num_comments"),
        },
        references=[
            {
                "kind": "permalink",
                "url": f"https://www.reddit.com{post.get('permalink')}"
                if post.get("permalink")
                else target.url,
                "label": title or target.url,
            }
        ],
        content_items=content_items,
        provenance={
            "backend": "reddit_json",
            "source_url": target.url,
            "final_url": target.url,
            "api_url": json_url,
        },
        metadata={
            "subreddit": post.get("subreddit"),
            "score": post.get("score"),
            "upvote_ratio": post.get("upvote_ratio"),
            "num_comments": post.get("num_comments"),
        },
        raw_payload={"reddit_json": payload},
    )


def _flatten_bluesky_replies(node: dict[str, Any], depth: int = 0) -> list[dict[str, Any]]:
    replies: list[dict[str, Any]] = []
    for child in node.get("replies", []) if isinstance(node, dict) else []:
        if not isinstance(child, dict):
            continue
        post = child.get("post", {}) if isinstance(child.get("post"), dict) else {}
        record = post.get("record", {}) if isinstance(post.get("record"), dict) else {}
        text = _strip_text(str(record.get("text") or ""))
        if text:
            replies.append(
                {
                    "kind": "reply",
                    "author": (post.get("author", {}) or {}).get("handle"),
                    "text": text,
                    "published_at": post.get("indexedAt") or record.get("createdAt"),
                    "depth": depth,
                    "metadata": {
                        "uri": post.get("uri"),
                        "cid": post.get("cid"),
                    },
                }
            )
        replies.extend(_flatten_bluesky_replies(child, depth=depth + 1))
    return replies


def _scrape_bluesky_public(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    parsed = urlparse(target.url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[0] != "profile" or parts[2] != "post":
        raise RuntimeError("Unsupported Bluesky URL format.")
    handle = parts[1]
    rkey = parts[3]
    did = resolve_bluesky_handle(handle)
    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    payload = get_bluesky_post_thread(uri, depth=max(2, min(runtime.max_retries_per_target + 3, 10)))

    thread = payload.get("thread")
    if not isinstance(thread, dict):
        raise RuntimeError("Bluesky thread payload missing thread data.")

    post = thread.get("post", {}) if isinstance(thread.get("post"), dict) else {}
    record = post.get("record", {}) if isinstance(post.get("record"), dict) else {}
    author = (post.get("author", {}) or {}).get("handle")
    title = _strip_text(str(target.title or f"Bluesky post by @{author or handle}"))
    text = _strip_text(str(record.get("text") or ""))
    replies = _flatten_bluesky_replies(thread)
    text_fragments = [text] if text else []
    text_fragments.extend(
        reply_text
        for item in replies
        for reply_text in [_coerce_optional_string(item.get("text"))]
        if reply_text
    )

    content_items: list[dict[str, Any]] = []
    if text:
        content_items.append(
            {
                "kind": "post",
                "source_url": target.url,
                "title": title,
                "author": author,
                "text": text,
                "published_at": post.get("indexedAt") or record.get("createdAt"),
                "metadata": {
                    "uri": post.get("uri"),
                    "reply_count": post.get("replyCount"),
                    "repost_count": post.get("repostCount"),
                    "like_count": post.get("likeCount"),
                    "quote_count": post.get("quoteCount"),
                },
            }
        )
    content_items.extend(replies)

    joined_text = "\n\n".join(text_fragments)
    return ScrapedContent(
        fetch_backend="bluesky_public",
        normalized_url=target.normalized_url,
        final_url=target.url,
        platform="bluesky",
        domain="bsky.app",
        title=title,
        description=target.description,
        author=author,
        published_at=post.get("indexedAt") or record.get("createdAt"),
        language="en",
        site_name="Bluesky",
        content_text=joined_text or text,
        excerpt=(joined_text or text)[:400],
        raw_text=joined_text or text,
        http_status=200,
        authors=[{"name": author, "handle": author}] if author else [],
        engagement={
            "reply_count": post.get("replyCount"),
            "repost_count": post.get("repostCount"),
            "like_count": post.get("likeCount"),
            "quote_count": post.get("quoteCount"),
        },
        references=[
            {
                "kind": "uri",
                "url": target.url,
                "label": str(post.get("uri") or target.url),
                "external_id": post.get("uri"),
            }
        ],
        content_items=content_items,
        provenance={
            "backend": "bluesky_public",
            "source_url": target.url,
            "thread_uri": post.get("uri"),
        },
        metadata={
            "uri": post.get("uri"),
            "reply_count": post.get("replyCount"),
            "repost_count": post.get("repostCount"),
            "like_count": post.get("likeCount"),
            "quote_count": post.get("quoteCount"),
        },
        raw_payload=payload,
    )


def _scrape_youtube_oembed(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    payload = get_youtube_oembed(
        target.url,
        timeout_seconds=max(8.0, float(runtime.source_timeout_seconds)),
    )
    title = _strip_text(str(payload.get("title") or target.title))
    author = _strip_text(str(payload.get("author_name") or "")) or None
    provider_name = _strip_text(str(payload.get("provider_name") or "YouTube"))
    description = _strip_text(str(target.description or "YouTube video metadata extracted from oEmbed."))
    text = "\n\n".join(item for item in [title, description] if item)
    return ScrapedContent(
        fetch_backend="youtube_oembed",
        normalized_url=target.normalized_url,
        final_url=target.url,
        platform="youtube",
        domain="youtube.com",
        title=title,
        description=description,
        author=author,
        site_name=provider_name,
        content_text=text,
        excerpt=text[:400],
        raw_text=text,
        http_status=200,
        authors=[{"name": author}] if author else [],
        references=[
            {
                "kind": "video",
                "url": target.url,
                "label": title or target.url,
            }
        ],
        content_items=[
            {
                "kind": "video",
                "source_url": target.url,
                "title": title,
                "author": author,
                "text": description,
                "metadata": {
                    "thumbnail_url": payload.get("thumbnail_url"),
                    "thumbnail_width": payload.get("thumbnail_width"),
                    "thumbnail_height": payload.get("thumbnail_height"),
                },
            }
        ],
        provenance={
            "backend": "youtube_oembed",
            "source_url": target.url,
            "provider": provider_name,
        },
        metadata={"provider": "youtube_oembed"},
        raw_payload=payload,
    )


def _flatten_hn_comments(item: dict[str, Any], runtime: ScrapeRuntimeConfig, depth: int = 0) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    kids = item.get("kids", [])
    if not isinstance(kids, list):
        return comments
    for kid in kids[:80]:
        if not isinstance(kid, int):
            continue
        child = get_hn_item(kid, timeout_seconds=max(8.0, float(runtime.source_timeout_seconds)))
        if child.get("type") != "comment":
            continue
        text = _strip_text(BeautifulSoup(str(child.get("text") or ""), "html.parser").get_text(" ", strip=True))
        if text:
            comments.append(
                {
                    "kind": "comment",
                    "author": child.get("by"),
                    "text": text,
                    "published_at": _utc_from_unix(child.get("time")),
                    "depth": depth,
                    "metadata": {"id": child.get("id"), "score": child.get("score")},
                }
            )
        if depth < 2:
            comments.extend(_flatten_hn_comments(child, runtime, depth=depth + 1))
    return comments


def _scrape_hackernews_api(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    parsed = urlparse(target.url)
    item_ids = parse_qs(parsed.query).get("id", [])
    if not item_ids:
        raise RuntimeError("Hacker News URL missing item id.")
    item_id = int(item_ids[0])
    story = get_hn_item(item_id, timeout_seconds=max(8.0, float(runtime.source_timeout_seconds)))
    comments = _flatten_hn_comments(story, runtime)
    story_text = _strip_text(BeautifulSoup(str(story.get("text") or ""), "html.parser").get_text(" ", strip=True))
    title = _strip_text(str(story.get("title") or target.title))
    description = _strip_text(str(target.description or "Hacker News story and discussion"))
    content_items = [
        {
            "kind": "story",
            "source_url": target.url,
            "title": title,
            "author": story.get("by"),
            "text": story_text or title,
            "published_at": _utc_from_unix(story.get("time")),
            "metadata": {
                "id": story.get("id"),
                "score": story.get("score"),
                "descendants": story.get("descendants"),
                "url": story.get("url"),
            },
        }
    ]
    content_items.extend(comments)
    text_fragments = [
        text
        for item in content_items
        for text in [_coerce_optional_string(item.get("text"))]
        if text
    ]
    joined_text = "\n\n".join(text_fragments)
    return ScrapedContent(
        fetch_backend="hackernews_api",
        normalized_url=target.normalized_url,
        final_url=target.url,
        platform="hackernews",
        domain="news.ycombinator.com",
        title=title,
        description=description,
        author=story.get("by"),
        published_at=_utc_from_unix(story.get("time")),
        site_name="Hacker News",
        content_text=joined_text,
        excerpt=joined_text[:400],
        raw_text=joined_text,
        http_status=200,
        authors=[{"name": story.get("by")}] if story.get("by") else [],
        engagement={
            "score": story.get("score"),
            "descendants": story.get("descendants"),
        },
        references=[
            {
                "kind": "story_url",
                "url": story.get("url") or target.url,
                "label": title or target.url,
            }
        ],
        content_items=content_items,
        provenance={
            "backend": "hackernews_api",
            "source_url": target.url,
            "story_id": story.get("id"),
        },
        metadata={
            "story_id": story.get("id"),
            "score": story.get("score"),
            "descendants": story.get("descendants"),
            "story_url": story.get("url"),
        },
        raw_payload={"story": story},
    )


def _scrape_rss_feed(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    payload = fetch_rss_feed(
        target.url,
        timeout_seconds=max(8.0, float(runtime.source_timeout_seconds)),
        max_items=40,
    )
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        raise RuntimeError("Feed payload did not return any entries.")
    content_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = _strip_text(str(item.get("description") or item.get("title") or ""))
        content_items.append(
            {
                "kind": "feed_item",
                "source_url": item.get("link") or target.url,
                "title": _strip_text(str(item.get("title") or "")),
                "text": text,
                "author": item.get("author"),
                "published_at": item.get("published_at"),
                "metadata": {
                    "link": item.get("link"),
                    "guid": item.get("guid"),
                },
            }
        )
    text_fragments = [
        text
        for item in content_items
        for text in [_coerce_optional_string(item.get("text"))]
        if text
    ]
    joined_text = "\n\n".join(text_fragments)
    parsed = urlparse(target.url)
    return ScrapedContent(
        fetch_backend="rss_feed",
        normalized_url=target.normalized_url,
        final_url=target.url,
        platform="rss",
        domain=(parsed.netloc or target.domain or "").lower(),
        title=_strip_text(str(payload.get("title") or target.title)),
        description=_strip_text(str(payload.get("description") or target.description)),
        site_name=_strip_text(str(payload.get("title") or parsed.netloc)),
        content_text=joined_text,
        excerpt=joined_text[:400],
        raw_text=joined_text,
        raw_html=None,
        http_status=200,
        references=[
            {
                "kind": "feed",
                "url": target.url,
                "label": _strip_text(str(payload.get("title") or target.url)),
            }
        ],
        content_items=content_items,
        provenance={
            "backend": "rss_feed",
            "source_url": target.url,
            "feed_link": payload.get("link"),
        },
        metadata={
            "format": payload.get("format"),
            "feed_link": payload.get("link"),
            "item_count": len(content_items),
        },
        raw_payload=payload,
    )


def _scrape_firecrawl_backend(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    payload = scrape_firecrawl(
        target.url,
        formats=["markdown", "html", "links"],
        timeout_seconds=max(20.0, float(runtime.source_timeout_seconds)),
        only_main_content=False,
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    html = str(data.get("html") or "")
    markdown = str(data.get("markdown") or "")
    if html:
        extracted = _extract_html_payload(
            url=target.normalized_url,
            final_url=str(data.get("metadata", {}).get("sourceURL") or target.url),
            html=html,
            backend="firecrawl",
            http_status=200,
            fallback_platform=classify_target_platform(target),
            raw_payload=payload,
        )
        extracted.markdown = markdown or None
        if markdown and not extracted.content_text:
            extracted.content_text = markdown
            extracted.raw_text = markdown
        return extracted

    text = markdown.strip()
    if not text:
        raise RuntimeError("Firecrawl returned no HTML or markdown content.")
    return ScrapedContent(
        fetch_backend="firecrawl",
        normalized_url=target.normalized_url,
        final_url=target.url,
        platform=classify_target_platform(target),
        domain=(target.domain or urlparse(target.url).netloc).lower(),
        title=target.title,
        description=target.description,
        content_text=text,
        excerpt=text[:400],
        raw_text=text,
        markdown=markdown,
        http_status=200,
        references=[
            {"kind": "source", "url": target.url, "label": target.title or target.url}
        ],
        content_items=[{"kind": "document", "title": target.title, "text": text}],
        provenance={"backend": "firecrawl", "source_url": target.url},
        metadata={"provider": "firecrawl"},
        raw_payload=payload,
    )


def _scrape_crawlbase_backend(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    payload = crawlbase_fetch_url(
        target.url,
        javascript=True,
        timeout_seconds=max(20.0, float(runtime.source_timeout_seconds)),
    )
    return _extract_html_payload(
        url=target.normalized_url,
        final_url=target.url,
        html=str(payload.get("content") or ""),
        backend="crawlbase",
        http_status=int(payload.get("status_code") or 200),
        fallback_platform=classify_target_platform(target),
        raw_payload=payload,
    )


def _scrape_camoufox_backend(
    target: ScrapeTarget, runtime: ScrapeRuntimeConfig
) -> ScrapedContent:
    from agents.scraper.models import ScrapedContent

    session = camoufox_start_browser(
        start_url=target.url,
        timeout_seconds=max(20.0, float(runtime.source_timeout_seconds)),
    )
    session_id = str(session["session_id"])
    try:
        payload = camoufox_extract_text(session_id, selector="body", max_chars=30000)
    finally:
        camoufox_close_browser(session_id)

    text = _strip_text(str(payload.get("text") or ""))
    if not text:
        raise RuntimeError("Camoufox did not extract any text.")
    return ScrapedContent(
        fetch_backend="camoufox",
        normalized_url=target.normalized_url,
        final_url=str(payload.get("url") or target.url),
        platform=classify_target_platform(target),
        domain=(target.domain or urlparse(target.url).netloc).lower(),
        title=_strip_text(str(payload.get("title") or target.title)),
        description=target.description,
        content_text=text,
        excerpt=text[:400],
        raw_text=text,
        http_status=200,
        references=[
            {
                "kind": "rendered_source",
                "url": str(payload.get("url") or target.url),
                "label": _strip_text(str(payload.get("title") or target.title or target.url)),
            }
        ],
        content_items=[
            {
                "kind": "rendered_document",
                "source_url": str(payload.get("url") or target.url),
                "title": payload.get("title"),
                "text": text,
            }
        ],
        provenance={
            "backend": "camoufox",
            "source_url": target.url,
            "rendered_url": str(payload.get("url") or target.url),
            "session_mode": session.get("mode"),
        },
        metadata={"provider": "camoufox", "mode": session.get("mode")},
        raw_payload=payload,
    )


__all__ = [
    "available_scrape_backends",
    "build_backend_plan",
    "classify_target_platform",
    "scrape_target_with_backend",
]
