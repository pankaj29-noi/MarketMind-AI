# ENGINEERING_BASELINE.md — Phase 0 Measured Baseline

**Measured:** 2026-09-21
**Machine:** local dev (macOS, Python 3.13 venv, DuckDB in-memory)
**Dataset under test:** `data/marketmind_demo_marketplace_4000.csv` — 4,000 rows × 24 columns
**Rule applied:** every number below was produced by running a command. Nothing is estimated. Where a value could not be measured, it is marked `NOT MEASURED` with the reason.

---

## 1. Test suite

Command: `DEMO_MODE=auto python -m pytest backend/tests -q`

| Metric | Value |
|---|---:|
| Tests collected | 213 |
| Passed | 212 |
| Failed | 1 |
| Skipped | 0 |
| Wall time | 13.73 s |

**The single failure:**

```
FAILED backend/tests/test_marketplace_lead.py::TestMarketplaceAPI::test_lead_analyze
AssertionError: assert 'needs_info' == 'complete'
```

Captured cause in the same test log:

```
ERROR backend.marketplace.lead.nodes: Requirement parser failed: Error code: 429 -
Rate limit reached for model `openai/gpt-oss-120b` ... tokens per day (TPD):
Limit 200000, Used 199777, Requested 702
```

This test performs a **live LLM call**, so it fails whenever the Groq daily token quota is exhausted. It is a non-hermetic test, not a logic regression.

Test distribution across 25 files (top 10):

| File | Tests |
|---|---:|
| `test_marketplace_lead.py` | 19 |
| `test_components.py` | 18 |
| `test_semantic_redteam.py` | 17 |
| `test_requirement_coverage.py` | 15 |
| `test_analytics_demo_fallback.py` | 15 |
| `test_marketplace_analytics_fallback.py` | 12 |
| `test_sql_readonly_guard.py` | 11 |
| `test_code_generation_semantics.py` | 11 |
| `test_adaptive_questions.py` | 11 |
| `test_sql_quality_validator.py` | 10 |

---

## 2. Lint and type status

| Check | Status |
|---|---|
| Frontend `npx tsc --noEmit` | **Clean** — no output, exit 0 |
| Backend `ruff` | **NOT MEASURED** — `No module named ruff` in the project venv |
| Backend `mypy` | **NOT MEASURED** — `No module named mypy` in the project venv |

There is currently **no enforced Python lint or type gate** in this environment.

---

## 3. Backend startup

| Metric | Value |
|---|---|
| `from backend.main import app` | OK, 1,083.4 ms |
| Registered routes | 20 |
| `GET /health` (local TestClient) | HTTP 200 in 5.0 ms |
| `/health` body | `{'status': 'ok', 'service': 'marketmind-api', 'agent_ready': False}` |

Note `agent_ready: False` — the health endpoint reports OK even though the LangGraph agent is not marked ready, so health is not a true readiness signal.

Route inventory:

```
GET  /health                                POST /upload
POST /marketplace/demo                      POST /marketplace/analytics-demo
GET  /marketplace/analytics-demo/examples   POST /session/{session_id}/suggested-questions
POST /session/{session_id}/followup-questions
POST /marketplace/lead/analyze              POST /marketplace/feedback
GET  /marketplace/observability/runs        GET  /marketplace/observability/summary
POST /analyze                               GET  /execution/{session_id}/trace
GET  /history/{session_id}                  GET  /report/{execution_id}/pdf
GET  /metrics                               (+ /docs, /redoc, /openapi.json, /docs/oauth2-redirect)
```

---

## 4. Frontend build

Command: `npm run build` in `frontend/`

| Metric | Value |
|---|---:|
| Build result | **Success** |
| Build time | 1.24 s |
| `dist/index.html` | 1.06 kB (gzip 0.54 kB) |
| `dist/assets/index-*.css` | 126.51 kB (gzip 20.24 kB) |
| `dist/assets/index-*.js` | **5,473.41 kB (gzip 1,637.60 kB)** |

Build emits: `Some chunks are larger than 500 kB after minification.` The app ships as a single ~5.5 MB JS chunk with no code splitting.

---

## 5. API / deployment health (live probes)

| Endpoint | Result |
|---|---|
| `https://marketmind-api.onrender.com/health` | **HTTP 503** — `This service has been suspended by its owner` (0.40 s) |
| `https://marketmind-api.vercel.app/health` | **HTTP 404** (0.17 s) |
| `https://marketmind-ai-pankaj.vercel.app` | HTTP 200 (0.20 s) |
| `https://frontend-rho-nine-9ijte1vo4k.vercel.app` | HTTP 200 (0.20 s) |
| `https://marketmind-ai.vercel.app` | HTTP 200 (0.66 s) |

**Production is currently non-functional end to end.** The frontends are live, but no reachable backend exists: Render is suspended and no working Vercel API deployment answers `/health`. Any deployed UI can load but cannot analyze.

---

## 6. LLM provider health (measured directly, per model)

Trivial prompt (`"Reply OK."`):

| Model | Result |
|---|---|
| Groq `openai/gpt-oss-120b` | OK — 280 / 1,012 / 1,147 / 1,536 ms across calls (avg 943 ms over 3) |
| Groq `openai/gpt-oss-20b` | OK — 384 ms, 553 ms |
| Groq `qwen/qwen3.6-27b` | **404 `model_not_found`** — 142 ms |
| Gemini `gemini-2.0-flash` | **404 no longer available** — 1,327 ms |
| Gemini `gemini-1.5-flash` | **404 not found** — 443 ms |
| Gemini `gemini-3.6-flash` | **429 RESOURCE_EXHAUSTED** — 35,831 ms |
| Gemini `gemini-flash-latest` | **429 RESOURCE_EXHAUSTED** — 36,452 ms |

Realistic prompt (10,004 chars, the size the planner actually sends):

| Model | Result |
|---|---|
| Groq `openai/gpt-oss-120b` | **429 tokens-per-day** — 448 ms (`Limit 200000, Used 199777`) |
| Groq `openai/gpt-oss-20b` | **429 tokens-per-minute** — 45,376 ms (client retried internally before surfacing) |

**Worst-case cost of one logical `invoke_llm()` call** when every candidate is walked:
0.45 + 45.4 + 0.14 + 1.33 + 35.8 + 0.44 + 36.5 ≈ **120 seconds**.

`gemini-2.0-flash` — the model hardcoded as `GEMINI_FALLBACK_MODEL` in `render.yaml` — is dead. There is currently **no working fallback provider**.

---

## 7. Prompt sizes actually sent

Captured by intercepting `invoke_llm` at the node boundary, 24-column dataset, expert question:

| Node | Prompt chars | Est. tokens (chars/4) |
|---|---:|---:|
| `planner` | 10,004 | ~2,501 |
| `code_generator` | 8,838 | ~2,210 |

At 5.6 LLM calls/question and ~2.3k tokens/call, one question costs roughly **13k tokens**, which exhausts a 200k/day quota in about **15 questions**.

---

## 8. Current latency — live end-to-end pipeline

Single session, 4,000-row CSV, 10 questions through the real `/analyze` pipeline.

| Stage | Value |
|---|---:|
| Upload (4,000 rows × 24 cols) | 91.6 ms |
| Suggested questions — cold | 99.1 ms |
| Suggested questions — warm (cache hit) | 18.1 ms |
| Tier mix returned | quick 3 / analytics 3 / advanced 5 / expert 3 |

End-to-end `/analyze`:

| Metric | Value |
|---|---:|
| p50 total | **132,948.8 ms** (~133 s) |
| p95 total | **283,848.5 ms** (~284 s) |
| Max total | **283,848.5 ms** |
| Avg LLM calls / question | **5.6** |
| Pipeline success | **8 / 10** |

Per question:

| Tier | Question | Total ms | LLM calls | Complexity | Success |
|---|---|---:|---:|---|---|
| simple | What is the total revenue? | 1,340 | 1 | SIMPLE | yes |
| simple | How many orders are there? | 1,933 | 2 | SIMPLE | yes |
| medium | Which customer region has the highest total revenue? | 91,265 | 7 | MEDIUM | yes |
| medium | How has revenue changed over time by month? | 118,050 | 6 | COMPLEX | yes |
| complex | Which customer regions have above-average revenue but below-average profit? | 151,860 | 7 | MEDIUM | yes |
| complex | What percentage of total revenue comes from the top 10 products? | 174,936 | 7 | VERY_COMPLEX | **no** |
| expert | Top 3 suppliers by revenue within each customer region, excluding suppliers with <5 orders | 283,849 | 9 | VERY_COMPLEX | yes |
| expert | Which suppliers increased revenue YoY while their profit declined? | 161,278 | 7 | VERY_COMPLEX | yes |
| unsupported | Which supplier has the highest employee satisfaction? | 140,124 | 6 | MEDIUM | yes (correct abstention) |
| ambiguous | Show me sales | 125,773 | 4 | SIMPLE | **no** (returned "Analysis Failed", not a clarification) |

Slowest node timings observed inside single questions: `code_generator` 120,088 ms, `planner` 76,589 ms, `report_agent` 71,538 ms, `visualization_generator` 31,748 ms. Given that a healthy Groq call returns in 0.3–1.5 s, these durations are **rate-limit retry/backoff time, not inference time**.

The two SIMPLE questions confirm the deterministic fast path works: 1.3–1.9 s, 1–2 LLM calls, `source: deterministic_fallback`, no Groq dependency for the answer itself.

---

## 9. Current LLM call count

| Path | Measured LLM calls |
|---|---:|
| SIMPLE (deterministic fast path) | 1–2 |
| MEDIUM | 6–7 |
| COMPLEX / VERY_COMPLEX | 7–9 |
| Average across the 10-question run | **5.6** |

Nodes that consumed calls: `supervisor`, `planner`, `code_generator`, `validator`, `visualization_generator`, `report_agent`. Even SIMPLE questions that are answered deterministically still spend 1–2 LLM calls on `supervisor` and `validator`.

---

## 10. Current benchmark accuracy

### 10a. Deterministic SQL harnesses (no LLM in the loop)

`python -m backend.benchmarks.run_csv_benchmark` — 100 questions:

| Difficulty | Result | Avg latency |
|---|---:|---:|
| easy | 20/20 | 0.178 ms |
| medium | 25/25 | 0.391 ms |
| hard | 30/30 | 0.812 ms |
| very_hard | 25/25 | 0.904 ms |
| **Total** | **100/100 (100%)** | — |

`python -m backend.benchmarks.run_demo_benchmark` — 100 questions:

| Metric | Value |
|---|---:|
| Suite OK | **100/100 (100%)** |
| SQL questions executed | 98 |
| Abstain probes | 1 |
| Refuse probes | 1 |
| Avg / p50 / p95 / max SQL latency | 0.648 / 0.578 / 1.573 / 2.082 ms |

> **Interpretation warning.** These harnesses execute the *ground-truth SQL* against DuckDB and verify the data layer. They do **not** measure NL→SQL accuracy and must never be quoted as "MarketMind is 100% accurate."

### 10b. Question discovery (8 datasets)

`python -m backend.benchmarks.run_question_discovery_benchmark`:

| Metric | Value |
|---|---:|
| Advanced questions displayed | 31 |
| Expert questions displayed | 17 |
| Advanced candidates validated | 76 |
| Expert candidates validated | 43 |
| Schema-valid | **100.0%** |
| Execution success | **100.0%** |
| Cold p50 / max latency | 34.83 ms / 200.62 ms |

### 10c. End-to-end NL→SQL accuracy

**The only real NL→SQL evidence available today is the 10-question live run: 8/10 pipeline success.**

Two of those answers were independently verified against DuckDB ground truth computed outside the pipeline:

| Pipeline answer | Independent ground truth | Verdict |
|---|---|---|
| "The South region has the highest total revenue." | South = 9,721,375.45 (North 9,451,730.17, Central 9,208,990.37) | **Correct** |
| "peaking at $1.79M in May 2023 and dipping to $0.90M in February 2024" | 2023-05 = 1,790,570; 2024-02 = 904,950 | **Correct** |

The remaining 6 successful answers were **not** independently verified in this run. There is **no 150-question NL→SQL accuracy figure yet** — that suite does not exist.

---

## 11. Baseline summary

| Area | Status |
|---|---|
| Tests | 212/213 pass; the 1 failure is quota-induced, not logic |
| Python lint/type gate | Absent |
| TypeScript types | Clean |
| Backend startup | Works, 1.08 s |
| Frontend build | Works, but 5.5 MB single JS chunk |
| Production backend | **Down** (Render suspended, no Vercel API) |
| Data layer correctness | Strong — 200/200 deterministic SQL questions pass in sub-millisecond time |
| Question discovery | Strong — 100% schema-valid and executable across 8 datasets |
| Deterministic fast path | Works — 1.3–1.9 s, 1–2 LLM calls |
| LLM-dependent paths | **Severely degraded** — p50 133 s, p95 284 s, caused by a dead/exhausted provider chain |
| NL→SQL accuracy evidence | Thin — 8/10 on one run, 2 answers verified correct |

The engine underneath is fast and correct. Everything that routes through the LLM provider chain is currently the bottleneck and the reliability risk.
