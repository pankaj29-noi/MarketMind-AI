# AUDIT_REPORT.md — MarketMind AI (re-audit after autonomous fix loop)

**Date:** 2026-09-21  
**Repo:** `DataAgent-Pro` / MarketMind-AI  
**Baseline suite:** 315 passed / 0 failed  
**Deterministic NL→SQL floor:** 92/150 (**61.33%**) — was 44/150 (29.33%) earlier today

Source of truth for architecture: [Map analytics LangGraph](8b4411a7-1962-42f8-8a5a-db664ffae77b), [Map upload schema services](b43f526b-18cd-41d2-80d5-b9f759b7e5ad).

---

## P0 — fixed this loop (or previously)

| Issue | Status |
|---|---|
| Dead LLM fallback chain (~120s/call) | Fixed (`ee51601`+) |
| Ranking returned as percent-of-total | Fixed (`78e953f`) |
| Missing-metric hallucination (satisfaction→revenue) | Fixed (`f0e8efe`) |
| Suggestion cache not cleared on re-upload | **Fixed this commit** |
| Cross-session DuckDB / cache leakage (unproven) | **Regression tests added** |

## P0 — external blockers (need human)

| Issue | Evidence | Action |
|---|---|---|
| Render API suspended | `https://marketmind-api.onrender.com/health` → 503 HTML | Unsuspend Render service |
| Groq daily token budget | TPD ~200k exhausted during earlier runs | Wait for reset / upgrade |

## P1 — fixed this loop

| Issue | Status |
|---|---|
| SUM/AVG stole group-by questions | Fixed — structured patterns win |
| Charts hardcoded dark theme | Fixed — Plotly reads `document.documentElement.dark` |
| Theme not persisted | Fixed — `localStorage('marketmind-theme')` |
| Cold-start retries absent on FE | Fixed — `apiFetch` with backoff on analyze/suggestions |
| Warm suggestion path re-profiled every time | Fixed — fingerprint short-circuit before `profile_dataset` |

## P1 — remaining (code, not external)

| Issue | Impact | Next |
|---|---|---|
| Deterministic expert accuracy 17.2% | Expert Qs still need LLM path | Expand top-N-per-group / YoY / multi-condition patterns |
| Medium paraphrases partially fail | ~6 paraphrase bank items | More synonym coverage |
| Frontend JS bundle ~5.5 MB | Slow first paint | Code-split Plotly |
| Healthy-provider latency unmeasured | Quota | Re-run `run_pipeline_latency` after Groq reset |

## P2

| Issue | Notes |
|---|---|
| `SANDBOX_MEMORY_LIMIT_MB` not enforced | Documented earlier |
| CORS methods/headers `*` | Functional but broad |
| No auth on API | Rate limit only |
| Root `vercel.json` FastAPI config misleading | Backend is Render |

## P3

Docs polish, comment cleanup — deferred.

---

## Measured numbers (this re-audit)

| Metric | Value |
|---|---:|
| Tests | **315 / 315** |
| NL→SQL overall | **61.33%** |
| Simple | **97.5%** |
| Medium | **65.9%** |
| Advanced | **52.5%** |
| Expert | **17.2%** |
| Abstain / Ambiguous | **100% / 100%** |
| Frontend `tsc` | clean |
| Frontend build | success (5.5 MB chunk) |
| Production API | **503 suspended** |

---

## Recommended next repair order

1. Unsuspend Render → live smoke  
2. After Groq reset → measure healthy LLM path latency + expert accuracy  
3. Expand top-N-per-group / HAVING / YoY patterns to raise expert floor  
4. Code-split Plotly to cut FE bundle  
