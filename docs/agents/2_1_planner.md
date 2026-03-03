# 2.1 — Planner Agent

## Purpose

`PlannerAgent` is the first sub-agent in the pipeline. It transforms a topic into an actionable research plan used by downstream collection and analysis stages.

## What planner produces

Structured `ResearchPlan` output containing:

- topic summary
- keywords
- hashtags
- platform strategy (`name`, `priority`, `reason`)
- search queries
- estimated volume
- stop condition
- reasoning

## Current planner behavior

1. Ensures per-topic DB exists (`init_topic_db`).
2. Writes topic input checkpoint (`topic_inputs`).
3. Runs web-grounding step:
   - tool-enabled context pass using `google_search_snippets`
   - stores `planner_web_context` checkpoint artifact
4. Attempts structured LLM output (`with_structured_output(ResearchPlan)`).
5. If structured output fails, falls back to text response.
6. Persists artifacts in append-only format for recovery/debugging.

## Tool grounding design

Planner does not call Serper directly.

Layered integration:

- Planner -> `agents/tools/search.py` (`google_search_snippets`)
- Tool -> `utils/serper.py` (`search_google_serper`)
- Utility -> Serper API (or demo fallback payload)

This keeps provider logic centralized and replaceable.

## Persistence model

Planner checkpoints are saved in per-topic SQLite DB (`data/scrapes/<topic-slug>.db`):

### `topic_inputs`
- topic + clarification rows (append-only)

### `pipeline_artifacts`
- planner output fragments by type:
  - `planner_raw_output`
  - `planner_keyword`
  - `planner_hashtag`
  - `planner_query`
  - `planner_platform`
  - `planner_topic_summary`
  - `planner_estimated_volume`
  - `planner_stop_condition`
  - `planner_reasoning`
  - `planner_web_context`
  - fallback/error artifacts where applicable

### `agent_status`
- `agent_name`, `status`, `retries`, `last_error`
- `started_at`, `updated_at`, `completed_at`
- used to support stage-level recovery and resume decisions

## Why this matters

- Avoids repeated costly LLM calls after crashes.
- Enables resuming from saved planner outputs.
- Improves observability for retries/failures.
- Keeps deterministic data trail for debugging.

## Integration points

- Agent class: `agents/planner/agent.py`
- Service layer: `agents/services/planner_checkpoint.py`
- Search tool: `agents/tools/search.py`
- Provider adapter: `utils/serper.py`

## Planned evolution

- Add explicit resume shortcut: if planner status is completed and valid artifacts exist, reuse without re-invocation.
- Expand tool grounding with more source strategies while preserving the same utility abstraction pattern.
- Keep structured output as the primary path and enforce stricter schema validation over time.
