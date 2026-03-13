"""Harvester agent package.

::

    from agents.harvester import HarvesterAgent, HarvestPlan

    harvester = HarvesterAgent(llm_provider="google")
    result = harvester.invoke("Nepal elections 2026")
"""

from typing import TYPE_CHECKING

from .models import HarvestPlan, HarvestTaskPlan

if TYPE_CHECKING:
    from .agent import HarvesterAgent

__all__ = ["HarvestPlan", "HarvestTaskPlan", "HarvesterAgent"]


def __getattr__(name: str):
    if name == "HarvesterAgent":
        from .agent import HarvesterAgent

        return HarvesterAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
