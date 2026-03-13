"""Runtime configuration and backend registry for phase-3 scraping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from env import config
from utils.camoufox import camoufox_is_available

if TYPE_CHECKING:
    from agents.scraper.models import ScrapeRuntimeConfig


@dataclass(frozen=True, slots=True)
class ScrapeBackendSpec:
    """Static description of a scraping backend."""

    name: str
    description: str
    env_key: str | None = None
    default_enabled: bool = True
    required_config_keys: tuple[str, ...] = ()
    requires_runtime_probe: bool = False


SCRAPE_BACKEND_REGISTRY: dict[str, ScrapeBackendSpec] = {
    "generic_http": ScrapeBackendSpec(
        name="generic_http",
        description="Direct HTTP fetch for normal web pages.",
    ),
    "firecrawl": ScrapeBackendSpec(
        name="firecrawl",
        description="Firecrawl hosted scraping for JS-heavy or structured pages.",
        env_key="SCRAPER_ENABLE_FIRECRAWL",
        required_config_keys=("FIRECRAWL_API_KEY",),
    ),
    "crawlbase": ScrapeBackendSpec(
        name="crawlbase",
        description="Crawlbase rendered fetch fallback.",
        env_key="SCRAPER_ENABLE_CRAWLBASE",
        required_config_keys=("CRAWLBASE_JS_TOKEN", "CRAWLBASE_TOKEN"),
    ),
    "camoufox": ScrapeBackendSpec(
        name="camoufox",
        description="Stealth browser runtime for blocked or dynamic sites.",
        env_key="SCRAPER_ENABLE_CAMOUFOX",
        requires_runtime_probe=True,
    ),
}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int) -> int:
    raw = config.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def registered_scrape_backends() -> dict[str, ScrapeBackendSpec]:
    """Return the central registry of generic scraper backends."""
    return dict(SCRAPE_BACKEND_REGISTRY)


def resolve_enabled_scrape_backends() -> tuple[str, ...]:
    """Resolve enabled backends from env using one registry-driven path.

    Preferred override: ``SCRAPER_ENABLED_BACKENDS=generic_http,firecrawl``.
    Legacy per-backend flags remain supported for backward compatibility.
    """
    raw = config.get("SCRAPER_ENABLED_BACKENDS")
    if raw is not None:
        requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
        if requested:
            return tuple(name for name in requested if name in SCRAPE_BACKEND_REGISTRY)

    enabled: list[str] = []
    for name, spec in SCRAPE_BACKEND_REGISTRY.items():
        if _as_bool(
            config.get(spec.env_key or f"SCRAPER_ENABLE_{name.upper()}"),
            spec.default_enabled,
        ):
            enabled.append(name)
    return tuple(enabled)


def backend_capability_snapshot(
    enabled_backends: tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return per-backend readiness details for logging and run metadata."""
    enabled = set(enabled_backends or resolve_enabled_scrape_backends())
    snapshot: dict[str, dict[str, Any]] = {}
    for name, spec in SCRAPE_BACKEND_REGISTRY.items():
        configured = True
        missing_keys: list[str] = []
        if spec.required_config_keys:
            configured = any(bool(config.get(key)) for key in spec.required_config_keys)
            if not configured:
                missing_keys = list(spec.required_config_keys)

        probe_ok = True
        if spec.requires_runtime_probe:
            probe_ok = camoufox_is_available()

        available = name in enabled and configured and probe_ok
        reason_parts: list[str] = []
        if name not in enabled:
            reason_parts.append("disabled")
        if not configured:
            reason_parts.append(f"missing_config:{'/'.join(missing_keys)}")
        if spec.requires_runtime_probe and not probe_ok:
            reason_parts.append("runtime_unavailable")

        snapshot[name] = {
            "enabled": name in enabled,
            "configured": configured,
            "available": available,
            "description": spec.description,
            "reason": ",".join(reason_parts) if reason_parts else "ready",
        }
    return snapshot


def available_registered_backends(runtime: ScrapeRuntimeConfig) -> list[str]:
    """Return enabled backends that are currently usable."""
    if not runtime.backend_status:
        snapshot = backend_capability_snapshot(runtime.enabled_backends)
    else:
        snapshot = runtime.backend_status
    return [name for name, details in snapshot.items() if details.get("available")]


def build_scrape_runtime_config() -> ScrapeRuntimeConfig:
    """Build the runtime config for the scraper from env/config."""
    from agents.scraper.models import ScrapeRuntimeConfig

    enabled_backends = resolve_enabled_scrape_backends()
    return ScrapeRuntimeConfig(
        max_concurrency=max(1, _as_int("SCRAPER_MAX_CONCURRENCY", 6)),
        source_timeout_seconds=max(15, _as_int("SCRAPER_SOURCE_TIMEOUT_SECONDS", 90)),
        max_targets_per_run=max(1, _as_int("SCRAPER_MAX_TARGETS_PER_RUN", 250)),
        max_retries_per_target=max(1, _as_int("SCRAPER_MAX_RETRIES_PER_TARGET", 3)),
        allow_existing_reuse=_as_bool(config.get("SCRAPER_ALLOW_EXISTING_REUSE"), True),
        reuse_existing_days=max(1, _as_int("SCRAPER_REUSE_EXISTING_DAYS", 7)),
        enabled_backends=enabled_backends,
        backend_status=backend_capability_snapshot(enabled_backends),
    )


__all__ = [
    "SCRAPE_BACKEND_REGISTRY",
    "ScrapeBackendSpec",
    "available_registered_backends",
    "backend_capability_snapshot",
    "build_scrape_runtime_config",
    "registered_scrape_backends",
    "resolve_enabled_scrape_backends",
]
