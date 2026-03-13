"""Export endpoints — download analysis results in various formats.

Routes::

    GET /api/sessions/{id}/export?format=json  → JSON download
    GET /api/sessions/{id}/export?format=csv   → CSV download
    GET /api/sessions/{id}/export?format=md    → Markdown report

Supports exporting any version (current or historical) via the
optional ``version`` query parameter.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from server.models import AnalysisResult, Session
from server.services.session_manager import session_manager

router = APIRouter(prefix="/api/sessions", tags=["export"])


async def _resolve_result(
    session_id: str,
    version: int | None,
) -> tuple[Session, AnalysisResult, int]:
    """Resolve the session and target version's result.

    Returns (session, result, resolved_version).
    Raises HTTPException on failure.
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Default to current version
    target_version = version if version is not None else session.version

    if target_version == session.version:
        if not session.result:
            raise HTTPException(
                status_code=409,
                detail="Analysis not completed yet — nothing to export.",
            )
        return session, session.result, target_version

    # Look up historical version
    for snap in session.version_history:
        if snap.version == target_version:
            if not snap.result:
                raise HTTPException(
                    status_code=409,
                    detail=f"Version {target_version} has no result data.",
                )
            return session, snap.result, target_version

    raise HTTPException(
        status_code=404,
        detail=f"Version {target_version} not found.",
    )


def _filename(topic: str, version: int, ext: str) -> str:
    """Generate a safe filename for downloads."""
    slug = topic.lower().replace(" ", "-")[:40]
    ts = datetime.now().strftime("%Y%m%d")
    return f"sentiment-{slug}-v{version}-{ts}.{ext}"


def _result_to_json(result: AnalysisResult) -> str:
    """Serialize an AnalysisResult to pretty JSON."""
    return result.model_dump_json(indent=2)


def _result_to_csv(result: AnalysisResult) -> str:
    """Convert posts to a flat CSV table."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow(
        [
            "id",
            "platform",
            "author",
            "content",
            "url",
            "positive",
            "negative",
            "neutral",
            "compound",
            "keywords",
            "timestamp",
        ]
    )

    for post in result.posts:
        writer.writerow(
            [
                post.id,
                post.platform,
                post.author,
                post.content,
                post.url,
                post.sentiment.positive,
                post.sentiment.negative,
                post.sentiment.neutral,
                post.sentiment.compound,
                "; ".join(post.keywords),
                post.timestamp.isoformat(),
            ]
        )

    return buf.getvalue()


def _result_to_markdown(result: AnalysisResult) -> str:
    """Generate a formatted Markdown analysis report."""
    s = result.summary
    lines: list[str] = []

    lines.append(f"# Sentiment Analysis Report: {result.topic}")
    lines.append("")
    lines.append(f"*Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}*")
    lines.append("")

    # ── Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    if s.avg_compound > 0.1:
        tone = "**positive**"
    elif s.avg_compound < -0.1:
        tone = "**negative**"
    else:
        tone = "**neutral**"
    lines.append(
        f"Analysis of **{s.total_posts} posts** across "
        f"**{len(result.platforms)} platforms** reveals an overall "
        f"{tone} sentiment (compound score: **{s.avg_compound:.2f}**)."
    )
    lines.append("")

    # ── Key Metrics
    lines.append("## Key Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Posts | {s.total_posts} |")
    lines.append(f"| Average Compound | {s.avg_compound:.4f} |")
    lines.append(f"| Positive | {s.positive_pct:.1f}% |")
    lines.append(f"| Negative | {s.negative_pct:.1f}% |")
    lines.append(f"| Neutral | {s.neutral_pct:.1f}% |")
    lines.append("")

    # ── Platform Breakdown
    lines.append("## Platform Breakdown")
    lines.append("")
    lines.append("| Platform | Posts | Avg Sentiment | Positive | Negative | Neutral |")
    lines.append("|----------|-------|---------------|----------|----------|---------|")
    for p in result.platforms:
        lines.append(
            f"| {p.platform.capitalize()} | {p.post_count} | "
            f"{p.avg_sentiment:.4f} | {p.positive_pct:.1f}% | "
            f"{p.negative_pct:.1f}% | {p.neutral_pct:.1f}% |"
        )
    lines.append("")

    # ── Top Keywords
    if s.top_keywords:
        lines.append("## Top Keywords")
        lines.append("")
        lines.append(", ".join(f"`{kw}`" for kw in s.top_keywords))
        lines.append("")

    # ── Sentiment Over Time
    if s.sentiment_over_time:
        lines.append("## Sentiment Over Time")
        lines.append("")
        lines.append("| Date | Avg Sentiment | Posts | Positive | Negative | Neutral |")
        lines.append("|------|---------------|-------|----------|----------|---------|")
        for day in s.sentiment_over_time:
            lines.append(
                f"| {day['date']} | {day['avg_sentiment']:.4f} | "
                f"{day['post_count']} | {day['positive']} | "
                f"{day['negative']} | {day['neutral']} |"
            )
        lines.append("")

    # ── Notable Posts
    lines.append("## Notable Posts")
    lines.append("")
    if s.most_positive_post:
        lines.append("**Most Positive:**")
        lines.append(f"> {s.most_positive_post}")
        lines.append("")
    if s.most_negative_post:
        lines.append("**Most Negative:**")
        lines.append(f"> {s.most_negative_post}")
        lines.append("")

    # ── Research Plan
    if result.plan:
        lines.append("## Research Plan")
        lines.append("")
        lines.append(f"**Summary:** {result.plan.topic_summary}")
        lines.append("")
        if result.plan.search_queries:
            lines.append("**Search Queries:**")
            for q in result.plan.search_queries:
                lines.append(f"- {q}")
            lines.append("")

    lines.append("---")
    lines.append("*Report generated by Sentiment Analyzer Agent*")

    return "\n".join(lines)


@router.get("/{session_id}/export")
async def export_analysis(
    session_id: str,
    format: str = Query("json", pattern="^(json|csv|md)$"),
    version: int | None = Query(
        None, description="Version to export (default: current)"
    ),
):
    """Export analysis results as JSON, CSV, or Markdown.

    Query parameters:
        format: ``json`` | ``csv`` | ``md``
        version: Optional version number (defaults to current active version)
    """
    session, result, ver = await _resolve_result(session_id, version)
    topic = session.topic or "analysis"

    if format == "json":
        content = _result_to_json(result)
        media_type = "application/json"
        ext = "json"
    elif format == "csv":
        content = _result_to_csv(result)
        media_type = "text/csv"
        ext = "csv"
    else:  # md
        content = _result_to_markdown(result)
        media_type = "text/markdown"
        ext = "md"

    filename = _filename(topic, ver, ext)

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
