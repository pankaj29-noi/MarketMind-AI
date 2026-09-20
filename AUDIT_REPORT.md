# MarketMind AI — AUDIT_REPORT

**Date:** 2026-09-21  
**Repo:** https://github.com/pankaj29-noi/MarketMind-AI  
**HEAD:** `4d420e8` (`main` tracking `origin/main`)  
**Live frontend:** https://marketmind-ai-pankaj.vercel.app  
**Live backend:** https://marketmind-ai-93u1.onrender.com  

This report is based on reading the repository and probing live health. No code was modified during Phase 0.

---

## Architecture summary

MarketMind AI is a dual-workflow agentic marketplace platform:

1. **Marketplace Analytics** (`backend/agents/`): Supervisor-routed LangGraph over DuckDB. Capabilities: SCHEMA → SQL → ANALYSIS → VISUALIZATION → PYTHON_ANALYSIS → REPORT. Semantic layer includes `requirement_coverage.py`, `report_grounding.py`, SQL/Python quality validators, and deterministic SQL fallbacks.
2. **Lead Intelligence** (`backend/marketplace/lead/`): Linear LangGraph — parse → validate → product match → supplier match → **deterministic ranking** → format. Observability records run/node timings (Postgres or memory).

**Frontend:** React 19 + Vite 8 + Tailwind v4 + Framer Motion; pages Workspace / Lead Intelligence / Agent Monitoring.  
**Deploy:** Frontend → Vercel; Backend → Render (free). Backend is not suitable for Vercel serverless (prior bundle-size failure documented).

---

## Current working features (verified by code + live probe)

| Feature | Evidence |
|---|---|
| Health endpoint | Live `GET /health` → `{"status":"ok","service":"marketmind-api","agent_ready":true}` |
| Frontend serves | Live `https://marketmind-ai-pankaj.vercel.app` → HTTP 200 |
| Marketplace demo load | `POST /marketplace/demo` + `demo_data.py` |
| Analytics graph | `agents/graph.py` + capability registry |
| Lead graph + deterministic ranking | `lead/graph.py`, `lead/ranking.py` WEIGHTS |
| Observability + feedback | `marketplace/observability.py` + FE services |
| DEMO_MODE / provider guards | `config.py` (`use_lead_demo_extraction`, `use_analytics_demo_fallback`) |
| Postgres soft-fail | `database/connection.py`, repository memory maps |
| Synthetic seed data | `data/marketplace/*.csv` (~2041 rows) |

---

## Findings (ranked)

### P0 — broken / dangerous / deployment-blocking

#### P0-1. CORS `allow_origins=["*"]` with `allow_credentials=True`
- **File:** `backend/main.py` (~L119–126)
- **Issue:** Spec-contradictory; browsers may reject credentialed requests; overly permissive for a public LLM-backed API.
- **Fix direction:** Explicit allowlist (Vercel production origins + localhost for dev).

#### P0-2. SQL quality validator treats non-SELECT as valid
- **File:** `backend/services/sql/sql_quality_validator.py` L54–55  
  `if not query_upper.strip().startswith("SELECT"): return {"is_valid": True, ...}`
- **Issue:** Destructive / non-read queries skip all quality checks. Execution path has a separate keyword block in `mcp/data_access.py`, but the validator itself is wrong and can mislead callers/tests.
- **Fix direction:** Non-SELECT must be `is_valid: False` with a critical issue. Align with executor denylist.

#### P0-3. Public API has no auth / rate limit while consuming LLM quota
- **Files:** `backend/main.py` all POST routes; live Render URL is public
- **Issue:** Anyone can hit `/analyze`, `/upload`, `/marketplace/lead/analyze` and burn Groq/Gemini credits or OOM the 512MB free instance.
- **Fix direction:** At minimum: rate limiting + optional shared secret header / demo token; document exposure honestly if left open for portfolio.

#### P0-4. CSV upload has no size / row cap
- **File:** `backend/main.py` `upload_csv` (~L220–295)
- **Issue:** Entire file read into memory (`await file.read()`), no max bytes/rows. On Render free (512MB) this is a DoS/OOM vector.
- **Fix direction:** Max upload size (e.g. 10–25MB) + row limit after parse; reject early.

---

### P1 — important correctness / reliability

#### P1-1. DuckDB executor denylist incomplete (`COPY` / `ATTACH` / etc.)
- **File:** `backend/mcp/data_access.py` `run_query` L297–299, L324–326  
  Blocks: `insert/update/delete/drop/alter/create` (substring with trailing space).
- **Issue:** DuckDB supports `COPY ... TO`, `ATTACH`, `EXPORT`, `INSTALL`, `LOAD`, etc. File write / extension load not blocked. Heuristic is also fragile (comment/string false positives/negatives).
- **Fix direction:** Require single SELECT-only statement; reject multi-statement; expand denylist; prefer AST/parser if available.

#### P1-2. Sandbox memory limit configured but unused
- **Files:** `backend/config.py` `SANDBOX_MEMORY_LIMIT_MB`; `backend/agents/sandbox.py`
- **Issue:** Timeout + env whitelist exist; **no enforcement of memory limit**. Subprocess can still allocate until host OOM. AST validator exists (`python_quality_validator.py`) but sandbox does not re-validate before run at this layer (callers may).
- **Honest limitation:** Without OS cgroups/seccomp, full isolation is not claimed. Improve: always run AST gate in `run_python_in_sandbox`; document remaining risk.

#### P1-3. Stale tests fail against newer provider guards
- **File:** `backend/tests/test_fallback.py`  
- **Root cause:** Patches `GROQ_API_KEY="test_groq_key"` but `has_valid_groq_key()` rejects short/placeholder keys → `get_llm()` raises `ValueError` (`config.py` L246).
- **Also:** `test_mcp.py` uses `@pytest.mark.asyncio` without `pytest-asyncio`; `test_visualization_integration.py::test_malformed_spec_handling` expects `None` but validator returns a rejection dict.
- **Fix direction:** Update tests to match intended key validation (use `gsk_` + ≥20 chars fakes); add pytest-asyncio or sync-wrap MCP test; update assertion.

#### P1-4. Production observability is ephemeral
- **Files:** `marketplace/observability.py`, Render env (no `DATABASE_URL` documented in prior deploy)
- **Issue:** In-memory runs/feedback reset on cold start / redeploy. Agent Monitoring appears “empty” after sleep — looks broken in demos.
- **Fix direction:** Wire Neon/Supabase Postgres or document clearly in UI when memory backend is active.

#### P1-5. Upload error responses may leak internals
- **File:** `backend/main.py` L287 `detail=f"Failed to process CSV: {str(e)}"`
- **Issue:** Exception text can include paths / driver messages. Prefer generic client message + server log.

#### P1-6. Analyze path is fully synchronous / long-blocking
- **File:** `backend/main.py` `POST /analyze`; Render free cold start + multi-node agent
- **Issue:** Frontend may wait minutes with no progress events; risk of gateway timeouts; UX “stuck” feeling.
- **Fix direction (incremental):** Request timeouts + cancel messaging; later SSE for node progress (P2).

#### P1-7. `requirements.txt` installs test/MCP packages in production
- **Files:** `requirements.txt` includes `mcp`, `fastmcp`, `pytest` (via prior full list — verify current), `langchain-mcp-adapters`
- **Issue:** Larger image, longer Render builds, unused attack surface.
- **Fix direction:** Slim runtime requirements; keep extras in `requirements-dev.txt`.

---

### P2 — quality improvements

#### P2-1. Overlapping fallback engines
- `backend/marketplace/sql_fallback.py` vs `backend/services/analytics_fallback.py`
- Risk of silent wrong-answer if selection logic drifts. Keep both but clarify precedence in one place + tests.

#### P2-2. Very large modules
| Module | ~LOC |
|---|---:|
| `requirement_coverage.py` | 1161 |
| `report_agent.py` | 971 |
| `main.py` | 862 |
| `analytics_fallback.py` | 649 |

Refactor only when touching these for other reasons; split FastAPI routers first.

#### P2-3. Dead / leftover deploy config
- Root `vercel.json`, `pyproject.toml` `[tool.vercel]`, `requirements-vercel.txt` from abandoned Vercel-API attempt — confuse future deployers.

#### P2-4. Frontend infinite-loading / cold-start UX
- `App.tsx` analyze/upload paths; Render spin-down causes long first request.
- Need explicit timeout + “API waking up” messaging (already partial message exists).

#### P2-5. Many unused shadcn UI primitives
- `frontend/src/components/ui/*` (~50 files) inflate cognitive load; optional dead-code trim.

#### P2-6. Broad `except Exception` usage
- Dozens of sites across `main.py`, agents, observability — acceptable for soft-fail architecture but swallows unexpected bugs. Narrow where it hides P0s.

#### P2-7. MCP stack half-integrated
- Lazy import in `mcp/client.py`; `mcp_server/` excluded from deploy. Finish or remove.

#### P2-8. Analytics node timings not on monitoring API
- Agent Monitoring UI only shows Lead workflow runs from observability endpoints.

---

### P3 — optional enhancements

- SSE/WebSocket streaming of analytics node progress  
- Auth / per-user history  
- Bundle analysis / lazy-load Plotly  
- Neon Postgres for durable observability  
- Keep-alive for Render free tier  
- Formal threat model doc for sandbox limits  

---

## Security issues (summary)

| ID | Severity | Topic |
|---|---|---|
| P0-1 | High | CORS misconfiguration |
| P0-3 | High | Unauthenticated public LLM/API abuse |
| P0-4 | High | Unbounded upload / memory DoS |
| P0-2 / P1-1 | High–Med | SQL validation / DuckDB write primitives |
| P1-2 | Med | Sandbox not memory-capped; no OS isolation |
| P1-5 | Low–Med | Error leakage |
| — | Ops | Real API keys previously appeared in chat/logs — **rotate Groq/Google keys** |

Secret scan of tracked files: no live `gsk_`/`AIza` keys in git (only placeholders / prefix checks in `config.py`). Local `.env` is gitignored (verify remains so).

Frontend: no `dangerouslySetInnerHTML` / `console.log` found in `frontend/src` during Phase 0 search.

---

## Correctness / AI issues

- Semantic stack exists and should stay (`requirement_coverage`, `report_grounding`, validators).
- SQL validator non-SELECT bug (P0-2) undermines trust in the gate.
- Dual fallbacks need precedence tests so fallback never answers out-of-scope questions as if LLM succeeded.
- DEMO provenance must remain accurate (`extraction_source` / `analysis_source`) — verify in Lead + analytics responses during Phase 4.

---

## Reliability / observability / performance

- Render free cold start (~30–60s) + no Postgres ⇒ empty monitoring after sleep.  
- Sync `/analyze` amplifies timeout risk.  
- Session TTL in `session_manager.py` (1800s) — need isolation regression tests (Phase 9).  
- `SANDBOX_MEMORY_LIMIT_MB` unused (P1-2).

---

## Testing gaps

- Failing suite items are **stale tests**, not proof of app breakage — still must be fixed (P1-3).
- Missing: adversarial sandbox tests (`os`, `subprocess`, `socket`, …), SELECT-only SQL regression, upload size rejection, CORS allowlist tests, session isolation tests.
- Frontend: no unit/e2e suite in `package.json` (only `build` / `lint`).

---

## Frontend / backend contract notes

API calls centralized via `API_BASE` in:
- `App.tsx` — upload, demo, analyze, trace, history  
- `LeadIntelligence.tsx` — lead analyze  
- `services/observability.ts` — runs, summary, feedback  
- `services/analytics.ts` — metrics  

Need Phase 10 pass for TS type ↔ Pydantic parity and timeout/retry states.

---

## Documentation / maintainability

- README is strong and mostly aligned.  
- `docs/MarketMind_AI_FULL_CONTEXT.md` is an engineering dump (useful).  
- Leftover Vercel-API configs should be removed or clearly marked obsolete (P2-3).  
- No TODO/FIXME markers found in application source during Phase 0 search.

---

## Deployment issues

| Item | Status |
|---|---|
| Render health | OK at audit time |
| Vercel frontend | HTTP 200 |
| Auto-deploy from GitHub | Assumed for Render/Vercel when connected — verify after first push |
| Backend on Vercel | Correctly abandoned |
| `VITE_API_BASE_URL` | Must remain Render URL; rebuild required after env change |

---

## Recommended fix order (execution plan)

1. **P0-1** CORS allowlist  
2. **P0-2** SQL validator reject non-SELECT + align denylist (**P1-1**)  
3. **P0-4** Upload size/row limits  
4. **P0-3** Rate limit and/or demo API key header (lightweight)  
5. **P1-3** Fix failing tests  
6. **P1-2** AST re-validate inside sandbox + document limits  
7. **P1-5** Sanitize upload/error details  
8. Slim `requirements.txt` (**P1-7**)  
9. Frontend cold-start / timeout UX (**P2-4**)  
10. Observability durability docs or Neon (**P1-4**)  

Each: targeted tests → commit → push → live verify.

---

## What was NOT invented

Every finding cites a concrete file/behavior observed in this repo or live HTTP probe on 2026-09-21. Items labeled P3 are optional enhancements, not claimed defects.
