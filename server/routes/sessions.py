"""Session CRUD + analysis trigger endpoints.

Routes::

    GET    /api/sessions           → list all sessions
    POST   /api/sessions           → create a new session
    GET    /api/sessions/{id}      → get session detail
    DELETE /api/sessions/{id}      → delete a session
    POST   /api/sessions/{id}/start    → start analysis
    POST   /api/sessions/{id}/messages → send a message
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException

from agents.services import bootstrap_topic
from server.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    MessageRole,
    SendMessageRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionStatus,
    StartAnalysisRequest,
    SwitchVersionRequest,
    VersionListResponse,
)
from server.services.session_manager import session_manager
from server.services.pipeline import run_analysis

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions():
    """Get all analysis sessions."""
    sessions = await session_manager.list_sessions()
    return SessionListResponse(sessions=sessions)


@router.post("", response_model=CreateSessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest):
    """Create a new analysis session.

    If ``topic`` is provided, the session is created with the topic
    already set (but analysis is NOT started automatically — call
    ``/start`` for that).
    """
    session = await session_manager.create_session(
        topic=req.topic,
        llm_provider=req.llm_provider,
    )
    return CreateSessionResponse(session=session)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    """Get a single session by ID."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse(session=session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """Delete a session."""
    deleted = await session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/{session_id}/start", response_model=SessionDetailResponse)
async def start_analysis(
    session_id: str,
    req: StartAnalysisRequest,
    background_tasks: BackgroundTasks,
):
    """Start the analysis pipeline for a session.

    This triggers the full pipeline (plan → search → scrape → clean →
    analyse) as a background task.  Progress is streamed via WebSocket.

    The session must be in ``idle`` or ``error`` status to restart.
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in (SessionStatus.IDLE, SessionStatus.ERROR, SessionStatus.COMPLETED):
        raise HTTPException(
            status_code=409,
            detail=f"Session is already {session.status.value}. Wait for completion or create a new session.",
        )

    # Update topic if different
    session.topic = req.topic
    session.llm_provider = req.llm_provider

    # Bootstrap DB checkpointing immediately on topic intake
    bootstrap_topic(req.topic)

    # Add user message
    await session_manager.add_message(
        session_id, MessageRole.USER, req.topic,
    )

    # Add assistant acknowledgment
    await session_manager.add_message(
        session_id, MessageRole.ASSISTANT,
        f"Starting sentiment analysis for **\"{req.topic}\"**...\n\n"
        f"I'll analyse public opinion across multiple platforms. "
        f"This typically takes 30-60 seconds.",
    )

    # Launch pipeline as background task
    background_tasks.add_task(
        run_analysis,
        session_id=session_id,
        topic=req.topic,
        provider=req.llm_provider,
        model=req.llm_model,
    )

    # Return updated session
    session = await session_manager.get_session(session_id)
    return SessionDetailResponse(session=session)  # type: ignore[arg-type]


@router.post("/{session_id}/refresh", response_model=SessionDetailResponse)
async def refresh_analysis(
    session_id: str,
    background_tasks: BackgroundTasks,
):
    """Refresh (re-run) analysis for a completed session.

    Bumps the version, clears old results/events, and re-runs the
    pipeline with the same topic.  Progress is streamed via WebSocket.
    This creates a V2 (V3, …) of the same analysis.
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Only completed sessions can be refreshed. Current status: {session.status.value}",
        )

    if not session.topic:
        raise HTTPException(status_code=400, detail="Session has no topic to refresh")

    topic = session.topic
    provider = session.llm_provider

    # Refresh creates a new run entry linked to the same topic DB
    bootstrap_topic(topic)

    # Bump version and clear old data
    session = await session_manager.refresh_session(session_id)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to reset session")

    # Add system message about the refresh
    await session_manager.add_message(
        session_id, MessageRole.ASSISTANT,
        f"**Refreshing analysis (v{session.version})** for **\"{topic}\"**…\n\n"
        f"Re-collecting and re-analysing data to get the latest sentiment.",
    )

    # Re-run pipeline
    background_tasks.add_task(
        run_analysis,
        session_id=session_id,
        topic=topic,
        provider=provider,
    )

    session = await session_manager.get_session(session_id)
    return SessionDetailResponse(session=session)  # type: ignore[arg-type]


@router.get("/{session_id}/versions", response_model=VersionListResponse)
async def list_versions(session_id: str):
    """List all archived versions for a session.

    Returns the current active version number and all archived
    version snapshots.  The active version's data is on the session
    itself; historical versions live in ``version_history``.
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return VersionListResponse(
        current_version=session.version,
        versions=session.version_history,
    )


@router.post("/{session_id}/version", response_model=SessionDetailResponse)
async def switch_version(session_id: str, req: SwitchVersionRequest):
    """Switch the session's active view to a different version.

    Swaps the current result/events with the archived version data.
    The previously active data is archived in its place so nothing
    is ever lost.
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Collect all available versions: current + history
    available = {session.version} | {v.version for v in session.version_history}
    if req.version not in available:
        raise HTTPException(
            status_code=404,
            detail=f"Version {req.version} not found. Available: {sorted(available)}",
        )

    if req.version == session.version:
        return SessionDetailResponse(session=session)

    updated = await session_manager.switch_version(session_id, req.version)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to switch version")

    return SessionDetailResponse(session=updated)


@router.post("/{session_id}/messages", response_model=SessionDetailResponse)
async def send_message(session_id: str, req: SendMessageRequest):
    """Send a message to a session (e.g., clarification response).

    Currently just records the message. Future: triggers the appropriate
    agent response based on session state.
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await session_manager.add_message(
        session_id, MessageRole.USER, req.content,
    )

    # If session is completed, add a chat response using the analysis results
    if session.status == SessionStatus.COMPLETED and session.result:
        # Simple echo for now — future: RAG-powered responses
        await session_manager.add_message(
            session_id, MessageRole.ASSISTANT,
            f"Thanks for your question about **\"{session.topic}\"**.\n\n"
            f"Based on the analysis of {session.result.summary.total_posts} posts, "
            f"the overall sentiment is "
            f"{'positive' if session.result.summary.avg_compound > 0.1 else 'negative' if session.result.summary.avg_compound < -0.1 else 'neutral'} "
            f"(compound score: {session.result.summary.avg_compound:.2f}).\n\n"
            f"*RAG-powered conversational answers coming soon!*",
        )

    session = await session_manager.get_session(session_id)
    return SessionDetailResponse(session=session)  # type: ignore[arg-type]
