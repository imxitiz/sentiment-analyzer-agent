# 2.3 — Scraper Agent

## Purpose

`ScraperAgent` is Phase 3 of the pipeline. It reads the link queue built by the harvester, fetches the full content of each URL using platform-specialized backends and rendered fallbacks, and persists rich structured raw documents in MongoDB for downstream cleaning and sentiment analysis.

Unlike the harvester, the scraper does not use an LLM tool-calling loop. It bypasses LangGraph entirely and runs as a direct async worker fan-out. The LLM is only involved through a recovery sub-agent that is invoked when a backend fails and the scraper needs to decide whether to retry, switch backend, or abandon the URL.

---

## Where it fits in the pipeline

```
HarvesterAgent → [discovered_links in SQLite] → ScraperAgent → [scraped_documents in MongoDB]
                                                              → [scrape_targets status in SQLite]
```

---

## Main responsibilities

1. **Bootstrap the scrape queue** — copy `discovered_links` rows into `scrape_targets` (SQLite) if not already present.
2. **Parallel deep extraction** — fan out bounded async workers, one per target URL.
3. **Platform-aware routing** — classify each URL and build an ordered backend plan starting from the cheapest/most specialized option.
4. **Smart reuse** — if a fresh raw document already exists in MongoDB for the same normalized URL, attach it to the new topic instead of re-scraping.
5. **AI-assisted recovery** — on backend failure, ask `ScraperRecoveryAgent` whether to retry, switch backend, or mark the URL as terminal.
6. **Dual persistence** — track per-URL scrape status in SQLite; store full raw documents in MongoDB.
7. **Checkpoint everything** — run records, per-target errors, and summary in topic SQLite DB.

---

## Current flow (step by step)

1. `invoke(topic)` — in demo mode, returns static stats immediately. Otherwise calls `asyncio.run(ainvoke(topic))`.
2. `ainvoke` writes `topic_inputs` checkpoint, marks `agent_status = working`.
3. `_runtime_config()` → `build_scrape_runtime_config()` — reads env vars, resolves enabled backends, probes Camoufox availability.
4. `init_scraper_tables(topic)` — creates `scrape_runs` and `scrape_targets` tables in topic SQLite DB.
5. `bootstrap_scrape_targets(topic)` — `INSERT OR IGNORE` all rows from `discovered_links` into `scrape_targets`. Returns the count of newly inserted rows.
6. `load_scrape_targets(topic, limit=runtime.max_targets_per_run)` — selects `not_started` targets ordered by `quality_score DESC, relevance_score DESC`.
7. `start_scrape_run(...)` — inserts run row in `scrape_runs`.
8. `build_document_store()` — returns `MongoDocumentStore` instance.
9. `document_store.start_run(...)` — upserts run record in MongoDB `scrape_runs` collection.
10. `document_store.sync_targets(...)` — upserts all targets into MongoDB `scrape_targets` collection, linking them to the current topic via `topic_refs`.
11. Creates `ScraperRecoveryAgent` (LLM sub-agent, see below).
12. `asyncio.gather(...)` — fans out one `_worker(target)` coroutine per target, bounded by `asyncio.Semaphore(runtime.max_concurrency)`.
13. Per target: check document reuse → build backend plan → try backends in order → invoke recovery agent on failures.
14. `scrape_status_counts(topic)` — final status breakdown from SQLite.
15. `finish_scrape_run(...)` in SQLite + `document_store.finish_run(...)` in MongoDB.
16. `_checkpoint_agent_status(completed)`, `scraper_summary` artifact.
17. Returns `{"output": <summary string>, "stats": <dict>}`.

---

## Per-target processing logic

```
target received
    │
    ├─► document_store.find_document(normalized_url)
    │       └─ found + is_fresh?  ──► attach_existing_document() → status=reused
    │
    └─► build_backend_plan(target, runtime)
            │
            ├─ empty plan ──► status=failed (no_backend)
            │
            └─► for backend in ordered_plan (up to max_retries_per_target):
                    ├─ scrape_target_with_backend(target, backend) ──► success
                    │       └─► document_store.save_document() → status=completed
                    │
                    └─ exception
                            └─► _run_recovery_agent(target, backend, error, remaining)
                                    ├─ mark_terminal=True ──► exit loop, status=failed
                                    ├─ should_retry=False ──► exit loop, status=failed
                                    └─ should_retry=True  ──► continue loop with next backend
```

**Document reuse**: `_can_reuse_document()` returns `True` when `allow_existing_reuse=True` and the document's `last_scraped_at` is within `reuse_existing_days` days. Reused documents are attached to the new topic in MongoDB without re-fetching. Saves cost and time for recurring topics.

---

## Platform classification and backend routing

`classify_target_platform(target)` infers the platform from the URL domain and path, or uses the `platform` field written by the harvester.

`build_backend_plan(target, runtime)` returns an ordered list of backend names to try, filtered by what is currently enabled and available.

| Platform | Backend order |
| --- | --- |
| `reddit` | `reddit_json`, `generic_http`, `firecrawl`, `camoufox`, `crawlbase` |
| `bluesky` | `bluesky_public`, `firecrawl`, `camoufox`, `generic_http`, `crawlbase` |
| `youtube` | `youtube_oembed`, `generic_http`, `firecrawl`, `crawlbase`, `camoufox` |
| `hackernews` | `hackernews_api`, `generic_http`, `firecrawl`, `crawlbase`, `camoufox` |
| `rss` | `rss_feed`, `generic_http`, `firecrawl`, `crawlbase` |
| `facebook`, `instagram`, `tiktok`, `x`, `twitter` | `firecrawl`, `camoufox`, `generic_http`, `crawlbase` |
| `web` / news / blogs | `generic_http`, `firecrawl`, `crawlbase`, `camoufox` |

Platform-specific backends (`reddit_json`, `bluesky_public`, `youtube_oembed`, `hackernews_api`, `rss_feed`) are **always included in the plan when their platform matches** regardless of the generic backend enable flags. They are low-cost public API calls with no API key requirement.

---

## Scraping backends

All backends are wrapped in `scrape_target_with_backend()` → `asyncio.to_thread(_scrape_target_sync())`.

### Platform-specialized backends

| Backend | Adapter | What it fetches |
| --- | --- | --- |
| `reddit_json` | `requests` → `reddit.com/<post>.json` | Post body + flat comment tree + engagement metrics (score, upvote_ratio, num_comments) |
| `bluesky_public` | `utils/bluesky.py` | Post thread via AT Protocol public API (`resolveHandle` + `getPostThread`) |
| `youtube_oembed` | `utils/youtube.py` | oEmbed metadata (title, uploader, thumbnail) via YouTube's public oEmbed endpoint |
| `hackernews_api` | `utils/hackernews.py` | HN item + threaded comments via Firebase item API (`algolia.io`) |
| `rss_feed` | `utils/rss.py` | Feed entries: title, link, summary, author, published, feed metadata |

### Generic / rendered backends

| Backend | Adapter | When to use |
| --- | --- | --- |
| `generic_http` | `requests` + `BeautifulSoup` | Normal, publicly accessible web pages |
| `firecrawl` | `utils/firecrawl.py` → `scrape_firecrawl()` | JS-heavy pages, structured extraction, Firecrawl-hosted rendering |
| `crawlbase` | `utils/crawlbase.py` → `crawlbase_fetch_url()` | Rendered fetch using Crawlbase JS token |
| `camoufox` | `utils/camoufox.py` → `camoufox_start_browser()` / `extract_text()` / `close()` | Bot-blocked or heavy anti-bot pages needing stealth browser |

The `generic_http` backend parses HTML with BeautifulSoup: extracts `og:*` / `twitter:*` meta tags, JSON-LD schemas, article/main content, geo meta tags (`place:location:*`, `geo.region`), and all inline text.

---

## ScraperRecoveryAgent — the AI-assisted sub-agent

`ScraperRecoveryAgent` is an LLM sub-agent that lives inside the scraper's process. It is **not** registered in the global agent registry, so it cannot be discovered or delegated to by the orchestrator. It is instantiated directly by `ScraperAgent` and used only for failure triage.

### Purpose

When a backend fails for a URL, the scraper calls `_run_recovery_agent(...)`. This sends a JSON payload to the recovery agent asking it to diagnose the failure and decide what to do next.

### Input payload

```json
{
  "url": "https://example.com/post/1",
  "normalized_url": "https://example.com/post/1",
  "platform": "web",
  "failed_backend": "generic_http",
  "error": "ConnectionError: ...",
  "remaining_backends": ["firecrawl", "crawlbase"]
}
```

### Output (RecoveryPlan)

```python
class RecoveryPlan(BaseModel):
    should_retry: bool            # try again?
    recommended_backend: str | None  # which backend to use next
    mark_terminal: bool           # treat as permanent failure?
    reason: str                   # short operational explanation
```

### Recovery rules (from the prompt)

- If the error strongly signals the URL is gone forever (404, 410, "not found"), mark terminal.
- If the failing backend is blocked or insufficient and another backend remains, recommend the best remaining backend.
- Prefer specialized or browser-backed backends when HTTP fetch fails due to rendering/blocking.
- Never invent a backend not listed in `remaining_backends`.

### Fallback behavior

If the recovery agent itself fails (LLM error, timeout), `_run_recovery_agent` falls back deterministically:

- If `remaining_backends` is non-empty: `should_retry=True`, `recommended_backend=remaining[0]`.
- If empty: `mark_terminal=True`.

### Demo mode

In demo mode, the recovery agent decides without an LLM:

- HTTP 404/410 or "not found" in error → terminal.
- Remaining backends available → retry with `remaining[0]`.
- No backends → terminal.

### Configuration

- Provider: `google` (same as scraper, injected from `getattr(self.llm, "_provider", "dummy")`).
- Model: `gemini-2.5-flash`.
- Prompt: `agents/scraper/prompts/recovery.txt`.
- No timeout override — inherits BaseAgent default.

---

## ScrapedContent — the document returned by a backend

```python
@dataclass
class ScrapedContent:
    fetch_backend: str        # which backend produced this
    normalized_url: str
    final_url: str            # URL after any redirects
    platform: str
    domain: str
    title: str
    description: str
    author: str | None
    published_at: str | None
    language: str | None
    site_name: str | None
    content_text: str         # cleaned main text
    excerpt: str              # first 400 chars
    raw_text: str             # full raw text (no HTML)
    raw_html: str | None      # original HTML (when available)
    markdown: str | None      # Markdown version (Firecrawl)
    http_status: int | None
    entity_type: str          # "document", "thread", "comment", etc.
    geo: dict
    engagement: dict          # likes, shares, comments, upvote_ratio, etc.
    authors: list[dict]       # all identified authors
    references: list[dict]    # canonical + related URLs
    provenance: dict          # which backend, source URL, fetch metadata
    content_items: list[dict] # structured sub-items (comments, entries, etc.)
    metadata: dict
    raw_payload: dict         # full raw API/HTTP response
```

---

## Document store — MongoDB persistence

`MongoDocumentStore` implements `BaseDocumentStore` ABC. The factory function `build_document_store()` returns the active implementation — this makes it replaceable. All scraper code calls `document_store.save_document(...)`, never MongoDB directly.

### MongoDB collections

#### `scraped_documents`

One document per unique normalized URL. Stable `document_id` derived from `doc_<sha256(normalized_url)[:24]>`. When the same URL is seen again (across topics or runs), the existing document is updated in place and new topic references are added.

Key fields:

| Field | Purpose |
| --- | --- |
| `document_id` | Stable URL-derived ID (cross-topic reuse key) |
| `schema_version` | `2` — allows future migrations |
| `normalized_url` + `normalized_url_hash` | Indexed for dedup lookups |
| `canonical_url` | Final URL after redirects |
| `platform`, `domain`, `entity_type` | Classification |
| `fetch_backend` | Which backend produced the content |
| `title`, `description`, `author`, `authors[]` | Identity |
| `published_at`, `language`, `site_name` | Temporal + locale |
| `geo` | `{latitude, longitude, region, placename, locale}` |
| `engagement` | Platform-specific metrics (score, likes, comments, etc.) |
| `references[]` | Canonical URL + all outbound/source references |
| `provenance` | Source name, discovered_link_id, backend used, fetch metadata |
| `content_text` | Main content (cleaned) |
| `excerpt` | First 400 chars of content_text |
| `raw_text` | Full raw text |
| `raw_html` | Original HTML (when available) |
| `markdown` | Markdown version (Firecrawl only) |
| `content_items[]` | Structured sub-items (posts, comments, feed entries) |
| `content_hash` | SHA-256 of `content_text` for change detection |
| `analysis_state` | `{cleaning: "not_started", sentiment: "not_started"}` — updated by future agents |
| `topic_refs` | Map of `topic_slug → topic_ref_object` for cross-topic attachment |
| `topics[]`, `topic_slugs[]` | Array addToSet for quick multi-topic filtering |
| `updated_at`, `last_scraped_at` | Timestamps |

#### `scrape_targets`

Per-URL scrape status and topic references. Separate from `scraped_documents` so the queue state and the content store don't conflict.

| Field | Purpose |
| --- | --- |
| `normalized_url` | Primary key (unique indexed) |
| `target_id` | Links to SQLite `scrape_targets.unique_id` |
| `topics[]`, `topic_slugs[]` | All topics that discovered this URL |
| `scrape_status` | `{state, attempts, last_attempt_at}` |
| `topic_refs` | Per-topic quality/relevance/status |

#### `scrape_runs`

One document per scraper run, mirroring the SQLite `scrape_runs` table in MongoDB.

### Indexes

All three collections have indexes for:

- `normalized_url` (unique) and `normalized_url_hash`
- `topic_slugs`, `platform`, `domain`
- `analysis_state.cleaning` and `analysis_state.sentiment` (for downstream queuing)
- `authors.name`, `references.url`, `content_items.item_id` (for search)
- `(topic_slugs, platform, published_at)` (for filtered dashboard queries)

---

## SQLite persistence (per-topic)

The scraper owns two tables in `data/scrapes/<topic-slug>.db`:

### `scrape_runs`

Run-level metadata: `run_id`, `status`, `config_json`, `stats_json`, `error`.

### `scrape_targets`

Per-URL queue state. One row per URL, mirroring `discovered_links` entries.

| Column | Purpose |
| --- | --- |
| `unique_id` | Same as `discovered_links.unique_id` (SHA-256 prefix) |
| `normalized_url` | Unique per row |
| `status` | `not_started` → `pending` → `completed` / `failed` |
| `attempts` | How many backend attempts have been made |
| `selected_backend` | Which backend last ran (or attempted) |
| `document_id` | Set on success — references MongoDB `scraped_documents.document_id` |
| `last_error` | Error from the last failed backend |
| `started_at`, `completed_at`, `last_scraped_at` | Timestamps |

Indexed on `(status, attempts, quality_score DESC, relevance_score DESC)` so `load_scrape_targets` gets the best pending URLs first.

---

## ScrapeRuntimeConfig and backend registry

`build_scrape_runtime_config()` (in `agents/services/scraper_runtime.py`) builds `ScrapeRuntimeConfig` from env vars.

### Centralized backend registry

`SCRAPE_BACKEND_REGISTRY` maps backend name → `ScrapeBackendSpec`:

```python
@dataclass
class ScrapeBackendSpec:
    name: str
    description: str
    env_key: str | None         # env flag for enable/disable
    default_enabled: bool
    required_config_keys: tuple  # API key checks (at least one must be set)
    requires_runtime_probe: bool # e.g. Camoufox must self-report availability
```

`resolve_enabled_scrape_backends()` resolves enabled backends in priority order:

1. `SCRAPER_ENABLED_BACKENDS` (comma-separated list, e.g., `generic_http,firecrawl`) — preferred.
2. Legacy per-backend flags (`SCRAPER_ENABLE_FIRECRAWL`, etc.) — honored for backward compatibility.

`backend_capability_snapshot()` probes each backend: is it enabled? configured (API key present)? available (runtime probe passed)? Returns a dict used for logging and stored in `ScrapeRuntimeConfig.backend_status`.

`available_registered_backends(runtime)` returns the final usable list. Platform-specific backends (`reddit_json`, etc.) bypass this — they are included in backend plans by `build_backend_plan()` regardless.

### ScrapeRuntimeConfig fields

| Field | Env var | Default |
| --- | --- | --- |
| `max_concurrency` | `SCRAPER_MAX_CONCURRENCY` | 6 |
| `source_timeout_seconds` | `SCRAPER_SOURCE_TIMEOUT_SECONDS` | 90 |
| `max_targets_per_run` | `SCRAPER_MAX_TARGETS_PER_RUN` | 250 |
| `max_retries_per_target` | `SCRAPER_MAX_RETRIES_PER_TARGET` | 3 |
| `allow_existing_reuse` | `SCRAPER_ALLOW_EXISTING_REUSE` | `True` |
| `reuse_existing_days` | `SCRAPER_REUSE_EXISTING_DAYS` | 7 |
| `enabled_backends` | `SCRAPER_ENABLED_BACKENDS` (or legacy) | `generic_http,firecrawl,crawlbase,camoufox` |
| `backend_status` | — (runtime computed) | `{}` initially |

---

## Checkpoint artifacts written

| `artifact_type` | When written | What it contains |
| --- | --- | --- |
| `scraper_backend_error` | On each backend failure | URL, failed backend, error text, recovery decision |
| `scraper_summary` | On success | Markdown summary with counts |
| `scraper_error` | On run failure | Exception message |

---

## LLM configuration

- **ScraperAgent**: provider `google`, model `gemini-2.5-flash`. Only used to initialize `ScraperRecoveryAgent` — the agent itself runs no LLM calls.
- **ScraperRecoveryAgent**: same provider/model. Called synchronously in `_run_recovery_agent`. Uses `with_structured_output(RecoveryPlan)`.
- Scraper timeout: `1800` seconds (30 min) — large because up to 250 URLs can be scraped per run.
- Max retries: `2`.

---

## Demo mode

`_demo_invoke(topic)` returns static stats immediately without touching SQLite or MongoDB:

```python
{
    "queued_targets": 42,
    "completed": 31,
    "reused": 7,
    "failed": 4,
    "backend_usage": {"reddit_json": 8, "generic_http": 14, "firecrawl": 6, "camoufox": 3},
}
```

The full pipeline still runs — demo data propagated from the planner and harvester phases sits in SQLite — but the scraper's demo output is synthetic. This is intentional: real scraping requires network access, so demo mode provides a realistic-looking output without any I/O.

---

## Integration points

| Path | Role |
| --- | --- |
| `agents/scraper/agent.py` | `ScraperAgent` — main agent class |
| `agents/scraper/models.py` | `ScrapeTarget`, `ScrapedContent`, `ScrapeRuntimeConfig`, `RecoveryPlan` |
| `agents/scraper/recovery.py` | `ScraperRecoveryAgent` — LLM recovery sub-agent |
| `agents/scraper/prompts/system.txt` | Scraper system prompt |
| `agents/scraper/prompts/recovery.txt` | Recovery sub-agent system prompt |
| `agents/services/scraper_store.py` | SQLite tables: `scrape_runs`, `scrape_targets`; run + target lifecycle functions |
| `agents/services/scraper_sources.py` | All backend implementations + `build_backend_plan()` + `classify_target_platform()` |
| `agents/services/scraper_runtime.py` | `SCRAPE_BACKEND_REGISTRY`, `resolve_enabled_scrape_backends()`, `build_scrape_runtime_config()` |
| `agents/services/document_store.py` | `BaseDocumentStore` ABC + `MongoDocumentStore` implementation + `build_document_store()` factory |
| `utils/mongodb.py` | MongoDB connection singleton |
| `utils/bluesky.py` | Bluesky public API adapter |
| `utils/youtube.py` | YouTube oEmbed adapter |
| `utils/hackernews.py` | Hacker News Firebase item API adapter |
| `utils/rss.py` | RSS/Atom feed parser |
| `utils/firecrawl.py` | Firecrawl scrape adapter |
| `utils/crawlbase.py` | Crawlbase rendered fetch adapter |
| `utils/camoufox.py` | Camoufox stealth browser adapter |

---

## What happens when this agent starts

1. Expects `discovered_links` table to exist in the topic SQLite DB (written by the harvester).
2. `bootstrap_scrape_targets` copies them to `scrape_targets` — harmless to run multiple times.
3. Expects MongoDB to be reachable. If MongoDB is unavailable, `build_document_store()` will raise at construction time. This is intentional — scraping without a document store would throw content away.
4. Platform-specific backends require no API keys. Generic backends require API keys as noted.
5. All tables and MongoDB collections are created/ensured on first use.

---

## Circular import prevention

Service modules (`scraper_store.py`, `scraper_sources.py`, `document_store.py`) use `TYPE_CHECKING` guards to import scraper models:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agents.scraper.models import ScrapedContent, ScrapeTarget
```

Functions that need to construct model objects do `from agents.scraper.models import ...` as a deferred local import at runtime. This breaks the `agents.services → agents.scraper.models → agents.scraper.agent → agents.services` cycle.

---

## What the downstream phases receive

Documents in MongoDB `scraped_documents` with `analysis_state.cleaning = "not_started"` are the input queue for the (not yet built) cleaner agent.

Documents with `analysis_state.sentiment = "not_started"` are the input queue for the (not yet built) sentiment agent.

The `content_items[]` array already normalizes platform-specific structures (Reddit comments, HN comment trees, feed entries) into a unified format so the cleaner does not need to know which backend fetched the content.

---

## Planned evolution

- Explicit resume: when restarted, scraper already picks up `not_started` and `failed` (not exceeded retries) targets from the queue. A dedicated `can_resume()` check based on run status and agent_status artifact would make this more explicit.
- Deeper Twitter/X and TikTok support — currently relies on Firecrawl/Camoufox rendered backends. Specialized API backends (Apify, Twitter API v2) could be added via the existing `build_backend_plan` dispatch switch.
- Content deduplication at the document level using `content_hash` — skip saving documents with identical text even for different URLs.
- Pass raw documents to the cleaner/sentiment stage without full re-read: expose a MongoDB cursor-based reader that streams `analysis_state.cleaning = "not_started"` documents.
