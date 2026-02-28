"""Orchestrator agent — central coordinator of the analysis pipeline.

::

    from agents.orchestrator import OrchestratorAgent

    agent = OrchestratorAgent(llm_provider="google")
    result = agent.invoke("Nepal elections 2026")
"""

from .agent import OrchestratorAgent

__all__ = ["OrchestratorAgent"]
