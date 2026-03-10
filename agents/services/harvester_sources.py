"""Reusable harvesting sources and browser expanders."""

from __future__ import annotations

import asyncio
import json
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, urljoin

from Logging import context_logger
from env import config
from utils import (
    crawlbase_fetch_url,
    create_firecrawl_browser_session,
    delete_firecrawl_browser,
    execute_firecrawl_browser,
    search_firecrawl,
    search_google_serper,
)

from agents.harvester.models import (
    HarvestedLink,
    HarvestSourceResult,
    HarvestTaskPlan,
    HarvesterRuntimeConfig,
    ResearchBrief,
)
from .harvester_store import extract_domain, infer_platform, normalize_url, score_link


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href = ""
        self._current_title = ""
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        self._current_href = attrs_dict.get("href") or ""
        self._current_title = attrs_dict.get("title") or ""
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._current_href:
            return
        self.links.append(
            {
                "href": self._current_href,
                "title": self._current_title,
                "text": " ".join(item for item in self._current_text if item).strip(),
            }
        )
        self._current_href = ""
        self._current_title = ""
        self._current_text = []


def _build_platform_queries(brief: ResearchBrief) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    if brief.search_queries:
        for query in brief.search_queries:
            queries.append((query, "web"))

    platform_priority = [item.get("name", "web").lower() for item in brief.platforms]
    domains = {
        "reddit": "site:reddit.com",
        "twitter": "site:x.com OR site:twitter.com",
        "x": "site:x.com OR site:twitter.com",
        "facebook": "site:facebook.com",
        "youtube": "site:youtube.com",
        "tiktok": "site:tiktok.com",
        "news": "site:news.google.com OR site:reuters.com OR site:apnews.com",
    }
    for platform_name in platform_priority[:6]:
        operator = domains.get(platform_name)
        if not operator:
            continue
        queries.append((f"{brief.topic} {operator}", platform_name))

    if not queries:
        queries.append((brief.topic, "web"))
    return list(dict.fromkeys(queries))


def build_fallback_harvest_tasks(
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
) -> list[HarvestTaskPlan]:
    """Create deterministic harvesting tasks when LLM planning is unavailable."""
    tasks: list[HarvestTaskPlan] = []
    source_names: list[str] = ["serper"]
    if runtime.enable_firecrawl and config.get("FIRECRAWL_API_KEY"):
        source_names.append("firecrawl_search")
    if runtime.enable_serpapi and config.get("SERPAPI_API_KEY"):
        source_names.append("serpapi")
    # camoufox can function locally or via CLI, endpoint not strictly required
    if runtime.enable_camoufox:
        source_names.append("camoufox_browser")

    for query, platform_hint in _build_platform_queries(brief)[:10]:
        tasks.append(
            HarvestTaskPlan(
                query=query,
                platform_hint=platform_hint,
                source_names=source_names,
                target_results=runtime.per_query_limit,
                rationale=f"Deterministic fallback task for {platform_hint} discovery.",
            )
        )
    return tasks


async def collect_serper_results(
    task: HarvestTaskPlan,
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Collect links using Serper."""
    log = context_logger(
        "agents.services.harvester_sources.serper",
        actor=actor,
        phase="HARVESTER",
        topic=brief.topic,
    )
    data = await asyncio.to_thread(
        search_google_serper,
        task.query,
        max_results=min(runtime.per_query_limit, task.target_results),
    )
    organic = data.get("organic", [])
    links: list[HarvestedLink] = []
    for index, item in enumerate(organic, start=1):
        url = item.get("link", "")
        if not normalize_url(url):
            continue
        links.append(
            HarvestedLink(
                url=url,
                title=item.get("title", ""),
                description=item.get("snippet", ""),
                platform=infer_platform(url, task.platform_hint),
                source_name="serper",
                source_type="search",
                discovery_query=task.query,
                position=index,
                domain=extract_domain(url),
                quality_signal=max(0.0, 0.2 - (index - 1) * 0.01),
                relevance_signal=0.1,
                metadata={
                    "engine": "serper",
                    "demo": bool(data.get("demo", False)),
                    "knowledge_graph": data.get("knowledgeGraph", {}),
                },
                raw_payload=item,
            )
        )
    log.info(
        "Serper collected %d candidates",
        len(links),
        action="serper_collect",
        meta={"query": task.query, "demo": bool(data.get("demo", False))},
    )
    return HarvestSourceResult(
        source_name="serper",
        source_type="search",
        links=links,
        meta={"demo": bool(data.get("demo", False))},
    )


async def collect_firecrawl_results(
    task: HarvestTaskPlan,
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Collect links using Firecrawl search."""
    if not config.get("FIRECRAWL_API_KEY"):
        return HarvestSourceResult(
            source_name="firecrawl_search",
            source_type="search",
            warnings=["FIRECRAWL_API_KEY is not configured."],
        )
    data = await asyncio.to_thread(
        search_firecrawl,
        task.query,
        limit=min(runtime.per_query_limit, task.target_results),
        sources=["web", "news"],
        tbs="sbd:1,qdr:m",
        timeout_ms=runtime.source_timeout_seconds * 1000,
    )
    buckets = data.get("data", {})
    entries = [*buckets.get("web", []), *buckets.get("news", [])]
    links: list[HarvestedLink] = []
    for index, item in enumerate(entries, start=1):
        url = item.get("url", "")
        if not normalize_url(url):
            continue
        links.append(
            HarvestedLink(
                url=url,
                title=item.get("title", ""),
                description=item.get("description", "") or item.get("snippet", ""),
                platform=infer_platform(url, task.platform_hint),
                source_name="firecrawl_search",
                source_type="search",
                discovery_query=task.query,
                position=index,
                domain=extract_domain(url),
                published_at=item.get("date"),
                quality_signal=0.18,
                relevance_signal=0.12,
                metadata={
                    "firecrawl_id": data.get("id"),
                    "credits_used": data.get("creditsUsed"),
                    "warning": data.get("warning"),
                },
                raw_payload=item,
            )
        )
    return HarvestSourceResult(
        source_name="firecrawl_search",
        source_type="search",
        links=links,
        warnings=[warning for warning in [data.get("warning")] if warning],
        meta={"credits_used": data.get("creditsUsed")},
    )


async def collect_serpapi_results(
    task: HarvestTaskPlan,
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Collect links using SerpAPI."""
    if not config.get("SERPAPI_API_KEY"):
        return HarvestSourceResult(
            source_name="serpapi",
            source_type="search",
            warnings=["SERPAPI_API_KEY is not configured."],
        )
    # simple GET request to serpapi.com/search
    try:
        params = {
            "q": task.query,
            "api_key": config.get("SERPAPI_API_KEY"),
            "num": min(runtime.per_query_limit, task.target_results),
        }
        import requests

        response = requests.get("https://serpapi.com/search", params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return HarvestSourceResult(
            source_name="serpapi",
            source_type="search",
            warnings=[f"SerpAPI error: {exc}"],
        )
    organic = data.get("organic_results", [])
    links: list[HarvestedLink] = []
    for index, item in enumerate(organic, start=1):
        url = item.get("link") or item.get("url") or ""
        if not normalize_url(url):
            continue
        links.append(
            HarvestedLink(
                url=url,
                title=item.get("title", ""),
                description=item.get("snippet", ""),
                platform=infer_platform(url, task.platform_hint),
                source_name="serpapi",
                source_type="search",
                discovery_query=task.query,
                position=index,
                domain=extract_domain(url),
                quality_signal=0.15,
                relevance_signal=0.1,
                metadata={"engine": "serpapi"},
                raw_payload=item,
            )
        )
    return HarvestSourceResult(
        source_name="serpapi",
        source_type="search",
        links=links,
    )


async def collect_camoufox_browser_results(
    task: HarvestTaskPlan,
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Collect links using a Camoufox anti-detect browser.

    The underlying helper (:func:`utils.camoufox.camoufox_fetch_anchors`)
    automatically selects a backend (remote, local Python, CLI) based on
    configuration.  We simply delegate and translate the result into
    ``HarvestSourceResult``.
    """
    try:
        from utils.camoufox import camoufox_fetch_anchors

        payload = camoufox_fetch_anchors(task.query, max_links=runtime.per_query_limit)
        anchors = payload.get("anchors", []) if isinstance(payload, dict) else []
    except Exception as exc:
        return HarvestSourceResult(
            source_name="camoufox_browser",
            source_type="browser",
            warnings=[f"Camoufox error: {exc}"],
        )
    links: list[HarvestedLink] = []
    for index, item in enumerate(anchors, start=1):
        url = item.get("href", "")
        if not normalize_url(url):
            continue
        links.append(
            HarvestedLink(
                url=url,
                title=item.get("title", "") or item.get("text", ""),
                description="Discovered via Camoufox browser",
                platform=infer_platform(url, task.platform_hint),
                source_name="camoufox_browser",
                source_type="browser",
                discovery_query=task.query,
                position=index,
                domain=extract_domain(url),
                quality_signal=0.05,
                relevance_signal=0.05,
                metadata={"camoufox": True},
                raw_payload=item,
            )
        )
    return HarvestSourceResult(
        source_name="camoufox_browser",
        source_type="browser",
        links=links,
    )


def _browser_search_urls(task: HarvestTaskPlan) -> list[str]:
    encoded = quote_plus(task.query)
    platform = task.platform_hint.lower()
    if platform == "reddit":
        return [f"https://www.reddit.com/search/?q={encoded}"]
    if platform in {"news", "web"}:
        return [
            f"https://news.google.com/search?q={encoded}",
            f"https://duckduckgo.com/?q={encoded}",
        ]
    return [f"https://duckduckgo.com/?q={encoded}"]


async def collect_firecrawl_browser_results(
    task: HarvestTaskPlan,
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Collect links from rendered search pages using Firecrawl browser."""
    if not runtime.enable_browser_discovery or not config.get("FIRECRAWL_API_KEY"):
        return HarvestSourceResult(
            source_name="firecrawl_browser",
            source_type="browser",
            warnings=["Firecrawl browser discovery is unavailable."],
        )

    collected: list[HarvestedLink] = []
    warnings: list[str] = []
    for search_url in _browser_search_urls(task)[:2]:
        session = await asyncio.to_thread(
            create_firecrawl_browser_session,
            ttl=max(90, runtime.source_timeout_seconds),
            activity_ttl=max(60, runtime.source_timeout_seconds // 2),
        )
        session_id = str(session.get("id", ""))
        if not session_id:
            warnings.append("Browser session was not created.")
            continue
        code = """
            await page.goto(%s, { waitUntil: 'domcontentloaded', timeout: %d });
            await page.waitForTimeout(1500);
            const anchors = await page.$$eval('a', (els) =>
              els.slice(0, %d).map((el, index) => ({
                href: el.href || '',
                text: (el.innerText || '').trim(),
                title: el.title || '',
                position: index + 1,
              }))
            );
            return JSON.stringify(anchors);
        """ % (json.dumps(search_url), runtime.source_timeout_seconds * 1000, runtime.expansion_per_seed_limit)
        try:
            execution = await asyncio.to_thread(
                execute_firecrawl_browser,
                session_id,
                code=code,
                language="node",
                timeout_seconds=max(30.0, float(runtime.source_timeout_seconds)),
            )
            raw_result = execution.get("result", "[]")
            anchors = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            for item in anchors:
                url = item.get("href", "")
                if not normalize_url(url):
                    continue
                collected.append(
                    HarvestedLink(
                        url=url,
                        title=item.get("title", "") or item.get("text", ""),
                        description=f"Discovered via browser search page {search_url}",
                        platform=infer_platform(url, task.platform_hint),
                        source_name="firecrawl_browser",
                        source_type="browser",
                        discovery_query=task.query,
                        position=item.get("position"),
                        domain=extract_domain(url),
                        quality_signal=0.08,
                        relevance_signal=0.08,
                        metadata={"search_page": search_url, "anchor_text": item.get("text", "")},
                        raw_payload=item,
                    )
                )
        except Exception as exc:
            warnings.append(str(exc))
        finally:
            await asyncio.to_thread(delete_firecrawl_browser, session_id)

    return HarvestSourceResult(
        source_name="firecrawl_browser",
        source_type="browser",
        links=collected,
        warnings=warnings,
    )


async def expand_with_crawlbase(
    seed_links: list[HarvestedLink],
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Expand high-quality seed pages and extract outbound links with Crawlbase."""
    if not runtime.enable_crawlbase:
        return HarvestSourceResult(
            source_name="crawlbase_expand",
            source_type="expansion",
            warnings=["Crawlbase expansion disabled."],
        )
    if not (config.get("CRAWLBASE_JS_TOKEN") or config.get("CRAWLBASE_TOKEN")):
        return HarvestSourceResult(
            source_name="crawlbase_expand",
            source_type="expansion",
            warnings=["Crawlbase token is not configured."],
        )

    collected: list[HarvestedLink] = []
    warnings: list[str] = []
    for seed in seed_links[: runtime.expansion_seed_limit]:
        try:
            payload = await asyncio.to_thread(
                crawlbase_fetch_url,
                seed.url,
                javascript=True,
                timeout_seconds=max(90.0, float(runtime.source_timeout_seconds)),
            )
            parser = _AnchorExtractor()
            parser.feed(str(payload.get("content", "")))
            for index, item in enumerate(parser.links[: runtime.expansion_per_seed_limit], start=1):
                joined = urljoin(seed.url, item.get("href", ""))
                if not normalize_url(joined):
                    continue
                collected.append(
                    HarvestedLink(
                        url=joined,
                        title=item.get("title", "") or item.get("text", ""),
                        description=f"Expanded from seed {seed.url}",
                        platform=infer_platform(joined, seed.platform),
                        source_name="crawlbase_expand",
                        source_type="expansion",
                        discovery_query=seed.discovery_query,
                        position=index,
                        domain=extract_domain(joined),
                        quality_signal=0.03,
                        relevance_signal=0.02,
                        metadata={"anchor_text": item.get("text", ""), "seed_url": seed.url},
                        raw_payload=item,
                    )
                )
        except Exception as exc:
            warnings.append(f"{seed.url}: {exc}")

    return HarvestSourceResult(
        source_name="crawlbase_expand",
        source_type="expansion",
        links=collected,
        warnings=warnings,
    )


def select_expansion_seeds(
    candidates: list[HarvestedLink],
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
) -> list[HarvestedLink]:
    """Select the strongest candidates for page expansion."""
    scored: list[tuple[float, HarvestedLink]] = []
    for link in candidates:
        quality, relevance, rejection = score_link(link, brief)
        if rejection:
            continue
        scored.append((quality + relevance, link))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [link for _, link in scored[: runtime.expansion_seed_limit]]


__all__ = [
    "build_fallback_harvest_tasks",
    "collect_firecrawl_browser_results",
    "collect_firecrawl_results",
    "collect_serper_results",
    "collect_serpapi_results",
    "collect_camoufox_browser_results",
    "expand_with_crawlbase",
    "select_expansion_seeds",
]