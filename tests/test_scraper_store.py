from __future__ import annotations

from agents.services.harvester_store import init_harvest_tables
from agents.services.planner_checkpoint import db_path_for_topic
from agents.services.scraper_sources import build_backend_plan
from agents.services.scraper_store import bootstrap_scrape_targets, load_scrape_targets
from agents.scraper.models import ScrapeRuntimeConfig, ScrapeTarget


def test_bootstrap_scrape_targets_from_discovered_links() -> None:
    topic = "phase-3 scraper bootstrap test"
    db_path = db_path_for_topic(topic)
    if db_path.exists():
        db_path.unlink()

    init_harvest_tables(topic)
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO discovered_links(
                unique_id, normalized_url, url, topic, domain, platform,
                title, description, source_name, source_type,
                discovered_at, first_seen_at, last_seen_at, quality_score, relevance_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'), ?, ?)
            """,
            (
                "abc123",
                "https://example.com/post/1",
                "https://example.com/post/1",
                topic,
                "example.com",
                "web",
                "Example title",
                "Example description",
                "serper",
                "search",
                0.8,
                0.7,
            ),
        )

    inserted = bootstrap_scrape_targets(topic)
    assert inserted == 1

    targets = load_scrape_targets(topic)
    assert len(targets) == 1
    assert targets[0].normalized_url == "https://example.com/post/1"
    assert targets[0].status == "not_started"

    if db_path.exists():
        db_path.unlink()


def test_build_backend_plan_prioritizes_reddit_json() -> None:
    runtime = ScrapeRuntimeConfig(
        enabled_backends=("generic_http", "firecrawl", "crawlbase"),
    )
    target = ScrapeTarget(
        discovered_link_id=1,
        unique_id="reddit-1",
        normalized_url="https://www.reddit.com/r/test/comments/abc/post",
        url="https://www.reddit.com/r/test/comments/abc/post",
        topic="test",
        domain="www.reddit.com",
        platform="reddit",
    )

    plan = build_backend_plan(target, runtime)
    assert plan[0] == "reddit_json"
    assert "generic_http" in plan
