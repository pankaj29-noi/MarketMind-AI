# ENGINEERING_CHANGELOG.md

Every logical fix from the autonomous audit → fix → test → verify loop.

---

## 2026-09-21 — `ee51601`

**perf: fail fast on degraded LLM providers instead of walking dead models**

| | |
|---|---|
| **Problem** | One logical `invoke_llm()` call cost ~120s. End-to-end p50 was 133s, p95 284s. |
| **Root cause** | Fallback chain walked retired models (`qwen/qwen3.6-27b`, `gemini-2.0-flash`, `gemini-1.5-flash` all 404) and let langchain retry internally on 429 (~45s per model). Production default was the retired Gemini model. |
| **Solution** | Pruned retired models; clients built with timeout + `max_retries=0`; chain-wide 45s deadline; lead parser degrades to deterministic extractor on provider failure. |
| **Tests** | `test_llm_provider_chain.py`, `test_lead_provider_degradation.py`. Suite 232 → green. |
| **Performance** | Fully-failing chain: ~120s → **2.1s**. |
| **Accuracy** | Unchanged (correctness path untouched). |
| **Deploy** | Pushed to `main`. Render still suspended (manual). |

---

## 2026-09-21 — `604a233`

**perf: cut LLM calls per question with a response cache and deterministic skips**

| | |
|---|---|
| **Problem** | 5.6 LLM calls/question at ~2.3k tokens each exhausted a 200k/day budget in ~15 questions. |
| **Root cause** | Supervisor forced LLM routing whenever conversational context existed; validator ran an LLM semantic check even on pre-validated pattern SQL; identical prompts were re-sent. |
| **Solution** | Follow-up detection (only anaphora/ellipsis force LLM routing); validator skips LLM check for pattern SQL with coverage passed; content-addressed LLM response cache (T≤0.1, TTL 1800s). |
| **Tests** | `test_llm_call_budget.py`, `test_llm_cache.py`. Suite 254 passed. |
| **Performance** | SIMPLE path: 1 LLM call → **0**. Cache hit serves identical prompts with no provider round-trip. |
| **Accuracy** | Validation never skipped for LLM-authored SQL. |
| **Deploy** | Pushed. |

---

## 2026-09-21 — `43ac64b`

**perf: add per-provider circuit breaker for rate-limited LLMs**

| | |
|---|---|
| **Problem** | With Groq's daily budget exhausted, every node still paid ~1.4s discovering the same 429 — ~10s wasted per question before deterministic fallback. |
| **Root cause** | No memory of provider health across calls within a request or across requests. |
| **Solution** | Per-provider circuit breaker honouring the provider's own retry hint; any success closes it; non-rate-limit errors never trip it. |
| **Tests** | `test_llm_circuit.py`. Suite 263 passed. |
| **Performance** | Degraded-path p50 **132,949ms → 20ms**; p95 **283,849ms → 1,757ms**. |
| **Accuracy** | Fallback SQL still runs; answers when the pattern library covers the question. |
| **Deploy** | Pushed. |

---

## 2026-09-21 — `78e953f`

**fix: answer percent-of-total questions with a proportion, not a ranking**

| | |
|---|---|
| **Problem** | "What percentage of total revenue comes from the top 10 products?" failed after 174.9s. Worse: the deterministic fallback answered it with a top-10 ranking and "High" confidence. |
| **Root cause** | No percent-of-total-over-top-N pattern; requirement coverage accepted a ranking as a percentage; `\bproduct\b` never matched `product_name`. |
| **Solution** | `PERCENT_OF_TOTAL_TOP_N` pattern (denominator = overall total); coverage gate rejects rankings offered as percentages; dimension coverage recognises qualified columns. |
| **Tests** | `test_percent_of_total_pattern.py` including end-to-end against independent DuckDB ground truth. Suite 282 passed. |
| **Performance** | Question now answers in ~20ms on the deterministic path. |
| **Accuracy** | Verified: top-10 products = **23.41%** of 46,002,445.42 (exact match). |
| **Deploy** | Pushed. |

---

## 2026-09-21 — `70853d7`

**feat: clarify ambiguous questions instead of failing on them**

| | |
|---|---|
| **Problem** | "Show me sales" spent 125.8s and returned "Analysis Failed". |
| **Root cause** | No ambiguity detection; pipeline treated underspecified questions as ordinary failures. |
| **Solution** | Deterministic ambiguity detector for (a) metrics mapping to several columns and (b) bare measure requests with no operation. Schema-grounded suggestions; non-retriable; report headline "Clarification Needed". |
| **Tests** | `test_ambiguity.py`. Suite 303 passed. |
| **Performance** | Ambiguous questions resolve in <10ms with 0 LLM calls. |
| **Accuracy** | Well-specified questions unaffected (7 pinned by regression). |
| **Deploy** | Pushed. |

---

## 2026-09-21 — `49f199a`

**fix: make /health a real readiness probe**

| | |
|---|---|
| **Problem** | `/health` returned 200 `ok` while reporting `agent_ready=False`. Render gates deploys on this path. |
| **Root cause** | Health checked process liveness, not readiness. |
| **Solution** | 503 when agent graph missing; `degraded` when providers cooling / absent (deterministic fallback still works); never exposes credentials. |
| **Tests** | `test_health_readiness.py`. Suite 307 passed. |
| **Deploy** | Pushed. Render still suspended — health change cannot take effect until the service is unsuspended. |

---

## 2026-09-21 — `f0e8efe`

**test: add 150-question NL→SQL benchmark and stop inventing missing metrics**

| | |
|---|---|
| **Problem** | No real NL→SQL accuracy number existed. Existing "100%" figures measured DuckDB, not the AI. Fallback hallucinated answers for missing metrics. |
| **Root cause** | No multi-schema question bank with independent ground truth; `_is_out_of_domain` treated any question mentioning "supplier" as answerable. |
| **Solution** | 4 new 3k–4k schemas + 150-question bank + runner; unsupported-metric gate. |
| **Tests** | `test_unsupported_metric_abstention.py`. Suite **311 passed**. |
| **Accuracy (deterministic floor)** | overall **29.33%** (44/150); simple **87.5%**; abstain **10/10**; ambiguous **1/1**. Medium/expert floor is low — expected without LLM. |
| **Deploy** | Pushed. |

---

## Open blockers (require human action)

| Blocker | Reason | Required action | Impact |
|---|---|---|---|
| Render API suspended | `https://marketmind-api.onrender.com/health` → 503 "suspended by its owner" | Unsuspend the Render service (or point Vercel API at a live host) and set `GEMINI_FALLBACK_MODEL=gemini-3.6-flash` | Production cannot answer any question |
| Groq daily token budget exhausted | TPD Limit 200000, Used ~199777 | Wait for daily reset, or upgrade Groq tier / rotate key | Full LLM-path accuracy and healthy-provider latency cannot be re-measured |
