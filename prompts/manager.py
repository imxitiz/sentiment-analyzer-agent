"""Prompt manager: load and format prompt templates.

Supports two levels of prompt storage:
    1. **Global** prompts in ``prompts/raw_prompts/`` (shared across agents)
    2. **Registered** directories (e.g. agent-local ``prompts/`` folders)

Usage::

    from prompts.manager import get_prompt, list_prompts, register_prompt_dir

    # Global prompt (existing):
    tpl = get_prompt('plan', topic='electric vehicles')

    # Register an extra directory:
    register_prompt_dir('/path/to/agents/planner/prompts')

    # Search all dirs (registered first, then global):
    tpl = find_prompt('system')

The ``get_prompt`` / ``load_prompt`` functions remain backward-compatible
and always search the global ``raw_prompts/`` directory.
"""

from __future__ import annotations

import functools
import os
from typing import List

PROMPTS_DIR = os.path.dirname(__file__)
RAW_PROMPTS_DIR = os.path.join(PROMPTS_DIR, "raw_prompts")


def _filename(name: str) -> str:
    """Ensure the name ends with ``.txt``."""
    if name.endswith(".txt"):
        return name
    return f"{name}.txt"


# ── Global prompt loading (backward-compatible) ─────────────────────


@functools.lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """Load a prompt template by name from the global ``raw_prompts/`` dir.

    Raises ``FileNotFoundError`` if the prompt file doesn't exist.
    Results are cached.
    """
    path = os.path.join(RAW_PROMPTS_DIR, _filename(name))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_prompt(name: str, **kwargs) -> str:
    """Return a global prompt template, optionally formatted with kwargs.

    Falls back to a sentinel string if the file is missing.
    """
    try:
        tpl = load_prompt(name)
    except FileNotFoundError:
        return f"[missing-prompt:{name}]"

    if not kwargs:
        return tpl

    try:
        return tpl.format(**kwargs)
    except Exception:
        return tpl


def list_prompts() -> List[str]:
    """Return available global prompt names (without .txt extension)."""
    names: List[str] = []
    for fn in os.listdir(RAW_PROMPTS_DIR):
        if not fn.endswith(".txt"):
            continue
        names.append(fn[: -len(".txt")])
    return sorted(names)


# ── Registered directories (multi-source prompt discovery) ───────────

_REGISTERED_DIRS: list[str] = []


def register_prompt_dir(path: str) -> None:
    """Register an additional directory to search for prompts.

    Registered directories are searched **before** the global
    ``raw_prompts/`` directory.

    Args:
        path: Absolute path to a directory containing ``.txt`` prompts.
    """
    abs_path = os.path.abspath(path)
    if abs_path not in _REGISTERED_DIRS:
        _REGISTERED_DIRS.append(abs_path)


def find_prompt(name: str, search_dirs: list[str] | None = None, **kwargs) -> str:
    """Search registered dirs → optional extra dirs → global for a prompt.

    Unlike ``get_prompt`` (which only searches global), this function
    searches all registered directories first.

    Args:
        name: Prompt name (without ``.txt``).
        search_dirs: Additional directories to check first.
        **kwargs: ``str.format()`` placeholders.

    Returns:
        Formatted prompt string, or ``[missing-prompt:<name>]`` sentinel.
    """
    fname = _filename(name)
    dirs = list(search_dirs or []) + _REGISTERED_DIRS + [RAW_PROMPTS_DIR]

    for d in dirs:
        fpath = os.path.join(d, fname)
        if os.path.isfile(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if kwargs:
                try:
                    return content.format(**kwargs)
                except Exception:
                    return content
            return content

    return f"[missing-prompt:{name}]"


def list_all_prompts() -> list[str]:
    """List prompt names from all registered directories + global.

    Returns:
        Sorted, deduplicated list of prompt names.
    """
    names: set[str] = set()
    all_dirs = _REGISTERED_DIRS + [RAW_PROMPTS_DIR]

    for d in all_dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".txt"):
                names.add(fn[:-4])

    return sorted(names)
