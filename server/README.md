# Server — FastAPI Backend

> REST API + WebSocket server bridging the agent pipeline to the web interface.

## Quick Start

```bash
# From project root
uv run python -m server                         # default: 0.0.0.0:8000
uv run python -m server --port 8080             # custom port
uv run uvicorn server.app:app --reload --port 8000  # uvicorn directly
```

The server starts with **demo mode** by default (`DEFAULT_LLM_PROVIDER=dummy`), so no API keys are needed for development.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/docs` | Swagger UI (auto-generated) |
| `GET` | `/api/sessions` | List all sessions |
| `POST` | `/api/sessions` | Create a new session |
| `GET` | `/api/sessions/{id}` | Get session detail |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `POST` | `/api/sessions/{id}/start` | Start analysis pipeline |
| `POST` | `/api/sessions/{id}/messages` | Send a message (clarification, follow-up) |
| `WS` | `/ws/{session_id}` | Real-time event stream |

## Architecture

```
server/
├── __init__.py          # Package docstring
├── __main__.py          # CLI entry: python -m server
├── app.py               # FastAPI app factory (CORS, routes, health)
├── config.py            # ServerConfig (host, port, CORS origins, debug)
├── models.py            # All Pydantic models (Session, Events, Results)
├── routes/
│   ├── __init__.py
│   ├── sessions.py      # REST CRUD + start analysis
│   └── ws.py            # WebSocket real-time streaming
└── services/
    ├── __init__.py       # Mock data generator (generate_mock_result)
    ├── session_manager.py  # In-memory session store + subscriber pattern
    └── pipeline.py       # Pipeline runner (demo + live modes)
```

## Key Concepts

### Session Lifecycle

```
idle → planning → searching → scraping → cleaning → analysing → completed
                                                                    ↓
                                                              (error at any point)
```

Sessions track the full analysis lifecycle. Each session has:
- **messages**: Chat conversation (user + assistant + system)
- **events**: Agent progress events (streamed via WebSocket)
- **result**: Final `AnalysisResult` (posts, platforms, summary, plan)

### WebSocket Protocol

Client connects to `ws://localhost:8000/ws/{session_id}`.

**Server → Client**: JSON `AgentEvent` objects:
```json
{
  "type": "agent_progress",
  "agent": "planner",
  "message": "Found 10 keywords and 6 search queries",
  "data": { "keywords": [...], "queries": [...] },
  "timestamp": "2026-02-28T19:40:18.998223"
}
```

Event types: `agent_start`, `agent_progress`, `agent_complete`, `clarification_needed`, `pipeline_complete`, `status_change`, `error`.

**Client → Server**: JSON messages:
```json
{ "type": "user_message", "content": "..." }
```

On connect, the server **replays all past events** so late joiners catch up.

### Mock Data Generator

`generate_mock_result(topic)` produces realistic synthetic data:
- ~150 posts across 5 platforms (reddit, twitter, news, facebook, youtube)
- Distribution: ~35% positive, ~25% negative, ~40% neutral
- Deterministic per topic (seeded random)
- Platform breakdowns, sentiment over time, keyword extraction
- Content uses template-based generation with the topic injected

### Pipeline Runner

`run_analysis()` dispatches to:
- **Demo mode** (`provider="dummy"`): Simulates 6 phases with realistic delays (~9s total), then generates mock results.
- **Live mode** (any other provider): Currently falls back to demo. TODO: Wire up actual agent pipeline with async streaming.

## Configuration

| Env Variable | Default | Purpose |
| --- | --- | --- |
| `SERVER_HOST` | `0.0.0.0` | Bind host |
| `SERVER_PORT` | `8000` | Bind port |
| `SERVER_DEBUG` | `true` | Enable auto-reload |
| `DEFAULT_LLM_PROVIDER` | `dummy` | Default LLM provider for new sessions |
| `DEFAULT_LLM_MODEL` | `None` | Default model override |

CORS is pre-configured for `localhost:3000` (Bun dev server) and `localhost:8000`.

## Data Models

The core model hierarchy (defined in `models.py`):

```
Session
  ├── id, topic, status, llm_provider
  ├── messages: list[ChatMessage]
  │     └── id, role, content, timestamp, metadata
  ├── events: list[AgentEvent]
  │     └── type, agent, message, data, timestamp
  └── result: AnalysisResult | None
        ├── topic, plan (ResearchPlanData), completed_at
        ├── summary: SentimentSummary
        │     └── total_posts, avg_compound, positive/negative/neutral_pct
        │         most_positive_post, most_negative_post, top_keywords
        │         sentiment_over_time: [{date, avg_sentiment, post_count, ...}]
        ├── posts: list[AnalysedPost]
        │     └── id, platform, author, content, url
        │         sentiment: SentimentScore {positive, negative, neutral, compound}
        │         keywords, timestamp, metadata
        └── platforms: list[PlatformBreakdown]
              └── platform, post_count, avg_sentiment, positive/negative/neutral_pct
                  top_keywords
```

TypeScript mirrors of all models live in `Interface/src/lib/types.ts`.

## Testing

```bash
# Health check
curl http://localhost:8000/api/health

# Create session
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"topic": "Nepal elections 2026"}'

# Start analysis (returns immediately, runs in background)
curl -X POST http://localhost:8000/api/sessions/{id}/start \
  -H "Content-Type: application/json" \
  -d '{"topic": "Nepal elections 2026"}'

# Check results (~10s later)
curl http://localhost:8000/api/sessions/{id}
```
