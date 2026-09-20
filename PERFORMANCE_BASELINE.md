# MarketMind AI — PERFORMANCE_BASELINE

**Captured:** 2026-09-21
**Workload:** `business_financial_sample_3000_rows.csv` (3,000 rows, 14 cols) + derived 4,000-row sample
**Machine:** local macOS, Python 3.13 `.venv`, Groq key configured, local Postgres **down**
**Git context:** `main` @ `2064733` (+ local audit docs)

Artifacts: `scratch/perf_baseline/microbench.json`, profiling scripts under `scratch/perf_baseline/`.

---

## Executive finding

For 3k–4k row CSVs, **DuckDB is not the bottleneck**. Ingest (~40 ms) and hard analytical SQL (~2–5 ms) are negligible.

The dominant costs are:

1. **MCP stdio schema probe on every CSV analyze** (~**10.8 s**, then fails)
2. **LLM calls** (multiple per question: supervisor / planner / codegen / report / viz)
3. **False-positive SQL quality validation** → retries (e.g. “Missing LIMIT for Top/Bottom N”)
4. **Postgres pool wait** (~8 s) when `DATABASE_URL` points at a dead local Postgres during incidental session lookups

Accuracy is also hurt when MCP schema fails (subprocess cannot see in-memory DuckDB) and the profiler burns time before falling back.

---

## Dataset under test

| File | Rows | Cols | Size |
|---|---:|---:|---:|
| `scratch/perf_baseline/sample_3000.csv` | 3000 | 14 | ~619 KB |
| `scratch/perf_baseline/sample_4000.csv` | 4000 | 14 | (derived, seed=42) |

Columns include: `Series_reference`, `Period`, `Data_value`, `Series_title_1`…`Series_title_5`, etc.

---

## Microbenchmarks (no LLM)

Method: `session_manager.register_csv` + `get_schema` + `profile_dataset` + DuckDB SQL.
Times in **milliseconds** (mean of N runs).

### 3,000 rows

| Stage | Mean ms | Runs |
|---|---:|---|
| DuckDB `read_csv_auto` register | **38.96** | 5 |
| Thin `get_schema` (cold-ish) | **1.38** | 5 |
| Thin `get_schema` (hot) | **0.50** | 5 |
| Rich `profile_dataset` (adaptive profiler) | **13.21** | 3 |
| Simple `GROUP BY` + `ORDER BY` + `LIMIT 10` | **0.40** | 5 |
| Hard CTE + window `RANK` + share % | **4.74** | 5 |
| `get_column_stats` × 14 columns | **16.79** | 2 |

### 4,000 rows

| Stage | Mean ms | Runs |
|---|---:|---|
| DuckDB register | **37.55** | 5 |
| Thin `get_schema` | **0.63** | 5 |
| Rich `profile_dataset` | **11.43** | 3 |
| Simple agg | **0.47** | 5 |
| Hard CTE + windows | **1.63** | 5 |

**Interpretation:** At 3k–4k rows, SQL execution stays under ~5 ms. Profiling all columns richly is ~12 ms once — cheap enough to cache per session.

---

## MCP schema overhead (critical)

Same session, table already registered in-process:

| Path | Mean ms | Result |
|---|---:|---|
| Direct `get_schema` | **2.0** | success |
| Rich `profile_dataset` | **12.0** | success |
| `invoke_mcp_tool_sync("get_dataset_schema")` | **10781.8** | **error** |

MCP failure mode (observed):

1. Spawns FastMCP stdio subprocess (`backend/mcp/client.py`)
2. Subprocess cannot see the parent’s in-memory DuckDB session
3. `is_csv_session` false → attempts Postgres → **8 s pool wait** → error
4. Parent `schema_profiler_node` falls back to in-process `get_schema`

Current code path (`schema_profiler.py`): **always tries MCP first** for non-marketplace CSV uploads.

**Waste per question (first schema pass):** ~10–11 seconds of guaranteed-useless work before a 1–12 ms local profile.

During a long analyze run, MCP banners appeared **repeatedly** (schema + other tool boundaries), multiplying the cost.

---

## Full LangGraph pipeline (partial / interrupted)

Direct `create_agent_graph(None)` + Groq was started for easy/medium/hard questions.

Observed before abort (~5+ minutes, incomplete):

| Issue | Evidence |
|---|---|
| Repeated MCP FastMCP startups | Multiple stdio server banners mid-run |
| SQL quality validator blocks | `Missing LIMIT for Top/Bottom N queries` (CRITICAL) even when query intent may already be limited via window/`QUALIFY` |
| Semantic validator retries | Medium question flagged “average of averages” → reflection/retry loop |
| Groq model fallback | `openai/gpt-oss-120b` / `qwen/qwen3.6-27b` failures logged |
| Upload via TestClient with dead Postgres | **~8081 ms** upload (pool wait inside `create_session`) then `/analyze` **503** when lifespan left `agent_graph=None` under some TestClient/pool failure paths |

**Honest status:** Full end-to-end latency / LLM-call counts for easy/medium/hard were **not** completed in this baseline capture because the run was dominated by MCP + retry loops and was terminated to avoid unbounded LLM spend. Microbenchmarks + MCP timing above are complete and reproducible.

---

## Bottleneck ranking (3k–4k CSV)

| Rank | Bottleneck | Approx cost | Fix priority |
|---:|---|---|---|
| 1 | MCP schema subprocess on CSV sessions | ~10.8 s / call, always fails | **P0** |
| 2 | Multi-LLM supervisor/planner/codegen/report/viz chain | seconds–tens of seconds / call | **P0/P1** |
| 3 | SQL validator false positives → repair loops | +1–N LLM + re-exec | **P1** |
| 4 | Dead Postgres pool waits on session metadata | ~8 s | **P1** (soft-fail faster) |
| 5 | Thin schema vs rich profile (missing stats for LLM) | accuracy risk | **P1** |
| 6 | DuckDB ingest / SQL | <50 ms | already fine |

---

## What is already good

- CSV loaded **once** into session DuckDB (`CREATE OR REPLACE TABLE … read_csv_auto`)
- Scratch file kept for restore after eviction
- Adaptive `profile_dataset` already builds compact stats (nulls, uniques, samples, roles) without shipping full CSV to the LLM
- Schema profile can be reused from LangGraph checkpointer state when `dataset_id` matches
- Hard window/CTE SQL on 4k rows is milliseconds

---

## Target after optimization (not yet measured)

| Metric | Baseline | Target (3k–4k) |
|---|---|---|
| Schema path (CSV) | ~10.8 s MCP fail + fallback | **<20 ms** cached rich profile |
| Simple question E2E | unknown (blocked) | minimize LLM calls (≤2–3) |
| Complex question E2E | unknown (blocked) | prefer SQL-only; 1 repair max |
| Hard SQL exec | ~2–5 ms | keep |

Next steps (implementation phase): skip MCP for in-process DuckDB sessions; cache rich profiles on the session; complexity-based routing; safe query-result cache; 50-question benchmark harness with ground-truth SQL.

---

## Reproduction commands

```bash
cd DataAgent-Pro
.venv/bin/python - <<'PY'
# see scratch scripts / re-run microbench block from this audit
PY
```

Do not treat incomplete LLM E2E numbers as fabricated successes — they are explicitly marked incomplete above.
