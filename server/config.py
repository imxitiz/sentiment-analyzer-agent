"""Server configuration — centralised settings for the FastAPI backend."""

from __future__ import annotations

import os


class ServerConfig:
    """Server configuration loaded from environment with sensible defaults."""

    HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",   # Bun dev server
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    DEBUG: bool = os.getenv("SERVER_DEBUG", "true").lower() == "true"
    DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "dummy")
    DEFAULT_LLM_MODEL: str | None = os.getenv("DEFAULT_LLM_MODEL", None)


server_config = ServerConfig()
