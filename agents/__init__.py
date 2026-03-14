"""Agents — the multi-agent pipeline for sentiment analysis.

Public API::

    from agents import (
        # Registry
        register_agent, build_agent, list_agents, get_agent_class,
        # Base class (for creating new agents)
        BaseAgent,
        # Concrete agents
        OrchestratorAgent,
        HarvesterAgent,
        PlannerAgent, ResearchPlan,
            ScraperAgent,
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
from .harvester import HarvesterAgent, HarvestPlan, HarvestTaskPlan
from .planner import PlannerAgent, ResearchPlan
from .scraper import ScraperAgent, ScrapeRuntimeConfig, ScrapeTarget, ScrapedContent
from .cleaner import CleanerAgent, CleanerPlan, CleaningRuntimeConfig, CleanerResult
from .sentiment import SentimentAnalyzerAgent

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
    "HarvesterAgent",
    "HarvestPlan",
    "HarvestTaskPlan",
    "PlannerAgent",
    "ResearchPlan",
    "ScraperAgent",
    "ScrapeRuntimeConfig",
    "ScrapeTarget",
    "ScrapedContent",
    "CleanerAgent",
    "CleanerPlan",
    "CleaningRuntimeConfig",
    "CleanerResult",
    "SentimentAnalyzerAgent",
]
