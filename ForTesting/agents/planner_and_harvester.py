"""CLI smoke test for orchestrator -> planner -> harvester flow.

This script mirrors the real orchestrator checkpoint lifecycle while intentionally
stopping after harvesting. It is designed to validate:

1. Planner artifact production and persistence
2. Harvester task execution using planner-derived queries
3. Source execution coverage (Serper / Firecrawl / Camoufox)
4. SQLite persistence in discovered_links and link_observations

Examples:
    uv run python ForTesting/agents/planner_and_harvester.py --topic "Nepal elections 2026"
    uv run python ForTesting/agents/planner_and_harvester.py --topic "Nepal elections 2026" --planner-mode reuse
    uv run python ForTesting/agents/planner_and_harvester.py --topic "EV policy" --provider dummy
"""

from __future__ import annotations

import argparse
import json
import os
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
        description=(
            "Run planner+harvester smoke test with orchestrator checkpoint flow "
            "and optional planner resume mode."
        )
    )
    parser.add_argument(
        "--topic",
        "-t",
        type=str,
        default=None,
        help="Topic to run. If omitted with --interactive, asks from stdin.",
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
        help="LLM provider (default: copilot). Use dummy for offline smoke tests.",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="gpt-4o",
        help="Model name for provider (default: gpt-4o).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Model temperature (default: 0.2).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Max generation tokens (default: 2048).",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Print final orchestrator output payload.",
    )
    parser.add_argument(
        "--planner-mode",
        choices=("auto", "run", "reuse"),
        default="auto",
        help=(
            "Planner execution mode: auto (reuse if artifacts exist), "
            "run (always execute planner), reuse (require existing planner artifacts)."
        ),
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
        help="Optional URL to existing Copilot CLI server.",
    )

    parser.add_argument(
        "--enable-serper",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable Serper source collection (default: true).",
    )
    parser.add_argument(
        "--enable-firecrawl",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable Firecrawl search source collection (default: true).",
    )
    parser.add_argument(
        "--enable-browser-discovery",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable Firecrawl browser discovery source (default: true).",
    )
    parser.add_argument(
        "--enable-camoufox",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable Camoufox browser source collection (default: false).",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=None,
        help="Optional HARVESTER_MAX_LINKS override for this run.",
    )
    parser.add_argument(
        "--per-query-limit",
        type=int,
        default=None,
        help="Optional HARVESTER_PER_QUERY_LIMIT override for this run.",
    )
    parser.add_argument(
        "--source-timeout-seconds",
        type=int,
        default=None,
        help="Optional HARVESTER_SOURCE_TIMEOUT_SECONDS override for this run.",
    )
    return parser.parse_args()


def _resolve_topic(args: argparse.Namespace) -> str:
    if args.topic:
        return args.topic.strip()
    if args.interactive:
        return input("Topic: ").strip()
    raise SystemExit("Provide --topic or use --interactive")


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _configure_harvester_runtime(args: argparse.Namespace) -> None:
    """Apply per-run harvester flags via env vars and reload config cache."""
    os.environ["HARVESTER_ENABLE_SERPER"] = _bool_str(args.enable_serper)
    os.environ["HARVESTER_ENABLE_FIRECRAWL"] = _bool_str(args.enable_firecrawl)
    os.environ["HARVESTER_ENABLE_BROWSER_DISCOVERY"] = _bool_str(
        args.enable_browser_discovery
    )
    os.environ["HARVESTER_ENABLE_CAMOUFOX"] = _bool_str(args.enable_camoufox)

    if args.max_links is not None:
        os.environ["HARVESTER_MAX_LINKS"] = str(max(1, args.max_links))
    if args.per_query_limit is not None:
        os.environ["HARVESTER_PER_QUERY_LIMIT"] = str(max(1, args.per_query_limit))
    if args.source_timeout_seconds is not None:
        os.environ["HARVESTER_SOURCE_TIMEOUT_SECONDS"] = str(
            max(1, args.source_timeout_seconds)
        )

    from env import config

    config.reload()


def _planner_artifact_counts(topic: str) -> dict[str, int]:
    from agents.services.planner_checkpoint import db_path_for_topic

    path = db_path_for_topic(topic)
    if not path.exists():
        return {}

    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT artifact_type, COUNT(*)
            FROM pipeline_artifacts
            WHERE source_agent = 'planner'
            GROUP BY artifact_type
            ORDER BY artifact_type ASC
            """
        ).fetchall()

    return {str(artifact_type): int(count) for artifact_type, count in rows}


def _has_planner_brief(topic: str) -> bool:
    counts = _planner_artifact_counts(topic)
    return (
        counts.get("planner_query", 0) > 0
        and counts.get("planner_keyword", 0) > 0
        and counts.get("planner_platform", 0) > 0
    )


def _latest_run_for_topic(topic: str) -> dict[str, Any] | None:
    from agents.services.orchestrator_checkpoint import init_orchestrator_db

    db_path = init_orchestrator_db()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT run_id, status, active_agent, topic_db_path, created_at, updated_at, meta_json
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
        "meta": json.loads(row[6]) if row[6] else {},
    }


def _latest_harvest_run(topic: str) -> dict[str, Any] | None:
    from agents.services.planner_checkpoint import db_path_for_topic

    path = db_path_for_topic(topic)
    if not path.exists():
        return None

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT run_id, created_at, updated_at, status, source_agent, llm_provider,
                   llm_model, stats_json, error
            FROM harvest_runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    stats_raw = row[7]
    return {
        "run_id": str(row[0]),
        "created_at": str(row[1]),
        "updated_at": str(row[2]),
        "status": str(row[3]),
        "source_agent": str(row[4]),
        "llm_provider": str(row[5]) if row[5] is not None else None,
        "llm_model": str(row[6]) if row[6] is not None else None,
        "stats": json.loads(stats_raw) if stats_raw else {},
        "error": str(row[8]) if row[8] is not None else None,
    }


def _source_summary_by_run(
    topic: str,
    *,
    created_after: str,
) -> dict[str, int]:
    from agents.services.planner_checkpoint import db_path_for_topic

    path = db_path_for_topic(topic)
    if not path.exists():
        return {}

    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT value
            FROM pipeline_artifacts
            WHERE source_agent = 'harvester'
              AND artifact_type = 'harvester_source_summary'
              AND created_at >= ?
            ORDER BY id ASC
            """,
            (created_after,),
        ).fetchall()

    counts: dict[str, int] = {}
    for (value,) in rows:
        try:
            payload = json.loads(value)
        except Exception:
            continue
        source = str(payload.get("source", "")).strip()
        if not source:
            continue
        counts[source] = counts.get(source, 0) + 1
    return counts


def _observation_counts_for_run(topic: str, run_id: str) -> dict[str, int]:
    from agents.services.planner_checkpoint import db_path_for_topic

    path = db_path_for_topic(topic)
    if not path.exists():
        return {}

    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT source_name, COUNT(*)
            FROM link_observations
            WHERE run_id = ?
            GROUP BY source_name
            ORDER BY source_name ASC
            """,
            (run_id,),
        ).fetchall()
    return {str(source): int(count) for source, count in rows}


def _configure_expected_sources(args: argparse.Namespace) -> dict[str, bool]:
    from env import config

    firecrawl_available = bool(config.get(key="FIRECRAWL_API_KEY"))

    return {
        "serper": bool(args.enable_serper),
        "firecrawl_search": bool(args.enable_firecrawl and firecrawl_available),
        "firecrawl_browser": bool(
            args.enable_firecrawl
            and args.enable_browser_discovery
            and firecrawl_available
        ),
        "camoufox_browser": bool(args.enable_camoufox),
    }


def run() -> int:
    args = _parse_args()
    topic = _resolve_topic(args)
    if not topic:
        raise SystemExit("Topic cannot be empty")

    _bootstrap_project_root()
    _configure_harvester_runtime(args)

    from Logging import get_logger
    from agents.harvester import HarvesterAgent
    from agents.orchestrator import OrchestratorAgent
    from agents.planner import PlannerAgent
    from agents.services import (
        bootstrap_topic,
        record_orchestrator_event,
        update_topic_run,
    )
    from agents.services.planner_checkpoint import db_path_for_topic

    logger = get_logger("ForTesting.planner_and_harvester")

    class PlannerHarvesterOrchestrator(OrchestratorAgent):
        """Deterministic orchestrator that stops after harvester phase."""

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
                meta={
                    "mode": "planner_harvester_smoke",
                    "planner_mode_requested": args.planner_mode,
                },
            )

            planner = self._sub_agents[0]
            harvester = self._sub_agents[1]

            planner_executed = False
            planner_mode_used = "run"
            planner_result: dict[str, Any] | None = None

            planner_exists = _has_planner_brief(topic)
            if args.planner_mode == "reuse":
                if not planner_exists:
                    raise RuntimeError(
                        "Planner reuse requested but planner artifacts were not found "
                        "for this topic. Run once with --planner-mode run or auto."
                    )
                planner_mode_used = "reuse"
            elif args.planner_mode == "auto":
                planner_mode_used = "reuse" if planner_exists else "run"
            else:
                planner_mode_used = "run"

            if planner_mode_used == "run":
                planner_executed = True
                record_orchestrator_event(
                    run_id,
                    event_type="planner_started",
                    agent="planner",
                    status="running",
                    message="Planner started from smoke orchestrator",
                )
                planner_result = planner.invoke(topic, **kwargs)
                record_orchestrator_event(
                    run_id,
                    event_type="planner_complete",
                    agent="planner",
                    status="completed",
                    message="Planner completed from smoke orchestrator",
                )
            else:
                record_orchestrator_event(
                    run_id,
                    event_type="planner_reused",
                    agent="planner",
                    status="completed",
                    message="Planner step skipped; reusing existing planner artifacts",
                )

            record_orchestrator_event(
                run_id,
                event_type="harvester_started",
                agent="harvester",
                status="running",
                message="Harvester started from smoke orchestrator",
                meta={"planner_mode_used": planner_mode_used},
            )

            harvester_result = harvester.invoke(topic, **kwargs)

            record_orchestrator_event(
                run_id,
                event_type="harvester_complete",
                agent="harvester",
                status="completed",
                message="Harvester completed from smoke orchestrator",
                meta={
                    "planner_mode_used": planner_mode_used,
                    "planner_executed": planner_executed,
                    "harvester_stats": harvester_result.get("stats", {}),
                },
            )

            update_topic_run(
                run_id,
                status="completed",
                active_agent=self._name,
                meta={
                    "mode": "planner_harvester_smoke",
                    "planner_mode_used": planner_mode_used,
                    "planner_executed": planner_executed,
                },
            )
            record_orchestrator_event(
                run_id,
                event_type="pipeline_complete",
                agent=self._name,
                status="completed",
                message="Planner+Harvester smoke orchestration completed",
                meta={
                    "planner_mode_used": planner_mode_used,
                    "planner_executed": planner_executed,
                },
            )

            output_parts = [
                "# Planner + Harvester Smoke Test",
                f"Topic: {topic}",
                f"Planner mode used: {planner_mode_used}",
                "",
                harvester_result.get("output", ""),
            ]
            if planner_result and planner_result.get("output"):
                output_parts.extend(["", "## Planner Output", planner_result["output"]])

            return {
                "messages": [],
                "output": "\n".join(output_parts).strip(),
                "planner_mode_used": planner_mode_used,
                "planner_executed": planner_executed,
                "planner": planner_result,
                "harvester": harvester_result,
            }

    logger.info(
        "Starting planner+harvester smoke test",
        action="planner_harvester_smoke_start",
        meta={
            "topic": topic,
            "provider": args.provider,
            "model": args.model,
            "planner_mode": args.planner_mode,
            "enable_serper": args.enable_serper,
            "enable_firecrawl": args.enable_firecrawl,
            "enable_browser_discovery": args.enable_browser_discovery,
            "enable_camoufox": args.enable_camoufox,
        },
    )

    planner = PlannerAgent(
        llm_provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        cli_path=args.cli_path,
        cli_url=args.cli_url,
    )
    harvester = HarvesterAgent(
        llm_provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        cli_path=args.cli_path,
        cli_url=args.cli_url,
    )
    orchestrator = PlannerHarvesterOrchestrator(
        sub_agents=[planner, harvester],
        llm_provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        cli_path=args.cli_path,
        cli_url=args.cli_url,
        mcp_enabled=False,
    )

    result = orchestrator.invoke(topic)

    run_info = _latest_run_for_topic(topic)
    harvest_run = _latest_harvest_run(topic)
    planner_counts = _planner_artifact_counts(topic)
    source_summaries = (
        _source_summary_by_run(topic, created_after=harvest_run["created_at"])
        if harvest_run
        else {}
    )
    observation_counts = (
        _observation_counts_for_run(topic, harvest_run["run_id"]) if harvest_run else {}
    )
    expected_sources = _configure_expected_sources(args)

    topic_db = db_path_for_topic(topic)
    print("=" * 72)
    print("Planner + Harvester smoke run complete")
    print("=" * 72)
    print(f"Topic: {topic}")
    print(f"Provider: {args.provider}")
    print(f"Model: {args.model}")
    print(f"Planner mode requested: {args.planner_mode}")
    print(f"Planner mode used: {result.get('planner_mode_used')}")
    print(f"Planner executed: {result.get('planner_executed')}")
    print(f"Topic DB: {topic_db}")
    print()

    if run_info:
        print("Orchestrator run:")
        print(f"  run_id: {run_info['run_id']}")
        print(f"  status: {run_info['status']}")
        print(f"  active_agent: {run_info['active_agent']}")
        print(f"  created_at: {run_info['created_at']}")
        print(f"  updated_at: {run_info['updated_at']}")
        print(f"  topic_db_path: {run_info['topic_db_path']}")
    else:
        print("No orchestrator run record found.")

    print()
    print("Planner artifact counts:")
    if planner_counts:
        for key, value in planner_counts.items():
            print(f"  {key}: {value}")
    else:
        print("  (none)")

    print()
    if harvest_run:
        print("Harvest run:")
        print(f"  run_id: {harvest_run['run_id']}")
        print(f"  status: {harvest_run['status']}")
        print(f"  source_agent: {harvest_run['source_agent']}")
        print(f"  llm_provider: {harvest_run['llm_provider']}")
        print(f"  llm_model: {harvest_run['llm_model']}")
        print(f"  created_at: {harvest_run['created_at']}")
        print(f"  updated_at: {harvest_run['updated_at']}")
        if harvest_run.get("error"):
            print(f"  error: {harvest_run['error']}")

        print("  stats:")
        stats = harvest_run.get("stats", {})
        for key in sorted(stats.keys()):
            print(f"    {key}: {stats[key]}")
    else:
        print("No harvest run record found.")

    print()
    print("Source summaries (harvester_source_summary artifacts):")
    if source_summaries:
        for source, count in source_summaries.items():
            print(f"  {source}: {count}")
    else:
        print("  (none)")

    print()
    print("Observation rows by source (link_observations):")
    if observation_counts:
        for source, count in observation_counts.items():
            print(f"  {source}: {count}")
    else:
        print("  (none)")

    print()
    print("Validation checks:")
    has_harvest_run = harvest_run is not None
    harvest_completed = bool(
        has_harvest_run and harvest_run.get("status") == "completed"
    )
    has_observations = bool(
        has_harvest_run
        and int(harvest_run.get("stats", {}).get("observations_written", 0)) > 0
    )
    harvest_stats = harvest_run.get("stats", {}) if harvest_run else {}
    links_inserted = int(harvest_stats.get("links_inserted", 0))
    links_updated = int(harvest_stats.get("links_updated", 0))
    has_discovered_links = bool(
        has_harvest_run and (links_inserted > 0 or links_updated > 0)
    )

    print(f"  harvest_run_exists: {has_harvest_run}")
    print(f"  harvest_status_completed: {harvest_completed}")
    print(f"  observations_written > 0: {has_observations}")
    print(f"  links_inserted > 0 or links_updated > 0: {has_discovered_links}")

    source_checks_ok = True
    for source, expected in expected_sources.items():
        if not expected:
            print(f"  source_executed[{source}] (disabled): skipped")
            continue
        seen = source_summaries.get(source, 0) > 0
        source_checks_ok = source_checks_ok and seen
        print(f"  source_executed[{source}] (enabled): {seen}")

    passed = (
        has_harvest_run
        and harvest_completed
        and has_observations
        and has_discovered_links
        and source_checks_ok
    )

    if args.show_output:
        print()
        print("Orchestrator output:")
        print("-" * 72)
        print(result.get("output", ""))
        print("-" * 72)

    print()
    if passed:
        print("Result: PASS")
        return 0

    print("Result: FAIL (see checks above)")
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
