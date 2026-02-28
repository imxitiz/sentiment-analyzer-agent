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
        "--topic", "-t",
        type=str,
        help="Topic to analyse (example: 'Nepal elections 2026')",
    )
    p.add_argument(
        "--provider", "-p",
        type=str,
        default="gemini",
        help="LLM provider (default: gemini). Options: gemini, openai, ollama.",
    )
    p.add_argument(
        "--model", "-m",
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

    from agents.orchestrator import OrchestratorAgent
    from agents.planner import PlannerAgent

    if args.demo:
        logger.info("Demo mode — using static data (no LLM)")
    logger.info("Initialising agents…")

    # Create sub-agents (cheap model for planning)
    planner = PlannerAgent(llm_provider=provider)

    # Create orchestrator (powerful model for coordination)
    orchestrator = OrchestratorAgent(
        sub_agents=[planner],
        llm_provider=provider,
        model=model,
    )

    logger.info("Starting analysis for topic: %s", topic)

    if orchestrator.is_demo:
        # Demo mode: single invoke, print formatted output
        result = orchestrator.invoke(topic)
        print(result["output"])
    else:
        # Production: stream execution steps
        for step in orchestrator.stream(topic):
            for key, value in step.items():
                if not isinstance(value, dict):
                    continue
                for msg in value.get("messages", []):
                    if hasattr(msg, "pretty_print"):
                        msg.pretty_print()

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
