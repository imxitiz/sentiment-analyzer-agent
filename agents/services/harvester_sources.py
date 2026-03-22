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
        if runtime.enable_camoufox_agentic:
            source_names.append("camoufox_agentic")

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
    from utils.camoufox import camoufox_fetch_anchors

    anchors: list[dict[str, Any]] = []
    warnings: list[str] = []
    max_links = min(runtime.per_query_limit, max(1, task.target_results))
    for search_url in _browser_search_urls(task)[:2]:
        try:
            payload = await asyncio.to_thread(
                camoufox_fetch_anchors,
                search_url,
                max_links=max_links,
                timeout_seconds=max(60.0, float(runtime.source_timeout_seconds)),
                headless=True,
            )
            result_anchors = (
                payload.get("anchors", []) if isinstance(payload, dict) else []
            )
            for item in result_anchors:
                item_copy = dict(item)
                item_copy.setdefault("search_page", search_url)
                anchors.append(item_copy)
        except Exception as exc:
            warnings.append(f"Camoufox error: {exc}")

    if not anchors and warnings:
        return HarvestSourceResult(
            source_name="camoufox_browser",
            source_type="browser",
            warnings=warnings,
        )

    links: list[HarvestedLink] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(anchors, start=1):
        url = item.get("href", "")
        normalized_url = normalize_url(url)
        if not normalized_url:
            continue
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        domain = extract_domain(url)
        title = item.get("title", "") or item.get("text", "")
        anchor_text = item.get("text", "")
        if _is_search_engine_domain(domain):
            continue
        if _is_low_signal_browser_link(href=url, title=title, text=anchor_text):
            continue

        candidate = HarvestedLink(
            url=normalized_url,
            title=title,
            description="Discovered via Camoufox browser",
            platform=infer_platform(normalized_url, task.platform_hint),
            source_name="camoufox_browser",
            source_type="browser",
            discovery_query=task.query,
            position=index,
            domain=domain,
            quality_signal=0.03,
            relevance_signal=_sentiment_evidence_bonus(title=title, text=anchor_text),
            metadata={
                "camoufox": True,
                "search_page": item.get("search_page", ""),
                "anchor_text": anchor_text,
            },
            raw_payload=item,
        )
        quality, _, rejection = score_link(candidate, brief)
        if rejection:
            continue
        if quality < max(runtime.min_quality_score, 0.5):
            continue
        links.append(candidate)
    return HarvestSourceResult(
        source_name="camoufox_browser",
        source_type="browser",
        links=links,
        warnings=warnings,
    )


def _is_search_engine_domain(domain: str) -> bool:
    lowered = (domain or "").lower()
    return any(
        lowered.endswith(host)
        for host in (
            "google.com",
            "google.com.np",
            "accounts.google.com",
            "duckduckgo.com",
            "bing.com",
            "yahoo.com",
            "news.google.com",
        )
    )


def _is_navigable_href(href: str) -> bool:
    value = (href or "").strip().lower()
    if not value:
        return False
    if value.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False
    return bool(normalize_url(href))


def _is_low_signal_browser_link(*, href: str, title: str, text: str) -> bool:
    lowered_href = (href or "").lower()
    lowered_title = (title or "").strip().lower()
    lowered_text = (text or "").strip().lower()

    if any(token in lowered_href for token in ("&ia=", "&iax=", "&iaxm=", "assist=")):
        return True
    if "?q=" in lowered_href and any(
        host in lowered_href
        for host in ("duckduckgo.com", "google.com/search", "bing.com/search")
    ):
        return True
    if any(
        token in lowered_href
        for token in ("/servicelogin", "/signin", "/sign-in", "/accounts/")
    ):
        return True
    if lowered_title in {"all", "images", "videos", "news", "maps", "home", "sign in"}:
        return True
    if lowered_text in {"all", "images", "videos", "news", "maps", "home", "sign in"}:
        return True
    return False


def _sentiment_evidence_bonus(*, title: str, text: str) -> float:
    combined = f"{title} {text}".lower()
    evidence_terms = (
        "opinion",
        "reaction",
        "debate",
        "support",
        "oppose",
        "concern",
        "praise",
        "critic",
        "comment",
        "discussion",
        "review",
    )
    matches = sum(1 for term in evidence_terms if term in combined)
    return min(0.2, matches * 0.02)


async def collect_camoufox_agentic_results(
    task: HarvestTaskPlan,
    *,
    brief: ResearchBrief,
    runtime: HarvesterRuntimeConfig,
    actor: str,
) -> HarvestSourceResult:
    """Collect links using a stateful Camoufox browser workflow.

    This collector simulates multi-step browsing: open rendered search pages,
    rank candidate links, navigate into top seeds, and optionally traverse one
    additional hop to discover discussion-rich pages.
    """
    from utils.camoufox import (
        camoufox_close_browser,
        camoufox_extract_links,
        camoufox_extract_text,
        camoufox_is_available,
        camoufox_navigate,
        camoufox_start_browser,
    )

    log = context_logger(
        "agents.services.harvester_sources.camoufox_agentic",
        actor=actor,
        phase="HARVESTER",
        topic=brief.topic,
    )

    if not camoufox_is_available():
        return HarvestSourceResult(
            source_name="camoufox_agentic",
            source_type="browser",
            warnings=["Camoufox is not available in this environment."],
        )

    links: list[HarvestedLink] = []
    warnings: list[str] = []
    max_links_per_page = max(5, runtime.camoufox_agentic_links_per_page)
    max_seed_pages = max(1, runtime.camoufox_agentic_max_seed_pages)
    max_hops = max(1, runtime.camoufox_agentic_max_hops)

    def _normalize_candidates(anchors: list[dict[str, Any]]) -> list[HarvestedLink]:
        candidates: list[HarvestedLink] = []
        for index, item in enumerate(anchors, start=1):
            url = str(item.get("href", "")).strip()
            normalized = normalize_url(url)
            if not normalized:
                continue
            domain = extract_domain(normalized)
            if _is_search_engine_domain(domain):
                continue
            title = str(item.get("title", "") or item.get("text", ""))
            anchor_text = str(item.get("text", ""))
            if _is_low_signal_browser_link(
                href=normalized, title=title, text=anchor_text
            ):
                continue
            candidates.append(
                HarvestedLink(
                    url=normalized,
                    title=title,
                    description=anchor_text,
                    platform=infer_platform(normalized, task.platform_hint),
                    source_name="camoufox_agentic",
                    source_type="browser",
                    discovery_query=task.query,
                    position=index,
                    domain=domain,
                    quality_signal=0.09,
                    relevance_signal=0.08,
                    metadata={"hop": 0, "anchor_text": anchor_text},
                    raw_payload=dict(item),
                )
            )
        ranked: list[tuple[float, HarvestedLink]] = []
        for candidate in candidates:
            quality, relevance, rejection = score_link(candidate, brief)
            if rejection:
                continue
            ranked.append((quality + relevance, candidate))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked[:max_seed_pages]]

    def _run_session_sync() -> tuple[list[HarvestedLink], list[str]]:
        local_links: list[HarvestedLink] = []
        local_warnings: list[str] = []
        visited: set[str] = set()
        session_id = ""

        try:
            session = camoufox_start_browser(
                headless=True,
                main_world_eval=True,
                timeout_seconds=max(60.0, float(runtime.source_timeout_seconds)),
            )
            session_id = str(session.get("session_id", ""))
            if not session_id:
                return local_links, ["Camoufox session did not return a session_id."]

            seed_candidates: list[HarvestedLink] = []
            for search_url in _browser_search_urls(task)[:3]:
                try:
                    camoufox_navigate(
                        session_id,
                        search_url,
                        timeout_seconds=max(
                            45.0, float(runtime.source_timeout_seconds)
                        ),
                    )
                    extracted = camoufox_extract_links(
                        session_id,
                        max_links=max_links_per_page,
                    )
                    anchors = extracted.get("anchors", [])
                    seed_candidates.extend(_normalize_candidates(anchors))
                except Exception as exc:
                    local_warnings.append(
                        f"Search navigation failed for {search_url}: {exc}"
                    )

            frontier: list[str] = []
            for candidate in seed_candidates:
                normalized = normalize_url(candidate.url)
                if not normalized or normalized in visited:
                    continue
                visited.add(normalized)
                frontier.append(normalized)

            for hop in range(1, max_hops + 1):
                if not frontier:
                    break
                next_frontier: list[str] = []
                for seed_url in frontier[:max_seed_pages]:
                    try:
                        camoufox_navigate(
                            session_id,
                            seed_url,
                            timeout_seconds=max(
                                45.0, float(runtime.source_timeout_seconds)
                            ),
                        )
                        page_text = camoufox_extract_text(
                            session_id,
                            selector="body",
                            max_chars=max(300, runtime.camoufox_agentic_extract_chars),
                        )
                        title = str(page_text.get("title", ""))
                        text = str(page_text.get("text", ""))
                        if _is_low_signal_browser_link(
                            href=seed_url, title=title, text=text[:120]
                        ):
                            continue

                        link = HarvestedLink(
                            url=seed_url,
                            title=title,
                            description=text[:220],
                            platform=infer_platform(seed_url, task.platform_hint),
                            source_name="camoufox_agentic",
                            source_type="browser",
                            discovery_query=task.query,
                            domain=extract_domain(seed_url),
                            quality_signal=0.1 + max(0.0, 0.03 * (max_hops - hop)),
                            relevance_signal=0.08
                            + _sentiment_evidence_bonus(title=title, text=text),
                            metadata={"hop": hop},
                            raw_payload={
                                "title": title,
                                "text_preview": text[:500],
                                "hop": hop,
                            },
                        )
                        quality, relevance, rejection = score_link(link, brief)
                        if rejection:
                            continue
                        if quality < max(runtime.min_quality_score, 0.5):
                            continue
                        if relevance < 0.35:
                            continue
                        local_links.append(link)

                        if hop >= max_hops:
                            continue

                        outbound = camoufox_extract_links(
                            session_id,
                            max_links=max(10, max_links_per_page // 2),
                        )
                        for item in outbound.get("anchors", []):
                            href = str(item.get("href", "")).strip()
                            if not _is_navigable_href(href):
                                continue
                            normalized = normalize_url(href)
                            if not normalized or normalized in visited:
                                continue
                            domain = extract_domain(normalized)
                            title_hint = str(
                                item.get("title", "") or item.get("text", "")
                            )
                            text_hint = str(item.get("text", ""))
                            if _is_search_engine_domain(domain):
                                continue
                            if _is_low_signal_browser_link(
                                href=normalized,
                                title=title_hint,
                                text=text_hint,
                            ):
                                continue
                            visited.add(normalized)
                            next_frontier.append(normalized)
                    except Exception as exc:
                        local_warnings.append(
                            f"Seed navigation failed for {seed_url}: {exc}"
                        )

                frontier = next_frontier

            if not local_links:
                local_warnings.append(
                    "Camoufox agentic run produced no navigable candidates."
                )
            return local_links, local_warnings
        finally:
            if session_id:
                try:
                    camoufox_close_browser(session_id)
                except Exception:
                    pass

    links, warnings = await asyncio.to_thread(_run_session_sync)
    log.info(
        "Camoufox agentic collector finished",
        action="camoufox_agentic_collect",
        meta={
            "query": task.query,
            "collected": len(links),
            "warnings": len(warnings),
        },
    )
    return HarvestSourceResult(
        source_name="camoufox_agentic",
        source_type="browser",
        links=links,
        warnings=warnings,
    )


def _browser_search_urls(task: HarvestTaskPlan) -> list[str]:
    encoded = quote_plus(task.query)
    platform = task.platform_hint.lower()
    if "reddit" in platform:
        return [f"https://www.reddit.com/search/?q={encoded}"]
    if "youtube" in platform:
        return [
            f"https://www.youtube.com/results?search_query={encoded}",
            f"https://duckduckgo.com/?q=site%3Ayoutube.com+{encoded}",
        ]
    if "facebook" in platform:
        return [f"https://duckduckgo.com/?q=site%3Afacebook.com+{encoded}"]
    if "instagram" in platform:
        return [f"https://duckduckgo.com/?q=site%3Ainstagram.com+{encoded}"]
    if "news" in platform or platform == "news":
        return [
            f"https://duckduckgo.com/?q={encoded}",
            f"https://www.bing.com/search?q={encoded}",
        ]
    return [
        f"https://duckduckgo.com/?q={encoded}",
        f"https://www.bing.com/search?q={encoded}",
    ]


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
        """ % (
            json.dumps(search_url),
            runtime.source_timeout_seconds * 1000,
            runtime.expansion_per_seed_limit,
        )
        try:
            execution = await asyncio.to_thread(
                execute_firecrawl_browser,
                session_id,
                code=code,
                language="node",
                timeout_seconds=max(30.0, float(runtime.source_timeout_seconds)),
            )
            raw_result = execution.get("result", "[]")
            anchors = (
                json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            )
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
                        metadata={
                            "search_page": search_url,
                            "anchor_text": item.get("text", ""),
                        },
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
            for index, item in enumerate(
                parser.links[: runtime.expansion_per_seed_limit], start=1
            ):
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
                        metadata={
                            "anchor_text": item.get("text", ""),
                            "seed_url": seed.url,
                        },
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
    "collect_camoufox_agentic_results",
    "collect_firecrawl_browser_results",
    "collect_firecrawl_results",
    "collect_serper_results",
    "collect_serpapi_results",
    "collect_camoufox_browser_results",
    "expand_with_crawlbase",
    "select_expansion_seeds",
]
