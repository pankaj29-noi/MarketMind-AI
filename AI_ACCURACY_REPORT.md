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

## Question discovery (v2 tiered) — measured

Benchmark: `python -m backend.benchmarks.run_question_discovery_benchmark`
(8 datasets: sales, employees, products, customers, financial, time-series, small, messy)

| Metric | Result |
|---|---|
| Schema-valid displayed questions | **100%** |
| Advanced/expert proof-SQL execution success | **100%** |
| Validated advanced questions | **76** |
| Validated expert questions | **43** |
| Discovery latency cold p50 / max | **31.8 ms / 47.5 ms** |
| Discovery latency warm (cache hit) | **< 1 ms** |

Rich datasets return all four tiers (3 quick / 3 analytics / 5 advanced / 3 expert);
a `name, age` CSV returns quick + analytics only — expert questions are never forced.
Full detail in `QUESTION_DISCOVERY_REPORT.md`.

## Deployment verification — push `14271af`

| Probe | Result |
|---|---|
| `GET /health` | **200** `agent_ready=true` |
| Frontend Vercel | **200** |
| Render OpenAPI paths | **12** (local: 20) |
| `POST /session/{id}/suggested-questions` | not present on Render |
| `POST /session/{id}/followup-questions` | not present on Render |

Same pre-existing gap: Render is not auto-syncing from GitHub `main`. A manual Render
redeploy is required before the tiered question discovery is live in production.
