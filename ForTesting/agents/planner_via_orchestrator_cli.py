"""CLI smoke test for orchestrator -> planner flow.

This script intentionally limits orchestration to the planner phase so you can
validate real LLM behavior, structured planning output, and SQLite persistence
before moving to harvester/scraper phases.

Examples:
    uv run python ForTesting/agents/planner_via_orchestrator_cli.py --topic "Nepal elections 2026"
    uv run python ForTesting/agents/planner_via_orchestrator_cli.py --interactive
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _bootstrap_project_root() -> None:
    """Ensure project root imports work when executing this script directly."""
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run planner-only orchestration with Copilot and validate DB artifacts.",
    )
    parser.add_argument(
        "--topic",
        "-t",
        type=str,
        default=None,
        help="Topic to plan. If omitted with --interactive, topic is requested from stdin.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for topic in CLI when --topic is not provided.",
    )
    parser.add_argument(
        "--provider",
        "-p",
        type=str,
        default="copilot",
        help="LLM provider to use (default: copilot).",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="gpt-4o",
        help="Model name for the provider (default: gpt-4o).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Model temperature for planning (default: 0.2).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Max tokens for planning (default: 2048).",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Print orchestrator final output.",
    )
    parser.add_argument(
        "--cli-path",
        type=str,
        default=None,
        help="Optional path to Copilot CLI binary.",
    )
    parser.add_argument(
        "--cli-url",
        type=str,
        default=None,
        help="Optional URL to an existing Copilot CLI server.",
    )
    return parser.parse_args()


def _resolve_topic(args: argparse.Namespace) -> str:
    if args.topic:
        return args.topic.strip()
    if args.interactive:
        return input("Topic: ").strip()
    raise SystemExit("Provide --topic or use --interactive")


def _is_ambiguous_topic(topic: str) -> bool:
    text = topic.strip().lower()
    if not text:
        return True
    word_count = len(text.split())
    if word_count <= 2:
        return True
    vague_patterns = [
        r"^it$",
        r"^this$",
        r"^that$",
        r"^something",
        r"^anything",
        r"^about\s+it",
        r"^news$",
        r"^politics$",
    ]
    return any(re.search(pattern, text) for pattern in vague_patterns)


def _count_artifacts(topic: str, *, created_after: str | None = None) -> dict[str, int]:
    from agents.services.planner_checkpoint import db_path_for_topic

    path = db_path_for_topic(topic)
    if not path.exists():
        return {}

    counts: dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        if created_after:
            rows = conn.execute(
                """
                SELECT artifact_type, COUNT(*)
                FROM pipeline_artifacts
                WHERE created_at >= ?
                GROUP BY artifact_type
                ORDER BY artifact_type ASC
                """,
                (created_after,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT artifact_type, COUNT(*)
                FROM pipeline_artifacts
                GROUP BY artifact_type
                ORDER BY artifact_type ASC
                """
            ).fetchall()
    for artifact_type, count in rows:
        counts[str(artifact_type)] = int(count)
    return counts


def _latest_run_for_topic(topic: str) -> dict[str, Any] | None:
    from agents.services.orchestrator_checkpoint import init_orchestrator_db

    db_path = init_orchestrator_db()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT run_id, status, active_agent, topic_db_path, created_at, updated_at
            FROM topic_runs
            WHERE topic = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (topic,),
        ).fetchone()

    if row is None:
        return None

    return {
        "run_id": str(row[0]),
        "status": str(row[1]),
        "active_agent": str(row[2]) if row[2] is not None else None,
        "topic_db_path": str(row[3]),
        "created_at": str(row[4]),
        "updated_at": str(row[5]),
    }


def run() -> int:
    args = _parse_args()
    topic = _resolve_topic(args)

    _bootstrap_project_root()

    from Logging import get_logger
    from agents.orchestrator import OrchestratorAgent
    from agents.planner import PlannerAgent
    from agents.services import (
        bootstrap_topic,
        record_orchestrator_event,
        update_topic_run,
    )
    from agents.services.planner_checkpoint import db_path_for_topic
    from agents.tools.human import ask_human

    logger = get_logger("ForTesting.planner_via_orchestrator_cli")

    class PlannerOnlyOrchestrator(OrchestratorAgent):
        """Deterministic planner-only orchestrator for Copilot testing.

        This avoids LLM-level tool-calling requirements and still validates the
        real planner LLM + checkpoint persistence flow.
        """

        def _register_tools(self) -> list:
            return []

        def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
            topic = message.strip()
            run = bootstrap_topic(topic)
            run_id = run["run_id"]
            update_topic_run(
                run_id,
                status="running",
                active_agent=self._name,
                meta={"mode": "planner_only_deterministic"},
            )

            effective_topic = topic
            if _is_ambiguous_topic(topic):
                clarification = ask_human(
                    "Your topic seems broad/ambiguous. Please provide a more specific topic focus."
                ).strip()
                if clarification:
                    effective_topic = clarification

            planner = self._sub_agents[0]
            planner_result = planner.invoke(effective_topic, **kwargs)

            output = planner_result.get("output", "")
            if planner_result.get("plan") is not None:
                output = (
                    "Planner generated structured output successfully.\n\n" + output
                )

            update_topic_run(
                run_id,
                status="completed",
                active_agent=self._name,
                meta={"effective_topic": effective_topic},
            )
            record_orchestrator_event(
                run_id,
                event_type="pipeline_complete",
                agent=self._name,
                status="completed",
                message="Planner-only deterministic orchestration completed",
                meta={"effective_topic": effective_topic},
            )

            return {
                "messages": planner_result.get("messages", []),
                "output": output,
                "plan": planner_result.get("plan"),
            }

    if not topic:
        raise SystemExit("Topic cannot be empty")

    logger.info(
        "Starting planner-only orchestration test",
        action="planner_test_start",
        meta={
            "topic": topic,
            "provider": args.provider,
            "model": args.model,
        },
    )

    # class PlannerAgentNoWebContext(PlannerAgent):
    #     """Testing planner variant that skips web-context tool calls."""

    #     def _gather_web_context(self, topic: str) -> str:
    #         return ""

    # planner = PlannerAgentNoWebContext(
    #     llm_provider=args.provider,
    #     model=args.model,
    #     temperature=args.temperature,
    #     max_tokens=args.max_tokens,
    #     cli_path=args.cli_path,
    #     cli_url=args.cli_url,
    # )

    planner = PlannerAgent(
        llm_provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        cli_path=args.cli_path,
        cli_url=args.cli_url,
    )

    orchestrator = PlannerOnlyOrchestrator(
        sub_agents=[planner],
        llm_provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        cli_path=args.cli_path,
        cli_url=args.cli_url,
        mcp_enabled=False,
    )

    result = orchestrator.invoke(topic)

    topic_db = db_path_for_topic(topic)
    run_info = _latest_run_for_topic(topic)
    artifact_counts = _count_artifacts(
        topic,
        created_after=run_info["created_at"] if run_info else None,
    )

    print("=" * 70)
    print("Planner-only orchestration run complete")
    print("=" * 70)
    print(f"Topic: {topic}")
    print(f"Provider: {args.provider}")
    print(f"Model: {args.model}")
    print(f"Topic DB: {topic_db}")
    print()

    if run_info is None:
        print("No run record found in orchestrator.db")
    else:
        print("Orchestrator run:")
        print(f"  run_id: {run_info['run_id']}")
        print(f"  status: {run_info['status']}")
        print(f"  active_agent: {run_info['active_agent']}")
        print(f"  created_at: {run_info['created_at']}")
        print(f"  updated_at: {run_info['updated_at']}")
        print(f"  topic_db_path: {run_info['topic_db_path']}")

    print()
    print("Artifact counts in topic DB for this run:")
    if not artifact_counts:
        print("  (none)")
    else:
        for key, value in artifact_counts.items():
            print(f"  {key}: {value}")

    print()
    if args.show_output:
        print("Orchestrator output:")
        print("-" * 70)
        print(result.get("output", ""))
        print("-" * 70)
    else:
        print("Use --show-output to print full orchestrator output")

    planner_keyword_count = artifact_counts.get("planner_keyword", 0)
    planner_query_count = artifact_counts.get("planner_query", 0)
    planner_hashtag_count = artifact_counts.get("planner_hashtag", 0)
    planner_platform_count = artifact_counts.get("planner_platform", 0)

    passed = (
        planner_keyword_count > 0
        and planner_query_count > 0
        and planner_hashtag_count > 0
        and planner_platform_count > 0
    )

    print()
    print("Planner artifact validation:")
    print(f"  planner_keyword > 0: {planner_keyword_count > 0}")
    print(f"  planner_query > 0: {planner_query_count > 0}")
    print(f"  planner_hashtag > 0: {planner_hashtag_count > 0}")
    print(f"  planner_platform > 0: {planner_platform_count > 0}")

    if not passed:
        print("Result: FAIL (planner artifacts incomplete)")
        return 1

    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
