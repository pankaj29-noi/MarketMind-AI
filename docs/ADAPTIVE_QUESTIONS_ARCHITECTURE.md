# Adaptive Dataset-Aware Question Generation — Architecture

## Goal

After a user uploads a CSV, MarketMind profiles the dataset once, builds a semantic
capability map, generates **schema-grounded** natural-language questions, **proves**
each candidate by executing read-only SQL against DuckDB, then shows only validated
questions as one-click cards that call the existing `/analyze` endpoint.

Marketplace demo continues to use curated `MARKETPLACE_SAMPLE_QUESTIONS`.

## Existing pieces we reuse

| Piece | Role |
|---|---|
| `POST /upload` + `SessionManager.register_csv` | CSV → DuckDB session table |
| `get_schema` / DuckDB `PRAGMA table_info` | Column names/types |
| `analytical_roles.infer_analytical_roles` | Baseline role hints |
| `analytics_fallback.map_columns` | Metric/dimension alias matching |
| `mcp.data_access.run_query` + read-only guard | Proof execution |
| `sql_quality_validator.validate_sql` | Safety/quality gate on proof SQL |
| Frontend `Workspace` sample buttons + `handleSubmitQuestion` | One-click ask UX |
| `/analyze` LangGraph pipeline | Same engine for suggested & typed questions |

## New module: `backend/services/adaptive_questions/`

```
adaptive_questions/
  __init__.py          # public API: generate_suggested_questions(...)
  fingerprint.py       # dataset fingerprint
  profiler.py          # compact DatasetProfile (stats + samples)
  semantics.py         # SemanticColumn with type + confidence
  capabilities.py      # DatasetCapabilityMap
  templates.py         # deterministic intent → (question, proof_sql, category, difficulty)
  validator.py         # schema + SQL quality + DuckDB execution proof
  ranking.py           # deterministic score + diversity
  cache.py             # in-memory cache keyed by session+dataset+fingerprint
  engine.py            # orchestration
```

## Flow

```
UPLOAD CSV
  → register DuckDB table
  → (frontend) POST /session/{session_id}/suggested-questions
       → fingerprint
       → cache hit? return
       → profile once (approx stats via DuckDB aggregates, SAMPLE)
       → semantic typing (name + dtype + cardinality + patterns)
       → capability map
       → template candidates (no full-CSV to LLM)
       → for each candidate:
            validate_sql(proof_sql)
            run_query(proof_sql) must succeed with ≥0 rows acceptable
            reject on failure
       → dedupe by intent signature
       → rank + diversify
       → cache + return
  → UI cards
  → click → handleSubmitQuestion(text) → POST /analyze (unchanged)
```

## LLM usage

**Default path: zero LLM calls.** Deterministic templates + DuckDB proof.

Optional future: one compact LLM polish call on already-validated texts.
Not required for v1.

## Caching / isolation

Cache key: `(session_id, dataset_id, fingerprint)`

Fingerprint includes: sorted `(name, dtype)`, `row_count`, hash of sample digests.

On new upload (`applySession`), frontend clears suggestion state.
Backend cache entries for other sessions TTL-evict with session manager.

## API

`POST /session/{session_id}/suggested-questions`

```json
{
  "dataset_id": "uploaded_data_ab12",
  "count": 10,
  "difficulty": "mixed",
  "refresh": false,
  "exclude_ids": []
}
```

Response:

```json
{
  "dataset_id": "...",
  "fingerprint": "...",
  "profile_summary": { "row_count": 3842, "column_count": 18, ... },
  "generation_ms": 420,
  "questions": [
    {
      "id": "q_…",
      "text": "Which region has the highest total sales?",
      "category": "ranking",
      "difficulty": "easy",
      "confidence": 0.93,
      "intent": "top_group_by_measure"
    }
  ],
  "message": null
}
```

Low-quality datasets return empty `questions` with an explanatory `message`.

## Security

- CSV cells never interpreted as instructions
- Proof SQL must pass read-only SELECT gate
- Rate-limited via existing expensive-endpoint limiter
- No secrets in logs; profile samples truncated

## Frontend

- After CSV upload (not marketplace multi-table demo), fetch suggestions
- Card UI: “Questions for your dataset”
- Marketplace demo: keep curated examples
- “Generate more” → `refresh: true` + `exclude_ids`
- Follow-ups (v1.1): optional after analyze using result context — stubbed hook

## Non-goals (v1)

- Auto-joining multiple CSVs
- Streaming question generation
- Replacing analytics SQL planner

---

# v2 — Tiered Advanced Question Discovery

v2 keeps everything above and adds multi-condition **advanced** and multi-step
**expert** questions that are generated from the uploaded CSV only when that CSV
actually supports them.

## New pieces

| File | Role |
|---|---|
| `adaptive_questions/advanced_patterns.py` | Advanced/expert pattern library + complexity score + result-aware follow-ups |
| `adaptive_questions/engine.py` | Tier targets, family-level diversity, generation versioned cache, follow-up orchestration |
| `adaptive_questions/capabilities.py` | Ranked dimensions/measures + `additive_measures` (never SUMs a price/ratio when an additive measure exists) |
| `adaptive_questions/validator.py` | Adds result validation: advanced/expert suggestions must return ≥ 1 row |
| `POST /session/{id}/followup-questions` | Result-aware "Explore further" questions |
| `benchmarks/run_question_discovery_benchmark.py` | 8-dataset deterministic benchmark → `QUESTION_DISCOVERY_REPORT.md` |

## Tiers

| Tier | Meaning | Example shape |
|---|---|---|
| `quick` | direct single-value answers | totals, counts, distinct values |
| `analytics` | grouped / comparative | measure by dimension, monthly trend |
| `advanced` | multi-condition | above-average vs below-average, top-10 share, min sample size, tradeoffs, outliers |
| `expert` | multi-step | top-N per group with exclusions, YoY growth with declining second metric, Pareto/cumulative contribution, top-quintile within group, group leader contribution |

Pattern families implemented: top-N, top-N per group, above/below average, percent of
total, group contribution, minimum sample size, multi-condition, YoY, MoM, growth +
decline, ranking, ranking within group, group-average comparison, overall-average
comparison, outlier detection, high/low tradeoff, conditional aggregation, cumulative
contribution, concentration, percentile within group.

## Capability-driven tier budget

`compute_complexity_score(capabilities)` scores dimensions, measures, time fields and
entities into a band:

| Band | Quick | Analytics | Advanced | Expert |
|---|---:|---:|---:|---:|
| `rich` | 3 | 3 | 5 | 3 |
| `moderate` | 3 | 3 | 4 | 2 |
| `basic` | 3 | 3 | 2 | 0 |
| `minimal` | 3 | 2 | 0 | 0 |

Backfill is restricted to tiers the dataset supports, so a `name, age` CSV never gets
forced expert questions. Empty tiers are not rendered.

## Validation contract

Every displayed question passes, in order:

1. schema validation — bound columns must exist in the profile
2. SQL quality validation — read-only, no forbidden keywords
3. execution validation — proof SQL runs in the session's DuckDB
4. result validation — advanced/expert proofs must return at least one row

Rejections are logged with a reason and never surface in the UI.

## Diversity

Selection is family-aware: `above_overall_average` and `above_average_group` share the
`above_average` family, ranking variants share `ranking`, etc. Only one question per
family per response, so users never see ten near-identical ranking prompts.

## Cache + refresh

Cache key is `(session_id, dataset_id, fingerprint, GENERATION_VERSION)`. Bumping
`GENERATION_VERSION` invalidates every previously generated question set. "Generate
more" sends `refresh: true` plus `exclude_ids`, and results are not cached so the pool
keeps rotating.

## Follow-ups

`POST /session/{id}/followup-questions` receives the asked question plus the first
rows of the answer table. It maps a concrete value back to a real dimension, then
proposes breakdown / comparison / trend / tradeoff follow-ups — each proven by
read-only execution before display. No result value, no invented follow-up.

## Response additions

```json
{
  "generation_version": "v2-tiered",
  "complexity": { "score": 31, "band": "rich", "advanced_possible": true, "expert_possible": true },
  "tiers": [{ "tier": "advanced", "questions": [ ... ] }],
  "questions": [
    {
      "id": "q_…",
      "text": "Which suppliers increased revenue year over year while profit declined?",
      "tier": "expert",
      "required_columns": ["supplier", "order_date", "revenue", "profit"],
      "operations": ["time_analysis", "window", "multi_metric", "comparison"],
      "validation_status": "executed",
      "why": "Uses supplier, order date, revenue, profit"
    }
  ]
}
```

## Benchmark

`python -m backend.benchmarks.run_question_discovery_benchmark` runs 8 datasets
(sales, employees, products, customers, financial, time-series, small, messy) and
writes `QUESTION_DISCOVERY_REPORT.md` with schema validity, execution success,
tier coverage and cold/warm latency.
