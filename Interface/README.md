# Interface — Sentiment Analyzer Dashboard

> React + TanStack Router/Query + shadcn/ui + Recharts, served by Bun.

## Quick Start

```bash
bun install      # install deps
bun dev          # dev server on http://localhost:3000 (HMR)
bun start        # production mode
bun run build    # production bundle → dist/
bun run check    # lint (Biome)
```

**Requires the backend** running at `http://localhost:8000`. Start it with:
```bash
# From project root
uv run python -m server
```

## Architecture

### Stack

| Layer | Technology |
| --- | --- |
| Runtime | Bun (dev server with HMR, bundler, package manager) |
| UI Framework | React 19 |
| Routing | TanStack Router (code-based, type-safe) |
| Server State | TanStack Query v5 (caching, auto-refetch, mutations) |
| Forms | TanStack Form (installed, available for complex forms) |
| Components | shadcn/ui (New York style) + Radix UI primitives |
| Styling | Tailwind CSS v4 |
| Charts | Recharts v3 (PieChart, BarChart, AreaChart) |
| Icons | Lucide React |
| Date Utils | date-fns |

### Directory Structure

```
Interface/src/
├── index.ts              # Bun server entry (serves HTML, HMR)
├── index.html            # HTML shell with #root
├── index.css             # Tailwind imports + CSS variables (dark theme)
├── frontend.tsx          # React entry (QueryClientProvider + RouterProvider)
├── router.tsx            # TanStack Router config (code-based routes)
├── lib/
│   ├── types.ts          # TypeScript types (mirrors Python Pydantic models)
│   ├── api.ts            # HTTP client (typed fetch wrapper)
│   ├── ws.ts             # WebSocket client (auto-reconnect, typed events)
│   ├── query-client.ts   # TanStack Query client (staleTime: 30s, retry: 2)
│   └── utils.ts          # cn() helper (clsx + tailwind-merge)
├── hooks/
│   ├── use-sessions.ts   # TanStack Query hooks (CRUD, mutations, auto-refetch)
│   └── use-websocket.ts  # WebSocket hook (connects per session, collects events)
├── pages/
│   ├── home.tsx           # Landing page (topic input, suggested topics)
│   └── session.tsx        # Session workspace (chat ↔ dashboard toggle)
├── components/
│   ├── layout/
│   │   ├── app-layout.tsx  # Shell (sidebar + main content)
│   │   └── sidebar.tsx     # Collapsible sidebar with session list
│   ├── chat/
│   │   ├── chat-view.tsx       # Full chat container (messages + progress + input)
│   │   ├── chat-input.tsx      # Adaptive input (topic → disabled → follow-up)
│   │   ├── message-bubble.tsx  # User/assistant/system message rendering
│   │   └── agent-progress.tsx  # Real-time agent event timeline
│   ├── dashboard/
│   │   ├── dashboard-view.tsx  # Main dashboard layout + client-side filtering
│   │   ├── stats-cards.tsx     # 4 summary stat cards
│   │   ├── sentiment-chart.tsx # Donut chart (positive/neutral/negative %)
│   │   ├── platform-chart.tsx  # Horizontal stacked bar chart by platform
│   │   ├── timeline-chart.tsx  # Area chart (sentiment over time) + volume bars
│   │   ├── keyword-cloud.tsx   # Weighted keyword display
│   │   ├── filter-bar.tsx      # Platform toggles, sentiment filters, search
│   │   └── data-table.tsx      # Sortable, paginated, expandable post table
│   └── ui/                     # shadcn/ui primitives (button, card, input, etc.)
└── styles/
    └── globals.css             # Additional global styles
```

## Routes

| Path | Component | Description |
| --- | --- | --- |
| `/` | `HomePage` | Welcome screen, topic input, suggested topics |
| `/session/$sessionId` | `SessionPage` | Chat + Dashboard (auto-switches on completion) |

Routes are defined in `router.tsx` using TanStack Router's code-based API (not file-based, since Bun's bundler doesn't have the Vite plugin).

## Data Flow

```
User enters topic
  → useCreateSession() → POST /api/sessions
  → navigate(/session/$id)
  → useStartAnalysis() → POST /api/sessions/{id}/start
  → useSessionWebSocket(id) → ws://localhost:8000/ws/{id}
  → AgentEvents stream in → agent-progress.tsx renders timeline
  → pipeline_complete event → invalidate queries → session.result populated
  → auto-switch to DashboardView
  → charts render from session.result data
```

### Real-Time Updates

Two complementary mechanisms:
1. **WebSocket** (`use-websocket.ts`): Streams `AgentEvent` objects for the progress timeline. Auto-reconnect with exponential backoff (max 10 attempts).
2. **TanStack Query polling** (`use-sessions.ts`): `useSession()` auto-refetches every 2s while the session is active (`isSessionActive(status)` checks if status is planning/searching/scraping/cleaning/analysing).

When a `pipeline_complete` event arrives via WebSocket, it invalidates the session query to fetch the final result.

## UI Modes

### Chat Mode (default)
- Shows conversation messages (user input, assistant responses)
- Real-time agent progress timeline with per-agent icons and colours
- Adaptive input: topic entry (idle) → disabled (active) → follow-up questions (completed)

### Dashboard Mode (auto-activates on completion)
- Stats cards: total posts, avg sentiment, dominant sentiment, top keywords
- Sentiment donut chart (positive/neutral/negative percentages)
- Platform comparison bar chart (stacked by sentiment)
- Sentiment-over-time area chart + post volume bars
- Keyword cloud (weighted by frequency)
- Filter bar: platform toggles, sentiment quick filters, text search
- Sortable data table: expandable rows, pagination (20/page), external links

Users can toggle between Chat and Dashboard via tabs in the header.

## Key Patterns

### Path Alias
`@/*` maps to `./src/*` (configured in `tsconfig.json`). All internal imports use this alias:
```typescript
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
```

### Type Safety
All API types in `types.ts` mirror the Python Pydantic models in `server/models.py` 1:1. When the backend model changes, update `types.ts` to match.

### Query Key Factory
```typescript
export const sessionKeys = {
  all: ["sessions"] as const,
  lists: () => [...sessionKeys.all, "list"] as const,
  detail: (id: string) => [...sessionKeys.all, "detail", id] as const,
};
```

### Client-Side Filtering
The dashboard applies filters (platform, sentiment range, search query) client-side since all post data is already loaded. The `DashboardView` component manages filter state and passes filtered posts to child components.

## Adding New Components

1. **shadcn/ui component**: Follow the existing pattern in `components/ui/`. These are primitives.
2. **Feature component**: Create in the appropriate feature folder (`chat/`, `dashboard/`, `layout/`).
3. **New page**: Add a route in `router.tsx`, create the page in `pages/`.
4. **New hook**: Create in `hooks/`. Use TanStack Query for server state.

## Configuration

| Constant | Location | Default | Purpose |
| --- | --- | --- | --- |
| `API_BASE_URL` | `lib/api.ts` | `http://localhost:8000` | Backend API URL |
| `WS_BASE_URL` | `lib/api.ts` | derived from API_BASE_URL | WebSocket URL |
| `staleTime` | `lib/query-client.ts` | `30000` (30s) | Query cache staleness |
| `refetchInterval` | `hooks/use-sessions.ts` | `2000` (2s) | Active session polling |
| `maxReconnectAttempts` | `lib/ws.ts` | `10` | WebSocket reconnect limit |
| `pageSize` | `dashboard/data-table.tsx` | `20` | Posts per page |
