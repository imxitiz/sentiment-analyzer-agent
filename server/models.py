"""Pydantic models — shared data contracts between server and frontend.

These models define the exact shape of all API responses and WebSocket
events.  The TypeScript types in ``Interface/src/lib/types.ts`` mirror
these models 1:1.

Hierarchy::

    Session
      ├── messages: list[ChatMessage]
      ├── events: list[AgentEvent]
      └── result: AnalysisResult | None
                    ├── summary: SentimentSummary
                    ├── posts: list[AnalysedPost]
                    └── platforms: list[PlatformBreakdown]
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────


class SessionStatus(str, Enum):
    """Lifecycle of an analysis session."""

    IDLE = "idle"                            # Created, waiting for topic
    PLANNING = "planning"                    # Planner agent running
    SEARCHING = "searching"                  # Searcher agent running
    SCRAPING = "scraping"                    # Scraper agent running
    CLEANING = "cleaning"                    # Data cleaning
    ANALYSING = "analysing"                  # Sentiment analysis
    CLARIFICATION = "clarification_needed"   # Waiting for user input
    COMPLETED = "completed"                  # Done — dashboard ready
    ERROR = "error"                          # Something went wrong


class MessageRole(str, Enum):
    """Who sent the message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgentEventType(str, Enum):
    """Types of real-time events streamed over WebSocket."""

    AGENT_START = "agent_start"
    AGENT_PROGRESS = "agent_progress"
    AGENT_COMPLETE = "agent_complete"
    CLARIFICATION = "clarification_needed"
    PIPELINE_COMPLETE = "pipeline_complete"
    STATUS_CHANGE = "status_change"
    ERROR = "error"


# ── Chat Messages ─────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in the session conversation."""

    id: str
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Agent Events (WebSocket) ─────────────────────────────────────────


class AgentEvent(BaseModel):
    """A real-time event from the agent pipeline."""

    type: AgentEventType
    agent: str = ""                    # Which agent emitted this
    message: str = ""                  # Human-readable description
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


# ── Analysis Results ──────────────────────────────────────────────────


class SentimentScore(BaseModel):
    """Continuous sentiment score for a single piece of content."""

    positive: float = Field(ge=0, le=1, description="Positive sentiment (0-1)")
    negative: float = Field(ge=0, le=1, description="Negative sentiment (0-1)")
    neutral: float = Field(ge=0, le=1, description="Neutral sentiment (0-1)")
    compound: float = Field(ge=-1, le=1, description="Overall compound score (-1 to 1)")


class AnalysedPost(BaseModel):
    """A single post/comment with sentiment analysis applied."""

    id: str
    platform: str                      # reddit, twitter, news, facebook
    author: str = "anonymous"
    content: str
    url: str = ""
    sentiment: SentimentScore
    keywords: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlatformBreakdown(BaseModel):
    """Sentiment summary for a single platform."""

    platform: str
    post_count: int
    avg_sentiment: float               # Compound score average
    positive_pct: float
    negative_pct: float
    neutral_pct: float
    top_keywords: list[str] = Field(default_factory=list)


class SentimentSummary(BaseModel):
    """Aggregate sentiment statistics."""

    total_posts: int
    avg_compound: float
    positive_pct: float
    negative_pct: float
    neutral_pct: float
    most_positive_post: str = ""
    most_negative_post: str = ""
    top_keywords: list[str] = Field(default_factory=list)
    sentiment_over_time: list[dict[str, Any]] = Field(default_factory=list)


class ResearchPlanData(BaseModel):
    """Research plan from the planner agent (mirrors agents.planner.ResearchPlan)."""

    topic_summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    platforms: list[dict[str, str]] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    estimated_volume: str = ""
    reasoning: str = ""


class AnalysisResult(BaseModel):
    """Complete analysis output — powers the dashboard."""

    topic: str
    plan: ResearchPlanData | None = None
    summary: SentimentSummary
    posts: list[AnalysedPost] = Field(default_factory=list)
    platforms: list[PlatformBreakdown] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=datetime.now)


# ── Version History ───────────────────────────────────────────────────


class VersionSnapshot(BaseModel):
    """Archived snapshot of a completed analysis version.

    When a session is refreshed, the current result/events are saved here
    so users can browse any previous version without data loss.
    """

    version: int
    result: AnalysisResult | None = None
    events: list[AgentEvent] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


# ── Session ───────────────────────────────────────────────────────────


class Session(BaseModel):
    """Top-level session model — tracks one analysis run."""

    id: str
    topic: str | None = None
    status: SessionStatus = SessionStatus.IDLE
    version: int = Field(default=1, description="Analysis version (incremented on refresh)")
    version_history: list[VersionSnapshot] = Field(
        default_factory=list,
        description="Archived snapshots of previous analysis versions",
    )
    messages: list[ChatMessage] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    result: AnalysisResult | None = None
    llm_provider: str = "dummy"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ── API Request/Response Models ───────────────────────────────────────


class CreateSessionRequest(BaseModel):
    """POST /api/sessions — create a new analysis session."""

    topic: str | None = None
    llm_provider: str = "dummy"
    llm_model: str | None = None


class CreateSessionResponse(BaseModel):
    """Response after creating a session."""

    session: Session


class StartAnalysisRequest(BaseModel):
    """POST /api/sessions/{id}/start — begin analysis."""

    topic: str
    llm_provider: str = "dummy"
    llm_model: str | None = None


class SendMessageRequest(BaseModel):
    """POST /api/sessions/{id}/messages — send a message (clarification, etc.)."""

    content: str


class SwitchVersionRequest(BaseModel):
    """POST /api/sessions/{id}/version — switch to a specific version."""

    version: int


class SessionListResponse(BaseModel):
    """GET /api/sessions — list all sessions."""

    sessions: list[Session]


class SessionDetailResponse(BaseModel):
    """GET /api/sessions/{id} — single session detail."""

    session: Session


class VersionListResponse(BaseModel):
    """GET /api/sessions/{id}/versions — all version snapshots."""

    current_version: int
    versions: list[VersionSnapshot]
