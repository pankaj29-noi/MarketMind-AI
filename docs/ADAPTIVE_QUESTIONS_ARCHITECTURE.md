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
