# MarketMind AI — PERFORMANCE_REPORT

**Date:** 2026-09-21  
**Focus:** 3,000–4,000 row CSV analytics — fast, accurate, grounded, safe

Related artifacts:
- `PERFORMANCE_BASELINE.md` (pre-change measurements)
- `BENCHMARK_REPORT.md` (50-question deterministic SQL suite @ 3k rows)
- `scratch/perf_baseline/BENCHMARK_REPORT_4000.md` (same suite @ 4k rows)
- `scratch/perf_baseline/pipeline_direct.json` (pre-fix LangGraph node timings)

---

## 1. Baseline

| Stage (3k CSV) | Before |
|---|---|
| DuckDB register | ~39 ms |
| Thin schema | ~1–2 ms |
| Rich profile | ~12–13 ms |
| Hard SQL (CTE/windows) | ~2–5 ms |
| **MCP `get_dataset_schema`** | **~10,782 ms** then **always fails** |
| Full NL analyze E2E | Partial (`pipeline_direct.json`): easy ~37s (schema alone **10.6s**), medium ~197s (3 retries), hard ~120s |

Postgres pool wait on dead local DB: ~8 s (reduced to 2 s).

---

## 2. Bottlenecks found

1. **P0 — MCP stdio schema/tool calls on CSV path** (~10.8 s/call, useless for in-memory DuckDB).
2. **P1 — Thin schema** for LLM (missing null%, uniques, min/max, roles).
3. **P1 — SQL quality false positive** rejecting window `QUALIFY` / `RANK` top-N without `LIMIT`.
4. **P1 — Session lookup** tried Postgres before memory → multi-second stalls.
5. **P0 product regression** — `/marketplace/lead/analyze` route missing (fixed).
6. **P1 — Repeated viz LLM** even for trivial SIMPLE scalar results.
7. **P1 — Analysis result cache helpers** existed but were not wired into `/analyze`.

DuckDB itself is **not** a bottleneck at 3k–4k rows.

---

## 3. Optimizations implemented

| Change | Files |
|---|---|
| Skip MCP for CSV schema; rich `profile_dataset` + session cache | `schema_profiler.py`, `analytics_perf.py`, `session_manager.py` |
| Richer LLM schema context | `demo_data.py` `format_schema_context_for_llm` |
| Remove MCP from viz chartability + analysis stats | `visualization_executor.py`, `analysis_engine.py` |
| Accept window top-N without LIMIT | `sql_quality_validator.py` |
| Memory-first session lookup; pool wait 8s→2s | `repository.py`, `connection.py` |
| Broader deterministic SQL routing | `supervisor.py` |
| Restore Lead Intelligence route | `main.py` |
| Complexity classifier + session-isolated result cache | `analytics_perf.py` |
| **Wire result cache into `/analyze`** | `main.py` |
| **Skip visualization for SIMPLE ≤5-row results** | `supervisor.py` |
| **Cap report table payloads at 200 rows** | `report_agent.py`, `analytics_perf.py` |
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

### Schema path AFTER fix (measured 2026-09-21)

| Stage | ms |
|---|---:|
| `schema_profiler_node` cold (rich, 3k) | **~176** |
| `schema_profiler_node` hot (state cache) | **~0.01** |
| `get_or_build_csv_schema_profile` session cache | **~0.00** |

**vs baseline MCP fail path:** ~10,782 ms → ~176 ms on first schema (~**61×**), subsequent questions ~0 ms schema.

Pre-fix LangGraph easy run had `schema_profiler: 10632 ms` (`pipeline_direct.json`). That stage alone is now sub-200 ms.

### LLM-call reduction (structural + measured)

| Before | After |
|---|---|
| MCP schema spawn every CSV analyze | Removed |
| MCP chartability spawn | Removed |
| MCP correlation/outlier spawn | Removed |
| False LIMIT repairs on QUALIFY | Removed |
| Viz LLM for SIMPLE ≤5-row answers | Skipped → REPORT |
| Identical question re-ask (same session/fingerprint) | Cache hit → 0 LLM |

Honest gap: full 50-question NL→SQL→report Groq scoring not re-run in this pass (cost). SQL ground-truth suite covers analytical correctness of the hard query shapes.

---

## 7. Cache performance

| Cache | Behavior |
|---|---|
| Session `schema_profile_cache` | Per session/table; invalidated on `register_csv` / eviction |
| Graph state schema reuse | Prefers `rich` profiles |
| `/analyze` result cache | Session + dataset + fingerprint + normalized question; TTL 600s; max 64/session; isolation tested |

---

## 8. Frontend

- Results tables already paginate (10 rows/page) in `ResultsTableCard`.
- Backend now caps report table payloads at **200 rows** with `truncated` + `row_count_total`.
- Analyze guarded by `isAnalyzing` (no duplicate concurrent posts).
- Trace polling only while an analyze is in flight.

---

## 9. Remaining limitations

- Full LangGraph NL accuracy @ 50 questions with live LLM not scored in `BENCHMARK_REPORT.md` (SQL ground-truth only).
- Render deploy sync historically lagged GitHub `main` — verify after each push.
- Sandbox AST gaps (`open` / unbound `os` / `getattr` eval) from prior audit remain.
- Free Render cold starts still dominate perceived UI latency.

---

## 10. Git commits (performance track)

| SHA | Message |
|---|---|
| `e98abda` | fix(api): restore marketplace lead analyze route |
| `3099456` | perf: skip MCP for CSV schema and cache rich DuckDB profiles |
| `f7bcef0` | fix: accept window top-N SQL and fail-fast session lookups |
| `7f939d8` | test: add 50-question CSV analytics benchmark and perf regressions |
| `3687646` | docs: record CSV performance baseline, benchmark, and audit |
| *(this push)* | perf: wire analyze cache, skip SIMPLE viz, cap report rows |

---

## 11. Deployment verification

**Pushed:** `9574b59` → `origin/main` (https://github.com/pankaj29-noi/MarketMind-AI)

| Probe | Result |
|---|---|
| `GET https://marketmind-ai-93u1.onrender.com/health` | **200** `{"status":"ok","agent_ready":true}` |
| `POST /marketplace/lead/analyze` | **200** (Lead route live) |
| `POST /session/{id}/suggested-questions` | **404** — not on live OpenAPI |
| Live OpenAPI path count | **12** |
| Local OpenAPI path count (`main` HEAD) | **17** (includes suggested-questions) |
| Frontend `https://marketmind-ai-pankaj.vercel.app` | **200** |

**Conclusion:** Render is **partially** synced (Lead is live; adaptive suggested-questions + latest analyze-cache commit are **not** confirmed on the running service). Manual Render redeploy from latest `main` is required for full parity. Do not claim full auto-deploy success.


---

## Test suite (targeted)

- `pytest backend/tests/test_analytics_perf.py` — pass (includes 3k schema <2s, no MCP)
- `pytest backend/tests/test_marketplace_lead.py` — pass (Lead route restored)
