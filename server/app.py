"""FastAPI application factory.

Creates and configures the FastAPI app with:
    • CORS middleware (allow Interface dev server)
    • REST routes (session CRUD, analysis)
    • WebSocket route (real-time streaming)
    • Health check endpoint

Usage::

    # Development (with auto-reload)
    uv run uvicorn server.app:app --reload --port 8000

    # Or via the __main__ entry point
    uv run python -m server
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import server_config
from server.routes import sessions, ws


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="Sentiment Analyzer API",
        description=(
            "Backend API for the Sentiment Analyzer Agent — "
            "manages analysis sessions, streams real-time agent progress, "
            "and serves dashboard data."
        ),
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=server_config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ────────────────────────────────────────────────────────
    app.include_router(sessions.router)
    app.include_router(ws.router)

    # ── Health check ──────────────────────────────────────────────────
    @app.get("/api/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "service": "sentiment-analyzer-api"}

    return app


app = create_app()
