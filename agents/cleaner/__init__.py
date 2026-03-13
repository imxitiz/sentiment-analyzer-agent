"""Phase-4 cleaner agent package."""

from typing import TYPE_CHECKING

from .models import (
    CleanerPlan,
    CleanerRecoveryPlan,
    CleanerResult,
    CleaningRuntimeConfig,
)

if TYPE_CHECKING:
    from .agent import CleanerAgent

__all__ = [
    "CleanerAgent",
    "CleanerPlan",
    "CleanerRecoveryPlan",
    "CleanerResult",
    "CleaningRuntimeConfig",
]


def __getattr__(name: str):
    if name == "CleanerAgent":
        from .agent import CleanerAgent

        return CleanerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
