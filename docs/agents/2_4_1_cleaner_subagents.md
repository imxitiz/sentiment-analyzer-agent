# 2.4.1 Cleaner Sub-Agents

## Purpose

Cleaner uses focused sub-agents to keep high-cost reasoning isolated from the main deterministic processing path.

Current sub-agents:

- `CleanerPlannerAgent`
- `CleanerRecoveryAgent`

## CleanerPlannerAgent

Role:

- Analyze sampled raw records for a topic.
- Generate a structured `CleanerPlan` with runtime overrides.

Input payload:

- topic
- runtime snapshot
- sampled document previews (title/description/content/raw excerpts)

Output schema:

- `CleanerPlan`
  - strategy summary
  - optional normalization toggles
  - optional quality threshold overrides
  - optional language and dedupe settings
  - optional custom regex/replacement rules
  - confidence

Usage pattern:

- Called once per cleaner run (when enabled).
- Plan is passed into deterministic cleaning per document.
- Plan is stored in `clean_runs.plan` for audit/debug.

Why this helps:

- Topic-aware adaptation without requiring LLM calls for every record.
- Keeps deterministic pipeline stable while allowing strategic tuning.

## CleanerRecoveryAgent

Role:

- Recover failed/too-short deterministic outputs.
- Review sampled accepted outputs for quality assurance.

Input payload:

- topic and document metadata
- deterministic source/cleaned previews
- quality flags and metrics
- review reason (`fallback_on_failure` or `sample_quality_review`)

Output schema:

- `CleanerRecoveryPlan`
  - status: accepted/rejected/manual_review
  - cleaned_text
  - reason
  - quality_score
  - optional recommended plan adjustments

Usage pattern:

- Triggered only on failure/too_short and sampled QA records.
- Returned text can replace deterministic output when accepted.

Why this helps:

- Improves recall for hard records while keeping average cost low.
- Creates a controlled human-like review lane for edge cases.

## Coordination model

Main agent orchestration:

1. Build optional plan (`CleanerPlannerAgent`).
2. Run bulk deterministic cleaning with that plan.
3. Use `CleanerRecoveryAgent` on exceptions and QA sample.
4. Persist final record status plus quality metadata.

This separation keeps the core cleaner simple and scalable, with smart assistance only where it provides measurable value.

## Extension hooks

Future sub-agent patterns:

- PolicyGuard sub-agent for compliance filtering before sentiment.
- LanguageNormalizer sub-agent for language-specific canonicalization packs.
- AutoTuner sub-agent that aggregates `recommended_plan_adjustments` and proposes validated plan deltas.
