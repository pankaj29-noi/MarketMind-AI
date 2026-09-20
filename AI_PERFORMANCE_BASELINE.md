# MarketMind AI — AI_PERFORMANCE_BASELINE

**Captured:** 2026-09-21 03:50:01  
**Workload:** `scratch/perf_baseline/sample_{3000,4000}.csv` (business financial, 14 cols)  
**Machine:** local macOS, Python 3.13 `.venv`, Groq configured  
**Raw JSON:** `scratch/perf_baseline/ai_perf_baseline_raw.json`  
**Related:** `PERFORMANCE_BASELINE.md` (earlier MCP-era capture), `AI_ANALYTICS_ARCHITECTURE.md`

All numbers below are **measured**. Incomplete LLM-call instrumentation is called out explicitly — not invented.

---

## Executive finding

For 3k–4k row CSVs:

| Category | Finding |
|---|---|
| DuckDB ingest / SQL | **Not** the bottleneck (register tens–hundreds ms; hard SQL &lt;5 ms) |
| Schema (post MCP-skip) | Cold rich profile **~11–18 ms**; hot **~0 ms** |
| Deterministic validation | Requirement coverage + SQL validate **&lt;1 ms** |
| Dominant cost | **LLM-bound LangGraph nodes** (planner, codegen, validator LLM paths, viz, report) + retries |

---

## Microbenchmarks (no LLM)

Means over 3 register cycles (schema/SQL) or 20–50 validation iterations.

### 3,000 rows

| Stage | Mean ms |
|---|---:|
| DuckDB `register_csv` | **158.18** |
| `schema_profiler_node` cold (rich) | **17.75** |
| `schema_profiler_node` hot | **0.005** |
| Session schema cache hit | **0.003** |
| Simple `COUNT(*)` | **0.10** |
| Hard CTE + `%` share + `RANK` | **4.52** |
| `check_requirement_coverage` | **0.15** |
| `validate_sql` | **0.02** |

### 4,000 rows

| Stage | Mean ms |
|---|---:|
| DuckDB `register_csv` | **34.05** |
| `schema_profiler_node` cold | **10.42** |
| Hot / cache | **~0.00** |
| Simple `COUNT(*)` | **0.10** |
| Hard CTE + window | **0.91** |
| Requirement coverage | **0.08** |
| `validate_sql` | **0.02** |

---

## Complexity classification (deterministic)

| Question | Class |
|---|---|
| How many rows are there? | `SIMPLE` |
| Show top 5 industries by average Data_value | `COMPLEX` |
| Find top 10 by revenue share of total, exclude fewer than 5 orders | `VERY_COMPLEX` |

Note: `MEDIUM` band is not yet in the classifier (upgrade target).

---

## LangGraph end-to-end (partial, measured earlier)

Source: `scratch/perf_baseline/pipeline_direct.json`  
**Caveat:** Easy run still included pre-fix MCP schema cost (~10.6 s). Medium/hard reused cached schema. `llm_calls` counter was **not instrumented** (recorded 0); LLM time is embedded in node durations.

| Difficulty | Total ms | Retries | Notable node costs (ms) |
|---|---:|---:|---|
| easy | **37,365** | 1 | schema **10,632**; report **14,264**; viz gen **3,264**; planner×2 ~3k |
| medium | **197,346** | 3 | planner×4 ~66k; codegen×4 ~65k; validator LLM×2 ~36k; report ~16k |
| hard | **119,763** | 1 | planner×2 ~37k; codegen×2 ~34k; validator ~15k; report ~22k |

**Implication:** Correctness retries and report/viz LLM calls dominate wall time once schema is fixed. Fast-path + one-shot repair + skip SIMPLE viz are the highest-leverage next steps.

---

## Historical schema bottleneck (for comparison)

Pre-fix MCP `get_dataset_schema` on CSV sessions: **~10,782 ms** then fail (subprocess cannot see in-memory DuckDB). Documented in `PERFORMANCE_BASELINE.md`. **Fixed** via in-process rich profiling.

---

## What this baseline does *not* claim

- Full 100-question NL→SQL accuracy (suite expansion pending)
- Accurate LLM-calls-per-question (instrumentation pending)
- Live Render latency (cold starts dominate; separate deploy probes)

---

## Reproduction

```bash
cd DataAgent-Pro
.venv/bin/python - <<'PY'
# re-run the measurement block that wrote
# scratch/perf_baseline/ai_perf_baseline_raw.json
PY
```
