"""Session manager — in-memory session store and state machine.

Manages the lifecycle of analysis sessions.  Sessions are stored in
memory (dict) for now — future versions will persist to a database.

Thread-safe via asyncio locks (single event loop model).

Usage::

    from server.services.session_manager import session_manager

    session = await session_manager.create_session(topic="Nepal elections")
    session = await session_manager.get_session(session.id)
    sessions = await session_manager.list_sessions()
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from server.models import (
    AgentEvent,
    AgentEventType,
    AnalysisResult,
    ChatMessage,
    MessageRole,
    Session,
    SessionStatus,
    VersionSnapshot,
)


class SessionManager:
    """In-memory session store with async state management."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        # WebSocket connections per session: {session_id: set[callback]}
        self._subscribers: dict[str, set[Any]] = {}

    async def create_session(
        self,
        topic: str | None = None,
        llm_provider: str = "dummy",
    ) -> Session:
        """Create a new analysis session."""
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        session = Session(
            id=session_id,
            topic=topic,
            status=SessionStatus.IDLE,
            llm_provider=llm_provider,
            created_at=now,
            updated_at=now,
        )

        if topic:
            # Add initial user message
            session.messages.append(ChatMessage(
                id=str(uuid.uuid4())[:8],
                role=MessageRole.USER,
                content=topic,
                timestamp=now,
            ))

        async with self._lock:
            self._sessions[session_id] = session

        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    async def list_sessions(self) -> list[Session]:
        """List all sessions, most recent first."""
        sessions = list(self._sessions.values())
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._subscribers.pop(session_id, None)
                return True
            return False

    async def update_status(
        self,
        session_id: str,
        status: SessionStatus,
    ) -> Session | None:
        """Update session status and notify subscribers."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        async with self._lock:
            session.status = status
            session.updated_at = datetime.now()

        # Emit status change event
        await self.emit_event(session_id, AgentEvent(
            type=AgentEventType.STATUS_CHANGE,
            message=f"Status changed to {status.value}",
            data={"status": status.value},
        ))

        return session

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage | None:
        """Add a message to the session conversation."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        msg = ChatMessage(
            id=str(uuid.uuid4())[:8],
            role=role,
            content=content,
            metadata=metadata or {},
        )

        async with self._lock:
            session.messages.append(msg)
            session.updated_at = datetime.now()

        return msg

    async def add_event(
        self,
        session_id: str,
        event: AgentEvent,
    ) -> None:
        """Record an agent event and notify WebSocket subscribers."""
        session = self._sessions.get(session_id)
        if not session:
            return

        async with self._lock:
            session.events.append(event)
            session.updated_at = datetime.now()

        await self.emit_event(session_id, event)

    async def set_result(
        self,
        session_id: str,
        result: AnalysisResult,
    ) -> None:
        """Set the analysis result for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return

        async with self._lock:
            session.result = result
            session.status = SessionStatus.COMPLETED
            session.updated_at = datetime.now()

    async def refresh_session(
        self,
        session_id: str,
    ) -> Session | None:
        """Reset a completed session for re-analysis (version bump).

        Archives the current version's data into ``version_history``
        before clearing for the new run.  Old data is never lost.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        async with self._lock:
            # Archive current version before clearing
            snapshot = VersionSnapshot(
                version=session.version,
                result=session.result,
                events=list(session.events),
                started_at=session.created_at if session.version == 1 else session.updated_at,
                completed_at=datetime.now(),
            )
            session.version_history.append(snapshot)

            session.version += 1
            session.result = None
            session.events = []
            session.status = SessionStatus.IDLE
            session.updated_at = datetime.now()

        return session

    async def switch_version(
        self,
        session_id: str,
        target_version: int,
    ) -> Session | None:
        """Switch a session's active view to a historical version.

        Swaps the current result/events with the archived version
        and archives the current data in its place.
        If ``target_version`` equals the latest version, restores
        live data from the most recent run.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Already viewing the requested version
        if target_version == session.version:
            return session

        # Find the target snapshot in history
        target_idx: int | None = None
        for i, snap in enumerate(session.version_history):
            if snap.version == target_version:
                target_idx = i
                break

        if target_idx is None:
            return None  # Version not found

        async with self._lock:
            target_snap = session.version_history[target_idx]

            # Archive current version into the slot where target was
            current_snap = VersionSnapshot(
                version=session.version,
                result=session.result,
                events=list(session.events),
                started_at=session.created_at if session.version == 1 else session.updated_at,
                completed_at=datetime.now(),
            )
            session.version_history[target_idx] = current_snap

            # Restore target version data
            session.version = target_snap.version
            session.result = target_snap.result
            session.events = list(target_snap.events)
            session.updated_at = datetime.now()

            # Keep status as completed if we have a result
            if session.result:
                session.status = SessionStatus.COMPLETED

        return session

    # ── WebSocket subscriber management ───────────────────────────────

    def subscribe(self, session_id: str, callback: Any) -> None:
        """Register a WebSocket callback for session events."""
        self._subscribers.setdefault(session_id, set()).add(callback)

    def unsubscribe(self, session_id: str, callback: Any) -> None:
        """Remove a WebSocket callback."""
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(callback)
            if not subs:
                del self._subscribers[session_id]

    async def emit_event(self, session_id: str, event: AgentEvent) -> None:
        """Send an event to all WebSocket subscribers for a session."""
        subs = self._subscribers.get(session_id, set())
        for callback in list(subs):
            try:
                await callback(event)
            except Exception:
                # Remove broken connections
                subs.discard(callback)


# ── Singleton ─────────────────────────────────────────────────────────

session_manager = SessionManager()
