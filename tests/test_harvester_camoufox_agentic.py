"""Unit tests for autonomous Camoufox harvesting behavior."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.harvester.models import (
    HarvestTaskPlan,
    HarvesterRuntimeConfig,
    ResearchBrief,
)
from agents.services.harvester_sources import collect_camoufox_agentic_results


def _runtime() -> HarvesterRuntimeConfig:
    return HarvesterRuntimeConfig(
        enable_camoufox=True,
        enable_camoufox_agentic=True,
        camoufox_agentic_max_seed_pages=3,
        camoufox_agentic_max_hops=2,
        camoufox_agentic_links_per_page=8,
        camoufox_agentic_extract_chars=400,
        source_timeout_seconds=30,
    )


def _brief() -> ResearchBrief:
    return ResearchBrief(
        topic="nepal elections",
        keywords=["elections", "voters", "public opinion"],
        hashtags=["#NepalElections"],
        search_queries=["nepal elections opinion"],
    )


def _task() -> HarvestTaskPlan:
    return HarvestTaskPlan(
        query="nepal elections public reaction",
        platform_hint="web",
        source_names=["camoufox_agentic"],
        target_results=10,
        rationale="collect discussion-rich pages",
    )


def test_camoufox_agentic_returns_warning_when_unavailable(monkeypatch):
    import utils.camoufox as camoufox

    monkeypatch.setattr(camoufox, "camoufox_is_available", lambda: False)

    result = asyncio.run(
        collect_camoufox_agentic_results(
            _task(),
            brief=_brief(),
            runtime=_runtime(),
            actor="test",
        )
    )

    assert result.source_name == "camoufox_agentic"
    assert result.links == []
    assert result.warnings


def test_camoufox_agentic_collects_seed_pages_and_closes_session(monkeypatch):
    import utils.camoufox as camoufox

    state: dict[str, Any] = {"url": "", "closed": False}

    def fake_start_browser(**kwargs: Any) -> dict[str, Any]:
        return {"session_id": "s1", "mode": "local_python"}

    def fake_navigate(session_id: str, url: str, **kwargs: Any) -> dict[str, Any]:
        state["url"] = url
        return {"session_id": session_id, "url": url}

    def fake_extract_links(
        session_id: str, max_links: int = 40, selector: str = "a"
    ) -> dict[str, Any]:
        current = str(state.get("url", ""))
        if (
            "duckduckgo.com" in current
            or "bing.com" in current
            or "news.google.com" in current
        ):
            anchors = [
                {
                    "href": "https://www.reddit.com/r/Nepal/comments/abc123/election_reactions",
                    "title": "Election reactions",
                    "text": "public reactions and comments",
                },
                {
                    "href": "https://example.com/analysis/nepal-election-opinion",
                    "title": "Opinion analysis",
                    "text": "support and criticism in one place",
                },
            ]
        else:
            anchors = [
                {
                    "href": "https://example.com/discussion/thread-1",
                    "title": "discussion thread",
                    "text": "debate and criticism",
                }
            ]
        return {"session_id": session_id, "anchors": anchors}

    def fake_extract_text(
        session_id: str, selector: str = "body", max_chars: int = 4000
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "url": state.get("url", ""),
            "title": "Opinion roundup",
            "text": "Public reaction includes support, criticism, and neutral analysis.",
        }

    def fake_close_browser(session_id: str) -> dict[str, Any]:
        state["closed"] = True
        return {"session_id": session_id, "closed": True}

    monkeypatch.setattr(camoufox, "camoufox_is_available", lambda: True)
    monkeypatch.setattr(camoufox, "camoufox_start_browser", fake_start_browser)
    monkeypatch.setattr(camoufox, "camoufox_navigate", fake_navigate)
    monkeypatch.setattr(camoufox, "camoufox_extract_links", fake_extract_links)
    monkeypatch.setattr(camoufox, "camoufox_extract_text", fake_extract_text)
    monkeypatch.setattr(camoufox, "camoufox_close_browser", fake_close_browser)

    result = asyncio.run(
        collect_camoufox_agentic_results(
            _task(),
            brief=_brief(),
            runtime=_runtime(),
            actor="test",
        )
    )

    assert result.source_name == "camoufox_agentic"
    assert len(result.links) > 0
    assert any(link.source_name == "camoufox_agentic" for link in result.links)
    assert state["closed"] is True


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
