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
- **Top 3 commands**: `uv run python main.py -t "topic"` · `cd Interface && bun dev` · `uv sync`
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

# 5. Start the frontend (Bun required)
cd Interface && bun install && bun dev

# 6. Lint (Python)
uv run ruff check .

# 7. Lint (Interface)
cd Interface && bun run check
```

---

## Architecture

```arch
┌────────────────────────────────────────────────────────────────────┐
│                         main.py (CLI entry)                        │
│                    OrchestratorAgent / LangGraph                   │
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
```

> **Full end-to-end pipeline details**: see `docs/VISION.md` Section 2 for the complete 6-phase pipeline with data flow diagrams, storage strategy, and multi-agent architecture.

---

## Key Paths

| Path | Purpose |
| --- | --- |
| `main.py` | CLI entry point — runs orchestrator pipeline |
| `env.py` | `EnvConfig` singleton — audited, logged env var access |
| `BaseLLM/` | Unified LLM abstraction layer (Gemini, Ollama, OpenAI) |
| `BaseLLM/adapter.py` | `BaseLLMAdapter` ABC — DRY base with sync/async generate |
| `BaseLLM/_registry.py` | Single source of truth for all model names & provider aliases |
| `BaseLLM/main.py` | `get_llm()` factory — the only function agents need |
| `Logging/__init__.py` | Production structured logger (JSON files, ring buffer, ANSI) |
| `DataScraper/` | Data collection connectors (Serper, Reddit, Facebook) |
| `DataScraper/sqlite_store.py` | SQLite helpers for scraped data persistence |
| `prompts/` | Prompt template manager + raw `.txt` templates |
| `prompts/raw_prompts/` | Prompt files: `plan.txt`, `scrape.txt`, `clean.txt`, `summarize.txt` |
| `agents.old/` | Orchestrator agent + LangGraph workflow (being rebuilt) |
| `Interface/` | Frontend — Bun + React + Tailwind dashboard (in progress) |
| `data/scrapes/` | SQLite DBs per topic (gitignored) |
| `logs/` | Rotating log files (gitignored) |
| `docs/` | Design docs, ideas, project specs |
| `docs/VISION.md` | **Canonical project vision** — full pipeline, architecture, data strategy, what's built vs planned |
| `docs/IDEA.md`, etc. | Brainstorming artifacts — reference only, may be outdated |

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

- **To test the entire BaseLLM chain**: `get_llm("dummy").generate("test")` → returns `[DUMMY-LLM] test`. No API keys needed.
- **The `python` command may not work** on some setups — use `python3` explicitly if `python` produces no output.
- **`BaseLLM/_registry.py`** is the single source of truth for all model names, providers, and aliases. If you need to add a model, start there.
- **`agents.old/`** is the OLD orchestrator code. It works but is being replaced. The new multi-agent system will live in `agents/` (not yet created).
- **All prompt templates** use `str.format()` placeholders (e.g., `{topic}`). They live in `prompts/raw_prompts/*.txt`. To add a new task, create a new `.txt` file there.
- **The Interface** is a Bun-served React app. `cd Interface && bun dev` starts it on port 3000. It has basic API routes but no dashboard yet.
- **Logs** go to `logs/` (gitignored). If logs aren't appearing, check `LOG_FILE_ENABLED=true` in `.env`.
- **Data** goes to `data/scrapes/` (gitignored). Each topic gets its own SQLite file.

### Common Pitfalls to Avoid

- **Don't import `langchain_*` directly.** Always go through `BaseLLM`. This is a hard rule.
- **Don't use `os.getenv()`.** Always use `from env import config`. It logs access and masks secrets.
- **Don't use `print()` for operational output.** Use `from Logging import get_logger`.
- **Don't run `npm` or `yarn` in the Interface.** It's Bun-only. `bun install`, `bun dev`, `bun run check`.
- **Don't write multi-line git commit messages with `-m`.** They can fail silently. Use single-line: `git commit -m "type(scope): summary"`
- **Don't hardcode model names.** They belong in `BaseLLM/_registry.py`.

### What's Built vs What's Not (save yourself the search)

| Done ✅ | Not Yet ❌ |
| --- | --- |
| BaseLLM adapters (Gemini, Ollama, OpenAI, Dummy) | Multi-agent LangGraph pipeline |
| Production structured logging | HuggingFace sentiment model integration |
| EnvConfig singleton | MongoDB integration |
| Prompt template manager | Vector DB (FAISS/Pinecone) |
| Serper web search | Convex DB / real-time layer |
| SQLite link storage | Data cleaning agent |
| Basic Interface scaffold | Dashboard visualizations |
| LangGraph scaffold (agents.old/) | RAG chat interface |
| | Browser-based scraping (Playwright) |
| | Evaluation suite |

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

### Agents — Orchestration (in progress)

```python
from agents.orchestrator_agent import OrchestratorAgent

agent = OrchestratorAgent(llm_provider="gemini")
result = agent.run("elections")  # plan → search → scrape → summarize
```

LangGraph workflow in `agents.old/langgraph_orchestrator.py`. Being refactored into a proper multi-agent system.

---

## Message / API Protocols

### Python CLI

```bash
python main.py --topic "electric vehicles" --provider gemini --workflow simple
python main.py -t "nepal elections" -p openai -w langgraph
```

### Interface API (Bun server, port 3000)

```routes
GET  /api/hello          → { message, method }
POST /api/chat           → { reply, received, timestamp }
     body: { "message": "..." }
GET  /api/hello/:name    → { message: "Hello, <name>!" }
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
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_DIR` | No | `logs` | Log output directory |
| `LOG_FILE_ENABLED` | No | `true` | Enable/disable file logging |
| `LOG_MAX_BYTES` | No | `10485760` | Max log file size before rotation |
| `LOG_BACKUP_COUNT` | No | `5` | Number of rotated log files to keep |
| `LOG_BUFFER_SIZE` | No | `1000` | In-memory ring buffer size |

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
- **Interface**: `cd Interface && bun test`
- **Python lint**: `uv run ruff check .`

### 5 Critical Test Scenarios

1. `get_llm("dummy").generate("test")` returns `[DUMMY-LLM] test` — validates entire BaseLLM chain
2. All three adapters instantiate without crash: `GeminiAdapter()`, `OllamaAdapter()`, `OpenAIAdapter()`
3. `config.require("NONEXISTENT_KEY")` raises `EnvironmentError`
4. `get_prompt("plan", topic="test")` returns formatted prompt text (not `[missing-prompt:...]`)
5. `prepare_db_for_topic("test")` creates SQLite DB at `data/scrapes/test.db`

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
  - Scopes: `basellm`, `logging`, `env`, `scraper`, `agents`, `interface`, `prompts`
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

1. **Build multi-agent LangGraph pipeline** (`agents/` — new folder, replacing `agents.old/`)
   - Orchestrator agent that receives topic and creates a plan
   - Searcher/Harvester agent that discovers links (uses Serper, saves to SQLite)
   - Wire them with LangGraph state machine, checkpoint-able
   - Use `BaseLLM` for LLM calls — powerful model for orchestrator, cheap for searcher

2. **Add HuggingFace sentiment model**
   - NOT an LLM — dedicated classification model (e.g., `distilroberta-base` fine-tuned for sentiment)
   - Continuous score output (0→1), not binary
   - Create `SentimentAnalyzer/` module with adapter pattern like BaseLLM
   - Must run locally, fast inference, no API costs

3. **Implement data cleaning pipeline**
   - Deduplication, spam filtering, text normalization
   - Can use cheap LLM for relevance filtering
   - Input: raw scraped data → Output: cleaned data ready for sentiment

4. **Add MongoDB for raw scraped data**
   - Replace or augment SQLite for storing actual post content
   - SQLite stays for link discovery queue only
   - MongoDB stores unstructured content with max metadata

5. **Add Vector DB (FAISS/Pinecone) for embeddings**
   - Embed cleaned text for semantic search
   - Powers the RAG chat interface later

6. **Build dashboard visualizations (Interface)**
   - Sentiment spectrum (bell curve), time-series trends, platform comparison
   - See `docs/VISION.md` Section 7 "Dashboard Vision" for the 8 target widgets
   - Consider Convex DB for real-time reactive updates

7. **Add more scrapers** (Twitter/X, TikTok, news sites, browser-based via Playwright)

8. **Build RAG chat interface** — query collected data conversationally

9. **Implement evaluation suite** (accuracy, precision, recall for sentiment model)

10. **Deploy with monitoring** and circuit breakers

---

*This file is the bridge between AI sessions. Update it when you change the project. The next AI starts from zero — what you don't write here is lost forever and other Agent again have to search for that same info.*
