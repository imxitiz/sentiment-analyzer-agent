"""
Logging – Production-grade structured logging for Sentiment Analyzer Agent.
===========================================================================

Every log entry is a **complete story**: WHO triggered it, WHAT happened,
WHY it happened, and in WHAT context (session / pipeline phase).

Quick-start
-----------
::

    from Logging import get_logger

    logger = get_logger("my_module")
    logger.info("scrape started", action="scrape", phase="HARVESTER",
                topic="elections", session_id="abc-123")

Context loggers (pre-bound fields)
-----------------------------------
::

    from Logging import context_logger

    log = context_logger(actor="orchestrator", phase="PLANNER",
                         session_id="abc-123", topic="elections")
    log.info("Generating keywords", action="keyword_gen")
    log.error("LLM timeout", action="llm_call", reason="network",
              meta={"provider": "google", "model": "gemini-2.5-flash"})

File logging
------------
Set ``LOG_DIR`` env-var (default ``logs/``) to write daily rotating log
files.  Console output is always enabled.

Ring buffer
-----------
Recent entries are kept in memory (default 1 000).  Useful for streaming
to a dashboard via WebSocket::

    from Logging import get_recent_logs, subscribe

    subscribe(lambda entry: ws.send(entry))
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Optional


# =====================================================================
# CONFIG (all overridable via environment variables)
# =====================================================================

_LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOG_DIR: str = os.environ.get("LOG_DIR", "logs")
_LOG_FILE_ENABLED: bool = os.environ.get("LOG_FILE_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
_LOG_MAX_BYTES: int = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
_LOG_BACKUP_COUNT: int = int(os.environ.get("LOG_BACKUP_COUNT", "5"))
_RING_BUFFER_SIZE: int = int(os.environ.get("LOG_BUFFER_SIZE", "1000"))

_CONFIGURED = False
_LOCK = threading.Lock()


# =====================================================================
# STRUCTURED LOG ENTRY (dict – zero-dependency JSON serialisation)
# =====================================================================

def _make_entry(
    level: str,
    name: str,
    message: str,
    *,
    actor: str = "system",
    session_id: str = "",
    topic: str = "",
    phase: str = "",
    action: str = "",
    reason: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured log entry dict."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "logger": name,
        "message": message,
        "context": {
            "actor": actor,
            "session_id": session_id,
            "topic": topic,
            "phase": phase,
            "action": action,
            "reason": reason,
            "meta": meta or {},
        },
    }


# =====================================================================
# RING BUFFER (thread-safe in-memory store)
# =====================================================================

class _RingBuffer:
    """Fixed-size, thread-safe ring buffer of log entries."""

    def __init__(self, maxlen: int = _RING_BUFFER_SIZE) -> None:
        self._buf: list[dict[str, Any]] = []
        self._maxlen = maxlen
        self._lock = threading.Lock()
        self._subscribers: set[Callable[[dict[str, Any]], Any]] = set()

    def push(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._buf.append(entry)
            if len(self._buf) > self._maxlen:
                self._buf.pop(0)
        for cb in list(self._subscribers):
            try:
                cb(entry)
            except Exception:
                pass  # subscriber errors must never crash the logger

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buf[-limit:])

    def subscribe(self, callback: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        self._subscribers.add(callback)
        return lambda: self._subscribers.discard(callback)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


_ring = _RingBuffer()


def get_recent_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent *limit* structured log entries."""
    return _ring.recent(limit)


def subscribe(callback: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
    """Subscribe to live log stream.  Returns an unsubscribe function."""
    return _ring.subscribe(callback)


# =====================================================================
# CUSTOM FORMATTERS
# =====================================================================

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_COLORS: dict[str, str] = {
    "DEBUG": "\033[90m",     # gray
    "INFO": "\033[36m",      # cyan
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[35m",  # magenta
    "SUCCESS": "\033[32m",   # green
}
_LEVEL_SHORT: dict[str, str] = {
    "DEBUG": "DBG",
    "INFO": "INF",
    "WARNING": "WRN",
    "ERROR": "ERR",
    "CRITICAL": "CRT",
    "SUCCESS": " OK",
}


class _ColorConsoleFormatter(logging.Formatter):
    """Pretty, colour-coded console formatter with structured context."""

    def format(self, record: logging.LogRecord) -> str:
        lvl = record.levelname
        color = _COLORS.get(lvl, "")
        label = _LEVEL_SHORT.get(lvl, lvl[:3])
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%H:%M:%S.%f"
        )[:-3]

        phase = getattr(record, "phase", "") or ""
        actor = getattr(record, "actor", "") or ""
        session_id = getattr(record, "session_id", "") or ""
        topic = getattr(record, "topic", "") or ""
        action = getattr(record, "action", "") or ""
        reason = getattr(record, "reason", "") or ""
        meta = getattr(record, "meta", None)

        parts: list[str] = [
            f"{_DIM}{ts}{_RESET}",
            f"{color}{_BOLD}[{label}]{_RESET}",
            f"{_BOLD}[{phase or 'SYSTEM':^10s}]{_RESET}",
        ]
        if actor:
            parts.append(f"{_DIM}actor={actor}{_RESET}")
        if session_id:
            parts.append(f"{_DIM}sid={session_id[:8]}{_RESET}")
        if topic:
            parts.append(f'{_DIM}topic="{topic}"{_RESET}')

        parts.append(f"{color}{record.getMessage()}{_RESET}")

        if action:
            parts.append(f"{_DIM}[{action}]{_RESET}")
        if reason:
            parts.append(f"{_DIM}// {reason}{_RESET}")

        line = " ".join(parts)

        if meta:
            line += f"\n  {_DIM}meta: {json.dumps(meta, default=str)}{_RESET}"
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line += f"\n{record.exc_text}"
        return line


class _JSONFileFormatter(logging.Formatter):
    """One JSON object per line — no colour, machine-parseable."""

    def format(self, record: logging.LogRecord) -> str:
        entry = _make_entry(
            level=record.levelname,
            name=record.name,
            message=record.getMessage(),
            actor=getattr(record, "actor", "system"),
            session_id=getattr(record, "session_id", ""),
            topic=getattr(record, "topic", ""),
            phase=getattr(record, "phase", ""),
            action=getattr(record, "action", ""),
            reason=getattr(record, "reason", ""),
            meta=getattr(record, "meta", None),
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


# =====================================================================
# RING BUFFER HANDLER
# =====================================================================

class _RingBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        entry = _make_entry(
            level=record.levelname,
            name=record.name,
            message=record.getMessage(),
            actor=getattr(record, "actor", "system"),
            session_id=getattr(record, "session_id", ""),
            topic=getattr(record, "topic", ""),
            phase=getattr(record, "phase", ""),
            action=getattr(record, "action", ""),
            reason=getattr(record, "reason", ""),
            meta=getattr(record, "meta", None),
        )
        if record.exc_info:
            entry["exception"] = self.format(record)
        _ring.push(entry)


# =====================================================================
# SUCCESS LEVEL (custom – between INFO and WARNING)
# =====================================================================

SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def _success(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)


logging.Logger.success = _success  # type: ignore[attr-defined]


# =====================================================================
# CONFIGURE (called once, idempotent)
# =====================================================================

def _configure(level: Optional[str] = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    with _LOCK:
        if _CONFIGURED:
            return

        root = logging.getLogger()
        root.handlers.clear()

        numeric = getattr(logging, (level or _LOG_LEVEL).upper(), logging.INFO)
        root.setLevel(numeric)

        # 1) Console handler (always)
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(_ColorConsoleFormatter())
        console.setLevel(numeric)
        root.addHandler(console)

        # 2) JSON file handler (if enabled)
        if _LOG_FILE_ENABLED:
            log_dir = Path(_LOG_DIR)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "ssa.log"
            fh = RotatingFileHandler(
                log_file,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            fh.setFormatter(_JSONFileFormatter())
            fh.setLevel(logging.DEBUG)
            root.addHandler(fh)

        # 3) Ring buffer handler
        ring_handler = _RingBufferHandler()
        ring_handler.setLevel(logging.DEBUG)
        root.addHandler(ring_handler)

        _CONFIGURED = True


# =====================================================================
# STRUCTURED LOGGER WRAPPER
# =====================================================================

class StructuredLogger:
    """Thin wrapper around ``logging.Logger`` that accepts structured
    context as keyword arguments.

    Every level method (debug/info/warning/error/critical/success) accepts
    these **optional** kwargs on every call::

        actor, session_id, topic, phase, action, reason, meta
    """

    _CONTEXT_KEYS = frozenset(
        ("actor", "session_id", "topic", "phase", "action", "reason", "meta")
    )

    def __init__(self, inner: logging.Logger) -> None:
        self._inner = inner

    @property
    def name(self) -> str:
        return self._inner.name

    def isEnabledFor(self, level: int) -> bool:
        return self._inner.isEnabledFor(level)

    def _split(self, kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        ctx = {k: kwargs.pop(k) for k in list(kwargs) if k in self._CONTEXT_KEYS}
        return ctx, kwargs

    def _log(self, level: int, msg: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        ctx, remaining = self._split(kwargs)
        self._inner.log(level, msg, *args, extra=ctx, **remaining)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, args, kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, args, kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, args, kwargs)

    warn = warning

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, args, kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, args, kwargs)

    def success(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(SUCCESS_LEVEL, msg, args, kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        kwargs["exc_info"] = kwargs.get("exc_info", True)
        self._log(logging.ERROR, msg, args, kwargs)


# =====================================================================
# CONTEXT LOGGER (pre-bound fields)
# =====================================================================

class _ContextLogger:
    """Logger with pre-bound context fields.

    Every call merges defaults with per-call overrides (per-call wins).
    """

    def __init__(self, inner: StructuredLogger, defaults: dict[str, Any]) -> None:
        self._inner = inner
        self._defaults = defaults

    def _merge(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {**self._defaults, **kwargs}

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.debug(msg, *args, **self._merge(kwargs))

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.info(msg, *args, **self._merge(kwargs))

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.warning(msg, *args, **self._merge(kwargs))

    warn = warning

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.error(msg, *args, **self._merge(kwargs))

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.critical(msg, *args, **self._merge(kwargs))

    def success(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.success(msg, *args, **self._merge(kwargs))

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._inner.exception(msg, *args, **self._merge(kwargs))


# =====================================================================
# PUBLIC API
# =====================================================================

def get_logger(name: str) -> StructuredLogger:
    """Return a ``StructuredLogger`` for *name*.

    Ensures the logging system is configured on first call.
    """
    _configure()
    return StructuredLogger(logging.getLogger(name))


def context_logger(
    name: str = "ssa",
    *,
    actor: str = "system",
    session_id: str = "",
    topic: str = "",
    phase: str = "",
    action: str = "",
    **extra_defaults: Any,
) -> _ContextLogger:
    """Create a child logger with pre-bound context fields.

    Example::

        log = context_logger("BaseLLM", actor="gemini_adapter",
                             phase="LLM", session_id="abc-123")
        log.info("generation started", action="generate")
        log.error("timeout", reason="upstream_timeout",
                  meta={"model": "gemini-2.5-flash"})
    """
    base = get_logger(name)
    defaults: dict[str, Any] = {
        "actor": actor,
        "session_id": session_id,
        "topic": topic,
        "phase": phase,
        "action": action,
        **extra_defaults,
    }
    return _ContextLogger(base, defaults)


def new_session_id() -> str:
    """Generate a unique session ID for tracking a request end-to-end."""
    return uuid.uuid4().hex[:12]


# =====================================================================
# MODULE-LEVEL INIT (safe to import multiple times)
# ======================== =============================================

_configure()
