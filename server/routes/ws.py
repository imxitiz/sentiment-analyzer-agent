"""WebSocket endpoint for real-time agent event streaming.

Protocol::

    Client connects: ws://localhost:8000/ws/{session_id}
    Server sends JSON events:  { "type": "...", "agent": "...", "message": "...", "data": {...} }
    Client can send:           { "type": "user_message", "content": "..." }

Events flow through the SessionManager subscriber system:
  agent pipeline → SessionManager.emit_event() → WebSocket → browser
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.models import AgentEvent, MessageRole
from server.services.session_manager import session_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    """WebSocket connection for real-time session event streaming.

    On connect:
      • Validates session exists
      • Sends all past events as a replay (so late joiners catch up)
      • Subscribes to future events

    On disconnect:
      • Unsubscribes from events
    """
    session = await session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # Callback that forwards events to this WebSocket
    async def send_event(event: AgentEvent) -> None:
        try:
            await websocket.send_json(event.model_dump(mode="json"))
        except Exception:
            session_manager.unsubscribe(session_id, send_event)

    # Subscribe to future events
    session_manager.subscribe(session_id, send_event)

    try:
        # Replay past events so late joiners get caught up
        for past_event in session.events:
            await websocket.send_json(past_event.model_dump(mode="json"))

        # Send current status
        await websocket.send_json(
            {
                "type": "status_change",
                "agent": "",
                "message": f"Current status: {session.status.value}",
                "data": {"status": session.status.value},
                "timestamp": session.updated_at.isoformat(),
            }
        )

        # Listen for client messages
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                content = msg.get("content", "")

                if msg_type == "user_message" and content:
                    await session_manager.add_message(
                        session_id,
                        MessageRole.USER,
                        content,
                    )

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        session_manager.unsubscribe(session_id, send_event)
