# MarketMind AI — AUDIT_REPORT

**Audit date:** 2026-09-21
**Git HEAD:** `2064733` (`main` = `origin/main`)
**Scope:** Full repository read + live probes. **No source fixes in this phase.**

**Live frontend:** https://marketmind-ai-pankaj.vercel.app → HTTP 200
**Live backend:** https://marketmind-ai-93u1.onrender.com/health → `{"status":"ok","agent_ready":true}`

---

## Executive Summary

MarketMind AI is a dual-workflow agentic marketplace platform (Analytics LangGraph + Lead Intelligence LangGraph) with a React frontend and FastAPI backend. Recent work added CORS allowlisting, SQL read-only guards, upload caps, rate limiting, sandbox AST gating, and adaptive CSV suggested questions.

**The highest-severity finding in the current tree is a regression that removed the Lead Intelligence HTTP route from the FastAPI app.** Dead code for `analyze_buyer_lead` sits unreachable inside `suggested_questions_endpoint` after an early `return`. Local TestClient confirms `POST /marketplace/lead/analyze` → **404**. Live OpenAPI also lacks this path (and lacks `/session/.../suggested-questions`), so **GitHub `main` and Render production are out of sync**, and the local tree currently has a broken Lead API regardless.

Sandbox AST allowlisting still permits `open(...)` and `getattr(__builtins__,'eval')` without imports — defense-in-depth is incomplete. Production has no `DATABASE_URL` durability for observability. Frontend JS bundle remains ~5.5MB. Public LLM endpoints remain unauthenticated (rate-limited only).

---

## Architecture

| Layer | Implementation |
|---|---|
| Frontend | React 19 + Vite 8 + Tailwind v4 + Framer Motion (`frontend/`) |
| Backend | FastAPI (`backend/main.py`), Uvicorn |
| Analytics | LangGraph supervisor + capabilities (`backend/agents/`) |
| Lead | Separate LangGraph (`backend/marketplace/lead/`) — deterministic ranking |
| Data | DuckDB per session (`session_manager.py`); Postgres optional |
| Correctness | `requirement_coverage`, `report_grounding`, SQL/Python validators, fallbacks |
| Adaptive Qs | `backend/services/adaptive_questions/*` + FE cards |
| Deploy | Vercel (FE) + Render (API) |

---

## Current Working Features (as designed / partially verified)

| Feature | Evidence |
|---|---|
| Health | Live `/health` 200 |
| Frontend shell | Live FE 200 |
| Marketplace demo load | Route present locally + live OpenAPI |
| Analytics `/analyze` | Route present locally + live OpenAPI |
| Observability/feedback routes | Present live OpenAPI |
| Adaptive question engine (code) | Module + tests present on `main` |
| CORS allowlist (code) | `backend/config.py` `CORS_ALLOWED_ORIGINS`; not `*` |
| SQL SELECT-only guard (code) | `mcp/data_access.py` `_assert_read_only_sql` |
| Upload size/row caps (code) | `MAX_UPLOAD_*` in upload handler |
| Rate limit dependency (code) | `utils/rate_limit.py` on expensive POSTs |
| Lead ranking formula (code) | `lead/ranking.py` WEIGHTS unchanged |

---

## P0 Issues

### P0-1. Lead Intelligence API route missing (local regression)
- **File:** `backend/main.py` ~L403–465
- **Behavior:** `@app.post("/session/{session_id}/suggested-questions")` was inserted such that the **Lead handler decorator/signature was dropped**. Remaining Lead body is unreachable code after `return` / stuck in a dangling docstring.
- **Evidence:** `app.routes` has no `/marketplace/lead/analyze`; TestClient → 404; `test_marketplace_lead.py::TestMarketplaceAPI::test_lead_analyze` fails `assert 404 == 200`.
- **Why it matters:** Core product surface (Lead Intelligence) is broken in current `main` before any new deploy of this commit.

### P0-2. Render production ≠ GitHub `main`
- **Evidence:** Live OpenAPI paths (12): includes `/upload`, `/analyze`, `/marketplace/demo`, lead **absent**, **suggested-questions absent**. Local HEAD `2064733` contains both Lead (broken) and suggested-questions.
- **Live probe:** `POST /session/x/suggested-questions` → `{"detail":"Not Found"}`.
- **Why it matters:** Features/fixes on GitHub are not what users hit; auto-deploy appears not to have updated Render (or last successful deploy predates recent commits). Assessment/demo fidelity is compromised.

### P0-3. Sandbox AST allows dangerous builtins without imports
- **File:** `backend/services/python/python_quality_validator.py`
- **Evidence (local probe):**
  - `open('/etc/passwd')` → `(True, '')`
  - `os.system('id')` → `(True, '')` (name `os` not banned)
  - `getattr(__builtins__,'eval')('1')` → `(True, '')`
- **Why it matters:** `sandbox.py` gates on this validator before spawn; timeout/env scrub help but do not stop FS/read escapes via builtins. Must not claim “secure sandbox.”

---

## P1 Issues

### P1-1. No authentication on LLM-expensive public endpoints
- **Files:** `backend/main.py` `/analyze`, `/upload`, `/marketplace/*`, suggested-questions
- **Mitigation present:** sliding-window rate limit (`limit_expensive_endpoint`, 20/60s).
- **Gap:** Still abuseable for quota burn / DoS beyond rate window via distributed IPs.
- **Severity:** P1 for portfolio demo; P0 if real paid keys are exposed without monitoring.

### P1-2. `SANDBOX_MEMORY_LIMIT_MB` unused
- **Files:** `backend/config.py`, `backend/agents/sandbox.py` (documents limit as advisory)
- **Why:** Free Render 512MB can OOM on hostile/large Python.

### P1-3. Production observability ephemeral
- **Files:** `marketplace/observability.py`, Render env (no durable `DATABASE_URL` observed historically)
- **Why:** Agent Monitoring resets on cold start; looks “broken” in demos.

### P1-4. Analyze has no client timeout / abort
- **File:** `frontend/src/App.tsx` `handleAnalyze` — `fetch` without `AbortController`
- **Why:** Render cold start + long agent runs → infinite spinner risk.

### P1-5. Dual fallback engines can diverge
- **Files:** `marketplace/sql_fallback.py`, `services/analytics_fallback.py`
- **Why:** Silent wrong answers if precedence unclear.

### P1-6. `requirements.txt` still ships MCP/fastmcp to production image
- **File:** `requirements.txt` includes `mcp`, `fastmcp`, `langchain-mcp-adapters`
- **Why:** Larger builds, unused attack surface on Render.

### P1-7. Adaptive questions not live; FE may call missing API after Vercel catches up
- **Files:** FE `App.tsx` / `suggestedQuestions.ts` vs live OpenAPI
- **Why:** If FE deploys new UI before Render updates, CSV upload shows suggestion errors.

### P1-8. Keyword SQL denylist still heuristic
- **File:** `mcp/data_access.py` `_assert_read_only_sql`
- **Why:** Better than before (SELECT-only + COPY/ATTACH blocked), but string/comment edge cases remain; not a full SQL parser.

### P1-9. Broad `except Exception` across agents/main
- **Many files** under `backend/`
- **Why:** Soft-fail architecture is intentional but can hide regressions (as with P0-1 until a test hit it).

---

## P2 Issues

| ID | Topic | Location |
|---|---|---|
| P2-1 | Frontend bundle ~5.5MB JS | `npm run build` output |
| P2-2 | Leftover Vercel-API configs | root `vercel.json`, `pyproject.toml` `[tool.vercel]`, `requirements-vercel.txt` |
| P2-3 | Large modules | `requirement_coverage.py` ~1161, `report_agent.py` ~971, `main.py` ~940 |
| P2-4 | Unused shadcn UI primitives | `frontend/src/components/ui/*` |
| P2-5 | MCP half-integrated | `mcp/client.py` lazy; `mcp_server/` optional |
| P2-6 | Debug `print` in MCP sync wrapper | `mcp/client.py` L82 |
| P2-7 | Workspace `useEffect` missing `activePath` dep | lint warning |
| P2-8 | No FE unit/e2e suite | `package.json` scripts |
| P2-9 | Follow-up adaptive questions after analyze | documented as future in adaptive docs |
| P2-10 | Dirty tree: `frontend/.gitignore` modified uncommitted | `git status` |

---

## Security Issues

| Finding | Sev | Notes |
|---|---|---|
| P0-3 sandbox AST gaps | High | `open` / unbound `os` / `getattr` eval bypass |
| P1-1 unauthenticated LLM APIs | Med–High | Rate limit only |
| CORS | Improved | Explicit allowlist in code (`config.py` / `main.py`); verify live deploy has it |
| Secrets in git | OK this scan | No live `gsk_`/`AIza` in tracked files; `.env` gitignored |
| SQL destructive | Improved | SELECT-only + expanded denylist; heuristic residual risk (P1-8) |
| Upload | Improved | Size/row caps + basename; encoding normalization |
| Error leakage | Partially improved | Upload 500 sanitized; other endpoints may still stringify exceptions |

**Ops:** Keys were previously shared in chat — rotation still recommended.

---

## AI Correctness Issues

- Semantic stack present and should be preserved.
- Adaptive questions prove candidates via DuckDB (good) but **clicked** questions still go through full `/analyze` — wording must remain answerable by planner/fallback (monitor false “suggested but fails”).
- Report grounding / requirement coverage are large heuristic systems — need ongoing red-team, not removal.
- DEMO provenance helpers exist in `config.py`; keep labeling honest.

---

## Backend Issues

- **P0-1 Lead route regression** (above).
- Session manager TTL 1800s — isolation tests exist partially; concurrency stress limited.
- Postgres soft-fail works (tests show pool warnings then MemorySaver).
- `session_manager.execute_query` can run `PRAGMA` outside `_assert_read_only_sql` (by design for profiling); ensure LLM paths cannot call it with arbitrary SQL.

---

## Frontend Issues

- Adaptive suggestion UX wired for CSV; marketplace keeps curated samples.
- No request timeout on analyze (P1-4).
- Bundle size (P2-1).
- Lint warnings only (0 errors).

---

## Testing Issues

| Result | Detail |
|---|---|
| Suite | **184 passed, 1 failed**, ~17s |
| Failure | `test_marketplace_lead.py::TestMarketplaceAPI::test_lead_analyze` → 404 (P0-1) |
| Adaptive tests | Present and previously green when run targeted |
| Frontend | No automated tests configured |

Do **not** delete the failing Lead test — it correctly detected P0-1.

---

## Deployment Issues

| Item | Status |
|---|---|
| Render health | 200 |
| Render ↔ GitHub sync | **Broken / stale** (P0-2) |
| Auto-deploy | Not observed updating OpenAPI after pushes to `2064733` |
| Vercel FE | 200; may or may not include latest adaptive UI |
| `VITE_API_BASE_URL` | Should remain Render URL (verify in Vercel project after FE deploy) |
| Backend on Vercel | Correctly abandoned |

---

## Observability Issues

- Memory fallback when Postgres down — OK for demo core path.
- Without Postgres, monitoring empty after restart (P1-3).
- Analytics node-level timings still not fully exposed on monitoring APIs (Lead-focused).

---

## Performance Issues

- Sync `/analyze` + Render free cold start.
- Adaptive generation runs many proof queries (acceptable for small CSVs; watch large schemas).
- FE bundle 5.5MB.

---

## Maintainability Issues

- Accidental route deletion (P0-1) shows `main.py` is too large / fragile for inline inserts.
- Overlapping fallbacks (P1-5).
- Leftover deploy configs (P2-2).

---

## Documentation Issues

- Adaptive docs exist under `docs/`.
- README may not yet document suggested-questions API / deploy sync caveat.
- Prior AUDIT/BASELINE files exist; this report supersedes them for **2026-09-21 HEAD `2064733`**.

---

## Recommended Fix Order (after approval)

1. **P0-1** Restore `@app.post("/marketplace/lead/analyze")` cleanly; keep suggested-questions separate; regression already exists.
2. **P0-2** Manual Render deploy of latest `main` (or fix auto-deploy); verify OpenAPI includes Lead + suggested-questions; live smoke.
3. **P0-3** Harden AST validator (`open`, `os`/`sys` name bans, `getattr`/`builtins` patterns); adversarial tests already started in `test_sandbox_security.py`.
4. **P1-4** Frontend analyze timeout + cold-start messaging.
5. **P1-3** Neon/Supabase `DATABASE_URL` or UI banner for memory mode.
6. **P1-6** Slim production `requirements.txt`.
7. High-value P2: bundle split, remove dead Vercel-API configs, split FastAPI routers.

---

## What was not invented

Every finding cites concrete files, probes, or measured test/deploy results from this audit run.
