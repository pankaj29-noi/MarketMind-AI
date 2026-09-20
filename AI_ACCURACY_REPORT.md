# AI_ACCURACY_REPORT

**Date:** 2026-09-21  
**Git HEAD (at write):** see commits below  
**Principle:** Accuracy claims only from measured suites. NL→SQL live accuracy is **not** fully scored here.

Related:
- `AI_ANALYTICS_ARCHITECTURE.md`
- `AI_PERFORMANCE_BASELINE.md`
- `BENCHMARK_REPORT.md` (100-Q deterministic SQL @ 3k)
- `scratch/perf_baseline/BENCHMARK_REPORT_100_4000.md`
- `MODEL_FAILURE_ANALYSIS.md`

---

## 1–2. Accuracy

### Deterministic SQL ground truth (source of truth for analytical shapes)

| Dataset | Suite | OK | Notes |
|---|---|---:|---|
| 3,000 rows | 100 Q | **100/100 (100%)** | easy 20, medium 25, hard 30, very_hard 25 |
| 4,000 rows | 100 Q | **100/100 (100%)** | same SQL, derived sample |

Expected answers = executed `expected_sql` (not fabricated).

### NL→SQL end-to-end (LLM)

| Metric | Status |
|---|---|
| Baseline NL accuracy | **Not fully scored** (prior partial E2E only; see baseline) |
| Final NL accuracy | **Not claimed** — requires controlled Groq run post-deploy |

Partial prior E2E (3 questions) all `execution_success=true` but with high latency/retries under old MCP path.

---

## 3–6. Latency

### Micro (post schema fix)

| Stage | 3k ms | 4k ms |
|---|---:|---:|
| Register | ~158 | ~34 |
| Schema cold | ~18 | ~10 |
| Hard SQL | ~4.5 | ~0.9 |

### 100-Q SQL execution

| Dataset | Avg ms | p95 ms |
|---|---:|---:|
| 3k | 0.776 | 2.468 |
| 4k | ~0.48 | 1.184 |

### LangGraph wall time (historical partial)

| Difficulty | Total ms | Retries |
|---|---:|---:|
| easy | 37,365 | 1 (incl. 10.6s MCP schema) |
| medium | 197,346 | 3 |
| hard | 119,763 | 1 |

Engineering targets (not claims): SIMPLE 1–2s, COMPLEX 2–5s when model/infra allow.

---

## 7. LLM calls / question

| Path | Expected after upgrade |
|---|---|
| SIMPLE + pattern hit | **0** codegen LLM (deterministic SQL) |
| SIMPLE plan | **0** planner LLM |
| SIMPLE ≤5 rows | **0** viz LLM |
| Cache hit | **0** total |
| COMPLEX / VERY_COMPLEX | planner + codegen + (≤1 repair) + report (+ viz if chartable) |

Exact call counts: telemetry records node timings; true invoke counter still TBD.

---

## 8. Cache

| Cache | Isolation | Notes |
|---|---|---|
| Schema profile | per session/table | invalidated on register/evict |
| `/analyze` results | session+fingerprint+question | TTL 600s; tested |

Hit rate in production: measure via `analytics_telemetry.summarize_telemetry()` after traffic.

---

## 9–10. Hard / very-hard SQL accuracy

| Difficulty | 3k | 4k |
|---|---:|---:|
| hard | 30/30 | 30/30 |
| very_hard | 25/25 | 25/25 |

---

## 11. Failure categories

See `MODEL_FAILURE_ANALYSIS.md`. No fabricated NL failure rates.

---

## 12. Remaining limitations

- Full 100-Q NL→SQL Groq accuracy not yet scored
- Render may lag GitHub `main` (suggested-questions historically 404)
- Sandbox AST gaps remain (audit)
- Repair capped to **1** (may increase abstention vs endless retries — intentional)

---

## 13. Commits (this upgrade track)

| SHA | Message |
|---|---|
| `ef44550` | docs: AI architecture + performance baseline |
| `2fbaa2d` | feat: question IR, pattern fast-path, one-shot repair |
| `9fc09eb` | test: expand deterministic suite to 100 questions |
| Prior | MCP skip, analyze cache, Lead restore, window top-N |

---

## 14. Deployment verification

Probed after push `9fc09eb` (2026-09-21):

| Probe | Result |
|---|---|
| `GET /health` | **200** `agent_ready=true` |
| `POST /marketplace/lead/analyze` | **200** |
| `POST /session/.../suggested-questions` | **404** |
| Live OpenAPI paths | **12** (local HEAD has 17) |
| Frontend Vercel | **200** |

**Conclusion:** Render is **not** fully synced to latest `main`. Manual redeploy required for question-IR / fast-path / 100-Q code to be live. Do not claim full deploy success.


