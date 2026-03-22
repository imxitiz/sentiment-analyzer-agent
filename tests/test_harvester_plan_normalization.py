"""Unit tests for harvester plan normalization and source mapping."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.harvester.agent import HarvesterAgent
from agents.harvester.models import HarvestPlan, HarvestTaskPlan, HarvesterRuntimeConfig


def test_non_executable_source_is_mapped_to_available_source():
    agent = HarvesterAgent(llm_provider="dummy")
    runtime = HarvesterRuntimeConfig(per_query_limit=25, max_links=500)
    plan = HarvestPlan(
        summary="test",
        source_order=["news", "social"],
        max_links=999,
        min_quality_score=0.9,
        tasks=[
            HarvestTaskPlan(
                query="eid holiday nepal sentiment",
                platform_hint="news",
                source_names=["news"],
                target_results=100,
                rationale="collect news",
            )
        ],
        reasoning="test",
    )

    normalized = agent._normalize_harvest_plan(
        plan=plan,
        available_sources=["serper", "firecrawl_search"],
        runtime=runtime,
    )

    assert normalized is not None
    assert normalized.tasks
    assert normalized.tasks[0].source_names == ["serper"]
    assert normalized.tasks[0].target_results == 25
    assert normalized.max_links == 500


def test_repair_prompt_references_current_task_schema():
    prompt = HarvesterAgent._build_harvest_plan_repair_prompt(
        raw_text="raw",
        available_sources=["serper", "firecrawl_search"],
        per_query_limit=25,
    )

    assert "platform_hint" in prompt
    assert "source_names" in prompt
    assert "target_results" in prompt
    assert "source, query" not in prompt


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
