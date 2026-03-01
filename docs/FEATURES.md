# Features Documentation

> Full documentation of all features in the Sentiment Analyzer web interface.

---

## Table of Contents

1. [Export Reports](#1-export-reports)
2. [Version Comparison](#2-version-comparison)
3. [Version History & Switching](#3-version-history--switching)
4. [Real-time Analysis Dashboard](#4-real-time-analysis-dashboard)

---

## 1. Export Reports

Export analysis results in three formats — JSON, CSV, or Markdown — for offline analysis, sharing, or archiving.

### Overview

After an analysis completes, the **Export** button appears in the session header. Click it to choose a download format:

| Format | Best For | Content |
|--------|----------|---------|
| **JSON** | Programmatic use, reimport | Full structured data (summary, posts, platforms, plan) |
| **CSV** | Spreadsheets (Excel, Sheets) | Flat table of all analysed posts with sentiment scores |
| **Markdown** | Reports, sharing, docs | Formatted report with executive summary, tables, charts |

### API Endpoint

```
GET /api/sessions/{session_id}/export?format={json|csv|md}&version={n}
```

**Query Parameters:**

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `format` | Yes | `json` | Export format: `json`, `csv`, or `md` |
| `version` | No | current | Version number to export (default: active version) |

**Response:** File download with appropriate `Content-Disposition` header.

### Examples

```bash
# Export current version as JSON
curl -O "http://localhost:8000/api/sessions/{id}/export?format=json"

# Export version 1 as CSV
curl -O "http://localhost:8000/api/sessions/{id}/export?format=csv&version=1"

# Export as Markdown report
curl -O "http://localhost:8000/api/sessions/{id}/export?format=md"
```

### Markdown Report Structure

The Markdown export generates a complete analysis report with:

- **Executive Summary** — overall sentiment direction, post count, platform count
- **Key Metrics Table** — compound score, positive/negative/neutral percentages
- **Platform Breakdown** — per-platform sentiment stats
- **Top Keywords** — most frequently occurring keywords
- **Sentiment Over Time** — daily sentiment timeline
- **Notable Posts** — most positive and most negative posts
- **Research Plan** — the planner agent's strategy (queries, platforms, keywords)

### Frontend Integration

The `ExportButton` component renders a dropdown with format options. Each option triggers a `window.open()` to the export URL, which initiates a browser download.

**Usage in TSX:**

```tsx
import { ExportButton } from "@/components/dashboard/export-button";

<ExportButton sessionId={session.id} version={session.version} />
```

---

## 2. Version Comparison

Compare any two analysis versions side-by-side to track how sentiment evolves over time.

### Overview

After running a refresh (creating v2, v3, etc.), a **Compare** tab appears alongside Chat and Dashboard. The comparison shows:

- **Narrative summary** — human-readable description of what changed
- **Sentiment delta cards** — before/after for compound score, positive %, negative %, post count
- **Platform shifts** — per-platform sentiment changes with trend indicators
- **Keyword changes** — new keywords, dropped keywords, unchanged keywords

### Direction Classification

| Delta | Direction | Meaning |
|-------|-----------|---------|
| > +0.05 | **Improved** | Sentiment got more positive |
| < −0.05 | **Declined** | Sentiment got more negative |
| −0.05 to +0.05 | **Stable** | No significant change |

### API Endpoint

```
POST /api/compare
```

**Request Body:**

```json
{
  "base": {
    "session_id": "abc123",
    "version": 1
  },
  "target": {
    "session_id": "abc123",
    "version": 2
  }
}
```

The `base` and `target` can reference **different sessions** — enabling cross-topic comparison (e.g., "Party A sentiment" vs "Party B sentiment").

**Response:**

```json
{
  "comparison": {
    "base_topic": "Nepal elections 2026",
    "target_topic": "Nepal elections 2026",
    "base_version": 1,
    "target_version": 2,
    "sentiment": {
      "avg_compound_before": 0.12,
      "avg_compound_after": 0.18,
      "delta": 0.06,
      "positive_pct_before": 35.0,
      "positive_pct_after": 38.5,
      "negative_pct_before": 25.0,
      "negative_pct_after": 22.0,
      "neutral_pct_before": 40.0,
      "neutral_pct_after": 39.5,
      "total_posts_before": 150,
      "total_posts_after": 150,
      "direction": "improved"
    },
    "keywords": {
      "added": ["economic-reform", "infrastructure"],
      "removed": ["scandal"],
      "common": ["elections", "nepal", "opinion"]
    },
    "platforms": [
      {
        "platform": "reddit",
        "before_avg": 0.15,
        "after_avg": 0.22,
        "delta": 0.07,
        "before_posts": 30,
        "after_posts": 32
      }
    ],
    "narrative": "Comparing v1 vs v2 for \"Nepal elections 2026\". Overall sentiment improved by 0.06 (from 0.12 → 0.18). New keywords emerged: economic-reform, infrastructure."
  }
}
```

### Frontend Integration

The `ComparisonView` component renders inside the session page when the Compare tab is active. It includes version selectors, a compare button, and renders the structured diff.

**Usage in TSX:**

```tsx
import { ComparisonView } from "@/components/dashboard/comparison-view";

<ComparisonView session={session} />
```

**Requirements:**
- At least 2 completed versions must exist (run analysis, then refresh + run again)
- Both selected versions must have result data
- Base and target versions must be different

---

## 3. Version History & Switching

Non-destructive versioning — every refresh archives the old data so you can browse any previous version.

### How It Works

1. Complete an analysis → v1 data is on the session
2. Click **Refresh** → v1 is archived into `version_history`, session moves to v2
3. v2 completes → now you have v1 (archived) + v2 (active)
4. Click **VersionSwitcher** dropdown → choose v1 → session swaps to show v1 data (v2 goes to archive)
5. Switch back anytime — bidirectional swap, nothing is ever lost

### API Endpoints

```bash
# List all versions
GET /api/sessions/{id}/versions

# Switch active version
POST /api/sessions/{id}/version
Body: { "version": 1 }

# Refresh (create new version)
POST /api/sessions/{id}/refresh
```

### Data Model

```
Session
├── version: 2 (currently active)
├── result: AnalysisResult (v2 data)
├── events: AgentEvent[] (v2 events)
└── version_history: [
      VersionSnapshot {
        version: 1,
        result: AnalysisResult (v1 data),
        events: AgentEvent[],
        started_at: datetime,
        completed_at: datetime
      }
    ]
```

---

## 4. Real-time Analysis Dashboard

Interactive dashboard with charts, filters, and data table — powered by Recharts and TanStack Query.

### Dashboard Widgets

| Widget | Description |
|--------|-------------|
| **Stats Cards** | Total posts, compound score, positive/negative/neutral percentages |
| **Sentiment Pie Chart** | Visual breakdown of positive/negative/neutral distribution |
| **Platform Bar Chart** | Per-platform sentiment comparison |
| **Timeline Chart** | Sentiment trends over time (daily buckets) |
| **Keyword Cloud** | Most frequent keywords with proportional sizing |
| **Filter Bar** | Platform filter, sentiment range, text search |
| **Posts Table** | Sortable table of all analysed posts with sentiment scores |

### Chat ↔ Dashboard Auto-Switch

- Analysis starts → **Chat mode** (real-time progress, messages)
- Analysis completes → auto-switches to **Dashboard mode**
- User can toggle between modes via header tabs
- Compare tab appears when multiple versions exist

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Frontend (Bun + React, port 3000)              │
│  ├── ExportButton → window.open(export URL)     │
│  ├── ComparisonView → POST /api/compare         │
│  ├── VersionSwitcher → POST /version            │
│  └── DashboardView → session.result             │
├─────────────────────────────────────────────────┤
│  Backend (FastAPI, port 8000)                   │
│  ├── /api/sessions/{id}/export  (GET)           │
│  ├── /api/compare               (POST)         │
│  ├── /api/sessions/{id}/version (POST)          │
│  ├── /api/sessions/{id}/versions (GET)          │
│  └── /api/sessions CRUD + /start + /refresh     │
└─────────────────────────────────────────────────┘
```

---

## Files Reference

| File | Feature |
|------|---------|
| `server/routes/export.py` | Export endpoint (JSON/CSV/Markdown) |
| `server/routes/compare.py` | Comparison endpoint + models |
| `Interface/src/components/dashboard/export-button.tsx` | Export UI dropdown |
| `Interface/src/components/dashboard/comparison-view.tsx` | Comparison UI |
| `Interface/src/components/ui/version-switcher.tsx` | Version switching dropdown |
| `Interface/src/pages/session.tsx` | Main session page (integrates all features) |
| `Interface/src/hooks/use-sessions.ts` | TanStack Query hooks (compare, switch, etc.) |
| `Interface/src/lib/api.ts` | API client (export URL builder, compare call) |
| `Interface/src/lib/types.ts` | TypeScript types (ComparisonResult, ExportFormat, etc.) |
