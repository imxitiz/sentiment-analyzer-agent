"""Camoufox browser helpers.

Camoufox should be treated as a real browser runtime, not just a single-page
fetch helper. This module therefore supports two distinct use cases:

1. Short-lived helpers such as ``camoufox_fetch_anchors`` for harvesting.
2. Stateful browser sessions that agents can open, navigate, interact with,
   inspect, and close across multiple tool calls.

Supported backends:

* Local Python package via ``camoufox.sync_api.Camoufox``.
* Remote websocket endpoint exposed by ``python -m camoufox server``.
* Legacy HTTP JSON adapter for one-shot link extraction only.

The remote-server mode matters because Camoufox exposes Playwright-compatible
browser control over websocket. That means our agents can use it as a stealthy
browser when normal requests or scraping paths get blocked, or when a task
requires human-like browser navigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any
import json
import shlex
import shutil
import subprocess
import uuid

import requests

from env import config


@dataclass(slots=True)
class CamoufoxBrowserSession:
    """In-memory handle for a live Camoufox browser session."""

    session_id: str
    mode: str
    browser: Any
    page: Any
    cleanup: Any
    created_at: float
    last_used_at: float
    main_world_eval: bool


_SESSIONS: dict[str, CamoufoxBrowserSession] = {}
_SESSIONS_LOCK = RLock()


def _camoufox_endpoint(endpoint: str | None = None) -> str | None:
    return endpoint or config.get("CAMOUFOX_ENDPOINT")


def _camoufox_cli_command() -> list[str]:
    explicit = config.get("CAMOUFOX_CLI_PATH")
    if explicit:
        return shlex.split(explicit)

    python = shutil.which("python3") or shutil.which("python")
    if not python:
        return []
    return [python, "-m", "camoufox"]


def _load_local_camoufox() -> Any | None:
    try:
        try:
            from camoufox.sync_api import Camoufox
        except ImportError:
            from camoufox import Camoufox  # type: ignore
        return Camoufox
    except ImportError:
        return None


def _load_playwright_sync() -> Any | None:
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except ImportError:
        return None


def camoufox_is_available() -> bool:
    """Return whether any Camoufox backend is usable in this environment."""
    endpoint = _camoufox_endpoint()
    if endpoint:
        return True
    if _load_local_camoufox() is not None:
        return True
    return bool(_camoufox_cli_command())


def camoufox_start_browser(
    *,
    start_url: str | None = None,
    headless: bool | str = "virtual",
    main_world_eval: bool = False,
    endpoint: str | None = None,
    timeout_seconds: float = 60.0,
    **camoufox_kwargs: Any,
) -> dict[str, Any]:
    """Start a stateful Camoufox browser session.

    Preference order:
    1. Local Python Camoufox package.
    2. Remote websocket server from ``CAMOUFOX_ENDPOINT`` if it is a ws URL.

    The returned ``session_id`` can be reused across multiple tool calls for
    navigation and interaction.
    """
    local_camoufox = _load_local_camoufox()
    resolved_endpoint = _camoufox_endpoint(endpoint)

    if local_camoufox is not None:
        manager = local_camoufox(
            headless=headless,
            main_world_eval=main_world_eval,
            **camoufox_kwargs,
        )
        browser = manager.__enter__()
        page = browser.new_page()
        if start_url:
            page.goto(start_url, timeout=int(timeout_seconds * 1000))

        session_id = str(uuid.uuid4())[:12]
        session = CamoufoxBrowserSession(
            session_id=session_id,
            mode="local_python",
            browser=browser,
            page=page,
            cleanup=lambda: manager.__exit__(None, None, None),
            created_at=time(),
            last_used_at=time(),
            main_world_eval=main_world_eval,
        )
        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = session
        return _session_snapshot(session)

    if resolved_endpoint and resolved_endpoint.startswith(("ws://", "wss://")):
        sync_playwright = _load_playwright_sync()
        if sync_playwright is None:
            raise RuntimeError(
                "CAMOUFOX_ENDPOINT is a websocket endpoint, but Playwright is not installed."
            )

        playwright = sync_playwright().start()
        browser = playwright.firefox.connect(resolved_endpoint)
        page = browser.new_page()
        if start_url:
            page.goto(start_url, timeout=int(timeout_seconds * 1000))

        session_id = str(uuid.uuid4())[:12]
        session = CamoufoxBrowserSession(
            session_id=session_id,
            mode="remote_websocket",
            browser=browser,
            page=page,
            cleanup=lambda: (browser.close(), playwright.stop()),
            created_at=time(),
            last_used_at=time(),
            main_world_eval=main_world_eval,
        )
        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = session
        return _session_snapshot(session)

    raise RuntimeError(
        "Camoufox browser sessions require either the local Python package or a websocket CAMOUFOX_ENDPOINT."
    )


def camoufox_list_sessions() -> list[dict[str, Any]]:
    """Return lightweight metadata for currently open browser sessions."""
    with _SESSIONS_LOCK:
        return [_session_snapshot(session) for session in _SESSIONS.values()]


def camoufox_close_browser(session_id: str) -> dict[str, Any]:
    """Close a previously opened Camoufox browser session."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.pop(session_id, None)
    if session is None:
        raise KeyError(f"Unknown Camoufox session: {session_id}")

    session.cleanup()
    return {"session_id": session_id, "closed": True}


def camoufox_close_all_browsers() -> dict[str, Any]:
    """Close every live Camoufox session tracked in this process."""
    with _SESSIONS_LOCK:
        session_ids = list(_SESSIONS.keys())
    closed = 0
    for session_id in session_ids:
        try:
            camoufox_close_browser(session_id)
            closed += 1
        except Exception:
            continue
    return {"closed": closed}


def camoufox_navigate(
    session_id: str,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Navigate an existing Camoufox session to a new URL."""
    session = _require_session(session_id)
    session.page.goto(url, wait_until=wait_until, timeout=int(timeout_seconds * 1000))
    return _session_snapshot(session)


def camoufox_click(
    session_id: str, selector: str, *, timeout_seconds: float = 30.0
) -> dict[str, Any]:
    """Click an element in an existing Camoufox browser session."""
    session = _require_session(session_id)
    session.page.click(selector, timeout=int(timeout_seconds * 1000))
    return _session_snapshot(session)


def camoufox_type(
    session_id: str,
    selector: str,
    text: str,
    *,
    press_enter: bool = False,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Fill an input and optionally press Enter."""
    session = _require_session(session_id)
    session.page.fill(selector, text, timeout=int(timeout_seconds * 1000))
    if press_enter:
        session.page.press(selector, "Enter", timeout=int(timeout_seconds * 1000))
    return _session_snapshot(session)


def camoufox_evaluate(
    session_id: str,
    script: str,
    *,
    main_world: bool = False,
) -> dict[str, Any]:
    """Evaluate JavaScript in the current page.

    Camoufox runs isolated-world evaluation by default. To opt into main-world
    execution, pass ``main_world=True``. That prefixes the script with ``mw:``
    when needed.
    """
    session = _require_session(session_id)
    payload = script
    if main_world and not payload.startswith("mw:"):
        payload = f"mw:{payload}"
    result = session.page.evaluate(payload)
    return {"session_id": session_id, "result": result}


def camoufox_extract_links(
    session_id: str,
    *,
    max_links: int = 40,
    selector: str = "a",
) -> dict[str, Any]:
    """Extract links from the current page in an open session."""
    session = _require_session(session_id)
    links = session.page.eval_on_selector_all(
        selector,
        (
            "els => els.slice(0, %d).map((el, index) => ({"
            "href: el.href || '', title: el.title || '', "
            "text: (el.innerText || '').trim(), position: index + 1}))"
        )
        % max(1, min(int(max_links), 200)),
    )
    return {
        "session_id": session_id,
        "url": session.page.url,
        "title": session.page.title(),
        "anchors": links,
    }


def camoufox_extract_text(
    session_id: str,
    *,
    selector: str = "body",
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Extract text content from the current page."""
    session = _require_session(session_id)
    text = session.page.locator(selector).inner_text()
    return {
        "session_id": session_id,
        "url": session.page.url,
        "title": session.page.title(),
        "text": text[: max(200, max_chars)],
    }


def camoufox_fetch_anchors(
    url: str,
    *,
    max_links: int = 40,
    endpoint: str | None = None,
    timeout_seconds: float = 60.0,
    headless: bool | str = "virtual",
    main_world_eval: bool = False,
    **camoufox_kwargs: Any,
) -> dict[str, Any]:
    """Visit a page and return its anchors.

    This is the one-shot harvesting helper. It will:
    1. Use websocket Camoufox if ``CAMOUFOX_ENDPOINT`` is a ws URL.
    2. Use local Python Camoufox if installed.
    3. Use a legacy HTTP JSON adapter if ``CAMOUFOX_ENDPOINT`` is HTTP(S).
    """
    resolved_endpoint = _camoufox_endpoint(endpoint)
    if resolved_endpoint and resolved_endpoint.startswith(("http://", "https://")):
        response = requests.post(
            resolved_endpoint,
            json={"url": url, "maxLinks": max_links},
            timeout=max(5.0, timeout_seconds),
        )
        response.raise_for_status()
        return response.json()

    session = camoufox_start_browser(
        start_url=url,
        headless=headless,
        main_world_eval=main_world_eval,
        endpoint=resolved_endpoint,
        timeout_seconds=timeout_seconds,
        **camoufox_kwargs,
    )
    session_id = str(session["session_id"])
    try:
        return camoufox_extract_links(session_id, max_links=max_links)
    finally:
        camoufox_close_browser(session_id)


def camoufox_cli_path() -> str:
    """Return the Camoufox executable path reported by the CLI."""
    command = _camoufox_cli_command()
    if not command:
        raise RuntimeError("Camoufox CLI is not available")
    try:
        output = subprocess.check_output([*command, "path"], text=True)
        return output.strip()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Camoufox CLI path lookup failed") from exc


def camoufox_launch_server(**kwargs: Any) -> subprocess.Popen[Any]:
    """Launch a Camoufox remote websocket server using the CLI."""
    command = _camoufox_cli_command()
    if not command:
        raise RuntimeError("Camoufox CLI is not available")

    args = [*command, "server"]
    for key, value in kwargs.items():
        args.append(f"--{key.replace('_', '-')}")
        if not isinstance(value, bool):
            args.append(str(value))
    return subprocess.Popen(args)


def _require_session(session_id: str) -> CamoufoxBrowserSession:
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise KeyError(f"Unknown Camoufox session: {session_id}")
    session.last_used_at = time()
    return session


def _session_snapshot(session: CamoufoxBrowserSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "mode": session.mode,
        "url": getattr(session.page, "url", ""),
        "title": session.page.title() if session.page else "",
        "created_at": session.created_at,
        "last_used_at": session.last_used_at,
        "main_world_eval": session.main_world_eval,
    }


__all__ = [
    "CamoufoxBrowserSession",
    "camoufox_click",
    "camoufox_cli_path",
    "camoufox_close_all_browsers",
    "camoufox_close_browser",
    "camoufox_evaluate",
    "camoufox_extract_links",
    "camoufox_extract_text",
    "camoufox_fetch_anchors",
    "camoufox_is_available",
    "camoufox_launch_server",
    "camoufox_list_sessions",
    "camoufox_navigate",
    "camoufox_start_browser",
    "camoufox_type",
]
