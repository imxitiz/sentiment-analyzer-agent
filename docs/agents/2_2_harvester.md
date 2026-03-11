# 2.2 — Harvester Agent

## Purpose

`HarvesterAgent` is Phase 2 of the pipeline. It receives the planner's research artifacts and converts them into an actionable `HarvestPlan`, then executes multi-source, concurrent link collection and stores deduplicated, quality-scored candidate URLs in the per-topic SQLite database for the scraper to consume in Phase 3.

The agent's role is **link discovery only** — it collects URLs and their metadata, it does not fetch page content. That is the scraper's job.

---

## Where it fits in the pipeline

```
PlannerAgent → [pipeline_artifacts in SQLite] → HarvesterAgent → [discovered_links in SQLite] → ScraperAgent
```

The harvester reads what the planner wrote, not what the planner returns. Even if the orchestrator crashes after planner completes, the harvester can resume cold from the persistent artifacts.

---

## Main responsibilities

1. **Reconstruct planner context** — load `ResearchBrief` from planner's append-only SQL artifacts.
2. **Build a `HarvestPlan`** — ask the LLM (structured output) to turn the brief + available sources into a list of `HarvestTaskPlan` entries.
3. **Execute collection concurrently** — fan out async workers per task × source combination, bounded by a semaphore.
4. **Write links safely** — all collector output passes through `AsyncLinkWriter`, a single-consumer async queue that serializes SQLite writes to prevent race conditions.
5. **Expand promising seeds** — after the main search phase, select the highest-quality links as seed URLs and expand them with Crawlbase to find additional candidates.
6. **Checkpoint everything** — plan, per-source summaries, stats, and completion status all go into the topic SQLite DB.

---

## Current flow (step by step)

1. `invoke(topic)` → calls `asyncio.run(ainvoke(topic))`.
2. `ainvoke` writes `topic_inputs` checkpoint and sets `agent_status = working`.
3. `load_research_brief(topic)` — reads planner artifacts from `pipeline_artifacts` and reconstructs a `ResearchBrief`. Falls back to using the bare topic string if planner artifacts are missing.
4. `_runtime_config()` — reads all `HARVESTER_*` env vars and builds a `HarvesterRuntimeConfig` dataclass.
5. `init_harvest_tables(topic)` — creates `harvest_runs`, `discovered_links`, `link_observations` tables if they do not exist.
6. `_build_harvest_plan(topic, brief, runtime)` — either:
   - **Live mode**: asks LLM via `with_structured_output(HarvestPlan)` with available source names injected into the prompt context. Saves the prompt input as `harvester_plan_prompt` artifact before invoking.
   - **Demo or LLM failure**: calls `_demo_plan()` → `build_fallback_harvest_tasks()` which builds deterministic tasks from the brief's queries and platform hints.
7. Saves `harvester_plan` artifact (full JSON plan + task count).
8. `start_harvest_run(...)` — inserts run record into `harvest_runs`.
9. `record_orchestrator_event(...)` — notifies orchestrator that harvesting has started.
10. `AsyncLinkWriter.start()` — starts background consumer task draining the write queue.
11. `_collect_search_batches(...)` — builds the source map from flags in `runtime`, creates one coroutine per (task, source_name) pair, runs all via `asyncio.gather` with a per-task timeout.
12. Each collector submits `HarvestedLink` objects to the writer via `writer.submit_many(...)`.
13. Each completed source task saves a `harvester_source_summary` artifact.
14. `select_expansion_seeds(...)` — picks the best N links from search results.
15. `expand_with_crawlbase(...)` — fetches each seed URL via Crawlbase, extracts all anchor `<a href>` links, submits them to the writer.
16. `writer.close()` — flushes remaining queue items, stops the consumer.
17. `finish_harvest_run(...)`, `_checkpoint_agent_status(completed)`, `harvester_summary` artifact.
18. Returns `{"output": <markdown summary>, "plan": <HarvestPlan>, "stats": <WriterStats + extras>}`.

On any exception, the same cleanup path closes the writer, marks the run and agent status as failed, and saves a `harvester_error` artifact before re-raising.

---

## HarvestPlan — the LLM's output

```python
class HarvestPlan(BaseModel):
    summary: str            # short description of the strategy
    source_order: list[str] # global priority order of sources
    max_links: int          # upper bound on canonical links to store
    min_quality_score: float
    tasks: list[HarvestTaskPlan]
    reasoning: str          # why this plan is high quality
```

```python
class HarvestTaskPlan(BaseModel):
    query: str              # exact search query to execute
    platform_hint: str      # e.g. "reddit", "youtube", "web"
    source_names: list[str] # ordered adapters that should run this query
    target_results: int     # target raw count per source
    rationale: str          # why this query/source combination matters
```

The LLM produces one `HarvestTaskPlan` per query × platform combination it thinks will yield valuable links. The runtime then maps `source_names` to registered collector functions.

---

## Collection sources

All sources are async coroutines. Each returns a `HarvestSourceResult(source_name, source_type, links, warnings, meta)`.

| Source name | Adapter | Default | Requires |
| --- | --- | --- | --- |
| `serper` | `utils/serper.py` → `search_google_serper()` | on | `SERPER_API_KEY` (demo fallback works without it) |
| `firecrawl_search` | `utils/firecrawl.py` → `search_firecrawl()` | on | `FIRECRAWL_API_KEY` |
| `firecrawl_browser` | `utils/firecrawl.py` → `create_firecrawl_browser_session()` | on (when firecrawl is on) | `FIRECRAWL_API_KEY` |
| `serpapi` | `utils/serpapi.py` | off | `SERPAPI_API_KEY` |
| `camoufox_browser` | `utils/camoufox.py` → `camoufox_fetch_anchors()` | off | remote server, local Python pkg, or CLI |
| **Crawlbase expansion** | `utils/crawlbase.py` → `crawlbase_fetch_url()` | on | `CRAWLBASE_TOKEN` or `CRAWLBASE_JS_TOKEN` |

Source flags are resolved at runtime from env vars: `HARVESTER_ENABLE_SERPER`, `HARVESTER_ENABLE_FIRECRAWL`, `HARVESTER_ENABLE_BROWSER_DISCOVERY`, `HARVESTER_ENABLE_CRAWLBASE`, `HARVESTER_ENABLE_SERPAPI`, `HARVESTER_ENABLE_CAMOUFOX`.

Serper always works in demo mode (static payload returned by `utils/serper.py`) so the pipeline runs without any API keys.

---

## AsyncLinkWriter — the write queue

`AsyncLinkWriter` is a single-consumer async queue that serializes all SQLite writes. Collector tasks are highly concurrent; the writer prevents write-race conditions by funneling every `HarvestedLink` through one queue consumer.

```
collector_1 ──┐
collector_2 ──┤  asyncio.Queue  ──►  _worker()  ──►  SQLite
collector_N ──┘
```

The consumer processes links in batches of `writer_batch_size`. For each link it:

1. `normalize_url(url)` — strips tracking params (`utm_*`, `fbclid`, etc.), normalizes scheme/host/path, drops fragments.
2. `score_link(link, brief)` — returns `(quality_score, relevance_score, rejection_reason)`. Quality considers title/description presence, author, publication date, position in results, platform match, and relevance. Relevance counts keyword/hashtag matches from the brief.
3. If `rejection_reason` is not `None` or `quality_score < min_quality_score`, the link is rejected and logged in `link_observations` with `accepted=0`.
4. Otherwise, upsert into `discovered_links` (insert if new, update `last_seen_at`/`duplicate_count` if already exists) and insert into `link_observations` with `accepted=1`.

The writer exposes `is_full` (returns `True` when `links_inserted >= max_links`) so collectors can stop early. It also tracks `WriterStats`: `queued`, `observations_written`, `links_inserted`, `links_updated`, `duplicates_seen`, `rejected_low_quality`, `rejected_invalid`, `write_errors`.

---

## Persistence model

All tables live in the per-topic SQLite database: `data/scrapes/<topic-slug>.db`.

### `harvest_runs`

Run-level metadata, one row per `HarvesterAgent.ainvoke` call.

| Column | Purpose |
| --- | --- |
| `run_id` | UUID for this harvest run |
| `status` | `running` → `completed` / `failed` |
| `plan_json` | Full serialized `HarvestPlan` |
| `config_json` | `HarvesterRuntimeConfig` as dict |
| `stats_json` | Final `WriterStats` + extras |
| `error` | Last error message if failed |

### `discovered_links`

The canonical, deduplicated link table. One row per normalized URL.

| Column | Purpose |
| --- | --- |
| `unique_id` | SHA-256 of normalized URL (first 24 chars) |
| `normalized_url` | Tracking-stripped, canonical URL |
| `url` | Original URL as first seen |
| `topic` | Topic string |
| `platform` | Inferred platform (`reddit`, `youtube`, `web`, …) |
| `quality_score` | Computed by `score_link()` |
| `relevance_score` | Keyword/hashtag match score |
| `status` | `PENDING` (ready for scraper) |
| `duplicate_count` | How many times this URL was seen |
| `source_name` | First source that found this URL |

### `link_observations`

Append-only raw observation log — every occurrence from every source, including rejected ones.

| Column | Purpose |
| --- | --- |
| `run_id` | Which harvest run this observation belongs to |
| `unique_id` | Links back to `discovered_links` |
| `normalized_url` | For deduplication analysis |
| `accepted` | 1 if inserted into `discovered_links`, 0 if rejected |
| `rejection_reason` | `low_value_url`, `invalid_url`, `low_quality`, or `None` |

---

## ResearchBrief — input from planner

`load_research_brief(topic)` reconstructs this from planner artifacts in `pipeline_artifacts`:

```python
@dataclass
class ResearchBrief:
    topic: str
    topic_summary: str
    keywords: list[str]
    hashtags: list[str]
    platforms: list[dict]   # [{"name": "reddit", "priority": "high", "reason": "..."}]
    search_queries: list[str]
    estimated_volume: str
    stop_condition: str
    reasoning: str
```

If no planner artifacts exist, the brief defaults to the bare topic string with an empty keyword list. Collection still runs, just with less precision.

---

## URL normalization and scoring (key logic)

`normalize_url(url)`:

- Strips UTM/tracking params: `utm_*`, `fbclid`, `gclid`, `mc_cid`, `ref`, `si`, etc.
- Lowercases scheme and host.
- Strips trailing slash from non-root paths.
- Removes fragment identifier (#section).
- Rejects non-HTTP/HTTPS schemes (returns "").

`is_probably_low_value_url(url)`:

- Rejects URLs matching patterns like `/login`, `/privacy`, `/share`, `/intent/`, `/sharer`.
- Rejects static asset extensions (`.jpg`, `.png`, `.css`, `.js`).

`score_link(link, brief)`:

- Quality score components: base `0.2` + title `+0.12` + description `+0.10` + author `+0.05` + published_at `+0.05` + position-based up to `+0.20` + non-web platform `+0.08` + provider `quality_signal` + relevance boost.
- Relevance: count of brief terms (topic, keywords, hashtags) that appear in `title + description + discovery_query + anchor_text_metadata`.
- Final quality clamped to `[0.0, 1.0]`.

---

## HarvesterRuntimeConfig

Built from env vars by `_runtime_config()`. All fields have typed defaults and are read safely (invalid values fall back to defaults).

| Field | Env var | Default |
| --- | --- | --- |
| `max_links` | `HARVESTER_MAX_LINKS` | 1000 |
| `max_concurrency` | `HARVESTER_MAX_CONCURRENCY` | 8 |
| `source_timeout_seconds` | `HARVESTER_SOURCE_TIMEOUT_SECONDS` | 120 |
| `writer_batch_size` | `HARVESTER_WRITER_BATCH_SIZE` | 50 |
| `writer_queue_size` | `HARVESTER_QUEUE_SIZE` | 5000 |
| `per_query_limit` | `HARVESTER_PER_QUERY_LIMIT` | 25 |
| `min_quality_score` | `HARVESTER_MIN_QUALITY_SCORE` | 0.35 |
| `expansion_seed_limit` | `HARVESTER_EXPANSION_SEED_LIMIT` | 12 |
| `expansion_per_seed_limit` | `HARVESTER_EXPANSION_PER_SEED_LIMIT` | 25 |
| `enable_serper` | `HARVESTER_ENABLE_SERPER` | `True` |
| `enable_firecrawl` | `HARVESTER_ENABLE_FIRECRAWL` | `True` |
| `enable_browser_discovery` | `HARVESTER_ENABLE_BROWSER_DISCOVERY` | `True` |
| `enable_crawlbase` | `HARVESTER_ENABLE_CRAWLBASE` | `True` |
| `enable_serpapi` | `HARVESTER_ENABLE_SERPAPI` | `False` |
| `enable_camoufox` | `HARVESTER_ENABLE_CAMOUFOX` | `False` |

---

## Demo mode

When `llm_provider="dummy"` or `--demo` is set:

- `_build_harvest_plan()` calls `_demo_plan()` → `build_fallback_harvest_tasks(brief, runtime)` which deterministically generates `HarvestTaskPlan` entries from `brief.search_queries` and `brief.platforms`.
- All source collectors still run, but Serper returns a static demo payload (defined in `utils/serper.py`) and non-Serper sources that require API keys gracefully return empty `HarvestSourceResult` with a warning.
- The writer still runs. Demo data gets inserted into SQLite just like live data.
- This means `data/scrapes/<topic>.db` is populated and the scraper can bootstrap from it even in demo mode.

---

## Checkpoint artifacts written

| `artifact_type` | When written | What it contains |
| --- | --- | --- |
| `harvester_plan_prompt` | Before LLM call | Input JSON sent to the LLM |
| `harvester_plan` | After plan built | Full `HarvestPlan` JSON |
| `harvester_plan_fallback` | On LLM failure | Error message, fallback was used |
| `harvester_source_summary` | After each source | source name, count, warnings, query |
| `harvester_summary` | On success | Markdown summary with stats |
| `harvester_error` | On failure | Exception message |

---

## LLM configuration

- Default provider: `google` (Gemini)
- Default model: `gemini-2.5-flash`
- Timeout: `1200` seconds (20 min) — long because concurrent collection can run many queries
- Max retries: `2`
- LLM is used **only** to build the `HarvestPlan`. All collection is deterministic code.

---

## Integration points

| Path | Role |
| --- | --- |
| `agents/harvester/agent.py` | Agent class |
| `agents/harvester/models.py` | `HarvestPlan`, `HarvestTaskPlan`, `ResearchBrief`, `HarvestedLink`, `HarvestSourceResult`, `HarvesterRuntimeConfig` |
| `agents/harvester/prompts/system.txt` | System prompt |
| `agents/services/harvester_store.py` | SQLite schema, URL normalization, quality scoring, `AsyncLinkWriter` |
| `agents/services/harvester_sources.py` | Collector functions for each source + `build_fallback_harvest_tasks()` |
| `agents/services/planner_checkpoint.py` | `db_path_for_topic()`, `init_topic_db()` (reused for table bootstrapping) |
| `utils/serper.py` | Serper search adapter |
| `utils/firecrawl.py` | Firecrawl search and browser session adapter |
| `utils/crawlbase.py` | Crawlbase rendered fetch adapter |
| `utils/serpapi.py` | SerpAPI adapter |
| `utils/camoufox.py` | Camoufox stealth browser adapter |

---

## What happens when this agent starts

1. It expects the topic SQLite DB to exist and the planner to have written artifacts into `pipeline_artifacts`.
2. If no planner artifacts exist, it still runs with a minimal `ResearchBrief` (bare topic string).
3. It creates `harvest_runs`, `discovered_links`, `link_observations` tables if they do not exist.
4. It does NOT read from MongoDB (that is the scraper's territory).
5. It does NOT write to MongoDB.
6. Its output is `discovered_links` rows, each with `status = 'PENDING'` — ready for the scraper.

---

## Output consumed by ScraperAgent

`ScraperAgent.bootstrap_scrape_targets(topic)` copies all rows from `discovered_links` into `scrape_targets` (INSERT OR IGNORE). The scraper then loads `status = 'not_started'` targets and begins its work. The two agents share the same per-topic SQLite DB but own different tables.

---

## Planned evolution

- Explicit resume: if `harvester_summary` artifact and `harvest_runs.status = 'completed'` already exist for this topic, skip re-harvesting and return the existing stats.
- Twitter/X and TikTok specialized collectors (currently those fall back to Serper/Firecrawl search with `site:` operators).
- Per-source retry logic independent of the per-task semaphore (some sources are rate-limited rather than timing out).
- Quality signal feedback loop: after scraping, propagate actual content richness back to improve `quality_score` for future harvesting decisions.
