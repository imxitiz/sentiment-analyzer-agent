from agents.scraper.models import ScrapeRuntimeConfig, ScrapeTarget
from agents.services.scraper_runtime import backend_capability_snapshot
from agents.services.scraper_sources import build_backend_plan


def _target(url: str, platform: str = "web") -> ScrapeTarget:
    return ScrapeTarget(
        discovered_link_id=1,
        unique_id="u1",
        normalized_url=url,
        url=url,
        topic="test-topic",
        platform=platform,
    )


def test_backend_plan_reddit_prefers_reddit_json() -> None:
    runtime = ScrapeRuntimeConfig()
    plan = build_backend_plan(
        _target("https://www.reddit.com/r/test/comments/abc/demo"), runtime
    )
    assert plan[0] == "reddit_json"


def test_backend_plan_bluesky_includes_public_api() -> None:
    runtime = ScrapeRuntimeConfig()
    plan = build_backend_plan(
        _target("https://bsky.app/profile/alice.bsky.social/post/3kxyz"), runtime
    )
    assert "bluesky_public" in plan


def test_backend_plan_youtube_includes_oembed() -> None:
    runtime = ScrapeRuntimeConfig()
    plan = build_backend_plan(
        _target("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), runtime
    )
    assert "youtube_oembed" in plan


def test_backend_plan_hackernews_includes_hn_api() -> None:
    runtime = ScrapeRuntimeConfig()
    plan = build_backend_plan(
        _target("https://news.ycombinator.com/item?id=8863"), runtime
    )
    assert "hackernews_api" in plan


def test_backend_plan_rss_includes_feed_backend() -> None:
    runtime = ScrapeRuntimeConfig()
    plan = build_backend_plan(_target("https://example.com/feed.xml"), runtime)
    assert "rss_feed" in plan


def test_backend_capability_snapshot_keeps_generic_http_ready() -> None:
    snapshot = backend_capability_snapshot(("generic_http",))
    assert snapshot["generic_http"]["available"] is True
    assert snapshot["generic_http"]["reason"] == "ready"
