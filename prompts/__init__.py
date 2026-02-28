"""Prompt management — load and format prompt templates.

Two levels of prompt storage:
    1. **Global** prompts in ``prompts/raw_prompts/`` (shared across agents)
    2. **Agent-local** prompts in ``agents/<name>/prompts/`` (per-agent)

Available global prompts: ``plan``, ``clean``, ``scrape``, ``summarize``.

Usage::

    from prompts import get_prompt, list_prompts

    text = get_prompt("plan", topic="Nepal elections 2026")
    names = list_prompts()  # → ["clean", "plan", "scrape", "summarize"]
"""

from .manager import (
    get_prompt,
    load_prompt,
    list_prompts,
    register_prompt_dir,
    find_prompt,
    list_all_prompts,
)

__all__ = [
    "get_prompt",
    "load_prompt",
    "list_prompts",
    "register_prompt_dir",
    "find_prompt",
    "list_all_prompts",
]
