"""Domain models for phase-3 deep scraping."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass(slots=True)
class ScrapeTarget:
    """A queued URL ready for deep scraping."""

    discovered_link_id: int | None
    unique_id: str
    normalized_url: str
    url: str
    topic: str
    domain: str | None = None
    platform: str = "web"
    title: str = ""
    description: str = ""
    author: str | None = None
    published_at: str | None = None
    quality_score: float = 0.0
    relevance_score: float = 0.0
    source_name: str = ""
    status: str = "not_started"
    attempts: int = 0
    extra_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScrapedContent:
    """Normalized payload returned by one scraping backend."""

    fetch_backend: str
    normalized_url: str
    final_url: str
    platform: str
    domain: str
    title: str = ""
    description: str = ""
    author: str | None = None
    published_at: str | None = None
    language: str | None = None
    site_name: str | None = None
    content_text: str = ""
    excerpt: str = ""
    raw_text: str = ""
    raw_html: str | None = None
    markdown: str | None = None
    http_status: int | None = None
    entity_type: str = "document"
    geo: dict[str, Any] = field(default_factory=dict)
    engagement: dict[str, Any] = field(default_factory=dict)
    authors: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    content_items: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScrapeRuntimeConfig:
    """Non-LLM runtime controls for the scraping phase."""

    max_concurrency: int = 6
    source_timeout_seconds: int = 90
    max_targets_per_run: int = 250
    max_retries_per_target: int = 3
    allow_existing_reuse: bool = True
    reuse_existing_days: int = 7
    enabled_backends: tuple[str, ...] = (
        "generic_http",
        "firecrawl",
        "crawlbase",
        "camoufox",
    )
    backend_status: dict[str, dict[str, Any]] = field(default_factory=dict)


class RecoveryPlan(BaseModel):
    """Structured output from the scraper recovery sub-agent."""

    should_retry: bool = Field(description="Whether the scraper should try again")
    recommended_backend: str | None = Field(
        default=None,
        description="Best next backend to try, if any",
    )
    mark_terminal: bool = Field(
        description="Whether the error should be treated as terminal for this URL"
    )
    reason: str = Field(description="Short explanation of the decision")

