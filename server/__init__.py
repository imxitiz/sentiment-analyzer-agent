"""Web API server — FastAPI bridge between the agent pipeline and the Interface.

This package provides:
    • REST endpoints for session management (CRUD, start analysis)
    • WebSocket endpoint for real-time agent progress streaming
    • Mock data service for frontend development without LLM keys

Usage::

    # Development
    uv run python -m server

    # Or with uvicorn directly
    uv run uvicorn server.app:app --reload --port 8000
"""
