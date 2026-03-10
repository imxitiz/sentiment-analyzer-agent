"""Domain models for link harvesting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class HarvestTaskPlan(BaseModel):
    """One query execution unit in the harvesting plan."""

    query: str = Field(description="Search query to execute")
    platform_hint: str = Field(description="Target platform or source family")
    source_names: list[str] = Field(
        description="Ordered list of source adapters that should execute this query"
    )
    target_results: int = Field(
        description="How many raw results this task should try to collect"
    )
    rationale: str = Field(description="Why this query/source combination matters")


class HarvestPlan(BaseModel):
    """Structured plan produced for the harvester runtime."""

    summary: str = Field(description="Short summary of the harvesting strategy")
    source_order: list[str] = Field(
        description="Global priority order of harvesting sources"
    )
    max_links: int = Field(description="Upper bound of accepted canonical links")
    min_quality_score: float = Field(
        description="Minimum score required before a link is accepted"
    )
    tasks: list[HarvestTaskPlan] = Field(
        description="Concrete harvesting tasks to execute in parallel"
    )
    reasoning: str = Field(description="Why this harvesting plan is high quality")


@dataclass(slots=True)
class ResearchBrief:
    """Planner output reconstructed from the topic database."""

    topic: str
    topic_summary: str = ""
    keywords: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    platforms: list[dict[str, str]] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    estimated_volume: str = ""
    stop_condition: str = ""
    reasoning: str = ""


@dataclass(slots=True)
class HarvestedLink:
    """Normalized link candidate emitted by a provider or browser expander."""

    url: str
    title: str = ""
    description: str = ""
    platform: str = "web"
    source_name: str = ""
    source_type: str = "search"
    discovery_query: str = ""
    author: str | None = None
    published_at: str | None = None
    position: int | None = None
    domain: str | None = None
    language: str | None = None
    quality_signal: float = 0.0
    relevance_signal: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HarvestSourceResult:
    """Batch of links returned by a harvesting source."""

    source_name: str
    source_type: str
    links: list[HarvestedLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HarvesterRuntimeConfig:
    """Non-LLM runtime controls for the harvesting phase."""

    max_links: int = 1000
    max_concurrency: int = 8
    source_timeout_seconds: int = 120
    writer_batch_size: int = 50
    writer_queue_size: int = 5000
    per_query_limit: int = 25
    min_quality_score: float = 0.35
    expansion_seed_limit: int = 12
    expansion_per_seed_limit: int = 25
    enable_serper: bool = True
    enable_firecrawl: bool = True
    enable_browser_discovery: bool = True
    enable_crawlbase: bool = True
    enable_serpapi: bool = False
    enable_camoufox: bool = False
