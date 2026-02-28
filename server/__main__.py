"""Entry point for ``python -m server``.

Usage::

    uv run python -m server
    uv run python -m server --port 8000 --host 0.0.0.0
"""

from __future__ import annotations

import argparse

import uvicorn

from server.config import server_config


def main() -> None:
    """Run the FastAPI server with uvicorn."""
    parser = argparse.ArgumentParser(description="Sentiment Analyzer API Server")
    parser.add_argument("--host", default=server_config.HOST, help="Bind host")
    parser.add_argument("--port", type=int, default=server_config.PORT, help="Bind port")
    parser.add_argument("--reload", action="store_true", default=server_config.DEBUG, help="Enable auto-reload")
    args = parser.parse_args()

    print(f"🚀 Starting Sentiment Analyzer API on http://{args.host}:{args.port}")
    print(f"📖 API docs: http://localhost:{args.port}/api/docs")
    print(f"🔌 WebSocket: ws://localhost:{args.port}/ws/{{session_id}}")

    uvicorn.run(
        "server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
