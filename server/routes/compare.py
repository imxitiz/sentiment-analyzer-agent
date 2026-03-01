"""Comparison endpoint — diff two analysis versions or sessions.

Routes::

    POST /api/compare → Compare two analysis results

Accepts two references (session_id + version) and returns a structured
diff: sentiment deltas, keyword changes, platform shifts, and a
narrative summary.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.models import AnalysisResult
from server.services.session_manager import session_manager

router = APIRouter(prefix="/api", tags=["compare"])


# ── Request / Response Models ─────────────────────────────────────────


class ComparisonRef(BaseModel):
    """Reference to a specific analysis result (session + version)."""

    session_id: str
    version: int | None = Field(
        None,
        description="Version to compare (default: current active version)",
    )


class CompareRequest(BaseModel):
    """POST /api/compare body."""

    base: ComparisonRef = Field(description="The 'before' reference")
    target: ComparisonRef = Field(description="The 'after' reference")


class SentimentDelta(BaseModel):
    """Change in sentiment metrics."""

    avg_compound_before: float
    avg_compound_after: float
    delta: float
    positive_pct_before: float
    positive_pct_after: float
    negative_pct_before: float
    negative_pct_after: float
    neutral_pct_before: float
    neutral_pct_after: float
    total_posts_before: int
    total_posts_after: int
    direction: str  # "improved", "declined", "stable"


class KeywordDelta(BaseModel):
    """Changes in top keywords between two analyses."""

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    common: list[str] = Field(default_factory=list)


class PlatformDelta(BaseModel):
    """Sentiment shift for a single platform."""

    platform: str
    before_avg: float | None = None
    after_avg: float | None = None
    delta: float | None = None
    before_posts: int = 0
    after_posts: int = 0


class ComparisonResult(BaseModel):
    """Full comparison output."""

    base_topic: str
    target_topic: str
    base_version: int
    target_version: int
    sentiment: SentimentDelta
    keywords: KeywordDelta
    platforms: list[PlatformDelta] = Field(default_factory=list)
    narrative: str = ""
    compared_at: datetime = Field(default_factory=datetime.now)


class CompareResponse(BaseModel):
    """API response wrapper."""

    comparison: ComparisonResult


# ── Helpers ───────────────────────────────────────────────────────────


async def _resolve_ref(ref: ComparisonRef) -> tuple[str, int, AnalysisResult]:
    """Resolve a ComparisonRef to (topic, version, result).

    Raises HTTPException on failure.
    """
    session = await session_manager.get_session(ref.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{ref.session_id}' not found.",
        )

    target_version = ref.version if ref.version is not None else session.version

    if target_version == session.version:
        if not session.result:
            raise HTTPException(
                status_code=409,
                detail=f"Session '{ref.session_id}' v{target_version} has no result.",
            )
        return session.topic or "Unknown", target_version, session.result

    for snap in session.version_history:
        if snap.version == target_version:
            if not snap.result:
                raise HTTPException(
                    status_code=409,
                    detail=f"Session '{ref.session_id}' v{target_version} has no result.",
                )
            return session.topic or "Unknown", target_version, snap.result

    raise HTTPException(
        status_code=404,
        detail=f"Version {target_version} not found in session '{ref.session_id}'.",
    )


def _compute_direction(delta: float) -> str:
    """Classify a sentiment delta as improved/declined/stable."""
    if delta > 0.05:
        return "improved"
    if delta < -0.05:
        return "declined"
    return "stable"


def _build_narrative(
    base_topic: str,
    target_topic: str,
    base_ver: int,
    target_ver: int,
    sd: SentimentDelta,
    kd: KeywordDelta,
) -> str:
    """Generate a human-readable comparison narrative."""
    parts: list[str] = []

    # Title
    if base_topic == target_topic:
        parts.append(
            f"Comparing **v{base_ver}** vs **v{target_ver}** "
            f"for **\"{base_topic}\"**."
        )
    else:
        parts.append(
            f"Comparing **\"{base_topic}\"** (v{base_ver}) vs "
            f"**\"{target_topic}\"** (v{target_ver})."
        )

    # Sentiment shift
    if sd.direction == "improved":
        parts.append(
            f"Overall sentiment **improved** by {abs(sd.delta):.2f} "
            f"(from {sd.avg_compound_before:.2f} → {sd.avg_compound_after:.2f})."
        )
    elif sd.direction == "declined":
        parts.append(
            f"Overall sentiment **declined** by {abs(sd.delta):.2f} "
            f"(from {sd.avg_compound_before:.2f} → {sd.avg_compound_after:.2f})."
        )
    else:
        parts.append(
            f"Overall sentiment remained **stable** "
            f"({sd.avg_compound_before:.2f} → {sd.avg_compound_after:.2f})."
        )

    # Volume change
    diff = sd.total_posts_after - sd.total_posts_before
    if diff > 0:
        parts.append(f"Data volume increased by {diff} posts ({sd.total_posts_before} → {sd.total_posts_after}).")
    elif diff < 0:
        parts.append(f"Data volume decreased by {abs(diff)} posts ({sd.total_posts_before} → {sd.total_posts_after}).")

    # Keywords
    if kd.added:
        parts.append(f"New keywords emerged: {', '.join(kd.added[:5])}.")
    if kd.removed:
        parts.append(f"Keywords dropped out: {', '.join(kd.removed[:5])}.")

    return " ".join(parts)


# ── Endpoint ──────────────────────────────────────────────────────────


@router.post("/compare", response_model=CompareResponse)
async def compare_analyses(req: CompareRequest):
    """Compare two analysis results — different versions or sessions.

    Returns a structured diff with sentiment deltas, keyword changes,
    platform shifts, and a narrative summary.  Perfect for tracking
    how sentiment evolves over time or comparing different topics.
    """
    base_topic, base_ver, base_result = await _resolve_ref(req.base)
    target_topic, target_ver, target_result = await _resolve_ref(req.target)

    bs = base_result.summary
    ts_ = target_result.summary

    # ── Sentiment delta
    delta = round(ts_.avg_compound - bs.avg_compound, 4)
    sentiment = SentimentDelta(
        avg_compound_before=bs.avg_compound,
        avg_compound_after=ts_.avg_compound,
        delta=delta,
        positive_pct_before=bs.positive_pct,
        positive_pct_after=ts_.positive_pct,
        negative_pct_before=bs.negative_pct,
        negative_pct_after=ts_.negative_pct,
        neutral_pct_before=bs.neutral_pct,
        neutral_pct_after=ts_.neutral_pct,
        total_posts_before=bs.total_posts,
        total_posts_after=ts_.total_posts,
        direction=_compute_direction(delta),
    )

    # ── Keyword delta
    base_kws = set(bs.top_keywords)
    target_kws = set(ts_.top_keywords)
    keywords = KeywordDelta(
        added=sorted(target_kws - base_kws),
        removed=sorted(base_kws - target_kws),
        common=sorted(base_kws & target_kws),
    )

    # ── Platform deltas
    base_plats = {p.platform: p for p in base_result.platforms}
    target_plats = {p.platform: p for p in target_result.platforms}
    all_plats = sorted(set(base_plats) | set(target_plats))

    platforms: list[PlatformDelta] = []
    for plat in all_plats:
        bp = base_plats.get(plat)
        tp = target_plats.get(plat)
        pd_delta = None
        if bp and tp:
            pd_delta = round(tp.avg_sentiment - bp.avg_sentiment, 4)
        platforms.append(PlatformDelta(
            platform=plat,
            before_avg=bp.avg_sentiment if bp else None,
            after_avg=tp.avg_sentiment if tp else None,
            delta=pd_delta,
            before_posts=bp.post_count if bp else 0,
            after_posts=tp.post_count if tp else 0,
        ))

    # ── Narrative
    narrative = _build_narrative(base_topic, target_topic, base_ver, target_ver, sentiment, keywords)

    result = ComparisonResult(
        base_topic=base_topic,
        target_topic=target_topic,
        base_version=base_ver,
        target_version=target_ver,
        sentiment=sentiment,
        keywords=keywords,
        platforms=platforms,
        narrative=narrative,
    )

    return CompareResponse(comparison=result)
