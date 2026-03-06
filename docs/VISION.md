# Project Vision & Current Architecture

> The single source of truth for **what this project is**, **how it works end-to-end**, and **where each piece lives today**.
>
> Other docs in this folder (`IDEA.md`, `CHATGPT_CHAT.md`, `GEMINI_CHAT.md`, `Prompt-task-runner-cto-new.md`) are brainstorming artifacts. This file is the **canonical, up-to-date** description.

---

## 1. What We're Building

A **"Self-Driving Research Lab"** for sentiment analysis. The user gives it a topic (e.g. "Nepal elections 2026"), and the system autonomously:

1. Expands the topic into keywords, hashtags, platform strategies
2. Discovers and collects links across social media & news
3. Scrapes raw content from those links
4. Cleans and enriches the data with metadata
5. Runs sentiment analysis (continuous spectrum, not binary)
6. Stores everything with rich metadata for filtering & semantic search
7. Presents results on a real-time interactive dashboard
8. Allows the user to chat with the collected data (RAG)

Primary use case: **election sentiment monitoring** — but the system is topic-agnostic.

---

## 2. End-to-End Pipeline (User Perspective)

```arch
User types topic in chat interface
        │
        ▼
┌─────────────────────────────────────────────┐
│  Phase 1: TOPIC REFINEMENT                  │
│  • Orchestrator receives topic              │
│  • Optionally asks user for clarification   │
│  • Expands into keywords, hashtags          │
│  • Searches web/Wikipedia for context       │
│  • Saves keywords to DB for tracking        │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Phase 2: LINK HARVESTING                   │
│  • Multiple async agents search in parallel │
│  • Google, Serper, platform APIs, etc.      │
│  • Links pushed to SQLite DB continuously   │
│  • Per-topic SQLite file with:              │
│    slug, unique_id, url, platform,          │
│    title, description, timestamp            │
│  • Orchestrator monitors: enough? timeout?  │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Phase 3: DEEP SCRAPING                     │
│  • Read links from SQLite DB                │
│  • Open browser / fetch content             │
│  • Extract text, metadata, author,          │
│    timestamps, platform info                │
│  • Store raw data → NoSQL (MongoDB)         │
│  • Async, concurrent workers                │
│  • Capture MAX metadata possible:           │
│    source URL, author, post time,           │
│    scrape time, platform, language,         │
│    engagement metrics (likes/comments)      │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Phase 4: CLEANING & ENRICHMENT             │
│  • Deduplicate, remove spam/ads             │
│  • Normalize text (encoding, whitespace)    │
│  • Filter non-relevant content              │
│  • Compute embeddings → Vector DB           │
│    (FAISS / Pinecone / Weaviate)            │
│  • Store cleaned data back to NoSQL         │
│    with cleaning metadata                   │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Phase 5: SENTIMENT ANALYSIS                │
│  • NOT using the main LLM — uses a         │
│    dedicated sentiment model                │
│    (e.g. HuggingFace DistilRoBERTa)        │
│  • Continuous spectrum score (0→1 or 1→10)  │
│    NOT binary pos/neg                       │
│  • Per-post individual rating               │
│  • Uses topic context for aspect-based      │
│    analysis (what specifically is pos/neg)  │
│  • Save scores + reasoning to DB            │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Phase 6: DASHBOARD & INSIGHTS              │
│  • Real-time reactive UI (Convex DB or      │
│    similar pushes updates instantly)         │
│  • Shows pipeline progress live             │
│  • Sentiment distribution (bell curve)      │
│  • Time-series trends                       │
│  • Platform comparison (radar chart)        │
│  • Topic clusters (word cloud / bubbles)    │
│  • Key influencer posts                     │
│  • Raw evidence spotlight                   │
│  • Chat interface for querying data (RAG)   │
│  • "Refresh" creates Version 2 — never      │
│    overwrites previous data                 │
└─────────────────────────────────────────────┘
```

---

## 3. Multi-Agent Architecture

This is **not** a single linear script. It's an **agentic mesh** with specialized workers:

| Agent | Role | Tools |
| --- | --- | --- |
| **Orchestrator** | Receives topic, creates plan, assigns work to sub-agents, monitors progress, decides phase transitions | LLM (powerful model), prompt templates |
| **Searcher / Harvester** | Discovers links across platforms | Serper API, platform search APIs, browser automation |
| **Scraper** | Extracts raw content from discovered links | Browser automation, HTTP clients, platform APIs |
| **Cleaner** | Deduplicates, normalizes, filters data | Regex, LLM-assisted spam detection |
| **Analyst** | Runs sentiment scoring on each post | Dedicated sentiment model (HuggingFace), NOT the main LLM |
| **Summarizer** | Generates aggregate insights | LLM for synthesis and RAG |

**Key principle**: The orchestrator **triggers** work, but the actual scraping, saving, and analysis is done **programmatically by code** — not by the LLM deciding when to save. The LLM decides *what* and *when to start*; the code handles *how* and *storage*.

**Different LLMs for different tasks**:

- Orchestrator/Planner → powerful model (Gemini Pro, GPT-4o)
- Scraping decisions → medium model (Gemini Flash, GPT-4o-mini)
- Sentiment analysis → dedicated HuggingFace model (not an LLM at all)
- All configurable via `BaseLLM` — swap any provider per agent

---

## 4. Data Storage Strategy

```arch
┌───────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   SQLite      │     │   MongoDB        │     │   Vector DB      │
│   (per-topic) │ ──► │   (NoSQL)        │ ──► │   (FAISS/etc.)   │
│               │     │                  │     │                  │
│ • Discovered  │     │ • Raw scraped    │     │ • Embeddings     │
│   links       │     │   content        │     │ • Semantic search│
│ • URL, slug   │     │ • All metadata   │     │ • RAG chatbot    │
│ • Platform    │     │ • Unstructured   │     │ • Filtering      │
│ • Status      │     │ • Cleaning state │     │                  │
│ • Timestamps  │     │ • Sentiment      │     │                  │
│               │     │   scores         │     │                  │
└───────────────┘     └──────────────────┘     └──────────────────┘
        │                      │                        │
        │                      ▼                        │
        │              ┌──────────────────┐             │
        └─────────────►│  Convex DB       │◄────────────┘
                       │  (Real-time)     │
                       │                  │
                       │ • Pipeline status│
                       │ • Structured     │
                       │   analysis data  │
                       │ • Dashboard feed │
                       │ • Live updates   │
                       └──────────────────┘
```

- **SQLite** (`data/scrapes/<topic>.db`): Lightweight link queue. One file per topic. Concurrent writes from multiple harvester agents. Fields: slug, unique_id, url, platform, title, description, published_at, status (PENDING/SCRAPED/FAILED).
- **MongoDB**: Raw scraped content. Unstructured data with max metadata. Never deleted; new scrapes are new documents.
- **Vector DB** (FAISS/Pinecone/Weaviate): Embeddings of cleaned text for semantic search and RAG chat.
- **Convex DB** (or similar reactive DB): Structured analysis results pushed in real-time to the dashboard. Pipeline status updates.

**Non-destructive versioning**: If user "refreshes" a topic after days, it creates Version 2 alongside Version 1. Old data is **never overwritten**.

---

## 5. What's Built So Far

### Completed (production-ready)

| Module | Status | What it does |
| --- | --- | --- |
| `BaseLLM/` | **Done** | Unified LLM abstraction. Adapters for Gemini, Ollama, OpenAI. DRY base class with sync/async, logging, timing. Factory `get_llm()`. Per-agent model assignment. |
| `Logging/` | **Done** | Production structured logger. JSON files (rotating 10MB), ANSI console, ring buffer (1000 entries), context loggers, `subscribe()` for live streaming. |
| `env.py` | **Done** | `EnvConfig` singleton. Audited env var access, secret masking, startup audit. Never use `os.getenv()` directly. |
| `prompts/` | **Done** | Template manager. `plan.txt`, `scrape.txt`, `clean.txt`, `summarize.txt`. `str.format()` placeholders. |
| `agents/` | **Partial** | Multi-agent runtime with Orchestrator, Planner, and Harvester agents; tool registry; demo/live-safe checkpointing; timeout/retry/circuit breaker controls. |
| `HarvesterAgent` | **Done** | Phase 2 link harvesting: structured harvest planning, async multi-source fan-out, queued SQLite writes, deduplicated canonical links, and append-only observation logs. |
| `DataScraper/` | **Partial** | Placeholder area for later deep-scrape connectors. Phase 2 link harvesting now lives in the agent/service layer instead. |

### In Progress / Scaffolded

| Module | Status | What it does |
| --- | --- | --- |
| `server/` | **Working** | FastAPI backend with session CRUD, WebSocket streaming, export/compare APIs, mock-data pipeline runner, and dashboard support. |
| `Interface/` | **Working** | Bun + React dashboard with chat, analysis views, charts, filters, exports, and comparison UI. |
| `main.py` | **Working** | CLI entry point that now boots planner + harvester under the orchestrator. |

### Not Yet Started

| Module | Target |
| --- | --- |
| Sentiment model integration | HuggingFace DistilRoBERTa or similar |
| Data cleaning agent/pipeline | Dedup, spam filter, normalization |
| MongoDB integration | Raw scraped data storage |
| Vector DB integration | FAISS/Pinecone for embeddings |
| Convex DB / reactive layer | Real-time dashboard data |
| Browser-based scraping | Playwright/Puppeteer for JS-heavy sites |
| Dashboard visualizations | Charts, sentiment curves, word clouds |
| RAG chat interface | Query collected data conversationally |
| Evaluation suite | Accuracy, precision, recall metrics |

---

## 6. Tech Stack (Current & Planned)

| Layer | Current | Planned |
| --- | --- | --- |
| **Language (Backend)** | Python 3.13 | Python (stays) |
| **Language (Frontend)** | TypeScript (Bun) | TypeScript (stays) |
| **Package Manager (Python)** | UV | UV (stays) |
| **Package Manager (TS)** | Bun | Bun (stays) |
| **LLM Framework** | LangChain + LangGraph | LangChain + LangGraph (stays) |
| **LLM Providers** | Gemini, Ollama, OpenAI | Same + possibly Anthropic |
| **Sentiment Model** | — | HuggingFace (DistilRoBERTa or similar) |
| **Link Storage** | SQLite (per-topic) | SQLite (stays) |
| **Raw Data Storage** | — | MongoDB |
| **Vector DB** | — | FAISS / Pinecone / Weaviate |
| **Real-time DB** | — | Convex DB (or similar) |
| **Web Search** | Serper API | Serper (stays) + possibly others |
| **Browser Scraping** | — | Playwright / headless browser |
| **Frontend Framework** | React (Bun serve) | React + dashboard library |
| **Styling** | Tailwind CSS | Tailwind (stays) |
| **Charts** | — | Recharts / D3.js |
| **Linting (Python)** | Ruff | Ruff (stays) |
| **Linting (TS)** | Biome | Biome (stays) |

---

## 7. Dashboard Vision

The "Golden Dashboard" for a completed topic analysis:

1. **Pipeline Status** — What stage the analysis is at, live progress
2. **Sentiment Spectrum** — Bell curve: distribution of sentiment scores across all posts
3. **Temporal Evolution** — Time-series: how sentiment changed over time, event spikes
4. **Platform Comparison** — Radar chart: Reddit vs Facebook vs News vs TikTok
5. **Topic Clusters** — Word cloud or bubble chart: *why* people feel a certain way
6. **Key Influencers** — Top posts that shifted conversation most
7. **Raw Evidence** — 10 random posts with individual analysis scores
8. **Chat Interface** — Ask questions about the data ("What do Reddit users think about X?")

Each topic is a **session**. Refreshing creates a **new version** for historical comparison.

---

## 8. Design Decisions & Rationale

| Decision | Why |
| --- | --- |
| **SQLite for links, not a big DB** | Lightweight, file-per-topic, zero-setup, concurrent reads. Link discovery is a fast transient step. |
| **MongoDB for raw scraped data** | Unstructured social media content doesn't fit relational schemas. Max flexibility for metadata. |
| **Separate sentiment model (not LLM)** | LLMs are slow and expensive for per-post scoring at scale. HuggingFace models run locally, are fast, and purpose-built. |
| **Continuous sentiment (0→1), not binary** | Binary pos/neg misses nuance. A spectrum captures intensity ("slightly negative" vs "furious"). |
| **Convex for dashboard** | Reactive by default — no WebSocket plumbing. DB mutation → instant UI update. |
| **LangGraph over linear scripts** | Allows cycles (retry, go back and search more), state checkpointing, and human-in-the-loop breakpoints. |
| **BaseLLM abstraction** | Different agents need different models. Orchestrator gets a powerful model; scrapers get a cheap one. One factory, swap freely. |
| **Non-destructive versioning** | Research needs historical comparison. Never delete old data; "refresh" = new version. |

---

## 9. Relationship to Other Docs

| File | What it is | Status |
| --- | --- | --- |
| `docs/ProjectDetail.md` | Original project brief from internship | Reference only — defines scope |
| `docs/IDEA.md` | Early brainstorm with tech stack ideas | Inspiration — some tech choices may change |
| `docs/CHATGPT_CHAT.md` | Deep research chat on architecture | Reference — thorough but aspirational |
| `docs/GEMINI_CHAT.md` | Detailed engineering analysis | Reference — good patterns, some outdated |
| `docs/Prompt-task-runner-cto-new.md` | CTO-style task runner prompt | Reference — the ideal end state |
| **`docs/VISION.md` (this file)** | **Canonical current project vision** | **Source of truth** |
| `AGENTS.md` | AI agent operating manual | **Source of truth for how to code** |

When the docs contradict each other, **this file** defines what the project actually is. `AGENTS.md` defines how to work on it.
