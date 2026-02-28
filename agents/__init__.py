"""Agents — the multi-agent pipeline for sentiment analysis.

Public API::

    from agents import (
        # Registry
        register_agent, build_agent, list_agents, get_agent_class,
        # Base class (for creating new agents)
        BaseAgent,
        # Concrete agents
        OrchestratorAgent,
        PlannerAgent, ResearchPlan,
    )

    # Quick start:
    agent = build_agent("orchestrator", llm_provider="google")
    result = agent.invoke("Nepal elections 2026")
"""

from .base import BaseAgent
from ._registry import (
    register_agent,
    build_agent,
    get_agent_class,
    list_agents,
    is_registered,
)

# Import concrete agents to trigger @register_agent decorators
from .orchestrator import OrchestratorAgent
from .planner import PlannerAgent, ResearchPlan

__all__ = [
    # Base
    "BaseAgent",
    # Registry
    "register_agent",
    "build_agent",
    "get_agent_class",
    "list_agents",
    "is_registered",
    # Agents
    "OrchestratorAgent",
    "PlannerAgent",
    "ResearchPlan",
]
