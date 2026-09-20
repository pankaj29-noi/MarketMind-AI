# MarketMind AI — PERFORMANCE_REPORT

**Date:** 2026-09-21
**Focus:** 3,000–4,000 row CSV analytics — fast, accurate, grounded, safe

Related artifacts:
- `PERFORMANCE_BASELINE.md` (pre-change measurements)
- `BENCHMARK_REPORT.md` (50-question deterministic SQL suite @ 3k rows)
- `scratch/perf_baseline/BENCHMARK_REPORT_4000.md` (same suite @ 4k rows)

---

## 1. Baseline

| Stage (3k CSV) | Before |
|---|---|
| DuckDB register | ~39 ms |
| Thin schema | ~1–2 ms |
| Rich profile | ~12–13 ms |
| Hard SQL (CTE/windows) | ~2–5 ms |
| **MCP `get_dataset_schema`** | **~10,782 ms** then **always fails** (subprocess cannot see in-memory DuckDB; falls through to dead Postgres ~8 s) |
| Full NL analyze E2E | Incomplete (dominated by MCP + retry loops; aborted) |

Postgres pool wait on dead local DB: ~8 s (reduced to 2 s after fix).
Upload via TestClient with dead Postgres: ~8 s.

---

## 2. Bottlenecks found

1. **P0 — MCP stdio schema/tool calls on CSV path** (~10.8 s/call, useless for in-memory DuckDB). Also hit visualization chartability + analysis correlation/outlier paths.
2. **P1 — Thin schema** for LLM (missing null%, uniques, min/max, roles) despite adaptive profiler already existing.
3. **P1 — SQL quality false positive** rejecting window `QUALIFY` / `RANK` top-N without `LIMIT`.
4. **P1 — Session lookup** tried Postgres before memory → multi-second stalls.
5. **P0 product regression** — `/marketplace/lead/analyze` route missing (dead code after suggested-questions insert).

DuckDB itself is **not** a bottleneck at 3k–4k rows.

---

## 3. Optimizations implemented

| Change | Files |
|---|---|
| Skip MCP for CSV schema; use rich `profile_dataset` + session cache | `schema_profiler.py`, `analytics_perf.py`, `session_manager.py` |
| Richer LLM schema context (null%, unique, min/max, role, fingerprint) | `demo_data.py` `format_schema_context_for_llm` |
| Remove MCP from visualization chartability + analysis correlation/outliers | `visualization_executor.py`, `analysis_engine.py` |
| Accept window top-N without LIMIT | `sql_quality_validator.py` |
| Memory-first session lookup; pool wait 8s→2s | `repository.py`, `connection.py` |
| Slightly broader deterministic SQL routing (without stealing ambiguous/Python cases) | `supervisor.py` |
| Restore Lead Intelligence route | `main.py` |
| Question complexity classifier + session-isolated result cache helpers | `analytics_perf.py` |
| 50-question benchmark harness + tests | `backend/benchmarks/*`, `test_analytics_perf.py` |

---

## 4–6. Benchmark / accuracy / latency results

### Deterministic SQL ground truth (50 questions)

| Dataset | OK | Avg SQL ms | p95 SQL ms |
|---|---:|---:|---:|
| **3,000 rows** | **50/50 (100%)** | 0.744 | 2.570 |
| **4,000 rows** | **50/50 (100%)** | 0.520 | 1.197 |

Difficulties (3k): easy 10/10, medium 10/10, hard 15/15, very_hard 15/15.

Expected answers = executed `expected_sql` (not fabricated).

### Schema path after fix

| Stage | ms |
|---|---:|
| `schema_profiler_node` cold (rich) | **~117** (first profile; includes stats) |
| `schema_profiler_node` with cached state | **~0.01** |
| `get_or_build_csv_schema_profile` cached | **~0.00** |

**Estimated savings vs baseline MCP fail path:** ~10.8 s → ~0.1 s on first schema (~**100×**), subsequent questions ~0 ms schema.

### LLM-call reduction

Not fully re-measured end-to-end with Groq in this pass (cost/time). Structural reductions:

- 0 MCP subprocess spawns on CSV schema / viz chartability / analysis stats
- Deterministic SQL routing retained for common aggregation language
- Window top-N no longer forces repair loops solely for missing LIMIT

Honest gap: full NL→SQL→report latency + LLM calls/question still need a controlled live Groq run after Render deploy.

---

## 7. LLM-call reduction (structural)

| Before | After |
|---|---|
| MCP schema spawn every CSV analyze | Removed |
| MCP chartability spawn | Removed (local `is_result_chartable`) |
| MCP correlation/outlier spawn | Removed (local pandas paths) |
| False LIMIT repairs on QUALIFY | Removed |

---

## 8. Cache performance

| Cache | Behavior |
|---|---|
| Session `schema_profile_cache` | Per session/table; invalidated on `register_csv` / eviction |
| Graph state schema reuse | Unchanged; now prefers `rich` profiles |
| Analysis result cache helpers | Session + dataset + fingerprint + normalized question; isolation tested |

---

## 9. Remaining limitations

- Full LangGraph NL accuracy @ 50 questions with live LLM not yet scored in `BENCHMARK_REPORT.md` (SQL ground-truth only).
- Adaptive suggested-questions still not confirmed on Render until deploy sync.
- Sandbox AST gaps (`open` / unbound `os` / `getattr` eval) from prior audit remain.
- Free Render cold starts still dominate perceived UI latency.
- Result-cache not yet wired into `/analyze` response path (helpers + tests ready).

---

## 10. Git commits

(Filled at commit time — see `git log`.)

---

## 11. Deployment verification

Pending push + Render/Vercel auto-deploy. Will verify:

- `GET https://marketmind-ai-93u1.onrender.com/health`
- OpenAPI includes `/marketplace/lead/analyze` and suggested-questions
- Frontend https://marketmind-ai-pankaj.vercel.app

Do not claim live deploy success until probes return evidence.

---

## Test suite

`python -m pytest -q` → **191 passed** after these changes.
