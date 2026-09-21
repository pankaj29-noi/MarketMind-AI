# FINAL_ENGINEERING_REPORT.md

**Date:** 2026-09-22  
**Scope:** Full MarketMind AI recheck → fix → test → verify → commit → push  
**Repo:** `DataAgent-Pro` (`https://github.com/pankaj29-noi/MarketMind-AI`)  
**Latest commit (this follow-up):** accuracy gates from SQL pipeline audit

---

## Verdict

Safe, verified fixes from this pass were implemented and regression-tested.
**377 / 377** backend tests passed (after accuracy follow-up). Frontend build
succeeded earlier in the pass. Production API remains **unavailable** because
Render reports the service as **suspended by its owner**.

---

## Architecture (unchanged)

```
CSV upload → session DuckDB → profile/schema cache
   → suggested questions (simple, schema-bound, DuckDB-verified)
   → click → /analyze → SQLCoder/patterns → SQL validate → DuckDB
   → result validation → grounded report (+ optional chart)
```

DuckDB remains the numerical source of truth. Suggested questions never
hardcode answers; click uses the normal analyze pipeline.

---

## Test & build results (this pass)

| Check | Result |
|---|---|
| `pytest backend/tests` (before rate-limit isolation) | **361 pass / 6 fail** — all 6 were HTTP **429** from shared limiter |
| `pytest backend/tests` (after fixes) | **377 pass / 0 fail** (~54s) |
| Frontend build | **pass** |
| Frontend lint (`oxlint`) | warnings only (no errors) |
| Multi-schema E2E (HR 3200 + IoT) | **pass** — 8 questions each, SQL validate + DuckDB execute |
| Suggestion gen @ 3200 rows | **245 ms** (cold profile+validate) |
| Suggestion gen @ 200 rows (IoT) | **21 ms** |

---

## Fixes implemented (verified)

### Security
1. **DuckDB filesystem table-functions blocked** in `_assert_read_only_sql` and
   `validate_sql` (`read_csv`, `parquet_scan`, `glob`, etc.).
2. **Python sandbox hardened** — `open()` limited to `result.json`; pandas
   `read_*` / `to_csv` limited to relative scratch filenames.
3. **CSV prompt-injection hardening** — sample tokens sanitized in
   `sqlcoder_schema` and `format_schema_context_for_llm`; SQLCoder prompt
   states samples are untrusted DATA.

### Reliability / product
4. **Pytest rate-limit isolation** — suite no longer fails with false 429s.
5. **Suggested/followup session restore** — uses `is_csv_session` like `/analyze`;
   rejects `dataset_id` not registered on the session.
6. **Expensive endpoint limit** raised 20→40 / 60s (safer for suggestion click-through).

### Accuracy (SQL pipeline follow-up)
8. **Single-table `FROM` validation** — reject hallucinated table names; allow multi-CTE.
9. **Segment filter coverage** — Consumer requirement no longer passes on Corporate SQL.
10. **Fallback SQL must pass `validate_sql`**; empty LLM SQL is a hard failure.
11. Window `OVER` aggregates no longer false-trigger GROUP BY; ORDER BY checks first key.
12. Suggestion templates use **AVG** for rate/score measures instead of SUM.

---

## Suggested questions (reconfirmed)

- Cap **5–10**, simple/quick only (`GENERATION_VERSION=v3-simple-only`)
- Schema-derived column names only
- Each candidate validated + DuckDB-executed before display
- Click path remains Question → SQL → validate → DuckDB → grounded answer
- Non-demo schemas (HR salary/department, IoT temp/site) produce adapted
  questions with **no** hardcoded revenue/product assumptions

---

## Theme

- Persistence via `localStorage` (`marketmind-theme`) + early `<head>` script
  (no FOUC)
- Charts re-theme via `MutationObserver` on `documentElement.class`

---

## Deployment status (live probes)

| Target | Probe | Result |
|---|---|---|
| `https://marketmind-api.onrender.com/health` | GET | **503** HTML: “This service has been suspended by its owner.” |
| `https://marketmind-ai.vercel.app/` | GET | **200**, but serves a **different** “Market Mind Mentor” app (not this frontend build) |

**Action required (manual, outside code):** unsuspend / redeploy Render
`marketmind-api`, and confirm the Vercel project tied to
`frontend/.vercel/project.json` (`marketmind-ai`) auto-deploys this repo’s
`frontend/` and points `VITE_API_BASE_URL` at the live API.

---

## Remaining limitations (honest)

1. **Render API suspended** — no production smoke analyze possible until unsuspended.
2. **Python sandbox** is defense-in-depth (AST + scrubbed env + timeout), not a
   full OS jail/cgroup.
3. **`session_manager.execute_query`** still allows internal profiling SQL
   (PRAGMA); user/LLM SQL continues to go through `run_query` + read-only gate.
4. **Cloud LLM quotas** in the developer environment still cause degraded-path
   analyze behaviour when Groq/Gemini are rate-limited; deterministic patterns /
   DEMO fallback cover many simple questions.
5. Plotly remains large when charts are shown (deferred, not eliminated).

---

## Commits in this loop

- Prior: `d23ff13` simple DuckDB-verified suggested questions
- This pass: security + reliability + bundle split (see git history after push)

---

## Principle applied

CHECK → FIND → FIX (safe) → TEST → VERIFY → MEASURE → COMMIT → PUSH → PROBE DEPLOY  
Nothing above is claimed fixed unless it was executed and observed in this pass.
