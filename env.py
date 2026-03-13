"""
env – Centralized, logged environment variable access.
=======================================================

**Never** call ``os.getenv()`` directly in the rest of the codebase.
Always import from here so that every access is logged and auditable::

    from env import config

    config.GOOGLE_API_KEY      # reads + logs on first access
    config.OPENAI_API_KEY      # reads + logs on first access

The ``EnvConfig`` class:
    • Reads from ``os.environ`` (supports ``.env`` files via ``dotenv`` if installed).
    • Masks secret values in logs (shows ``GOOG…4xFq`` instead of the full key).
    • Logs a WARNING for any missing required key.
    • Logs an INFO for every successful read (once per key).
    • Is a singleton – safe to import from anywhere.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from Logging import get_logger

logger = get_logger("env")


def _mask_secret(value: str, *, visible: int = 4) -> str:
    """Return a masked version of *value* safe for logging.

    Shows the first *visible* and last *visible* chars with ``…`` in between.
    Short values are fully masked.
    """
    if len(value) <= visible * 2 + 2:
        return "***"
    return f"{value[:visible]}…{value[-visible:]}"


class EnvConfig:
    """Singleton that reads, caches, and logs environment variable access.

    Declare all known keys as class-level annotations with a default of
    ``None``.  On first attribute access the value is read from
    ``os.environ``, logged, cached, and returned.
    """

    # ── Declared keys ────────────────────────────────────────────────
    # Add new env vars here.  Default = None means "optional".
    _KEYS: dict[str, str | None] = {
        "GOOGLE_API_KEY": None,
        "OPENAI_API_KEY": None,
        "SERPER_API_KEY": None,
        "FIRECRAWL_API_KEY": None,
        "CRAWLBASE_TOKEN": None,
        "CRAWLBASE_JS_TOKEN": None,
        "SERPAPI_API_KEY": None,
        "MONGODB_URI": None,
        "MONGODB_DATABASE": "sentiment_analyzer",
        "CAMOUFOX_ENDPOINT": None,
        # optional path to the local Camoufox CLI executable; if set we will
        # prefer running ``<path>`` instead of ``python -m camoufox`` when launching
        # servers or fetching the browser.  This is useful when a virtualenv or
        # container has several pythons in play.
        "CAMOUFOX_CLI_PATH": None,
        # Optional MCP config file path (Claude-style mcpServers JSON)
        "MCP_CONFIG_PATH": None,
        "OLLAMA_BASE_URL": "http://localhost:11434",
        # Agent runtime resilience defaults
        "AGENT_TIMEOUT_SECONDS": "300",
        "AGENT_MAX_RETRIES": "1",
        "AGENT_CIRCUIT_BREAKER_THRESHOLD": "3",
        "AGENT_CIRCUIT_BREAKER_COOLDOWN_SECONDS": "600",
        # Harvester controls
        "HARVESTER_MAX_LINKS": "1000",
        "HARVESTER_MAX_CONCURRENCY": "8",
        "HARVESTER_SOURCE_TIMEOUT_SECONDS": "120",
        "HARVESTER_WRITER_BATCH_SIZE": "50",
        "HARVESTER_QUEUE_SIZE": "5000",
        "HARVESTER_PER_QUERY_LIMIT": "25",
        "HARVESTER_MIN_QUALITY_SCORE": "0.35",
        "HARVESTER_EXPANSION_SEED_LIMIT": "12",
        "HARVESTER_EXPANSION_PER_SEED_LIMIT": "25",
        "HARVESTER_ENABLE_SERPER": "true",
        "HARVESTER_ENABLE_FIRECRAWL": "true",
        "HARVESTER_ENABLE_BROWSER_DISCOVERY": "true",
        "HARVESTER_ENABLE_CRAWLBASE": "true",
        "HARVESTER_ENABLE_SERPAPI": "false",
        "HARVESTER_ENABLE_CAMOUFOX": "false",
        # Scraper controls
        "SCRAPER_MAX_CONCURRENCY": "6",
        "SCRAPER_SOURCE_TIMEOUT_SECONDS": "90",
        "SCRAPER_MAX_TARGETS_PER_RUN": "250",
        "SCRAPER_MAX_RETRIES_PER_TARGET": "3",
        "SCRAPER_ALLOW_EXISTING_REUSE": "true",
        "SCRAPER_REUSE_EXISTING_DAYS": "7",
        "SCRAPER_ENABLED_BACKENDS": "generic_http,firecrawl,crawlbase,camoufox",
        "SCRAPER_ENABLE_GENERIC_HTTP": "true",
        "SCRAPER_ENABLE_FIRECRAWL": "true",
        "SCRAPER_ENABLE_CRAWLBASE": "true",
        "SCRAPER_ENABLE_CAMOUFOX": "true",
        # Cleaner controls
        "CLEANER_MAX_CONCURRENCY": "8",
        "CLEANER_MAX_DOCUMENTS_PER_RUN": "500",
        "CLEANER_SAMPLE_REVIEW_RATE": "0.05",
        "CLEANER_MAX_SAMPLE_REVIEWS": "20",
        "CLEANER_MIN_CLEAN_CHARS": "30",
        "CLEANER_MAX_CLEAN_CHARS": "12000",
        "CLEANER_REMOVE_PUNCTUATION": "true",
        "CLEANER_LOWERCASE_TEXT": "true",
        "CLEANER_REPLACE_URLS_WITH_TOKEN": "true",
        "CLEANER_REPLACE_MENTIONS_WITH_TOKEN": "true",
        "CLEANER_PRESERVE_CASE_FOR_SHOUTING": "false",
        "CLEANER_EXTRACTION_BACKENDS": "content_fields,trafilatura,readability,bs4",
        "CLEANER_MIN_ALPHA_RATIO": "0.35",
        "CLEANER_MAX_URL_RATIO": "0.3",
        "CLEANER_MAX_SYMBOL_RATIO": "0.35",
        "CLEANER_REJECT_NON_PREFERRED_LANGUAGES": "false",
        "CLEANER_PREFERRED_LANGUAGES": "en",
        "CLEANER_ENABLE_FUZZY_DEDUPE": "true",
        "CLEANER_FUZZY_DEDUPE_THRESHOLD": "93",
        "CLEANER_FUZZY_CANDIDATE_LIMIT": "250",
        "CLEANER_LLM_PLAN_ENABLED": "true",
        "CLEANER_LLM_PLAN_SAMPLE_SIZE": "24",
        "CLEANER_LLM_PLAN_MAX_CHARS_PER_SAMPLE": "1600",
        "CLEANER_LLM_FALLBACK_MAX_CHARS": "2200",
        "CLEANER_LLM_FORCE_FULL_REWRITE": "false",
        "CLEANER_LLM_FALLBACK_ENABLED": "true",
        # Logging overrides (also consumed directly by Logging module,
        # listed here so they show up in the audit log)
        "LOG_LEVEL": "INFO",
        "LOG_DIR": "logs",
        "LOG_FILE_ENABLED": "true",
    }

    # Keys whose values are secrets and must be masked in logs
    _SECRETS: frozenset[str] = frozenset(
        {
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "SERPER_API_KEY",
            "FIRECRAWL_API_KEY",
            "CRAWLBASE_TOKEN",
            "CRAWLBASE_JS_TOKEN",
            "SERPAPI_API_KEY",
            "MONGODB_URI",
            "CAMOUFOX_ENDPOINT",
            "CAMOUFOX_CLI_PATH",
        }
    )

    def __init__(self) -> None:
        self._cache: dict[str, str | None] = {}
        self._loaded = False

        # Try loading .env file if python-dotenv is available
        try:
            from dotenv import load_dotenv

            load_dotenv()
            logger.info(
                ".env file loaded via python-dotenv",
                action="dotenv_load",
                phase="ENV",
                actor="env",
            )
        except ImportError:
            logger.debug(
                "python-dotenv not installed – reading from os.environ only",
                action="dotenv_skip",
                phase="ENV",
                actor="env",
            )

        self._audit_all()

    def _audit_all(self) -> None:
        """Read and log every declared key once at startup."""
        for key, default in self._KEYS.items():
            self._read(key, default)
        self._loaded = True

    def _read(self, key: str, default: str | None = None) -> str | None:
        """Read *key* from ``os.environ``, cache, and log the result."""
        if key in self._cache:
            return self._cache[key]

        value = os.environ.get(key, default)
        self._cache[key] = value

        is_secret = key in self._SECRETS
        display = _mask_secret(value) if (value and is_secret) else (value or "<unset>")

        if value is None:
            logger.warning(
                "env var %s is NOT SET (no default)",
                key,
                action="env_read",
                phase="ENV",
                actor="env",
                meta={"key": key, "status": "missing"},
            )
        else:
            logger.info(
                "env var %s = %s",
                key,
                display,
                action="env_read",
                phase="ENV",
                actor="env",
                meta={"key": key, "status": "loaded", "is_secret": is_secret},
            )

        return value

    def __getattr__(self, name: str) -> str | None:
        # Only intercept declared keys
        if name.startswith("_") or name not in self._KEYS:
            raise AttributeError(f"EnvConfig has no attribute {name!r}")
        return self._read(name, self._KEYS[name])

    def get(self, key: str, default: str | None = None) -> str | None:
        """Explicit getter – works for any env var, not just declared ones."""
        if key in self._cache:
            return self._cache[key]

        value = os.environ.get(key, default)
        self._cache[key] = value

        is_secret = key.upper().endswith(
            ("_KEY", "_SECRET", "_TOKEN", "_PASSWORD", "API_KEY")
        )
        display = _mask_secret(value) if (value and is_secret) else (value or "<unset>")

        logger.debug(
            "env.get(%s) = %s",
            key,
            display,
            action="env_get",
            phase="ENV",
            actor="env",
            meta={"key": key},
        )
        return value

    def require(self, key: str) -> str:
        """Like ``get`` but raises ``EnvironmentError`` if the key is missing."""
        value = self.get(key)
        if not value:
            logger.critical(
                "REQUIRED env var %s is missing – cannot continue",
                key,
                action="env_require",
                phase="ENV",
                actor="env",
                meta={"key": key},
            )
            raise EnvironmentError(f"Required environment variable {key!r} is not set")
        return value

    def reload(self) -> None:
        """Clear cache and re-read everything.  Useful after dotenv changes."""
        logger.info(
            "Reloading all environment variables",
            action="env_reload",
            phase="ENV",
            actor="env",
        )
        self._cache.clear()
        self._audit_all()

    def as_dict(self, *, unmask: bool = False) -> dict[str, str | None]:
        """Return all declared keys as a dict (masked by default)."""
        result: dict[str, str | None] = {}
        for key in self._KEYS:
            val = self._cache.get(key)
            if val and key in self._SECRETS and not unmask:
                result[key] = _mask_secret(val)
            else:
                result[key] = val
        return result


# ── Singleton ────────────────────────────────────────────────────────
config = EnvConfig()

# ── Backward-compat bare names (used by old code: ``from env import SERPER_API_KEY``) ──
SERPER_API_KEY: str | None = config.get("SERPER_API_KEY")
GEMINI_API_KEY: str | None = config.get("GOOGLE_API_KEY")
OPENAI_API_KEY: str | None = config.get("OPENAI_API_KEY")
