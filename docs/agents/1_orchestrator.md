# 1 — Orchestrator Agent

## Purpose

`OrchestratorAgent` is the primary controller for the sentiment analysis pipeline. It is responsible for receiving the topic, bootstrapping persistence, coordinating sub-agents, and recording run lifecycle state.

## Main responsibilities

1. **Topic intake and bootstrap**
   - Immediately bootstrap persistence when a topic is received.
   - Create/append a run row in central orchestrator DB (`data/scrapes/orchestrator.db`).
   - Initialize the per-topic DB (`data/scrapes/<topic-slug>.db`) before planner execution.

2. **Delegation orchestration**
   - Expose sub-agents as tools (`delegate_to_<agent>` pattern).
   - In current implementation, planner is the first sub-agent.

3. **Lifecycle tracking**
   - Update run status in `topic_runs` (`received` -> `running` -> `completed|failed`).
   - Append timeline events to `orchestrator_events` for observability and debugging.

4. **Resilience by default (via BaseAgent)**
   - Timeout per invocation.
   - Single retry by default.
   - Circuit breaker after consecutive failures.

## Current flow

1. Topic reaches orchestrator (`invoke`).
2. Orchestrator calls `bootstrap_topic(topic)`.
3. `bootstrap_topic` creates/updates:
   - central run metadata in orchestrator DB,
   - per-topic DB schema,
   - initial topic row/artifact checkpoints.
4. Orchestrator marks run `running`.
5. Orchestrator executes pipeline by delegating to sub-agents (currently planner).
6. On success/failure, orchestrator writes final status + event.

## Data model (current)

### Central DB: `orchestrator.db`

- `topic_runs`
  - `run_id`, `topic`, `topic_slug`, `topic_db_path`
  - `status`, `active_agent`, `retries`, `error`, `meta_json`
  - `created_at`, `updated_at`

- `orchestrator_events`
  - append-only run events by timestamp
  - event type/status/message/meta for auditability

### Per-topic DB: `<topic-slug>.db`

- Created at topic intake, not deferred to planner.
- Used by all agents for checkpoints and recovery.

## Integration points

- Agent class: `agents/orchestrator/agent.py`
- Service layer: `agents/services/orchestrator_checkpoint.py`
- API intake integration: `server/routes/sessions.py`

## Planned evolution

- Add more sub-agents (searcher/harvester, scraper, cleaner, analyzer).
- Add resume logic at orchestration layer to skip already-completed stages.
- Introduce stronger central store (future DB) while keeping the current service abstraction stable.
