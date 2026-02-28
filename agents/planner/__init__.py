"""Planner agent — generates research plans for sentiment analysis.

::

    from agents.planner import PlannerAgent, ResearchPlan

    planner = PlannerAgent(llm_provider="google")
    result = planner.invoke("Nepal elections 2026")
"""

from .agent import PlannerAgent, ResearchPlan

__all__ = ["PlannerAgent", "ResearchPlan"]
