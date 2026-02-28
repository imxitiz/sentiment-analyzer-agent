"""Mock data generator — realistic fake data for frontend development.

Generates analysis results that look like real sentiment analysis output
so the dashboard can be developed and tested without running the actual
pipeline or requiring any API keys.

Usage::

    from server.services.mock import generate_mock_result
    result = generate_mock_result("Nepal elections 2026")
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Any

from server.models import (
    AnalysedPost,
    AnalysisResult,
    PlatformBreakdown,
    ResearchPlanData,
    SentimentScore,
    SentimentSummary,
)


def _make_id(seed: str, idx: int) -> str:
    """Deterministic short ID from seed + index."""
    return hashlib.md5(f"{seed}-{idx}".encode()).hexdigest()[:12]


# ── Content Templates ─────────────────────────────────────────────────

_POSITIVE_TEMPLATES = [
    "I'm really excited about {topic}! This could change everything.",
    "Great progress on {topic}. The future looks bright.",
    "{topic} is definitely moving in the right direction. Impressive work.",
    "The latest developments in {topic} are truly encouraging.",
    "I've been following {topic} closely and I'm cautiously optimistic.",
    "Finally some good news about {topic}! This is what we needed.",
    "Love seeing the momentum around {topic}. Keep it going!",
    "{topic} just keeps getting better. Really proud of how far we've come.",
    "The data on {topic} is very promising. Looking forward to what's next.",
    "Incredibly bullish on {topic}. The fundamentals are strong.",
]

_NEGATIVE_TEMPLATES = [
    "I'm very concerned about the direction of {topic}. This isn't sustainable.",
    "{topic} has been nothing but disappointment. When will things change?",
    "The handling of {topic} has been a disaster. Someone needs to be accountable.",
    "Deeply worried about {topic}. The current approach is failing.",
    "Another setback for {topic}. At this point I've lost all confidence.",
    "{topic} criticism is absolutely warranted. The numbers don't lie.",
    "The state of {topic} is alarming. We need radical changes immediately.",
    "Can't believe how badly {topic} has been managed. Total incompetence.",
    "{topic} is heading in a terrible direction and nobody seems to care.",
    "Disappointed doesn't even begin to describe my feelings about {topic}.",
]

_NEUTRAL_TEMPLATES = [
    "Interesting developments regarding {topic}. Need to see more data.",
    "Following {topic} with interest. It could go either way at this point.",
    "{topic} update: things are proceeding as expected. Nothing surprising.",
    "Attended a discussion about {topic} today. A mix of perspectives.",
    "The latest report on {topic} shows some mixed signals. Analyzing further.",
    "Not sure what to make of {topic} yet. The evidence is inconclusive.",
    "{topic} is evolving. Hard to say whether it's positive or negative.",
    "Observed some changes in {topic}. The data is still being collected.",
    "The discourse around {topic} is getting more nuanced. Both sides have points.",
    "{topic} remains a complex issue with no easy answers.",
]

_PLATFORMS = ["reddit", "twitter", "news", "facebook", "youtube"]
_AUTHORS_BY_PLATFORM = {
    "reddit": ["u/data_nerd_42", "u/policy_wonk", "u/concerned_citizen", "u/optimist_prime", "u/deep_thinker"],
    "twitter": ["@analyst_pro", "@citizen_voice", "@news_watcher", "@data_driven", "@street_perspective"],
    "news": ["Reuters", "AP News", "The Guardian", "Al Jazeera", "BBC"],
    "facebook": ["Citizen Forum Group", "Policy Discussion", "Community Watch", "Local Voices", "Public Debate"],
    "youtube": ["DataViz Pro", "Analysis Channel", "Street Interviews", "Policy Explained", "Deep Dive News"],
}


def _random_sentiment(bias: str = "neutral") -> SentimentScore:
    """Generate a random but coherent sentiment score with a bias."""
    if bias == "positive":
        pos = random.uniform(0.5, 0.95)
        neg = random.uniform(0.01, 0.2)
    elif bias == "negative":
        pos = random.uniform(0.01, 0.2)
        neg = random.uniform(0.5, 0.95)
    else:
        pos = random.uniform(0.15, 0.55)
        neg = random.uniform(0.15, 0.55)

    neu = max(0, 1.0 - pos - neg)
    compound = round(pos - neg, 4)
    return SentimentScore(
        positive=round(pos, 4),
        negative=round(neg, 4),
        neutral=round(neu, 4),
        compound=round(compound, 4),
    )


def _generate_posts(topic: str, count: int = 150) -> list[AnalysedPost]:
    """Generate a list of mock analysed posts."""
    posts: list[AnalysedPost] = []
    now = datetime.now()

    # Distribution: ~35% positive, ~25% negative, ~40% neutral
    biases = (
        ["positive"] * int(count * 0.35) +
        ["negative"] * int(count * 0.25) +
        ["neutral"] * (count - int(count * 0.35) - int(count * 0.25))
    )
    random.shuffle(biases)

    templates = {
        "positive": _POSITIVE_TEMPLATES,
        "negative": _NEGATIVE_TEMPLATES,
        "neutral": _NEUTRAL_TEMPLATES,
    }

    topic_keywords = [w.lower() for w in topic.split() if len(w) > 2]
    extra_keywords = ["sentiment", "analysis", "opinion", "public", "trend", "data"]

    for i, bias in enumerate(biases):
        platform = random.choice(_PLATFORMS)
        author = random.choice(_AUTHORS_BY_PLATFORM[platform])
        template = random.choice(templates[bias])
        content = template.format(topic=topic)

        post_keywords = random.sample(topic_keywords, min(2, len(topic_keywords)))
        post_keywords += random.sample(extra_keywords, random.randint(1, 3))

        posts.append(AnalysedPost(
            id=_make_id(topic, i),
            platform=platform,
            author=author,
            content=content,
            url=f"https://{platform}.com/post/{_make_id(topic, i)}",
            sentiment=_random_sentiment(bias),
            keywords=post_keywords,
            timestamp=now - timedelta(
                hours=random.randint(0, 168),  # up to 1 week
                minutes=random.randint(0, 59),
            ),
        ))

    # Sort by timestamp descending
    posts.sort(key=lambda p: p.timestamp, reverse=True)
    return posts


def _compute_platform_breakdown(posts: list[AnalysedPost]) -> list[PlatformBreakdown]:
    """Aggregate posts by platform."""
    by_platform: dict[str, list[AnalysedPost]] = {}
    for post in posts:
        by_platform.setdefault(post.platform, []).append(post)

    breakdowns: list[PlatformBreakdown] = []
    for platform, platform_posts in sorted(by_platform.items()):
        compounds = [p.sentiment.compound for p in platform_posts]
        avg = sum(compounds) / len(compounds) if compounds else 0

        pos_count = sum(1 for c in compounds if c > 0.2)
        neg_count = sum(1 for c in compounds if c < -0.2)
        neu_count = len(compounds) - pos_count - neg_count
        total = len(compounds) or 1

        # Collect top keywords
        kw_counts: dict[str, int] = {}
        for p in platform_posts:
            for kw in p.keywords:
                kw_counts[kw] = kw_counts.get(kw, 0) + 1
        top_kws = sorted(kw_counts, key=kw_counts.get, reverse=True)[:5]  # type: ignore[arg-type]

        breakdowns.append(PlatformBreakdown(
            platform=platform,
            post_count=len(platform_posts),
            avg_sentiment=round(avg, 4),
            positive_pct=round(pos_count / total * 100, 1),
            negative_pct=round(neg_count / total * 100, 1),
            neutral_pct=round(neu_count / total * 100, 1),
            top_keywords=top_kws,
        ))

    return breakdowns


def _compute_summary(
    topic: str,
    posts: list[AnalysedPost],
) -> SentimentSummary:
    """Compute aggregate sentiment statistics."""
    compounds = [p.sentiment.compound for p in posts]
    avg = sum(compounds) / len(compounds) if compounds else 0

    pos_count = sum(1 for c in compounds if c > 0.2)
    neg_count = sum(1 for c in compounds if c < -0.2)
    neu_count = len(compounds) - pos_count - neg_count
    total = len(compounds) or 1

    # Find extremes
    most_pos = max(posts, key=lambda p: p.sentiment.compound) if posts else None
    most_neg = min(posts, key=lambda p: p.sentiment.compound) if posts else None

    # Top keywords across all posts
    kw_counts: dict[str, int] = {}
    for p in posts:
        for kw in p.keywords:
            kw_counts[kw] = kw_counts.get(kw, 0) + 1
    top_kws = sorted(kw_counts, key=kw_counts.get, reverse=True)[:10]  # type: ignore[arg-type]

    # Sentiment over time (daily buckets)
    daily: dict[str, list[float]] = {}
    for p in posts:
        day = p.timestamp.strftime("%Y-%m-%d")
        daily.setdefault(day, []).append(p.sentiment.compound)

    sentiment_over_time = [
        {
            "date": day,
            "avg_sentiment": round(sum(scores) / len(scores), 4),
            "post_count": len(scores),
            "positive": sum(1 for s in scores if s > 0.2),
            "negative": sum(1 for s in scores if s < -0.2),
            "neutral": sum(1 for s in scores if -0.2 <= s <= 0.2),
        }
        for day, scores in sorted(daily.items())
    ]

    return SentimentSummary(
        total_posts=len(posts),
        avg_compound=round(avg, 4),
        positive_pct=round(pos_count / total * 100, 1),
        negative_pct=round(neg_count / total * 100, 1),
        neutral_pct=round(neu_count / total * 100, 1),
        most_positive_post=most_pos.content if most_pos else "",
        most_negative_post=most_neg.content if most_neg else "",
        top_keywords=top_kws,
        sentiment_over_time=sentiment_over_time,
    )


def generate_mock_plan(topic: str) -> ResearchPlanData:
    """Generate a mock research plan for the given topic."""
    slug = topic.lower().replace(" ", "")
    return ResearchPlanData(
        topic_summary=f"Comprehensive sentiment analysis of public opinion on: {topic}",
        keywords=[
            topic, f"{topic} opinion", f"{topic} sentiment",
            f"{topic} debate", f"{topic} controversy", f"{topic} support",
            f"{topic} criticism", f"{topic} public opinion",
            f"{topic} social media", f"{topic} news",
        ],
        hashtags=[
            f"#{slug}", f"#{slug}opinion", f"#{slug}debate",
            f"#{slug}news", f"#{slug}sentiment", f"#{slug}trending",
        ],
        platforms=[
            {"name": "reddit", "priority": "high", "reason": f"Large discussion threads on {topic}"},
            {"name": "twitter", "priority": "high", "reason": "Real-time public opinion"},
            {"name": "news", "priority": "medium", "reason": "Editorial perspectives"},
            {"name": "facebook", "priority": "medium", "reason": "Community group discussions"},
            {"name": "youtube", "priority": "low", "reason": "Comment sentiment on related videos"},
        ],
        search_queries=[
            f"{topic} sentiment", f"{topic} public opinion",
            f"site:reddit.com {topic}", f"site:twitter.com {topic}",
            f"{topic} news analysis", f'"{topic}" reaction OR response',
        ],
        estimated_volume=f"Expected 500-2000 posts across 5 platforms for '{topic}'",
        reasoning=f"Multi-platform strategy targeting diverse opinion sources for '{topic}'",
    )


def generate_mock_result(topic: str, post_count: int = 150) -> AnalysisResult:
    """Generate a complete mock analysis result.

    Returns a fully populated ``AnalysisResult`` with realistic but
    synthetic data.  The distribution is roughly 35% positive, 25%
    negative, 40% neutral — a realistic public opinion mix.

    Args:
        topic: The analysis topic.
        post_count: Number of mock posts to generate.

    Returns:
        Complete ``AnalysisResult`` ready for dashboard rendering.
    """
    random.seed(hash(topic) % (2**31))  # Deterministic per topic

    posts = _generate_posts(topic, post_count)
    platforms = _compute_platform_breakdown(posts)
    summary = _compute_summary(topic, posts)
    plan = generate_mock_plan(topic)

    return AnalysisResult(
        topic=topic,
        plan=plan,
        summary=summary,
        posts=posts,
        platforms=platforms,
        completed_at=datetime.now(),
    )
