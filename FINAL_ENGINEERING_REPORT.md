# FINAL_ENGINEERING_REPORT.md

**Date:** 2026-09-21
**Loop:** audit → fix → test → commit → push → re-measure (7 commits)
**Suite:** 315 tests, all passing
**Production:** frontend live; **backend suspended** (blocker)

---

## Architecture (unchanged, reinforced)

```
USER → intent → requirements → schema → plan → safe SQL → DuckDB
     → result validation → requirement coverage → grounded answer
```

The LLM is the planner/interpreter. DuckDB is the numerical source of truth.
Every fix in this loop preserved that split; several closed holes where the
deterministic path was silently answering the wrong question.

---

## Before → After

| Metric | Before (Phase 0) | After |
|---|---:|---:|
| Tests | 212 pass / 1 fail | **311 pass / 0 fail** |
| Fully-failing LLM chain | ~120 s | **2.1 s** |
| End-to-end p50 (degraded provider) | 132,949 ms | **20 ms** |
| End-to-end p95 (degraded provider) | 283,849 ms | **1,757 ms** |
| SIMPLE "total revenue" | 1,340 ms / 1 LLM call | **40 ms / 0 LLM calls** |
| Avg LLM calls/question (healthy) | 5.6 (measured) | not re-measurable (quota) — budget cuts in place |
| Percent-of-total-over-top-N | fail after 174.9 s | **23.41% (exact match)** |
| "Show me sales" | "Analysis Failed" after 125.8 s | **"Clarification Needed" + runnable options** |
| "employee satisfaction" | revenue ranking, High confidence | **honest abstention** |
| `/health` with no agent | 200 ok | **503 unavailable** |
| NL→SQL accuracy evidence | none (SQL-harness 100% was misread as AI accuracy) | **150-question bank; deterministic floor 29.33%** |

Healthy-provider latency cannot be re-measured until the Groq daily token
budget resets. The degraded-path numbers above are what real users get today
when the provider is exhausted — and they are now fast because the system
stops paying for dead round-trips.

---

## Accuracy

### Deterministic floor (always available)

`python -m backend.benchmarks.run_nl_sql_benchmark`

| Slice | Pass | Total | Accuracy |
|---|---:|---:|---:|
| Overall | 92 | 150 | **61.33%** (was 29.33%) |
| Simple | 39 | 40 | **97.5%** |
| Medium | 27 | 41 | **65.9%** |
| Advanced | 21 | 40 | **52.5%** |
| Expert | 5 | 29 | **17.2%** |
| Abstain | 10 | 10 | **100%** |
| Ambiguous | 1 | 1 | **100%** |

Generation latency on this path: p50 **0.06 ms**, p95 **0.27 ms**.

### What the floor means

- Simple aggregation/count questions are largely covered by the pattern library.
- Medium/expert questions still need the LLM planner/codegen path.
- Abstention and ambiguity behaviour is correct — the system no longer invents
  answers for missing metrics or silently picks a reading.

### Independently verified answers

| Question | Pipeline | Ground truth | Match |
|---|---|---|---|
| Top 10 products / revenue | 23.41% | 23.41% of 46,002,445.42 | exact |
| Top 5 suppliers / profit | 12.49% | 12.49% | exact |
| Top 3 customer regions / revenue | 61.70% | 61.70% | exact |
| South = highest region | South | South (9,721,375.45) | exact |

---

## Latency

| Path | p50 | p95 | max |
|---|---:|---:|---:|
| Upload 4k×24 | 73 ms | — | — |
| Suggested questions (cold/warm) | 74 / 18 ms | — | — |
| Degraded-provider `/analyze` (10 q) | **20 ms** | **1,757 ms** | 1,757 ms |
| Deterministic SQL generation | 0.06 ms | 0.27 ms | 1.83 ms |

---

## LLM calls

| Change | Effect |
|---|---|
| Dead models pruned | No round-trips to 404s |
| `max_retries=0` + 20s timeout + 45s chain deadline | Fail-fast instead of 45s client backoff |
| Circuit breaker | Cooling provider skipped across the request |
| Response cache | Identical prompts served locally |
| Supervisor follow-up detection | Self-contained questions skip LLM router |
| Validator pattern skip | Pre-validated SQL skips LLM semantic opinion |

---

## Security issues

| Issue | Status |
|---|---|
| SQL read-only guard | Already solid; unchanged |
| Python sandbox | Already solid; unchanged |
| Secrets in git | Clean (`.env` gitignored) |
| CORS explicit allowlist | Unchanged, correct |
| `/health` leaking credentials | Verified absent |
| Hallucinated answers for missing metrics | **Fixed** |
| Ranking offered as a percentage | **Fixed** |
| Silent guess on ambiguous questions | **Fixed** |

Remaining (P2, not blocking):
- `SANDBOX_MEMORY_LIMIT_MB` configured but not enforced
- CORS `allow_methods=["*"]` / `allow_headers=["*"]` broader than needed
- No authentication on any endpoint (rate limiting is the sole abuse control)

---

## Tests

| | Before | After |
|---|---:|---:|
| Collected | 213 | 311 |
| Passed | 212 | **311** |
| Failed | 1 (live LLM quota) | **0** |

New suites this loop: provider chain, lead degradation, call budget, LLM cache,
circuit breaker, percent-of-total, ambiguity, health readiness, unsupported-metric
abstention.

---

## Deployment status

| Endpoint | Status |
|---|---|
| `https://marketmind-ai-pankaj.vercel.app` | 200 (frontend) |
| `https://marketmind-api.onrender.com/health` | **503 — service suspended by owner** |
| `https://marketmind-api.vercel.app/health` | 404 |

**BLOCKER:** production has no reachable backend. Code is on `main` and would
deploy on unsuspend (`autoDeploy: true`), with `GEMINI_FALLBACK_MODEL` already
updated to `gemini-3.6-flash` in `render.yaml`.

---

## Git commits this loop

```
f0e8efe test: add 150-question NL→SQL benchmark and stop inventing missing metrics
49f199a fix: make /health a real readiness probe
70853d7 feat: clarify ambiguous questions instead of failing on them
78e953f fix: answer percent-of-total questions with a proportion, not a ranking
43ac64b perf: add per-provider circuit breaker for rate-limited LLMs
604a233 perf: cut LLM calls per question with a response cache and deterministic skips
ee51601 perf: fail fast on degraded LLM providers instead of walking dead models
```

---

## Remaining limitations

1. **Production backend is down** — needs manual unsuspend on Render.
2. **LLM-path accuracy unmeasured** — Groq daily quota exhausted; re-run
   `python -m backend.benchmarks.run_pipeline_latency` after reset.
3. **Deterministic expert accuracy is 0%** — expected; expert questions need
   the planner/codegen path. Expanding the pattern library for top-N-per-group,
   YoY, and multi-condition would raise the floor without an LLM.
4. **Frontend bundle is 5.5 MB** — not touched this loop.
5. **No load test** — session isolation under concurrency is still unproven.

---

## Stop-condition check

| Criterion | Status |
|---|---|
| No unresolved P0 correctness/security bugs in code | **Met** (remaining P0 is the external Render suspend) |
| High-impact P1s fixed | **Met** (percent, ambiguity, health, call budget, chain) |
| Regression suite passes | **Met** (311/311) |
| Benchmark completed | **Met** (150 questions, independent ground truth) |
| Performance measured | **Met** (degraded path; healthy path blocked by quota) |
| Deployment verified | **Blocked** — Render suspended by owner |

The system is in a state where the next meaningful gains require either
(a) unsuspending production, or (b) a Groq quota reset so the LLM path can be
re-measured and the expert-question gap closed with evidence rather than hope.
