# Sentiment Analyzer Agent

> AI-powered end-to-end sentiment analysis pipeline: data collection → preprocessing → sentiment classification → interactive dashboard.

---

## ⚠️ Context Continuity Protocol — READ THIS FIRST

**This file is how you stay in sync.** Every AI chat session starts with zero context. When the previous AI finishes and the user starts a new chat, all that accumulated knowledge — what was built, what failed, what decisions were made, what's half-done — is **gone**. This file is the **only bridge** between sessions.

**Your responsibilities as an AI agent working on this project:**

1. **On session start**: Read this entire file. You now know everything the previous agent knew. Do not re-discover things already documented here. Do not ask questions already answered below.
2. **During work**: If you discover something non-obvious (a gotcha, a pattern, a shortcut, a decision rationale, where something lives, why something was built a certain way), **write it to this file** before your session ends.
3. **On session end**: Before the user closes the chat, update this file with:
   - Any architectural changes you made
   - Any new modules, files, or paths you created
   - Any gotchas or debugging insights you discovered
   - Any decisions made and **why**
   - Updated "Current State" if you changed what's built/in-progress
4. **Never assume the next agent will have your context.** They won't. Write it here or it's lost forever.

**The user should not have to re-explain the project to every new AI.** This file does that job. If a new agent reads this and still doesn't understand the project, this file has failed — fix it.

**Cross-reference**: `docs/VISION.md` is the canonical project vision (what we're building and why). This file (`AGENTS.md`) is the canonical operating manual (how to work on it, what's done, what to know). Read both.

---

## TL;DR

- **Purpose**: Collect social media data, run sentiment analysis (positive/neutral/negative), and surface insights via an interactive dashboard — primary use case is election sentiment monitoring.
- **Top 3 commands**: `uv run python -m server` · `cd Interface && bun dev` · `uv run python main.py -t "topic" --demo`
- **Owner**: Kshitiz Sharma ([@imxitiz](https://github.com/imxitiz))

---

## Quick Start

```bash
# 1. Clone & enter
git clone https://github.com/imxitiz/sentiment-analyzer-agent.git
cd sentiment-analyzer-agent

# 2. Create venv & install Python deps (requires uv)
uv venv && source .venv/bin/activate
uv sync

# 3. Set up environment
cp .env.example .env   # then fill in API keys
# Required: SERPER_API_KEY
# Optional: GOOGLE_API_KEY, OPENAI_API_KEY, OLLAMA_BASE_URL

# 4. Run the orchestrator (simple pipeline)
uv run python main.py --topic "electric vehicles" --provider gemini

# 4b. Run in demo mode (no API keys needed!)
uv run python main.py --topic "Nepal elections 2026" --demo

# 5. Start the backend API server (live mode with API keys; falls back to demo when keys are missing)
uv run python -m server
# API: http://localhost:8000  Docs: http://localhost:8000/api/docs

# 6. Start the frontend (Bun required)
cd Interface && bun install && bun dev
# Frontend: http://localhost:3000 (needs backend running on :8000)

# 7. Lint (Python)
uv run ruff check .

# 8. LSP (Python) - Pyrefly (A fast type checker and language server for Python with powerful IDE features too)
uv run pyrefly check

# 9. Lint (Interface)
cd Interface && bun run check
```

---

## Architecture

```arch
┌────────────────────────────────────────────────────────────────────┐
│                         main.py (CLI entry)                        │
│                   --demo / --provider / --topic                    │
├────────────────────────────────────────────────────────────────────┤
│                    agents/ (Multi-Agent Pipeline)                   │
│   ┌───────────────────────────────────────────────────────────┐    │
│   │  OrchestratorAgent (react mode — has tools)               │    │
│   │    ├─ delegate_to_planner → PlannerAgent (direct mode)    │    │
│   │    ├─ ask_human → Human-in-the-loop tool                  │    │
│   │    └─ (future: delegate_to_searcher, scraper, …)          │    │
│   └───────────────────────────────────────────────────────────┘    │
│    BaseAgent → _registry → tools/_registry                         │
│    Demo mode: provider="dummy" → static data, no LLM needed       │
├────────┬──────────────┬───────────────┬───────────────┬───────────┤
│ prompts│  BaseLLM     │  DataScraper  │   Logging     │   env.py  │
│ (.txt) │  (adapters)  │  (connectors) │  (structured) │ (config)  │
├────────┴──────────────┴───────────────┴───────────────┴───────────┤
│  LangChain / LangGraph            SQLite (data/scrapes/)          │
├───────────────────────────────────────────────────────────────────┤
│  External: Google Gemini · OpenAI · Ollama · Serper · Reddit/FB   │
└───────────────────────────────────────────────────────────────────┘

Pipeline flow:  Plan → Search → Scrape → Clean → Analyze → Summarize
                                                            ↓
                                              Interface (Bun + React)

┌───────────────────────────── Web Interface ────────────────────────┐
│  server/ (FastAPI on :8000)         Interface/ (Bun on :3000)     │
│  ├── REST sessions CRUD            ├── React 19 + TanStack Router │
│  ├── WebSocket event streaming     ├── TanStack Query (cache)     │
│  ├── Mock data generator           ├── Recharts (charts)          │
│  └── Pipeline runner (demo/live)   ├── shadcn/ui + Tailwind       │
│                                    └── WebSocket client (auto-    │
│                                        reconnect)                 │
└───────────────────────────────────────────────────────────────────┘
```

> **Full end-to-end pipeline details**: see `docs/VISION.md` Section 2 for the complete 6-phase pipeline with data flow diagrams, storage strategy, and multi-agent architecture.

---

## Key Paths

| Path | Purpose |
| --- | --- |
| `main.py` | CLI entry point — `--topic`, `--provider`, `--model`, `--demo` |
| `env.py` | `EnvConfig` singleton — audited, logged env var access |
| `agents/` | **Multi-agent pipeline** (orchestrator, planner, …) |
| `agents/base.py` | `BaseAgent` ABC — react/direct/demo modes, tool wrapping, prompt resolution, timeout/retry/circuit-breaker |
| `agents/_registry.py` | `@register_agent` decorator, `build_agent()`, `list_agents()` |
| `agents/services/` | Shared service layer for per-topic SQLite checkpoints |
| `agents/services/planner_checkpoint.py` | Topic DB init + append-only persistence (`topic_inputs`, `pipeline_artifacts`) |
| `agents/services/orchestrator_checkpoint.py` | Central orchestrator DB (`topic_runs`, `orchestrator_events`) + topic bootstrap |
| `agents/services/harvester_store.py` | Harvester SQLite schema, URL normalization, quality scoring, and async writer queue |
| `agents/services/harvester_sources.py` | Search providers and browser expansion runtime (Serper, SerpAPI, Firecrawl, Camoufox, Crawlbase) |
| `agents/tools/_registry.py` | `@agent_tool` decorator, tool catalog with categories |
| `agents/tools/human.py` | Human-in-the-loop tool (CLI input, swappable backend, web clarification bridge) |
| `agents/tools/browser.py` | Agent-facing Camoufox browser session tools (open/navigate/click/type/extract/evaluate/close) |
| `agents/tools/search.py` | Tool: `google_search_snippets` (Serper API top results for planner context) |
| `agents/tools/harvest.py` | Reusable harvest tools for Firecrawl search/browser and Crawlbase page fetch |
| `utils/serper.py` | Central Serper adapter utility (real API + demo fallback payload) |
| `utils/firecrawl.py` | Central Firecrawl REST adapter (search, scrape, browser sessions) |
| `utils/serpapi.py` | Lightweight SerpAPI search adapter |
| `utils/camoufox.py` | Flexible Camoufox integration: remote server, local Python API, or CLI wrapper |
| `utils/crawlbase.py` | Central Crawlbase adapter for rendered page fetches |
| `agents/orchestrator/` | Orchestrator agent — coordinates sub-agents via tool delegation |
| `agents/planner/` | Planner agent — generates `ResearchPlan` (keywords, hashtags, queries) |
| `agents/harvester/` | Harvester agent — builds `HarvestPlan`, fans out sources, and stores deduplicated links |
| `agents/<name>/prompts/` | Agent-local prompt templates (`system.txt`, etc.) |
| `BaseLLM/` | Unified LLM abstraction layer (Gemini, Ollama, OpenAI, Dummy) |
| `BaseLLM/adapter.py` | `BaseLLMAdapter` ABC — DRY base with sync/async generate |
| `BaseLLM/_registry.py` | Single source of truth for all model names & provider aliases |
| `BaseLLM/main.py` | `get_llm()` factory + `DummyAdapter` (zero-dependency) |
| `Logging/__init__.py` | Production structured logger (JSON files, ring buffer, ANSI) |
| `DataScraper/` | Data collection connectors (placeholder currently; connectors planned) |
| `prompts/` | Global prompt template manager + raw `.txt` templates |
| `prompts/raw_prompts/` | Shared prompts: `plan.txt`, `scrape.txt`, `clean.txt`, `summarize.txt` |
| `server/` | **FastAPI backend** — REST API + WebSocket + mock data + pipeline runner |
| `server/app.py` | FastAPI app factory (CORS, routes, health check) |
| `server/models.py` | All Pydantic models (Session, Events, Results) — TypeScript mirrors these |
| `server/routes/sessions.py` | Session CRUD + start analysis endpoints |
| `server/routes/export.py` | Export results as JSON / CSV / Markdown |
| `server/routes/compare.py` | Compare two analysis versions or sessions |
| `server/routes/ws.py` | WebSocket endpoint for real-time event streaming |
| `server/services/session_manager.py` | In-memory session store + subscriber pattern |
| `server/services/pipeline.py` | Pipeline runner bridge (demo + live modes) |
| `server/services/__init__.py` | Mock data generator (`generate_mock_result()`) |
| `Interface/` | **Frontend** — Bun + React + TanStack + Recharts + shadcn/ui |
| `docs/agents/` | Agent-by-agent architecture docs (orchestrator/planner and future agents) |
| `docs/FEATURES.md` | Detailed feature documentation (export, compare, versioning) |
| `data/scrapes/` | SQLite DBs per topic (gitignored) |
| `logs/` | Rotating log files (gitignored) |
| `docs/VISION.md` | **Canonical project vision** — full pipeline, architecture, what's built vs planned |

---

## Agent Knowledge Base

This section captures **non-obvious discoveries, gotchas, shortcuts, and accumulated insights** from working on this project. Every AI agent session should add to this section when they learn something that would save the next agent time. If you spent more than a few minutes figuring something out, write it here.

### Project Identity & Vision

- **What this IS**: A "Self-Driving Research Lab" for sentiment analysis. User provides a topic → system autonomously collects data → runs sentiment → shows results on a real-time dashboard.
- **Primary use case**: Election sentiment monitoring (e.g., "Nepal elections 2026"), but system is topic-agnostic.
- **Full pipeline**: Topic → Keywords → Link Harvest (SQLite) → Deep Scrape (MongoDB) → Clean → Sentiment (HuggingFace model) → Vector DB → Convex DB → Dashboard + RAG chat.
- **Read `docs/VISION.md`** for the complete end-to-end pipeline diagram and architecture. It's the canonical source of truth for *what* we're building. This file (`AGENTS.md`) is the canonical source for *how* to work on it.

### Critical Architecture Decisions (and WHY)

- **Sentiment analysis uses a dedicated HuggingFace model, NOT an LLM.** LLMs are too slow and expensive for per-post scoring at scale. The sentiment model runs locally and is purpose-built for classification. Never route sentiment through `BaseLLM`.
- **Sentiment is a continuous spectrum (0→1), not binary pos/neg.** Binary misses nuance. "slightly concerned" ≠ "furious". Always use continuous scores.
- **Different LLMs for different agents.** Orchestrator gets a powerful model (Gemini Pro, GPT-4o). Scraping/cleaning gets a cheap one (Gemini Flash, GPT-4o-mini). This is already supported by `BaseLLM` — each agent can call `get_llm()` with a different provider/model.
- **LLMs trigger work, code does the work.** The LLM decides *what* to scrape and *when*. The actual HTTP requests, file writes, and DB inserts are done by deterministic Python code, not LLM tool calls. Never let the LLM "decide" to save data — the code pipeline handles that.
- **Non-destructive versioning.** Refreshing a topic creates Version 2 alongside Version 1. Old data is never overwritten or deleted. Research needs historical comparison.
- **SQLite for links (fast, transient), MongoDB for raw data (unstructured, metadata-rich), Vector DB for embeddings (semantic search), Convex DB for real-time dashboard updates.**

### Codebase Patterns & Shortcuts

- **To test the entire pipeline end-to-end**: `uv run python main.py --demo -t "any topic"` — runs orchestrator → planner with static data, no API keys needed.
- **To test the entire BaseLLM chain**: `get_llm("dummy").generate("test")` → returns `[DUMMY-LLM] test`. No API keys needed.
- **The `python` command may not work** on some setups — use `python3` explicitly if `python` produces no output.
- **`BaseLLM/_registry.py`** is the single source of truth for all model names, providers, and aliases. If you need to add a model, start there.
- **`agents/_registry.py`** auto-registers agents by their `_name` via `@register_agent` decorator. Import the agent module → it's registered.
- **`agents/tools/_registry.py`** auto-registers tools via `@agent_tool(category="...")` decorator. Category-based discovery.
- **Agent execution modes**: `react` (has tools → LangGraph tool-calling loop), `direct` (no tools → single LLM call), `demo` (no LLM → static data).
- **Demo mode**: Set `provider="dummy"` or use `--demo` CLI flag. Each agent's `_demo_invoke()` returns realistic static data. The full pipeline runs — only the data is synthetic.
- **Prompt resolution order**: agent-local `prompts/` dir → global `prompts/raw_prompts/`. Agent prompts live alongside the agent code, global prompts are shared templates.
- **All prompt templates** use `str.format()` placeholders (e.g., `{topic}`). To add a new task, create a new `.txt` file in the appropriate `prompts/` dir.
- **The Interface** is a full-stack web app: React frontend (Bun, port 3000) + FastAPI backend (uvicorn, port 8000). Both must be running.
- **To start both**: Terminal 1: `uv run python -m server` · Terminal 2: `cd Interface && bun dev`
- **Frontend architecture**: TanStack Router (code-based, not file-based), TanStack Query (cache + polling), WebSocket client (auto-reconnect), Recharts for charts, shadcn/ui components.
- **Backend architecture**: REST API for session CRUD, WebSocket for real-time event streaming, mock data generator for demo mode, pipeline runner that bridges to the agent system.
- **Two UI modes**: Chat mode (real-time progress) → auto-switches to Dashboard mode (charts, filters, data table) on completion.
- **All TypeScript types** in `Interface/src/lib/types.ts` mirror Python Pydantic models in `server/models.py` 1:1. Keep them in sync.
- **Path alias**: `@/*` maps to `./src/*` in the Interface (configured in `tsconfig.json`). All imports use this.
- **Web demo/live bridge is intentionally boundary-honest**: the server currently exposes planning + harvesting only. Demo mode simulates those two phases, and live mode reads the real planner/harvester SQLite artifacts instead of fabricating scraping or sentiment output.
- **Web clarification is now resumable**: `ask_human()` can pause a live web session, emit a `clarification_needed` event/message, and resume the blocked agent run when the user replies through the chat UI.
- **Camoufox now has two roles**: one-shot harvesting helper (`camoufox_fetch_anchors`) and full stateful browser runtime (`agents/tools/browser.py`) with session lifecycle and Playwright-style interactions.
- **Logs** go to `logs/` (gitignored). If logs aren't appearing, check `LOG_FILE_ENABLED=true` in `.env`.
- **Data** goes to `data/scrapes/` (gitignored). Each topic gets its own SQLite file.
- **LangChain v1 API**: Use `create_agent` from `langchain.agents` (NOT `create_react_agent` from `langgraph.prebuilt` — that's deprecated). Pass `system_prompt=` (not `prompt=`).
- **All agents now enforce bounded execution by default** in `BaseAgent`: timeout (default 300s), one retry, and circuit breaker after 3 consecutive failures (10m cooldown).
- **Per-agent overrides are env-driven**: `AGENT_<AGENT_NAME>_TIMEOUT_SECONDS`, `AGENT_<AGENT_NAME>_MAX_RETRIES`, `AGENT_<AGENT_NAME>_CIRCUIT_BREAKER_THRESHOLD`, `AGENT_<AGENT_NAME>_CIRCUIT_BREAKER_COOLDOWN_SECONDS`.
- **Planner persistence is append-only and shared across demo/live**: every run creates/uses `data/scrapes/<topic>.db` and writes both user/topic inputs + planner artifacts, so crashes are debuggable and resumable.
- **Topic DB bootstrap is now orchestrator-owned**: when topic is received, orchestrator first writes to central `orchestrator.db` (`topic_runs`) and initializes topic DB before planner invocation.
- **Agent lifecycle status is checkpointed in topic DB**: `agent_status` table tracks `working/retrying/completed/failed`, retry count, last error, and timestamps for resume/debug.
- **Planner can do tool-based web grounding**: planner runs a tool-calling context pass via `google_search_snippets` (Serper) before producing the structured `ResearchPlan`.
- **Harvester persistence now uses a two-layer model**: `discovered_links` stores canonical deduplicated URLs, while `link_observations` stores every raw observation from every source. Deduplication happens in the async writer, not in source code.
- **New harvest sources available**: adapters for SerpAPI (search) and Camoufox (browser discovery) live under `utils/serpapi.py` and `utils/camoufox.py`. The Camoufox helper supports three modes:
  1. remote HTTP server (`CAMOUFOX_ENDPOINT`),
  2. local Python package (`pip install camoufox[geoip]`),
  3. CLI subprocess (will run ``python -m camoufox`` or use ``CAMOUFOX_CLI_PATH``).
  These sources are enabled with `HARVESTER_ENABLE_SERPAPI`/`_CAMOUFOX` and exposed as agent tools in `agents/tools/harvest.py`.
- **Harvester writes must go through `AsyncLinkWriter`**: collectors stay fully concurrent, but SQLite writes are serialized through one queue consumer to avoid cross-task write races and to centralize duplicate/quality decisions.
- **Browser discovery is provider-backed, not local-browser-coupled**: Firecrawl browser sessions are used for rendered search-page link discovery, and Crawlbase is used for seed-page expansion. This keeps browser tech replaceable.
- **External provider code must be centralized**: keep API-specific logic (Serper, future providers) in `utils/` adapter files and call them from tools/services. Avoid direct HTTP integration scattered across agents.

### Common Pitfalls to Avoid

- **Don't import `langchain_*` directly.** Always go through `BaseLLM`. This is a hard rule.
- **Don't use `os.getenv()`.** Always use `from env import config`. It logs access and masks secrets.
- **Don't use `print()` for operational output.** Use `from Logging import get_logger`.
- **Don't run `npm` or `yarn` in the Interface.** It's Bun-only. Use `bun install`, `bun dev`, and `bun run build`.
- **Don't write multi-line git commit messages with `-m`.** They can fail silently. Use single-line: `git commit -m "type(scope): summary"`
- **Don't hardcode model names.** They belong in `BaseLLM/_registry.py`.

### What's Built vs What's Not (save yourself the search)

| Done ✅ | Not Yet ❌ |
| --- | --- |
| BaseLLM adapters (Gemini, Ollama, OpenAI, Dummy) | HuggingFace sentiment model integration |
| Production structured logging | MongoDB integration |
| EnvConfig singleton | Vector DB (FAISS/Pinecone) |
| Prompt template manager (global + agent-local) | Convex DB / real-time layer |
| Serper web search | Data cleaning agent |
| SQLite link storage | RAG chat interface (placeholder only) |
| **Multi-agent framework** (BaseAgent, registries) | Browser-based scraping (Playwright) |
| **OrchestratorAgent** (react mode, sub-agent delegation) | Evaluation suite |
| **PlannerAgent** (structured output → ResearchPlan) | Searcher/Harvester agent |
| **HarvesterAgent** (structured output → `HarvestPlan`, async fan-out, queued SQLite writes) | Scraper agent |
| **Agent resilience runtime** (timeout + retry + circuit breaker in `BaseAgent`) | Scraper agent |
| **Planner checkpoint persistence** (topic SQLite DB with `topic_inputs` + `pipeline_artifacts`) | Summarizer agent |
| **Tool registry** (@agent_tool, categories) | Scraper agent |
| **Human-in-the-loop tool** (pluggable backend) | Summarizer agent |
| **Demo mode** (static data for planning + harvesting only, no LLM) | HuggingFace sentiment scoring in the web pipeline |
| **FastAPI backend** (REST + WebSocket + mock data) | |
| **React dashboard** (TanStack Router/Query, Recharts) | |
| **Chat UI** (messages, agent progress, adaptive input) | |
| **Dashboard UI** (stats, charts, filters, data table) | |
| **WebSocket streaming** (auto-reconnect, event replay) | |
| **Mock data generator** (150 posts, 5 platforms, deterministic) | |
| **Export reports** (JSON / CSV / Markdown download) | |
| **Version comparison** (structured diff, delta cards, narrative) | |
| **Live agent→server bridge for planning + harvesting** | |
| **Web clarification pause/resume flow** | |

---

## Core Modules & Responsibilities

### BaseLLM — Unified LLM Layer

Every LLM interaction goes through `BaseLLM`. Never import `langchain_*` directly.

```python
from BaseLLM import get_llm

# Factory (the only function you need)
llm = get_llm("google", model="gemini-2.5-flash")
llm.generate("Explain AI in one sentence.")      # sync
await llm.agenerate("Explain AI in one sentence.")  # async
llm.chat_model  # raw LangChain BaseChatModel for agents/chains
```

**Adapter pattern**: Subclasses set 3 class attrs + implement `_build_llm()`. Base class handles everything else (generate, agenerate, logging, timing, error handling).

```python
class MyAdapter(BaseLLMAdapter):
    _provider = "my_provider"
    _default_model = "my-model"
    _registry_models = ("my-model", "my-model-2")

    def _build_llm(self) -> None:
        self._llm = SomeLangChainChatModel(model=self._model, ...)
```

**Providers**: `google` (aliases: gemini, genai) · `ollama` · `openai` (aliases: chatgpt, gpt) · `dummy` (testing)

### Logging — Structured Production Logger

```python
from Logging import get_logger, context_logger

logger = get_logger("my_module")
logger.info("event", action="scrape", phase="HARVESTER", topic="elections")

# Context logger with pre-bound fields
log = context_logger("my_module", actor="scraper", session_id="abc-123")
log.info("started", action="fetch")
```

Features: JSON file output (rotating 10MB), ANSI color console, in-memory ring buffer (1000 entries), `subscribe()` for live streaming, custom `SUCCESS` log level.

### env.py — Centralized Config

```python
from env import config

config.GOOGLE_API_KEY   # reads + logs + caches on first access
config.require("SERPER_API_KEY")  # raises if missing
config.as_dict()        # all keys (secrets masked)
```

Never use `os.getenv()` directly. All access is logged and auditable.

### Prompts — Template Manager

```python
from prompts import get_prompt, list_prompts

prompt = get_prompt("plan", topic="electric vehicles")
list_prompts()  # → ["clean", "plan", "scrape", "summarize"]
```

Templates live in `prompts/raw_prompts/*.txt` using Python `str.format()` placeholders.

### DataScraper — Data Collection

```python
from DataScraper.main import scraper
from DataScraper.serper import search

results = search("electric vehicles")           # Serper web search
db_path = scraper("elections", "reddit")        # scrape → SQLite
```

Connectors: `serper.py` (web search via Serper API), `reddit.py`, `facebook.py`. All data stored in `data/scrapes/<topic>.db`.

### Agents — Multi-Agent Pipeline

The `agents/` package is a modular, extensible multi-agent framework. Each agent inherits from `BaseAgent`, registers itself via `@register_agent`, and can operate in three modes: **react** (tool-calling loop), **direct** (single LLM call), or **demo** (static data).

```python
from agents import OrchestratorAgent, PlannerAgent, build_agent

# Build manually
orchestrator = OrchestratorAgent(llm_provider="gemini")
result = orchestrator.invoke("Nepal elections 2026")

# Build from registry
agent = build_agent("orchestrator", llm_provider="openai")

# Demo mode (no LLM needed)
demo = OrchestratorAgent(llm_provider="dummy")
result = demo.invoke("any topic")  # static data, full pipeline
```

**OrchestratorAgent** (react mode): Coordinates the full pipeline. Sub-agents are auto-wrapped as tools so the LLM decides when to delegate. Default sub-agents: `[PlannerAgent]`.

**PlannerAgent** (direct mode): Generates a structured `ResearchPlan` (Pydantic model) with keywords, hashtags, platform strategies, and search queries. Uses `with_structured_output()` for JSON-structured responses.

**Adding a new agent**:

1. Create `agents/<name>/agent.py` — set `_name`, `_description`, override `_register_tools()` (for react mode) or `invoke()` (for direct mode)
2. Create `agents/<name>/prompts/system.txt` — agent's system prompt
3. Override `_demo_invoke()` for demo mode with realistic static data
4. Import in `agents/__init__.py` to trigger `@register_agent`

**Adding a new tool**:

```python
from agents.tools import agent_tool

@agent_tool(category="search")
def web_search(query: str) -> str:
    """Search the web for information."""
    return results
```

---

## Message / API Protocols

### Python CLI

```bash
python main.py --topic "electric vehicles" --provider gemini
python main.py -t "nepal elections" -p openai -m gpt-4o
python main.py -t "Tesla stock" --demo  # no API keys needed
```

### Interface API (Bun server, port 3000)

```routes
GET  /api/hello          → { message, method }
GET  /api/hello/:name    → { message: "Hello, <name>!" }
```

### Backend API (FastAPI, port 8000)

```routes
GET    /api/health                    → { status, service }
GET    /api/sessions                  → { sessions: Session[] }
POST   /api/sessions                  → { session: Session }
       body: { topic?, llm_provider?, llm_model? }
GET    /api/sessions/{id}             → { session: Session }
DELETE /api/sessions/{id}             → 204 No Content
POST   /api/sessions/{id}/start       → { session: Session }
       body: { topic, llm_provider?, llm_model? }
POST   /api/sessions/{id}/messages    → { session: Session }
       body: { content }
GET    /api/sessions/{id}/export      → StreamingResponse (file download)
       query: format={json|csv|md}, version?={n}
POST   /api/compare                   → { comparison: ComparisonResult }
       body: { base: {session_id, version?}, target: {session_id, version?} }
WS     /ws/{session_id}               → AgentEvent stream (JSON)
```

### LangGraph State Shape

```python
class State(TypedDict):
    topic: str
    plan: list[str]
    db_path: str
    scrapers: dict
    summary: str
```

---

## Code Style & Conventions

- **Python**: 3.13+, type hints everywhere, `from __future__ import annotations`
- **Naming**: `snake_case` for files/functions/variables, `PascalCase` for classes
- **Imports**: absolute imports from project root (`from BaseLLM import get_llm`, not relative)
- **Max function length**: ~50 lines — refactor when longer
- **Linter**: Ruff (`select = ["E", "F"]`, ignores `F401` unused imports and `E501` line length)
- **Docstrings**: Google-style, required for all public functions/classes
- **Error handling**: wrap in meaningful `RuntimeError` with original exception chained (`raise ... from exc`)
- **Logging**: always use `from Logging import get_logger` — never `print()` for operational output
- **Env vars**: always use `from env import config` — never `os.getenv()` directly
- **LLM access**: always use `from BaseLLM import get_llm` — never import `langchain_*` providers directly
- **Interface (TS)**: Bun-first, strict TypeScript, Biome for lint/format, Tailwind CSS
- **Adapter pattern**: new external services → implement an adapter behind an ABC

---

## Configuration & Feature Flags

### Environment Variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GOOGLE_API_KEY` | For Gemini | — | Google Gemini API key |
| `OPENAI_API_KEY` | For OpenAI | — | OpenAI/ChatGPT API key |
| `SERPER_API_KEY` | For search | — | Serper web search API key |
| `FIRECRAWL_API_KEY` | No | — | Firecrawl API key for search, scrape, and remote browser sessions |
| `CRAWLBASE_TOKEN` | No | — | Crawlbase standard crawling token |
| `CRAWLBASE_JS_TOKEN` | No | — | Crawlbase JavaScript crawling token for rendered pages |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `AGENT_TIMEOUT_SECONDS` | No | `300` | Global default timeout per agent invocation (seconds) |
| `AGENT_MAX_RETRIES` | No | `1` | Global retries after initial failure (`1` = one retry) |
| `AGENT_CIRCUIT_BREAKER_THRESHOLD` | No | `3` | Open breaker after N consecutive failures |
| `AGENT_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | No | `600` | Breaker cooldown before allowing requests again |
| `AGENT_<AGENT_NAME>_TIMEOUT_SECONDS` | No | — | Per-agent timeout override (e.g., `AGENT_PLANNER_TIMEOUT_SECONDS`) |
| `AGENT_<AGENT_NAME>_MAX_RETRIES` | No | — | Per-agent retries override |
| `AGENT_<AGENT_NAME>_CIRCUIT_BREAKER_THRESHOLD` | No | — | Per-agent failure threshold override |
| `AGENT_<AGENT_NAME>_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | No | — | Per-agent breaker cooldown override |
| `HARVESTER_MAX_LINKS` | No | `1000` | Upper bound of accepted canonical links stored for a topic |
| `HARVESTER_MAX_CONCURRENCY` | No | `8` | Maximum concurrent harvesting tasks across sources |
| `HARVESTER_SOURCE_TIMEOUT_SECONDS` | No | `120` | Per-source timeout for query execution and expansion |
| `HARVESTER_WRITER_BATCH_SIZE` | No | `50` | SQLite writer queue flush size |
| `HARVESTER_QUEUE_SIZE` | No | `5000` | In-memory queue capacity before producers backpressure |
| `HARVESTER_PER_QUERY_LIMIT` | No | `25` | Target raw results per query per source |
| `HARVESTER_MIN_QUALITY_SCORE` | No | `0.35` | Minimum score before a canonical link is accepted |
| `HARVESTER_EXPANSION_SEED_LIMIT` | No | `12` | Maximum seed URLs expanded after initial search collection |
| `HARVESTER_EXPANSION_PER_SEED_LIMIT` | No | `25` | Maximum outbound links collected from each expanded seed |
| `HARVESTER_ENABLE_SERPER` | No | `true` | Enable Serper query collection |
| `HARVESTER_ENABLE_FIRECRAWL` | No | `true` | Enable Firecrawl search collection |
| `HARVESTER_ENABLE_BROWSER_DISCOVERY` | No | `true` | Enable Firecrawl remote-browser discovery on rendered search pages |
| `HARVESTER_ENABLE_CRAWLBASE` | No | `true` | Enable Crawlbase page expansion from high-quality seed URLs |
| `HARVESTER_ENABLE_SERPAPI` | No | `false` | Enable SerpAPI search collection |
| `HARVESTER_ENABLE_CAMOUFOX` | No | `false` | Enable Camoufox browser discovery (requires either a server, the Python package, or CLI) |
| `CAMOUFOX_ENDPOINT` | No | — | URL of a running Camoufox HTTP server; if unset local Python/CLI mode is used. |
| `CAMOUFOX_CLI_PATH` | No | — | Optional explicit path to the `camoufox` CLI binary (e.g. `/usr/bin/python3 -m camoufox`). |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_DIR` | No | `logs` | Log output directory |
| `LOG_FILE_ENABLED` | No | `true` | Enable/disable file logging |
| `LOG_MAX_BYTES` | No | `10485760` | Max log file size before rotation |
| `LOG_BACKUP_COUNT` | No | `5` | Number of rotated log files to keep |
| `LOG_BUFFER_SIZE` | No | `1000` | In-memory ring buffer size |
| `SERVER_HOST` | No | `0.0.0.0` | FastAPI server bind host |
| `SERVER_PORT` | No | `8000` | FastAPI server bind port |
| `SERVER_DEBUG` | No | `true` | Enable uvicorn auto-reload |
| `DEFAULT_LLM_PROVIDER` | No | `dummy` | Default provider for new web sessions |

Per-agent override pattern (optional):

- `AGENT_PLANNER_TIMEOUT_SECONDS=120`
- `AGENT_ORCHESTRATOR_TIMEOUT_SECONDS=420`
- `AGENT_PLANNER_MAX_RETRIES=2`

### Config Files

| File | Purpose |
| --- | --- |
| `.env` | Local secrets (gitignored) |
| `pyproject.toml` | Python project config, dependencies, Ruff settings |
| `Interface/biome.jsonc` | Biome (TS linter/formatter) config |
| `Interface/bunfig.toml` | Bun configuration |
| `Interface/tsconfig.json` | TypeScript compiler options |
| `Interface/components.json` | shadcn/ui component config |

---

## Testing Strategy

- **Unit tests**: focus on Service layer logic (prompt formatting, data cleaning, adapter instantiation)
- **Smoke tests**: verify all imports and adapter creation work (`python -c 'from BaseLLM import get_llm; get_llm("dummy")'`)
- **Integration tests**: test scraper → SQLite pipeline with mock data
- **Interface**: `cd Interface && bun run build`
- **Python lint**: `uv run ruff check .`

### 5 Critical Test Scenarios

1. `get_llm("dummy").generate("test")` returns `[DUMMY-LLM] test` — validates entire BaseLLM chain
2. All three adapters instantiate without crash: `GeminiAdapter()`, `OllamaAdapter()`, `OpenAIAdapter()`
3. `config.require("NONEXISTENT_KEY")` raises `EnvironmentError`
4. `get_prompt("plan", topic="test")` returns formatted prompt text (not `[missing-prompt:...]`)
5. `prepare_db_for_topic("test")` creates SQLite DB at `data/scrapes/test.db`
6. `uv run python main.py --demo -t "test"` runs full pipeline with static data (exit 0)
7. `OrchestratorAgent(llm_provider="dummy").invoke("test")` returns structured output with planner data
8. `list_agents()` returns `["harvester", "orchestrator", "planner"]` — all agents registered
9. `HarvesterAgent(llm_provider="dummy").invoke("test")` writes canonical links plus observations into `data/scrapes/test.db`
10. `run_analysis_live(session_id, topic, provider="gemini")` executes the real orchestrator/planner/harvester flow (requires provider + at least one harvest source) and reports harvested-link stats without fabricating sentiment results
11. `curl http://localhost:8000/api/health` returns `{"status":"ok"}` — backend server smoke test
12. Create session → start analysis → check WebSocket events stream correctly, including clarification pause/resume when `ask_human()` is invoked
13. `cd Interface && bun build src/frontend.tsx --outdir=dist` compiles 608 modules without errors
14. `from utils.camoufox import camoufox_fetch_anchors` should raise a ``RuntimeError`` when no endpoint, package, or CLI is available (covered by tests/test_camoufox.py).

---

## Troubleshooting — Top 8 Problems & Fixes

| Problem | Fix |
| --- | --- |
| `ModuleNotFoundError: langchain_*` | `uv sync` or `uv pip install langchain-google-genai langchain-ollama langchain-openai` |
| Gemini adapter fails at init | Set `GOOGLE_API_KEY` in `.env` |
| OpenAI adapter fails at init | Set `OPENAI_API_KEY` in `.env` |
| Ollama connection refused | Start Ollama: `ollama serve` and pull a model: `ollama pull llama3.2` |
| `ImportError: BaseLLM` | Run from project root, ensure `.venv` is activated |
| Interface won't start | `cd Interface && bun install && bun dev` — requires Bun runtime |
| Logs not writing to file | Check `LOG_FILE_ENABLED=true` and `LOG_DIR=logs` in `.env` |
| Serper search returns empty | Verify `SERPER_API_KEY` is set and valid |
| Backend CORS errors in browser console | Backend CORS allows `localhost:3000` — make sure frontend runs on port 3000 |
| WebSocket won't connect | Ensure backend is running on port 8000, check `ws://localhost:8000/ws/{id}` |
| Recharts `Formatter` type error | Don't annotate formatter params — use `(value) => Number(value)` not `(value: number)` |
| Frontend `Cannot find module` in IDE | TS language server lag — run `bun build` to verify; if build succeeds, ignore |

---

## Adding New Features — Step-by-Step

1. **Plan**: identify which layer the change belongs to (BaseLLM / DataScraper / agents / Interface / prompts)
2. **Add config**: any new env vars → add to `env.py` `_KEYS` dict + this AGENTS.md config table
3. **Implement**: follow adapter pattern for external integrations; keep functions ≤50 lines
4. **Add logging**: use `context_logger()` with `actor`, `phase`, `action` fields
5. **Add prompts**: new LLM tasks → create `prompts/raw_prompts/<name>.txt`
6. **Test**: write smoke test, verify with `get_llm("dummy")` for LLM-dependent flows
7. **Update AGENTS.md**: if you changed architecture, commands, paths, or config

### Adding a New LLM Provider

1. Add model list + default to `BaseLLM/_registry.py`
2. Add provider key + aliases to `_PROVIDER_ALIASES` and `PROVIDERS` dicts
3. Create `BaseLLM/<provider>_adapter.py` — set 3 class attrs + implement `_build_llm()`
4. Add factory branch in `BaseLLM/main.py` `get_llm()`
5. Export from `BaseLLM/__init__.py`
6. Add convenience helper `get_<provider>_llm()` in `BaseLLM/main.py`

### Adding a New Data Scraper

1. Create `DataScraper/<platform>.py` with a `<platform>_scraper(topic, db_path=None) -> str` function
2. Register in `DataScraper/main.py` `scraper()` dispatcher
3. Add `site:<platform>.com` pattern to Serper search if needed
4. Write data into SQLite via `sqlite_store.insert_post()`

---

## Maintenance Guidelines

Update these when changing:

| What changed | Update where |
| --- | --- |
| Python dependency | `pyproject.toml` → `uv sync` |
| New env variable | `env.py` `_KEYS` dict + AGENTS.md config table |
| Build/run commands | AGENTS.md Quick Start + TL;DR |
| New module/folder | AGENTS.md Key Paths table |
| LLM provider added | `_registry.py` + adapter file + `main.py` factory + `__init__.py` exports |
| Prompt template added | `prompts/raw_prompts/<name>.txt` |
| Interface dependency | `Interface/package.json` → `bun install` |
| Architecture change | AGENTS.md Architecture diagram |

---

## Self-Update Policy

**This is a living document and the ONLY bridge between AI sessions.** Treat it accordingly.

### When to Update AGENTS.md

- **Always update at session end** if you made any changes to the codebase. The next AI session starts from zero — if you don't write it here, it's lost.
- Update for: architecture changes, new modules/files/paths, config changes, build/run command changes, new gotchas or debugging insights, tech decisions and rationale, anything you spent time figuring out.
- Add discoveries to the **Agent Knowledge Base** section — that's specifically for "things I learned so the next agent doesn't have to."
- If you changed what's built or in-progress, update the **"What's Built vs What's Not"** table in the Agent Knowledge Base.

### When NOT to Update

- Tiny bug fixes that don't change how the project works or is structured.
- Cosmetic refactors that don't change any public interface.
- Don't add changelog entries or timestamps — this isn't a changelog.

### How to Update

- **Merge into existing content** — don't duplicate or replace sections. If a section covers your topic, add to it.
- **Be concrete** — "Fixed the adapter" is useless. "OpenAI adapter needs `api_key` and `base_url` passed to `__init__`, not `_build_llm()`" is useful.
- **Keep it scannable** — bullet points, tables, code snippets. No essays.
- This file is sent directly to every new AI agent as its first context. It must be **clear, accurate, comprehensive, and current**.

### Cross-References

- `docs/VISION.md` — **what** we're building (full pipeline, architecture, design decisions). Read this for project understanding.
- `AGENTS.md` (this file) — **how** to work on it (code patterns, conventions, gotchas, current state). Read this for operational context.
- When docs contradict each other, `docs/VISION.md` wins for vision, `AGENTS.md` wins for code conventions.

---

## SWE Best Practices

<!-- !!BEST SWE PRACTICES FOR AI TO FOLLOW WHEN WORKING ON ANY PROJECT!! -->

### Model Context Protocol (MCP)

As an AI coding agent, you may have access to external tools via the Model Context Protocol (MCP). Use external tools only when they directly improve accuracy, verification, or understanding of a task — prioritizing efficiency, safety, and relevance. User instructions take precedence.

### Code Style

- Favor strict, type-safe code — typed Python (`from __future__ import annotations`), TS `strict` mode.
- Use functional patterns (pure functions, immutability) where appropriate.
- Atomic modules: limit functions/modules to ~50 lines. Refactor when longer.

### Identity & Mantra

You are an industrial-grade Software Architect & Systems Engineer. Code must be production-quality, maintainable, and scalable.

**Mantra**: "Change ONCE — reflect EVERYWHERE."

### Architectural Standards (Layered Law)

Enforce a layered architecture with at least two abstraction layers between major components:

1. **Presentation / Trigger** (CLI `main.py`, Interface) — dumb wrappers.
2. **Controller / Orchestrator** (`agents/`) — validate & route.
3. **Service Layer** (BaseLLM adapters, DataScraper, prompts) — single source of truth for rules/transactions.
4. **Repository / Adapter** (SQLite store, external API calls) — I/O, DB, API calls.
5. **Infrastructure / Config** (`env.py`, `Logging/`) — env and connection settings.

#### Dependency Rule

- Inner layers must not depend on outer layers. Use dependency injection; do not instantiate externals inside services.

### Core Development Rules

- Centralize constants/config in `env.py` and `BaseLLM/_registry.py`.
- No hardcoded values (strings, URLs, timeouts).
- Wrap common patterns (retry, logging, try/catch) in utilities.

### Performance & Resilience

- Async-first I/O (`agenerate()`, `ainvoke()`).
- Timeouts (default ≤ 5s), retries with exponential backoff, circuit-breakers for critical external calls.
- Null-safety: guard inputs aggressively.

### Customizability & Feature Flags

- Assume tomorrow everything changes. Put changes behind feature flags.
- Use adapter pattern for external systems (already in place for LLMs).

### Folder Structure (Feature-based)

- Organize by feature. Each feature folder must export via an `__init__.py` barrel file.

### Tooling Standards

- **Python**: UV package manager, Ruff linter.
- **Interface**: Bun (not npm/yarn), Biome linter, Tailwind CSS.
- TypeScript strict mode for the Interface.

### Testing

- Focus tests on Service Layer. Use TDD for critical logic.
- Tests must be fast and deterministic (mock external IO).

### Mandatory Checklist (before any commit)

- [ ] Everything configurable? (no hardcoding)
- [ ] ≥2 abstraction layers between producer and consumer
- [ ] Dependencies injected
- [ ] External calls have timeouts & retries
- [ ] Business logic isolated in Service layer
- [ ] Changing a feature should touch ≤3 files (architecture permitting)
- [ ] Run validation before handoff: lint + errors/warnings check (`ruff`, `pyrefly`, `get_errors`, and relevant smoke run)
- [ ] If a discovery is reusable cross-session, write it into `AGENTS.md` before ending

### Agent Handoff Rule (STRICT)

- Never end a coding session without checking for errors/warnings in changed files.
- Minimum required before handoff: run targeted lint/test command(s) and run editor error check.
- When adding/fixing architecture, explicitly decide: "session-local detail" vs "cross-session rule"; if cross-session, update `AGENTS.md` in the same task.

### Ultimate Rule

If a change requires many manual edits, refactor until change is localized.

---

## Editor & IDE Rules

- Do not modify `.editorconfig`, `.vscode/*`, `.idea/*`, or other IDE workspace settings except when absolutely necessary. Editor files are personal and noisy — changes must be proposed in PR with justification and marked OPTIONAL.
- If format/lint rules must change, prefer adding or updating a centralized formatter config (Ruff `pyproject.toml`, Biome `biome.jsonc`) and a `pre-commit` hook rather than changing individual devs' IDE settings.
- Agents should respect repo formatter settings. If running formatters, do so via CLI commands (`uv run ruff format .`, `cd Interface && bun run fix`), not by pushing IDE-specific settings.
- If you must change editor settings, add a clear PR section titled "Editor settings change — rationale & rollback" and make the change opt-in.

---

## Commit & PR Rules

- **Commit message format**: `<type>(<scope>): <short summary>`
  - Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`
  - Scopes: `basellm`, `logging`, `env`, `scraper`, `agents`, `interface`, `server`, `prompts`
  - Example: `feat(basellm): add Anthropic adapter`
- **AGENTS.md edits**: `AGENTS.md: <short summary>`
- **PR title**: `docs(agents): update AGENTS.md — <short summary>`
- **PR body must include**:
  - Brief justification (1–3 lines)
  - Quality checklist results
  - Key commands run & test outputs
- PRs should be small, focused, and reversible.

---

## How to Continue — Next Steps

Prioritized roadmap. Each item is a meaningful chunk of work (1-2 sessions).

1. ~~**Build multi-agent LangGraph pipeline**~~ ✅ DONE
   - BaseAgent ABC, agent registry, tool registry, orchestrator, planner
   - Demo mode with static data (no LLM needed)
   - `uv run python main.py --demo -t "any topic"` works end-to-end

2. ~~**Build Searcher/Harvester agent**~~ ✅ DONE
   - `HarvesterAgent` builds a `HarvestPlan` from planner artifacts and runtime config
   - Search fan-out supports Serper plus Firecrawl search, with optional Firecrawl browser discovery
   - `AsyncLinkWriter` serializes SQLite writes and stores both canonical links and raw observations
   - Crawlbase expansion follows high-quality seed URLs for additional link discovery

3. **Add HuggingFace sentiment model**
   - NOT an LLM — dedicated classification model (e.g., `distilroberta-base` fine-tuned for sentiment)
   - Continuous score output (0→1), not binary
   - Create `SentimentAnalyzer/` module with adapter pattern like BaseLLM
   - Must run locally, fast inference, no API costs

4. **Implement data cleaning pipeline**
   - Deduplication, spam filtering, text normalization
   - Can use cheap LLM for relevance filtering
   - Input: raw scraped data → Output: cleaned data ready for sentiment

5. **Add MongoDB for raw scraped data**
   - Replace or augment SQLite for storing actual post content
   - SQLite stays for link discovery queue only
   - MongoDB stores unstructured content with max metadata

6. **Add Vector DB (FAISS/Pinecone) for embeddings**
   - Embed cleaned text for semantic search
   - Powers the RAG chat interface later

7. ~~**Build full-stack web interface (FastAPI + React)**~~ ✅ DONE
   - FastAPI backend: REST sessions CRUD, WebSocket event streaming, mock data generator, pipeline runner
   - React frontend: TanStack Router/Query, Recharts charts, shadcn/ui, chat → dashboard adaptive UI
   - Demo mode works end-to-end: `uv run python -m server` + `cd Interface && bun dev`
   - See `server/README.md` and `Interface/README.md` for full docs

8. **Enhance dashboard visualizations**
   - Sentiment spectrum (bell curve), word cloud interactivity, geographic view
   - See `docs/VISION.md` Section 7 "Dashboard Vision" for the 8 target widgets
   - Consider Convex DB for real-time reactive updates

9. **Add more scrapers** (Twitter/X, TikTok, news sites, browser-based via Playwright)

10. **Build RAG chat interface** — query collected data conversationally

11. **Implement evaluation suite** (accuracy, precision, recall for sentiment model)

12. **Deploy with monitoring** and circuit breakers

---

*This file is the bridge between AI sessions. Update it when you change the project. The next AI starts from zero — what you don't write here is lost forever and other Agent again have to search for that same info.*
