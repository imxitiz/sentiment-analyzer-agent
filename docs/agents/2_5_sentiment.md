# 2.5 Sentiment Analyzer Agent

## Scope

`SentimentAnalyzerAgent` is Phase 5 of the pipeline. It scores sentiment for cleaned documents using the `SentimentAnalyzer` adapter layer (HuggingFace by default) and persists results for downstream analytics.

Design goals:

- Use a fast, dedicated sentiment model (not an LLM).
- Batch work for GPU/CPU efficiency.
- Keep behavior configurable through runtime flags.
- Provide LLM fallback only when necessary and budgeted.
- Persist rich run telemetry for debugging and comparison.

## Inputs and outputs

Input:

- Topic string from orchestrator.
- Cleaned documents from Mongo `cleaned_documents` where `status="accepted"` and sentiment is `not_started` or `failed`.

Output:

- Updated `cleaned_documents.sentiment` payload and `analysis_state.sentiment`.
- Updated `scraped_documents.sentiment` and `analysis_state.sentiment`.
- Run telemetry in `sentiment_runs`.
- `sentiment_results` per-document collection.
- `sentiment_summaries` aggregate per topic.
- Orchestrator events + pipeline artifact summary.

## Runtime flow

1. Load `SentimentRuntimeConfig` from env.
2. Pull pending cleaned documents for the topic (limit by `max_documents_per_run`).
3. Optionally build `SentimentPlan` with `SentimentPlannerAgent` from sampled records.
4. Start a `sentiment_run` record.
5. Analyze documents in batches using `SentimentAnalyzer`:
   - If batch fails, fallback to per-document analysis.
   - Apply keyword/context adjustments and label thresholds.
6. For low-confidence or failed cases:
   - Optional LLM recovery via `SentimentRecoveryAgent`.
   - Enforced budget (`SENTIMENT_LLM_FALLBACK_SAMPLE_SIZE`) to keep costs bounded.
7. Persist per-document results and run summary stats.
8. Emit completion events and checkpoint artifacts.

## Persistence model

Collections:

- `cleaned_documents`: source sentiment projection (`sentiment` + `analysis_state.sentiment`).
- `scraped_documents`: mirrors sentiment status for full lineage.
- `sentiment_results`: per-document output (topic-scoped).
- `sentiment_summaries`: per-topic aggregate stats.
- `sentiment_runs`: run metadata, runtime config, optional plan, and stats.

## Config-first controls

Key sentiment flags include:

- model/provider: `SENTIMENT_PROVIDER`, `SENTIMENT_MODEL`, `SENTIMENT_DEVICE`
- throughput: `SENTIMENT_BATCH_SIZE`, `SENTIMENT_MAX_CONCURRENCY`, `SENTIMENT_MAX_DOCUMENTS_PER_RUN`
- payload trimming: `SENTIMENT_MAX_TEXT_CHARS`
- thresholds: `SENTIMENT_POSITIVE_THRESHOLD`, `SENTIMENT_NEGATIVE_THRESHOLD`, `SENTIMENT_MIN_CONFIDENCE_THRESHOLD`
- topic/context: `SENTIMENT_INCLUDE_TOPIC_CONTEXT`, `SENTIMENT_TOPIC_CONTEXT_WEIGHT`
- keywords: `SENTIMENT_CUSTOM_KEYWORDS_POSITIVE`, `SENTIMENT_CUSTOM_KEYWORDS_NEGATIVE`
- planner: `SENTIMENT_LLM_PLAN_ENABLED`, `SENTIMENT_LLM_PLAN_SAMPLE_SIZE`
- fallback: `SENTIMENT_LLM_FALLBACK_ENABLED`, `SENTIMENT_LLM_FALLBACK_SAMPLE_SIZE`, `SENTIMENT_LLM_FALLBACK_MAX_CHARS`

## Operational notes

- Default HuggingFace model is `cardiffnlp/twitter-roberta-base-sentiment-latest` (social-media-optimized).
- The model ships `pytorch_model.bin`, so Transformers requires `torch>=2.6` for safe loading.
- GPU support currently requires Python 3.12 because PyTorch does not publish cp313 wheels yet.

## Failure handling

- Per-document errors are isolated and recorded as `failed`.
- Batch failures fall back to single-document analysis.
- LLM recovery is optional; if disabled or budget exhausted, the agent keeps the base result when possible.
- Run-level failures mark the `sentiment_run` as failed and persist error details.

## Implemented now vs next

Implemented:

- Batch analysis with configurable concurrency and GPU-safe defaults.
- Planner-assisted runtime overrides.
- LLM fallback for low-confidence or failed cases with budget.
- Mongo persistence for results, summaries, and run telemetry.

Next:

- Temporal sentiment trends from real pipeline output (not just mock UI).
- Topic-aware keyword expansion with automatic lexicon building.
- Language detection to auto-select multilingual models.
