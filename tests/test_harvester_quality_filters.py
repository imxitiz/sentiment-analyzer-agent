from agents.harvester.models import HarvestedLink, ResearchBrief
from agents.harvester.models import HarvestTaskPlan, HarvesterRuntimeConfig
from agents.services.harvester_sources import collect_camoufox_browser_results
from agents.services.harvester_store import score_link


def _brief() -> ResearchBrief:
    return ResearchBrief(
        topic="eid holiday nepal sentiment",
        keywords=["public reaction", "support", "oppose", "debate"],
        hashtags=["#EidHoliday", "#Nepal"],
        search_queries=["eid holiday nepal reaction"],
    )


def test_score_link_rejects_navigation_title_for_camoufox() -> None:
    link = HarvestedLink(
        url="https://duckduckgo.com/?q=eid+holiday+nepal&ia=web",
        title="All",
        description="Discovered via Camoufox browser",
        source_name="camoufox_browser",
        source_type="browser",
        platform="web",
    )

    quality, relevance, rejection = score_link(link, _brief())
    assert rejection in {"low_value_url", "navigation_link"}
    assert quality <= 0.1
    assert relevance <= 0.1


def test_score_link_prefers_opinionated_context() -> None:
    link = HarvestedLink(
        url="https://example.com/forum/thread/eid-holiday-nepal",
        title="Public reaction debate on Eid holiday in Nepal",
        description="Support and criticism in comments from citizens",
        source_name="camoufox_browser",
        source_type="browser",
        platform="web",
        discovery_query="eid holiday nepal public reaction",
        metadata={"anchor_text": "discussion thread with comments"},
    )

    quality, relevance, rejection = score_link(link, _brief())
    assert rejection is None
    assert quality >= 0.5
    assert relevance >= 0.4


def test_camoufox_browser_filters_navigation_links(monkeypatch) -> None:
    import utils.camoufox as camoufox

    def fake_fetch_anchors(*args, **kwargs):
        return {
            "anchors": [
                {
                    "href": "https://duckduckgo.com/?q=test&ia=web",
                    "title": "All",
                    "text": "All",
                },
                {
                    "href": "https://accounts.google.com/ServiceLogin",
                    "title": "Sign in",
                    "text": "Sign in",
                },
                {
                    "href": "https://www.reddit.com/r/Nepal/comments/abc123/public-reaction-thread",
                    "title": "Public reaction thread",
                    "text": "support and criticism in comments",
                },
            ]
        }

    monkeypatch.setattr(camoufox, "camoufox_fetch_anchors", fake_fetch_anchors)

    task = HarvestTaskPlan(
        query="eid holiday nepal public reaction",
        platform_hint="web",
        source_names=["camoufox_browser"],
        target_results=10,
        rationale="collect opinionated links",
    )
    runtime = HarvesterRuntimeConfig(enable_camoufox=True, per_query_limit=25)

    result = __import__("asyncio").run(
        collect_camoufox_browser_results(
            task,
            brief=_brief(),
            runtime=runtime,
            actor="test",
        )
    )

    assert len(result.links) == 1
    assert result.links[0].domain == "reddit.com"
