"""Agent service layer helpers.

Shared services for resilience checkpoints and reusable persistence logic.
"""
from .llm_tracer import get_llm_trace_context, llm_trace_context, save_llm_trace
from .planner_checkpoint import (
    db_path_for_topic,
    increment_agent_retry,
    init_topic_db,
    save_pipeline_artifact,
    save_planner_plan,
    save_topic_input,
    upsert_agent_status,
)
from .harvester_sources import (
    build_fallback_harvest_tasks,
    collect_firecrawl_browser_results,
    collect_firecrawl_results,
    collect_serper_results,
    expand_with_crawlbase,
    select_expansion_seeds,
)
from .harvester_store import (
    AsyncLinkWriter,
    backfill_harvest_metadata,
    backfill_published_dates,
    backfill_platform_labels,
    finish_harvest_run,
    init_harvest_tables,
    load_research_brief,
    start_harvest_run,
)
from .document_store import build_document_store
from .cleaner_store import (
    build_cleaner_store,
    build_cleaning_runtime_config,
    load_latest_clean_stats,
)
from .sentiment_store import (
    build_sentiment_runtime_config,
    build_sentiment_store,
    load_latest_sentiment_stats,
)
from .scraper_sources import (
    available_scrape_backends,
    build_backend_plan,
    classify_target_platform,
    scrape_target_with_backend,
)
from .scraper_runtime import (
    build_scrape_runtime_config,
    registered_scrape_backends,
    resolve_enabled_scrape_backends,
)
from .scraper_store import (
    bootstrap_scrape_targets,
    finish_scrape_run,
    init_scraper_tables,
    load_latest_scrape_stats,
    load_scrape_targets,
    scrape_status_counts,
    start_scrape_run,
    update_scrape_target,
)
from .orchestrator_checkpoint import (
    bootstrap_topic,
    create_topic_run,
    get_latest_run_id,
    init_orchestrator_db,
    record_orchestrator_event,
    topic_db_for,
    update_topic_run,
)
from .search_searchengine import search_searchengine

__all__ = [
    "bootstrap_topic",
    "build_fallback_harvest_tasks",
    "backfill_harvest_metadata",
    "backfill_published_dates",
    "backfill_platform_labels",
    "build_cleaner_store",
    "build_cleaning_runtime_config",
    "build_backend_plan",
    "build_document_store",
    "build_scrape_runtime_config",
    "build_sentiment_runtime_config",
    "build_sentiment_store",
    "collect_firecrawl_browser_results",
    "collect_firecrawl_results",
    "collect_serper_results",
    "classify_target_platform",
    "create_topic_run",
    "db_path_for_topic",
    "get_llm_trace_context",
    "expand_with_crawlbase",
    "finish_harvest_run",
    "finish_scrape_run",
    "get_latest_run_id",
    "increment_agent_retry",
    "init_harvest_tables",
    "init_orchestrator_db",
    "init_scraper_tables",
    "init_topic_db",
    "llm_trace_context",
    "load_research_brief",
    "load_latest_clean_stats",
    "load_latest_scrape_stats",
    "load_latest_sentiment_stats",
    "load_scrape_targets",
    "record_orchestrator_event",
    "registered_scrape_backends",
    "resolve_enabled_scrape_backends",
    "available_scrape_backends",
    "save_pipeline_artifact",
    "save_llm_trace",
    "save_planner_plan",
    "save_topic_input",
    "search_searchengine",
    "bootstrap_scrape_targets",
    "scrape_status_counts",
    "scrape_target_with_backend",
    "select_expansion_seeds",
    "AsyncLinkWriter",
    "start_harvest_run",
    "start_scrape_run",
    "topic_db_for",
    "update_scrape_target",
    "update_topic_run",
    "upsert_agent_status",
]
