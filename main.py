"""CLI entry point for the sentiment analysis agent pipeline.

Usage::

    uv run python main.py --topic "Nepal elections 2026"
    uv run python main.py -t "electric vehicles" -p gemini
    uv run python main.py -t "Tesla stock" -p openai --model gpt-4o
    uv run python main.py -t "AI regulation" --demo  # no LLM needed
"""

from __future__ import annotations

import argparse

from Logging import get_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(
        description="Run the sentiment analysis orchestrator agent",
    )
    p.add_argument(
        "--topic",
        "-t",
        type=str,
        help="Topic to analyse (example: 'Nepal elections 2026')",
    )
    p.add_argument(
        "--provider",
        "-p",
        type=str,
        default="gemini",
        help="LLM provider (default: gemini). Options: gemini, openai, ollama.",
    )
    p.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="LLM model name (default: provider default).",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode — static data, no LLM API keys needed.",
    )
    return p.parse_args()


def main() -> None:
    """Run the orchestrator agent pipeline."""
    args = _parse_args()
    topic = args.topic or input("Enter topic: ")

    # Demo mode → force dummy provider
    provider = "dummy" if args.demo else args.provider
    model = None if args.demo else args.model

    # if we're not already in demo mode, verify that essential keys exist;
    # otherwise default to dummy provider so the pipeline stays runnable.
    if not args.demo:
        from env import config

        try:
            config.require("SERPER_API_KEY")
        except EnvironmentError:
            logger.warning(
                "SERPER_API_KEY missing, forcing demo mode",
                action="fallback_demo",
            )
            provider = "dummy"

    from agents.orchestrator import OrchestratorAgent
    from agents.cleaner import CleanerAgent
    from agents.harvester import HarvesterAgent
    from agents.planner import PlannerAgent
    from agents.scraper import ScraperAgent

    if args.demo:
        logger.info("Demo mode — using static data (no LLM)")
    logger.info("Initialising agents…")

    # Create sub-agents (cheap model for planning)
    planner = PlannerAgent(llm_provider=provider)
    harvester = HarvesterAgent(llm_provider=provider)
    scraper = ScraperAgent(llm_provider=provider)
    cleaner = CleanerAgent(llm_provider=provider)

    # Create orchestrator (powerful model for coordination)
    orchestrator = OrchestratorAgent(
        sub_agents=[planner, harvester, scraper, cleaner],
        llm_provider=provider,
        model=model,
    )

    logger.info("Starting analysis for topic: %s", topic)

    result = orchestrator.invoke(topic)
    print(result["output"])

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
