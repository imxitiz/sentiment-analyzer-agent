"""Standalone Camoufox browser smoke test.

Purpose:
- Validate Camoufox runtime (local Python package / websocket endpoint) without
  loading the full agents registry.
- Exercise open -> navigate -> extract links/text -> close lifecycle.

Usage:
  uv run python ForTesting/camoufox_agentic_smoke.py --url "https://duckduckgo.com/?q=nepal+eid+holiday"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Camoufox standalone smoke test")
    parser.add_argument(
        "--url",
        type=str,
        default="https://duckduckgo.com/?q=nepal+eid+holiday",
        help="Initial URL to visit",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=20,
        help="Max anchors to extract",
    )
    return parser.parse_args()


def main() -> int:
    from utils.camoufox import (
        camoufox_close_browser,
        camoufox_extract_links,
        camoufox_extract_text,
        camoufox_is_available,
        camoufox_navigate,
        camoufox_start_browser,
    )

    args = parse_args()

    if not camoufox_is_available():
        print("Camoufox is not available (no local package and no websocket endpoint).")
        return 2

    session_id = ""
    try:
        session = camoufox_start_browser(
            start_url=args.url,
            headless=True,
            main_world_eval=True,
            timeout_seconds=60.0,
        )
        session_id = str(session.get("session_id", ""))
        if not session_id:
            print("Failed to create Camoufox session: missing session_id")
            return 3

        nav = camoufox_navigate(session_id, args.url, timeout_seconds=60.0)
        links = camoufox_extract_links(session_id, max_links=max(1, args.max_links))
        text = camoufox_extract_text(session_id, max_chars=600)

        print("Camoufox smoke: OK")
        print(
            json.dumps(
                {
                    "session": nav,
                    "link_count": len(links.get("anchors", [])),
                    "sample_links": links.get("anchors", [])[:5],
                    "text_preview": text.get("text", "")[:240],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"Camoufox smoke: FAIL - {exc}")
        return 1
    finally:
        if session_id:
            try:
                camoufox_close_browser(session_id)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
