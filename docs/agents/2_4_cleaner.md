# 2.4 Cleaner Agent

## Scope

`CleanerAgent` is Phase 4 of the pipeline. It converts raw scraped Mongo documents into sentiment-ready text with an adaptive, deterministic-first pipeline.

Design goals:

- Handle messy real-world web and social payloads.
- Minimize LLM cost by default.
- Keep behavior configurable through runtime flags.
- Persist enough metadata for debugging and iterative improvement.

## Inputs and outputs

Input:

- Topic string from orchestrator.
- Raw documents from Mongo `scraped_documents` where `analysis_state.cleaning` is `not_started` or `failed`.

Output:

- Updated `scraped_documents.cleaning` payload and `analysis_state.cleaning` status.
- Upserted sentiment-ready projection in `cleaned_documents`.
- Run telemetry in `clean_runs`.
- Pipeline artifact summary via orchestrator checkpoints.

## Runtime flow

1. Load `CleaningRuntimeConfig` from env.
2. Pull pending documents for topic.
3. Optionally build `CleanerPlan` with `CleanerPlannerAgent` from sampled records.
4. Process documents concurrently with semaphore-bounded workers.
5. For each document:
   - Adaptive deterministic cleaning (`clean_document(..., plan=...)`).
   - Exact hash dedupe.
   - Optional near-duplicate fuzzy dedupe.
   - Optional LLM fallback/review via `CleanerRecoveryAgent`.
   - Persist final result to Mongo.
6. Store run stats and emit orchestrator events.

## Deterministic cleaning pipeline

`agents/services/cleaner_text.py` performs:

- Candidate extraction from multiple backends:
  - `content_fields`
  - `trafilatura` (optional)
  - `readability` (optional)
  - `bs4` HTML extraction
- Source scoring and best-source selection.
- Normalization:
  - HTML unescape
  - Unicode repair (`ftfy` when available)
  - Emoji to semantic text (`emoji.demojize`)
  - Contraction expansion (`contractions` package with regex fallback)
  - URL and mention tokenization
  - Custom noise pattern removal
  - Optional punctuation removal and lowercase
- Quality gates:
  - minimum cleaned chars
  - alpha/url/symbol ratio thresholds
  - optional language filtering

## Deduplication strategy

- Exact dedupe: SHA-256 cleaned hash match within topic.
- Near dedupe: optional fuzzy matching against recent accepted records.
  - Uses RapidFuzz when installed.
  - Falls back gracefully when unavailable.

## LLM usage policy

Cleaner is deterministic-first.

LLM is used in two controlled paths only:

- Fallback when deterministic result is `failed` or `too_short`.
- Sampled quality review on a configurable subset of accepted records.

This keeps cost and latency bounded while preserving recovery capability.

## Persistence model

Collections:

- `scraped_documents`: source-of-truth raw docs plus nested cleaning payload.
- `cleaned_documents`: sentiment-ready projection indexed by `document_id` and topic.
- `clean_runs`: run-level metadata, runtime config, optional plan, and aggregate stats.

Per-record fields include:

- `status`, `reason`, `quality_flags`
- `cleaned_text`, `sentiment_text`, `cleaned_hash`, `cleaned_signature`
- `metrics` and `features` for observability

## Config-first controls

Key cleaner flags include:

- throughput: `CLEANER_MAX_CONCURRENCY`, `CLEANER_MAX_DOCUMENTS_PER_RUN`
- quality: `CLEANER_MIN_CLEAN_CHARS`, `CLEANER_MAX_CLEAN_CHARS`, ratio thresholds
- extraction: `CLEANER_EXTRACTION_BACKENDS`
- dedupe: `CLEANER_ENABLE_FUZZY_DEDUPE`, threshold and candidate limit
- planner: `CLEANER_LLM_PLAN_*`
- fallback: `CLEANER_LLM_FALLBACK_*`

## Failure handling

- Per-document errors map to `failed` status and continue the run.
- Run-level exceptions mark `clean_runs` failed and checkpoint an artifact error.
- Optional dependencies are loaded dynamically; missing packages do not crash cleaner startup.

## Implemented now vs next

Implemented:

- Adaptive extraction and normalization pipeline.
- Planner-assisted runtime overrides.
- Exact and optional near-duplicate dedupe.
- LLM fallback and sampled QA review.
- Mongo persistence + run telemetry.

Next:

- Merge repeated recovery recommendations into dynamic plan updates during the same run.
- Add benchmark suite for cleaner precision/recall on noisy corpora.
- Expand language-aware normalization packs.
