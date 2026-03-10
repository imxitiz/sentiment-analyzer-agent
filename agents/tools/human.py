"""Human-in-the-loop tool — ask the user for clarification.

Default: CLI ``input()``.  For UI integration, call
``set_human_input_handler(your_handler)`` to swap the backend.

Usage::

    from agents.tools.human import ask_human

    # Use as a tool in an agent:
    agent = OrchestratorAgent(extra_tools=[ask_human])

    # Swap backend for web UI:
    from agents.tools.human import set_human_input_handler
    set_human_input_handler(my_websocket_handler)
"""

from __future__ import annotations

from typing import Callable

from agents.tools import agent_tool

# ── Pluggable input handler ──────────────────────────────────────────

_human_input_handler: Callable[[str], str] | None = None


def set_human_input_handler(handler: Callable[[str], str]) -> None:
    """Replace the default CLI input with a custom handler.

    Args:
        handler: A callable that takes a question string and returns
            the user's response string.  Can be a WebSocket callback,
            a GUI dialog, etc.
    """
    global _human_input_handler
    _human_input_handler = handler


def clear_human_input_handler() -> None:
    """Restore the default CLI-backed input handler."""
    global _human_input_handler
    _human_input_handler = None


# ── The tool ─────────────────────────────────────────────────────────

@agent_tool(category="interaction")
def ask_human(question: str) -> str:
    """Ask the human user for clarification or additional information.

    Use this ONLY when the topic is genuinely ambiguous or you need
    critical information that cannot be inferred.  Do NOT ask
    unnecessarily — most topics are clear enough to proceed directly.

    In the web app this should surface a visible clarification prompt and
    temporarily pause the agent until the user responds.

    Args:
        question: The question to ask the user.

    Returns:
        The user's response as a string.
    """
    if _human_input_handler:
        return _human_input_handler(question)

    print(f"\n{'─' * 60}")
    print(f"🤖 Agent needs your input:\n\n{question}\n")
    response = input("Your response: ").strip()
    print(f"{'─' * 60}\n")
    return response


__all__ = [
    "ask_human",
    "clear_human_input_handler",
    "set_human_input_handler",
]
