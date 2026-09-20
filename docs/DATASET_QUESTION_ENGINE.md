# Dataset Question Engine

## Strategy

Hybrid **deterministic-first** generation:

1. Profile uploaded CSV in DuckDB (aggregates + samples only).
2. Assign semantic types with confidence (`monetary_measure`, `geographic_dimension`, …).
3. Build a capability map (dimensions / measures / time / entities / ops).
4. Expand structured templates into `(question_text, proof_sql, category, difficulty)`.
5. Validate every candidate:
   - columns exist
   - SQL quality / read-only gate
   - DuckDB execution succeeds
6. Deduplicate by intent+columns, rank, diversify categories/difficulty.
7. Cache by `(session_id, dataset_id, fingerprint)`.

No full CSV is sent to an LLM in v1.

## API

`POST /session/{session_id}/suggested-questions`

## Execution

UI clicks send the **exact** question string to existing `POST /analyze`.

## Isolation

New upload → frontend clears suggestion state → new fingerprint → new cache entry.
Marketplace multi-table demo continues to use curated samples.

## Limitations

- Single-table CSV uploads only (not multi-table joins).
- Ambiguous columns (`value`/`amount`) with low confidence are underweighted.
- Follow-up suggestions after results are not yet implemented (planned).
- Proof SQL uses DuckDB features (`DATE_TRUNC`, `CORR`); wording is tuned for the analytics engine but LLM path may still rephrase SQL.
