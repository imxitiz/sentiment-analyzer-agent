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
import uuid
from datetime import datetime

from server.models import (
    AgentEvent,
    AgentEventType,
    ChatMessage,
    MessageRole,
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
        f"Starting data collection...")

    # Phase 2: Searching
    await session_manager.update_status(session_id, SessionStatus.SEARCHING)
    await _emit(session_id, AgentEventType.AGENT_START, "searcher",
                "Harvesting links from search engines...")
    await asyncio.sleep(0.5)

    total_links = 0
    for query in plan.search_queries[:4]:
        found = 15 + hash(query) % 20
        total_links += found
        await _emit(session_id, AgentEventType.AGENT_PROGRESS, "searcher",
                    f'Found {found} results for "{query}"',
                    query=query, found=found, total=total_links)
        await asyncio.sleep(0.4)

    await _emit(session_id, AgentEventType.AGENT_COMPLETE, "searcher",
                f"Search complete: {total_links} links discovered",
                total_links=total_links)

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


async def run_analysis_live(session_id: str, topic: str, provider: str = "gemini", model: str | None = None) -> None:
    """Run the actual agent pipeline (requires API keys).

    This bridges the web API to the existing CLI agent pipeline:
      1. Creates OrchestratorAgent and PlannerAgent
      2. Streams execution steps
      3. Converts agent output to AnalysisResult

    TODO: Implement live agent integration when agents support async streaming.
    For now, falls back to demo mode.
    """
    # Fallback to demo mode for now
    await run_analysis_demo(session_id, topic)


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
