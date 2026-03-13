"""Agent registry — register, discover, and instantiate agents.

Every agent class decorated with ``@register_agent`` is automatically
discoverable by name.  The rest of the codebase uses the registry to
create agents without tight coupling to concrete classes.

Usage::

    from agents._registry import register_agent, build_agent, list_agents

    # Registering (in agent module):
    @register_agent
    class MyAgent(BaseAgent):
        _name = "my_agent"
        ...

    # Discovering / creating (anywhere):
    list_agents()                      # → ["my_agent", "orchestrator", ...]
    agent = build_agent("my_agent")    # → MyAgent instance
    agent = build_agent("my_agent", llm_provider="openai", model="gpt-4o")
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from Logging import get_logger

if TYPE_CHECKING:
    from .base import BaseAgent

logger = get_logger("agents.registry")

# ── Registry storage ─────────────────────────────────────────────────

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


# ── Public API ───────────────────────────────────────────────────────


def register_agent(cls: type[BaseAgent]) -> type[BaseAgent]:
    """Class decorator — auto-register an agent class by its ``_name``.

    Raises:
        ValueError: If ``_name`` is not set on the class.
        KeyError: If an agent with the same name is already registered.
    """
    name = getattr(cls, "_name", "")
    if not name:
        raise ValueError(
            f"Agent class {cls.__name__} must set '_name' class attribute."
        )

    if name in _AGENT_REGISTRY:
        existing = _AGENT_REGISTRY[name].__name__
        raise KeyError(
            f"Agent name {name!r} already registered by {existing}. "
            f"Cannot register {cls.__name__}."
        )

    _AGENT_REGISTRY[name] = cls
    logger.info(
        "Registered agent  name=%s  class=%s",
        name,
        cls.__name__,
    )
    return cls


def get_agent_class(name: str) -> type[BaseAgent]:
    """Look up an agent class by name.

    Raises:
        KeyError: If the name is not registered.
    """
    if name not in _AGENT_REGISTRY:
        available = ", ".join(list_agents()) or "(none)"
        raise KeyError(f"Unknown agent: {name!r}. Registered: {available}")
    return _AGENT_REGISTRY[name]


def build_agent(name: str, **kwargs: Any) -> BaseAgent:
    """Create an agent instance by registry name.

    Args:
        name: Registered agent name (e.g. ``"orchestrator"``).
        **kwargs: Forwarded to the agent's ``__init__``.

    Returns:
        Ready-to-use agent instance.

    Example::

        agent = build_agent("orchestrator", llm_provider="google")
        result = agent.invoke("Nepal elections 2026")
    """
    cls = get_agent_class(name)
    logger.info("Building agent  name=%s  kwargs=%s", name, list(kwargs.keys()))
    return cls(**kwargs)


def list_agents() -> list[str]:
    """Return sorted list of all registered agent names."""
    return sorted(_AGENT_REGISTRY.keys())


def is_registered(name: str) -> bool:
    """Check if an agent name is registered."""
    return name in _AGENT_REGISTRY
