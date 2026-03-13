"""Stateful browser tools for Camoufox-backed browsing.

These tools expose real browser control so an agent can open a stealth browser,
navigate around the web, interact with pages, and extract data over multiple
tool calls.
"""

from __future__ import annotations

import json
from typing import Any

from ._registry import agent_tool


@agent_tool(category="browser")
def camoufox_open_browser(
    start_url: str = "",
    headless: str = "virtual",
    main_world_eval: bool = False,
) -> str:
    """Open a Camoufox browser session and optionally navigate to a URL."""
    try:
        from utils.camoufox import camoufox_start_browser

        payload = camoufox_start_browser(
            start_url=start_url or None,
            headless=headless,
            main_world_eval=main_world_eval,
        )
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


@agent_tool(category="browser")
def camoufox_navigate_browser(session_id: str, url: str) -> str:
    """Navigate an open Camoufox session to another URL."""
    try:
        from utils.camoufox import camoufox_navigate

        payload = camoufox_navigate(session_id, url)
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc), "session_id": session_id, "url": url},
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_click_browser(session_id: str, selector: str) -> str:
    """Click an element in an open Camoufox session using a CSS selector."""
    try:
        from utils.camoufox import camoufox_click

        payload = camoufox_click(session_id, selector)
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {
                "success": False,
                "error": str(exc),
                "session_id": session_id,
                "selector": selector,
            },
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_type_browser(
    session_id: str,
    selector: str,
    text: str,
    press_enter: bool = False,
) -> str:
    """Fill an input field and optionally submit with Enter."""
    try:
        from utils.camoufox import camoufox_type

        payload = camoufox_type(session_id, selector, text, press_enter=press_enter)
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {
                "success": False,
                "error": str(exc),
                "session_id": session_id,
                "selector": selector,
            },
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_extract_text_browser(
    session_id: str,
    selector: str = "body",
    max_chars: int = 4000,
) -> str:
    """Extract visible text from a selector in an open Camoufox session."""
    try:
        from utils.camoufox import camoufox_extract_text

        payload = camoufox_extract_text(
            session_id, selector=selector, max_chars=max_chars
        )
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc), "session_id": session_id},
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_extract_links_browser(
    session_id: str,
    max_links: int = 40,
    selector: str = "a",
) -> str:
    """Extract anchors from the current page in an open Camoufox session."""
    try:
        from utils.camoufox import camoufox_extract_links

        payload = camoufox_extract_links(
            session_id, max_links=max_links, selector=selector
        )
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc), "session_id": session_id},
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_evaluate_browser(
    session_id: str,
    script: str,
    main_world: bool = False,
) -> str:
    """Evaluate JavaScript in the current Camoufox page."""
    try:
        from utils.camoufox import camoufox_evaluate

        payload = camoufox_evaluate(session_id, script, main_world=main_world)
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc), "session_id": session_id},
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_list_browser_sessions() -> str:
    """List all currently open Camoufox browser sessions."""
    try:
        from utils.camoufox import camoufox_list_sessions

        payload = camoufox_list_sessions()
        return json.dumps({"success": True, "sessions": payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


@agent_tool(category="browser")
def camoufox_close_browser_session(session_id: str) -> str:
    """Close a Camoufox browser session when it is no longer needed."""
    try:
        from utils.camoufox import camoufox_close_browser

        payload = camoufox_close_browser(session_id)
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc), "session_id": session_id},
            ensure_ascii=False,
        )


@agent_tool(category="browser")
def camoufox_close_all_browser_sessions() -> str:
    """Close all Camoufox browser sessions opened by the current process."""
    try:
        from utils.camoufox import camoufox_close_all_browsers

        payload = camoufox_close_all_browsers()
        return json.dumps({"success": True, **payload}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


__all__ = [
    "camoufox_click_browser",
    "camoufox_close_all_browser_sessions",
    "camoufox_close_browser_session",
    "camoufox_evaluate_browser",
    "camoufox_extract_links_browser",
    "camoufox_extract_text_browser",
    "camoufox_list_browser_sessions",
    "camoufox_navigate_browser",
    "camoufox_open_browser",
    "camoufox_type_browser",
]
