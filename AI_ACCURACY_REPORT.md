# AI_ACCURACY_REPORT

**Date:** 2026-09-21  
**Focus:** Universal analytics demo (4k marketplace orders) + prior financial CSV suite  

Related: `DEMO_BENCHMARK_REPORT.md`, `DEMO_PERFORMANCE_REPORT.md`, `DEMO_QUESTION_BANK.md`, `DEMO_DATA_DICTIONARY.md`

## Deterministic accuracy (ground truth SQL)

| Suite | Dataset | Result |
|---|---|---|
| Demo marketplace bank | 4,000-row orders CSV | **100/100** (98 SQL + 1 abstain + 1 refuse) |
| Financial CSV bank | 3k / 4k | **100/100** (prior) |

p50 / p95 SQL latency (demo 4k): see `DEMO_PERFORMANCE_REPORT.md` (~0.7 ms / ~2.0 ms).

## Production principle

Demo questions are **never** answered from hardcoded maps.  
Flow: question → understanding → schema → plan → SQL → DuckDB → validation → grounded answer.

Ground-truth SQL exists only under `backend/benchmarks/` for evaluation.

## NL→SQL live accuracy

Not fully scored with Groq in this pass. After Render sync of `/marketplace/analytics-demo`, run live simple/hard/very-hard samples.

## Deployment verification

Probed after push `ce9410b`:

| Probe | Result |
|---|---|
| `GET /health` | **200** `agent_ready=true` |
| Frontend Vercel | **200** |
| `POST /marketplace/analytics-demo` | **404** — Render OpenAPI still 12 paths (only `/marketplace/demo`) |
| Local HEAD | includes `/marketplace/analytics-demo` + examples |

**Conclusion:** GitHub `main` has the full demo upgrade; Render is **not** auto-synced. Manual Render redeploy from latest `main` is required before live demo verification of simple/hard/very-hard `/analyze` questions.
