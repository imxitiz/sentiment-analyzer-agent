# Sentiment Analyzer Agent

> AI-powered end-to-end sentiment analysis pipeline: data collection → preprocessing → LLM classification → interactive dashboard.

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

```
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

---

## Key Paths

| Path | Purpose |
|---|---|
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

```
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
|---|---|---|---|
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
|---|---|
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
|---|---|
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
|---|---|
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

- Update `AGENTS.md` only for **significant** changes: architecture/service-boundary changes; package manager or build command changes; config or feature flag schema changes; public API or persistence schema changes.
- Do **not** update for small bug fixes, cosmetic refactors, or private non-behavior edits unless they change a verbatim instruction/command in this file.
- When updating, **improve and merge** into existing content — do not replace human-written guidance without documented justification in the PR.
- Do not include changelog entries or who/when metadata inside AGENTS.md.

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

1. Build proper multi-agent LangGraph pipeline
2. Add sentiment classification model (HuggingFace)
3. Implement data cleaning agent
4. Add vector store for semantic search (FAISS/Pinecone)
5. Build interactive dashboard (Interface)
6. Add more scrapers (Twitter/X, TikTok, news)
7. Implement evaluation suite (accuracy/precision/recall)
8. Deploy with monitoring and circuit breakers

---

*This is a living document. Update it when the project's architecture, commands, or conventions change. Do not use it as a changelog.*
