from __future__ import annotations
from Logging import get_logger
import uuid
from contextlib import contextmanager

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import contextvars

logger = get_logger("agents.services.llm_tracer")


_LLM_TRACE_TOPIC: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_trace_topic",
    default=None,
)
_LLM_TRACE_AGENT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_trace_agent",
    default=None,
)


_DB_DIR = Path("data/scrapes")


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:80].strip("-") or "untitled-topic"


def db_path_for_topic(topic: str) -> Path:
    """Return per-topic SQLite path, creating parent directory if needed."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    return _DB_DIR / f"{_slugify(topic)}.db"


def _connect(topic: str) -> sqlite3.Connection:
    path = db_path_for_topic(topic)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


@contextmanager
def llm_trace_context(topic: str, source_agent: str | None = None):
    """Set topic/agent context for BaseLLM trace persistence.

    Context is stored in contextvars so BaseLLM can persist per-call traces
    without every caller passing topic metadata manually.
    """
    normalized_topic = topic.strip()
    if not normalized_topic:
        yield
        return

    topic_token = _LLM_TRACE_TOPIC.set(normalized_topic)
    agent_token = _LLM_TRACE_AGENT.set(source_agent)
    try:
        yield
    finally:
        _LLM_TRACE_TOPIC.reset(topic_token)
        _LLM_TRACE_AGENT.reset(agent_token)


def get_llm_trace_context() -> tuple[str | None, str | None]:
    """Return current topic/agent context used for LLM trace persistence."""
    return (_LLM_TRACE_TOPIC.get(), _LLM_TRACE_AGENT.get())


def save_llm_trace(
    topic: str,
    *,
    provider: str,
    model: str,
    call_kind: str,
    input_messages: list[dict[str, Any]] | None = None,
    input_text: str | None = None,
    output_text: str | None = None,
    error_text: str | None = None,
    latency_ms: float | None = None,
    source_agent: str | None = None,
    request_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """Append one BaseLLM request/response trace row into topic DB."""
    created_at = datetime.now(timezone.utc).isoformat()
    req_id = request_id or str(uuid.uuid4())
    meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
    messages_json = (
        json.dumps(input_messages, ensure_ascii=False)
        if input_messages is not None
        else None
    )
    with _connect(topic) as conn:
        conn.execute(
            """
            INSERT INTO llm_traces(
                created_at, request_id, source_agent, provider, model, call_kind,
                input_messages_json, input_text, output_text, error_text, latency_ms, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                req_id,
                source_agent,
                provider,
                model,
                call_kind,
                messages_json,
                input_text,
                output_text,
                error_text,
                latency_ms,
                meta_json,
            ),
        )
    return req_id
