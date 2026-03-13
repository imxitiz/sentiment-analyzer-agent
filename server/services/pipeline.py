"""Pipeline runner — bridge between the web API and the agent pipeline.

Runs the sentiment analysis pipeline asynchronously, streaming progress
events to the session manager (which forwards them to WebSocket clients).

Supports two modes:
    • **demo**: Simulates the pipeline with delays and mock data.
    • **live**: Actually invokes the agent pipeline (orchestrator → sub-agents).

Usage::

    from server.services.pipeline import run_analysis

    await run_analysis(session_id="abc123", topic="Nepal elections 2026")
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

from agents.services import (
    db_path_for_topic,
    load_latest_clean_stats,
    load_latest_scrape_stats,
    load_research_brief,
)
from agents.tools.human import clear_human_input_handler, set_human_input_handler
from server.config import server_config
from server.models import (
    AgentEvent,
    AgentEventType,
    ChatMessage,
    MessageRole,
    ResearchPlanData,
    SessionStatus,
)
from server.services.session_manager import session_manager
from server.services import generate_mock_result, generate_mock_plan


async def _emit(session_id: str, event_type: AgentEventType, agent: str, message: str, **data: object) -> None:
    """Helper to emit an agent event."""
    await session_manager.add_event(session_id, AgentEvent(
        type=event_type,
        agent=agent,
        message=message,
        data=dict(data),
    ))


async def run_analysis_demo(session_id: str, topic: str) -> None:
    """Run a simulated analysis pipeline with realistic delays.

    This creates a realistic demo experience:
      1. Planning (2s) → shows research plan
      2. Searching (3s) → shows discovered links
      3. Scraping (4s) → shows data collection progress
      4. Cleaning (2s) → shows dedup/filter stats
      5. Analysing (3s) → shows sentiment scores rolling in
      6. Complete → full mock result

    Args:
        session_id: Active session ID.
        topic: The analysis topic.
    """
    # Phase 1: Planning
    await session_manager.update_status(session_id, SessionStatus.PLANNING)
    await _emit(session_id, AgentEventType.AGENT_START, "planner",
                f"Generating research plan for: {topic}")
    await asyncio.sleep(0.8)

    plan = generate_mock_plan(topic)
    await _emit(session_id, AgentEventType.AGENT_PROGRESS, "planner",
                f"Found {len(plan.keywords)} keywords and {len(plan.search_queries)} search queries",
                keywords=plan.keywords[:5], queries=plan.search_queries[:3])
    await asyncio.sleep(0.6)

    await _emit(session_id, AgentEventType.AGENT_PROGRESS, "planner",
                f"Identified {len(plan.platforms)} target platforms",
                platforms=[p["name"] for p in plan.platforms])
    await asyncio.sleep(0.4)

    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "planner",
                "Research plan complete",
                plan=plan.model_dump())

    await session_manager.add_message(session_id, MessageRole.ASSISTANT,
        f"**Research Plan Ready**\n\n"
        f"I've identified {len(plan.keywords)} keywords, "
        f"{len(plan.hashtags)} hashtags, and "
        f"{len(plan.search_queries)} search queries across "
        f"{len(plan.platforms)} platforms.\n\n"
        f"Starting link harvesting...")

    # Phase 2: Harvesting
    await session_manager.update_status(session_id, SessionStatus.SEARCHING)
    await _emit(session_id, AgentEventType.AGENT_START, "harvester",
                "Harvesting candidate links from search sources...")
    await asyncio.sleep(0.5)

    total_links = 0
    for query in plan.search_queries[:4]:
        found = 15 + hash(query) % 20
        total_links += found
        await _emit(session_id, AgentEventType.AGENT_PROGRESS, "harvester",
                    f'Found {found} results for "{query}"',
                    query=query, found=found, total=total_links)
        await asyncio.sleep(0.4)

    stored_links = max(total_links - max(5, total_links // 6), 0)
    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "harvester",
                f"Harvesting complete: {stored_links} candidate links stored",
                total_links=total_links, stored_links=stored_links)

    # Phase 3: Scraping
    await session_manager.update_status(session_id, SessionStatus.SCRAPING)
    await _emit(session_id, AgentEventType.AGENT_START, "scraper",
                f"Deep scraping {total_links} URLs...")
    await asyncio.sleep(0.5)

    scraped = 0
    for platform in ["reddit", "twitter", "news", "facebook"]:
        batch = 20 + hash(platform + topic) % 30
        scraped += batch
        await _emit(session_id, AgentEventType.AGENT_PROGRESS, "scraper",
                    f"Scraped {batch} posts from {platform}",
                    platform=platform, batch_size=batch, total_scraped=scraped)
        await asyncio.sleep(0.5)

    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "scraper",
                f"Scraping complete: {scraped} posts collected",
                total_scraped=scraped)

    # Phase 4: Cleaning
    await session_manager.update_status(session_id, SessionStatus.CLEANING)
    await _emit(session_id, AgentEventType.AGENT_START, "cleaner",
                "Cleaning and deduplicating collected data...")
    await asyncio.sleep(0.5)

    duplicates = scraped // 8
    spam = scraped // 12
    clean_count = scraped - duplicates - spam
    await _emit(session_id, AgentEventType.AGENT_PROGRESS, "cleaner",
                f"Removed {duplicates} duplicates and {spam} spam posts",
                duplicates=duplicates, spam=spam, remaining=clean_count)
    await asyncio.sleep(0.4)

    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "cleaner",
                f"Cleaning complete: {clean_count} quality posts remaining",
                clean_count=clean_count)

    # Phase 5: Analysis
    await session_manager.update_status(session_id, SessionStatus.ANALYSING)
    await _emit(session_id, AgentEventType.AGENT_START, "analyser",
                "Running sentiment analysis model...")
    await asyncio.sleep(0.5)

    for i in range(0, clean_count, max(1, clean_count // 4)):
        pct = min(100, int((i / clean_count) * 100))
        await _emit(session_id, AgentEventType.AGENT_PROGRESS, "analyser",
                    f"Analysed {i}/{clean_count} posts ({pct}%)",
                    analysed=i, total=clean_count, percent=pct)
        await asyncio.sleep(0.3)

    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "analyser",
                f"Sentiment analysis complete for {clean_count} posts",
                analysed=clean_count)

    # Phase 6: Generate results and complete
    result = generate_mock_result(topic, post_count=min(clean_count, 150))
    await session_manager.set_result(session_id, result)

    await session_manager.add_message(session_id, MessageRole.ASSISTANT,
        f"**Analysis Complete!** 🎉\n\n"
        f"Processed **{result.summary.total_posts}** posts across "
        f"{len(result.platforms)} platforms.\n\n"
        f"**Overall Sentiment**: {_sentiment_label(result.summary.avg_compound)}\n"
        f"- Positive: {result.summary.positive_pct}%\n"
        f"- Neutral: {result.summary.neutral_pct}%\n"
        f"- Negative: {result.summary.negative_pct}%\n\n"
        f"Switch to the **Dashboard** tab to explore the full results.")

    await _emit(session_id, AgentEventType.PIPELINE_COMPLETE, "orchestrator",
                "Full analysis pipeline complete!",
                summary={
                    "total_posts": result.summary.total_posts,
                    "avg_compound": result.summary.avg_compound,
                    "positive_pct": result.summary.positive_pct,
                    "negative_pct": result.summary.negative_pct,
                    "neutral_pct": result.summary.neutral_pct,
                })
    await session_manager.update_status(session_id, SessionStatus.COMPLETED)


def _provider_ready(provider: str) -> tuple[bool, list[str]]:
    from env import config

    normalized = provider.strip().lower()
    reasons: list[str] = []
    if normalized == "dummy":
        reasons.append("The dummy provider only supports demo mode.")
        return False, reasons

    if normalized in {"google", "gemini", "genai"} and not config.get("GOOGLE_API_KEY"):
        reasons.append("GOOGLE_API_KEY is required for the selected Gemini provider.")
    elif normalized in {"openai", "chatgpt", "gpt"} and not config.get("OPENAI_API_KEY"):
        reasons.append("OPENAI_API_KEY is required for the selected OpenAI provider.")
    elif normalized not in {"google", "gemini", "genai", "openai", "chatgpt", "gpt", "ollama"}:
        reasons.append(f"Unsupported live provider: {provider}.")

    return not reasons, reasons


def _bool_env(name: str, default: bool) -> bool:
    from env import config

    raw = config.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _harvester_sources_ready() -> tuple[bool, list[str], list[str]]:
    from env import config
    from utils.camoufox import camoufox_is_available

    available: list[str] = []
    reasons: list[str] = []

    if _bool_env("HARVESTER_ENABLE_SERPER", True) and config.get("SERPER_API_KEY"):
        available.append("serper")
    if _bool_env("HARVESTER_ENABLE_FIRECRAWL", True) and config.get("FIRECRAWL_API_KEY"):
        available.append("firecrawl")
    if _bool_env("HARVESTER_ENABLE_SERPAPI", False) and config.get("SERPAPI_API_KEY"):
        available.append("serpapi")
    if _bool_env("HARVESTER_ENABLE_CAMOUFOX", False) and camoufox_is_available():
        available.append("camoufox")

    if not available:
        reasons.append(
            "No live harvesting source is currently usable. Enable at least one of Serper, Firecrawl, SerpAPI, or Camoufox."
        )

    return bool(available), available, reasons


def _scraper_ready() -> tuple[bool, list[str], list[str]]:
    from env import config
    from utils.camoufox import camoufox_is_available

    available: list[str] = []
    reasons: list[str] = []

    if not config.get("MONGODB_URI"):
        reasons.append("MONGODB_URI is required for live scraping document storage.")

    if _bool_env("SCRAPER_ENABLE_GENERIC_HTTP", True):
        available.append("generic_http")
    if _bool_env("SCRAPER_ENABLE_FIRECRAWL", True) and config.get("FIRECRAWL_API_KEY"):
        available.append("firecrawl")
    if _bool_env("SCRAPER_ENABLE_CRAWLBASE", True) and (
        config.get("CRAWLBASE_JS_TOKEN") or config.get("CRAWLBASE_TOKEN")
    ):
        available.append("crawlbase")
    if _bool_env("SCRAPER_ENABLE_CAMOUFOX", True) and camoufox_is_available():
        available.append("camoufox")

    if not available:
        reasons.append(
            "No live scraper backend is currently usable. Enable generic HTTP, Firecrawl, Crawlbase, or Camoufox."
        )

    return not reasons, available, reasons


def _live_readiness(provider: str) -> tuple[bool, list[str], list[str]]:
    provider_ok, provider_reasons = _provider_ready(provider)
    sources_ok, sources, source_reasons = _harvester_sources_ready()
    scraper_ok, scraper_sources, scraper_reasons = _scraper_ready()
    reasons = provider_reasons + source_reasons + scraper_reasons
    return provider_ok and sources_ok and scraper_ok, sources + scraper_sources, reasons


def _load_plan_data(topic: str) -> ResearchPlanData | None:
    brief = load_research_brief(topic)
    if not brief.topic_summary and not brief.keywords and not brief.search_queries:
        return None
    return ResearchPlanData(
        topic_summary=brief.topic_summary,
        keywords=brief.keywords,
        hashtags=brief.hashtags,
        platforms=brief.platforms,
        search_queries=brief.search_queries,
        estimated_volume=brief.estimated_volume,
        reasoning=brief.reasoning,
    )


def _load_latest_harvest_stats(topic: str) -> dict[str, object] | None:
    path = db_path_for_topic(topic)
    if not path.exists():
        return None

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT stats_json, status
            FROM harvest_runs
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return None

    stats_json, status = row
    stats = json.loads(stats_json) if stats_json else {}
    if isinstance(stats, dict):
        stats["status"] = status
        return stats
    return {"status": status}


def _build_web_human_handler(session_id: str, loop: asyncio.AbstractEventLoop):
    def _handler(question: str) -> str:
        future = asyncio.run_coroutine_threadsafe(
            session_manager.request_clarification(
                session_id,
                question,
                agent="orchestrator",
                resume_status=SessionStatus.PLANNING,
            ),
            loop,
        )
        return future.result()

    return _handler


async def run_analysis_live(session_id: str, topic: str, provider: str = "gemini", model: str | None = None) -> None:
    """Run the currently implemented live pipeline (requires API keys).

    This bridge should only reflect real implemented phases. Right now that is:
        1. Orchestrator
        2. Planner
        3. Harvester
        4. Scraper
        5. Cleaner

    It should not fabricate sentiment-analysis results.
    """
    can_run_live, sources, reasons = _live_readiness(provider)
    if not can_run_live:
        await _emit(
            session_id,
            AgentEventType.AGENT_PROGRESS,
            "orchestrator",
            "Live pipeline is not fully ready for this configuration. Falling back to demo mode.",
            reasons=reasons,
        )
        await run_analysis_demo(session_id, topic)
        return

    # run real agents in background thread to avoid blocking event loop
    from agents.orchestrator import OrchestratorAgent
    from utils.camoufox import camoufox_close_all_browsers

    await session_manager.update_status(session_id, SessionStatus.PLANNING)
    await _emit(session_id, AgentEventType.AGENT_START, "orchestrator",
                f"Running orchestrator for {topic}", sources=sources)

    loop = asyncio.get_running_loop()
    set_human_input_handler(_build_web_human_handler(session_id, loop))
    orchestrator = OrchestratorAgent(llm_provider=provider, model=model)
    try:
        result = await asyncio.to_thread(orchestrator.invoke, topic)
    except Exception as exc:
        await _emit(session_id, AgentEventType.ERROR, "orchestrator",
                    f"Orchestrator failed: {exc}", error=str(exc))
        await session_manager.update_status(session_id, SessionStatus.ERROR)
        return
    finally:
        clear_human_input_handler()
        try:
            camoufox_close_all_browsers()
        except Exception:
            pass

    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "orchestrator",
                "Orchestrator run complete",
                output=result.get("output"))

    plan_data = _load_plan_data(topic)
    if plan_data is not None:
        await _emit(
            session_id,
            AgentEventType.AGENT_COMPLETE,
            "planner",
            f"Research plan generated with {len(plan_data.keywords)} keywords and {len(plan_data.search_queries)} queries.",
            keywords=plan_data.keywords[:8],
            queries=plan_data.search_queries[:5],
        )

    harvest_stats = _load_latest_harvest_stats(topic)
    if harvest_stats is not None:
        await session_manager.update_status(session_id, SessionStatus.SEARCHING)
        await _emit(
            session_id,
            AgentEventType.AGENT_COMPLETE,
            "harvester",
            "Harvester completed candidate-link collection.",
            stats=harvest_stats,
        )

    harvested_links_value = (
        harvest_stats.get("stored_links", 0) if isinstance(harvest_stats, dict) else 0
    )
    harvested_links = (
        harvested_links_value if isinstance(harvested_links_value, int) else 0
    )
    scrape_stats = load_latest_scrape_stats(topic)
    if scrape_stats is not None:
        await session_manager.update_status(session_id, SessionStatus.SCRAPING)
        await _emit(
            session_id,
            AgentEventType.AGENT_COMPLETE,
            "scraper",
            "Scraper completed deep content extraction.",
            stats=scrape_stats,
        )

    planned_keywords = len(plan_data.keywords) if plan_data is not None else 0
    planned_queries = len(plan_data.search_queries) if plan_data is not None else 0
    scraped_documents_value = (
        scrape_stats.get("completed", 0) if isinstance(scrape_stats, dict) else 0
    )
    scraped_documents = (
        scraped_documents_value if isinstance(scraped_documents_value, int) else 0
    )
    reused_documents_value = (
        scrape_stats.get("reused", 0) if isinstance(scrape_stats, dict) else 0
    )
    reused_documents = (
        reused_documents_value if isinstance(reused_documents_value, int) else 0
    )

    cleaned_stats = load_latest_clean_stats(topic)
    cleaned_documents_value = (
        cleaned_stats.get("accepted", 0) if isinstance(cleaned_stats, dict) else 0
    )
    cleaned_documents = (
        cleaned_documents_value if isinstance(cleaned_documents_value, int) else 0
    )
    duplicate_documents_value = (
        cleaned_stats.get("duplicate", 0) if isinstance(cleaned_stats, dict) else 0
    )
    duplicate_documents = (
        duplicate_documents_value if isinstance(duplicate_documents_value, int) else 0
    )
    too_short_value = (
        cleaned_stats.get("too_short", 0) if isinstance(cleaned_stats, dict) else 0
    )
    too_short_documents = too_short_value if isinstance(too_short_value, int) else 0
    if cleaned_stats is not None:
        await session_manager.update_status(session_id, SessionStatus.CLEANING)
        await _emit(
            session_id,
            AgentEventType.AGENT_COMPLETE,
            "cleaner",
            "Cleaner completed preprocessing and normalization.",
            stats=cleaned_stats,
        )

    await session_manager.add_message(
        session_id,
        MessageRole.ASSISTANT,
        (
            f"Planning, harvesting, scraping, and cleaning finished for **{topic}**.\n\n"
            f"- Keywords planned: {planned_keywords}\n"
            f"- Search queries planned: {planned_queries}\n"
            f"- Candidate links harvested: {harvested_links}\n\n"
            f"- Raw documents scraped: {scraped_documents}\n"
            f"- Existing documents reused: {reused_documents}\n\n"
            f"- Cleaned documents accepted: {cleaned_documents}\n"
            f"- Duplicate documents skipped: {duplicate_documents}\n"
            f"- Too-short documents skipped: {too_short_documents}\n\n"
            f"Sentiment scoring is not implemented yet, so no sentiment summary was produced."
        ),
        metadata={
            "kind": "pipeline_boundary",
            "phase": "cleaning",
        },
    )
    await _emit(session_id, AgentEventType.PIPELINE_COMPLETE, "orchestrator",
                "Planning, harvesting, scraping, and cleaning pipeline complete",
                summary={
                    "phase": "cleaning",
                    "stored_links": harvested_links,
                    "scraped_documents": scraped_documents,
                    "reused_documents": reused_documents,
                    "cleaned_documents": cleaned_documents,
                    "duplicate_documents": duplicate_documents,
                    "too_short_documents": too_short_documents,
                    "keywords": planned_keywords,
                    "queries": planned_queries,
                })
    await session_manager.update_status(session_id, SessionStatus.COMPLETED)


async def run_analysis(
    session_id: str,
    topic: str,
    provider: str = "dummy",
    model: str | None = None,
) -> None:
    """Entry point — dispatch to demo or live pipeline.

    Args:
        session_id: Active session ID.
        topic: Analysis topic.
        provider: LLM provider (``"dummy"`` for demo mode).
        model: Optional model name override.
    """
    try:
        if provider == "dummy":
            await run_analysis_demo(session_id, topic)
        else:
            await run_analysis_live(session_id, topic, provider, model)
    except Exception as exc:
        await session_manager.update_status(session_id, SessionStatus.ERROR)
        await _emit(session_id, AgentEventType.ERROR, "orchestrator",
                    f"Pipeline failed: {exc}", error=str(exc))
        await session_manager.add_message(session_id, MessageRole.SYSTEM,
            f"**Error**: {exc}\n\nPlease try again or use demo mode.")


def _sentiment_label(compound: float) -> str:
    """Human-readable sentiment label from compound score."""
    if compound > 0.3:
        return "Positive 📈"
    if compound > 0.1:
        return "Slightly Positive 📊"
    if compound > -0.1:
        return "Neutral ➡️"
    if compound > -0.3:
        return "Slightly Negative 📉"
    return "Negative 🔻"
