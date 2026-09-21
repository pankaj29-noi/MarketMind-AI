# FULL_SYSTEM_AUDIT.md — MarketMind AI

**Audit date:** 2026-09-21
**Scope:** frontend, backend, AI orchestration, data layer, analytics, lead intelligence, deployment, testing
**Method:** read the actual source, then run it. Every quantitative claim traces to a command in [`ENGINEERING_BASELINE.md`](./ENGINEERING_BASELINE.md).
**Status:** Phase 0 only — no production code was modified.

---

## 1. Architecture

Three tiers, plus an external LLM dependency.

```
React 19 + TypeScript + Vite + Tailwind  (Vercel)
        │  fetch → API_BASE
        ▼
FastAPI  backend/main.py  — 20 routes        (Render, currently suspended)
        │
        ├── SessionManager ── one in-memory DuckDB connection per session (TTL 1800 s)
        ├── LangGraph agent graph — 13 nodes, supervisor-routed
        ├── Adaptive question engine — deterministic, schema-bound
        ├── PostgreSQL repository — observability/history, in-memory fallback
        └── Python sandbox — subprocess, scrubbed env, timeout
        │
        ▼
Groq (primary) → Gemini (fallback)
```

The 13 LangGraph nodes (`backend/agents/graph.py`): `supervisor`, `schema_profiler`, `planner`, `code_generator`, `python_analyst`, `sandbox_executor`, `validator`, `reflection`, `analysis_engine`, `visualization_generator`, `visualization_executor`, `visualization_reflection`, `report_agent`. Entry point is `supervisor`; every terminal node routes back to `supervisor`, which decides the next hop via conditional edges.

The design intent — LLM as interpreter, DuckDB as numerical truth — is genuinely implemented, not aspirational. Results are computed in DuckDB and the report node narrates executed output. The two live answers I verified against independent SQL were both numerically exact.

---

## 2. Data flow

```
CSV upload (POST /upload)
  → size/row cap check (15 MiB, 100k rows)
  → SessionManager.register_csv() → DuckDB view over the file
  → schema profile built once, cached by dataset fingerprint
  → adaptive question engine profiles capabilities, emits 4 tiers
  → each candidate question's proof SQL is executed before it is shown
```

Measured: upload of 4,000 rows × 24 columns takes **91.6 ms**; cold question generation **99.1 ms**, warm **18.1 ms**.

The CSV is parsed once into a session-scoped DuckDB view and reused. Raw CSV rows are never sent to the LLM — only the compact profile.

---

## 3. AI flow

```
/analyze
  → complexity classification (SIMPLE / MEDIUM / COMPLEX / VERY_COMPLEX)
  → result cache lookup (session + dataset + fingerprint + normalized question)
  → SIMPLE: deterministic pattern library → SQL → DuckDB → grounded answer
  → otherwise: supervisor → planner → code_generator → sandbox_executor
              → validator → reflection (one-shot repair) → visualization → report_agent
```

Measured LLM calls: **1–2 for SIMPLE**, **6–9 for MEDIUM and above**, average **5.6**. Prompts are compact relative to the dataset — planner 10,004 chars (~2.5k tokens), codegen 8,838 chars (~2.2k tokens) — but they are sent 6–9 times per question.

The reflection node implements a one-shot repair policy: one targeted retry, then a graceful report rather than a loop. That is correct and is covered by tests.

---

## 4. Frontend flow

`frontend/src/` — `App.tsx`, 4 pages (`Workspace`, `Analytics`, `LeadIntelligence`, `AgentMonitoring`), components grouped under `analysis/`, `analytics/`, `chat/`, `report/`, `monitoring/`, `lead/`, `ui/`, plus `PlotlyChart.tsx`.

Upload → `Workspace` shows a dataset summary → `SuggestedQuestionsPanel` renders Quick / Analytics / Advanced / Expert tiers → clicking a question posts to `/analyze` → result renders as table + optional Plotly chart → `fetchFollowupQuestions` produces result-aware follow-ups.

API base resolution (`frontend/src/lib/api.ts`) falls back to `http://localhost:8000` when `VITE_API_BASE_URL` is unset — so a production build without that env var silently points at localhost.

---

## 5. Backend flow

`backend/main.py` wires CORS from an explicit allowlist, mounts the upload directory, compiles the agent graph at startup, and exposes 20 routes. Seven expensive endpoints are protected by `Depends(limit_expensive_endpoint)`: `/upload`, `/marketplace/demo`, `/marketplace/analytics-demo`, `/analyze`, the two question endpoints, and the lead analyzer.

`/health` returns 200 in 5 ms but reports `agent_ready: False` — it checks process liveness, not readiness.

PostgreSQL is optional. When unavailable the repository logs `Failed to create session in Postgres` and falls back to in-memory storage, so analytics keep working without the database.

---

## 6. Current caching

| Cache | Key | Scope |
|---|---|---|
| Schema profile | dataset fingerprint | per dataset |
| Suggested questions (`adaptive_questions/cache.py`) | `session_id \| dataset_id \| fingerprint` | per session + dataset |
| Analytical results (`analytics_perf.py`) | `session_id \| dataset_id \| fingerprint \| normalized_question` | per session + dataset |
| Generation version | `GENERATION_VERSION = "v2-tiered"` | invalidates stale suggestion shapes |

Keys correctly include both session identity and dataset fingerprint, so results cannot leak between datasets or sessions. Warm suggestion fetch measured at 18.1 ms versus 99.1 ms cold.

Gap: **no LLM-response cache.** Identical planner or codegen prompts re-hit the provider and re-burn quota.

---

## 7. Current validation

Layered, and genuinely more than syntax checking:

1. **Upload validation** — byte cap and row cap before ingestion.
2. **SQL safety** — read-only guard rejecting writes/DDL/filesystem operations; 11 dedicated tests in `test_sql_readonly_guard.py`.
3. **SQL quality** (`sql_quality_validator.py`) — GROUP BY correctness, aggregate detection across a broad function set, alias and denominator checks.
4. **Semantic validation** — `test_code_generation_semantics.py` (11 tests) and `test_semantic_redteam.py` (17 tests) check that SQL means what the question asked.
5. **Requirement coverage** (`test_requirement_coverage.py`, 15 tests) — material requirements must appear in plan → SQL → result.
6. **Question proof execution** — every suggested question's SQL runs before display; advanced/expert candidates are rejected if they return zero rows.
7. **Report grounding** (`test_report_grounding.py`) — narration must derive from executed results.

Measured outcome: **100% schema-valid, 100% executable** across 119 validated advanced/expert candidates on 8 datasets.

---

## 8. Current security

| Control | State |
|---|---|
| CORS | Explicit allowlist in `config.py`, no wildcard with `allow_credentials=True`. Correct. |
| Rate limiting | Sliding-window limiter applied to 7 expensive endpoints. |
| Upload caps | 15 MiB / 100,000 rows, enforced pre-ingestion. |
| SQL injection | Read-only guard plus parameterized session queries. |
| Python sandbox | Subprocess, AST pre-validation, secret-scrubbed env whitelist, hard timeout. |
| Secrets in git | `.env` and `.env.*` gitignored; only `.env.example` is tracked. Verified. |
| Prompt injection | CSV cells reach prompts only as profile samples; red-team tests exist. |
| Session isolation | Per-session DuckDB connection with a per-session lock. |

Weak points: `allow_methods=["*"]` and `allow_headers=["*"]` are broader than needed; `SANDBOX_MEMORY_LIMIT_MB` is configured in `render.yaml` but **not actually enforced** — the code comments admit no cgroup limit is applied; there is no authentication on any endpoint, so rate limiting is the only abuse control.

---

## 9. Current tests

213 tests across 25 files, **212 passing, 1 failing, 0 skipped**, 13.73 s.

Coverage is real where it matters: SQL safety (11), semantic red-team (17), requirement coverage (15), code-generation semantics (11), SQL quality (10), adaptive questions (11), sandbox security (3), CORS (3), upload limits (2), rate limiting (2).

The single failure, `test_marketplace_lead.py::TestMarketplaceAPI::test_lead_analyze`, is caused by a live Groq 429 (daily token quota exhausted at 199,777/200,000), not by broken logic. It is a **non-hermetic test** that depends on a third-party quota to pass.

There are **no frontend tests** and **no load tests**.

---

## 10. Current deployment

| Target | Config | Live status |
|---|---|---|
| Render (`marketmind-api`) | `render.yaml`, free plan, `healthCheckPath: /health`, autoDeploy | **HTTP 503 — service suspended by owner** |
| Vercel API (`marketmind-api`) | `vercel.json`, `maxDuration: 300`, 1024 MB | **HTTP 404 on /health** |
| Vercel frontends | `frontend/vercel.json`, Vite | HTTP 200 on three URLs |

**Production does not work end to end.** The UI loads; nothing behind it answers. `render.yaml` also pins `GEMINI_FALLBACK_MODEL=gemini-2.0-flash`, a model that now returns 404, so even a revived backend would have a dead fallback.

---

## 11. Bottlenecks

Ranked by measured impact.

1. **LLM provider chain, by a wide margin.** p50 133 s, p95 284 s end to end. A healthy Groq call returns in 0.3–1.5 s, yet `code_generator` was observed at 120,088 ms, `planner` at 76,589 ms, `report_agent` at 71,538 ms. That difference is retry and backoff against 429s, not inference.
2. **Dead candidates in the fallback chain.** `qwen/qwen3.6-27b` 404, `gemini-2.0-flash` 404, `gemini-1.5-flash` 404. Each is a wasted round trip. Walking the full chain costs ~120 s for one logical call.
3. **Token burn.** 5.6 calls × ~2.3k tokens ≈ 13k tokens per question, exhausting a 200k daily quota in ~15 questions.
4. **Unconditional LLM calls on the fast path.** SIMPLE questions answered deterministically still spend 1–2 calls on `supervisor` and `validator`.
5. **Frontend bundle.** 5,473 kB JS (1,638 kB gzip) in a single chunk.

Non-bottlenecks, confirmed by measurement: DuckDB (sub-millisecond on 100-question suites), CSV ingestion (91.6 ms), question generation (34.8 ms p50), schema profiling (cached).

---

## 12. Accuracy risks

- **No end-to-end NL→SQL accuracy number exists.** The 100/100 figures come from harnesses that execute ground-truth SQL directly; they validate the data layer, not the AI. Quoting them as system accuracy would be the single most misleading thing this project could do.
- The only NL→SQL evidence is one 10-question run at **8/10 pipeline success**, with 2 answers independently verified correct and 6 unverified.
- Complexity classification is inconsistent. "Which customer regions have above-average revenue but below-average profit?" classified as MEDIUM; "How has revenue changed over time by month?" classified as COMPLEX. The router's labels do not track actual analytical difficulty.
- Provider degradation silently changes model identity mid-run: two questions were answered by `gpt-oss-20b` after `120b` failed. Answer quality varies by model with no signal to the user.

## 13. Hallucination risks

Structurally well defended. Results come from DuckDB, the report node narrates executed output, 17 red-team tests probe for invention, and abstention works — "Which supplier has the highest employee satisfaction?" correctly returned that the field does not exist.

Residual risks:
- Abstention took **140 s** and was reported as `success: true`, which conflates "the pipeline ran" with "the user got an answer."
- `report_agent` receives result rows and could editorialize beyond them; grounding tests cover this but coverage is not exhaustive.
- Under provider failure the system can fall back to a weaker model whose narration is less faithful, with no user-visible marker.

## 14. SQL risks

Read-only enforcement and quality validation are solid (11 + 10 tests). Real gaps:
- **"What percentage of total revenue comes from the top 10 products?" failed outright** after one repair — 4 codegen calls, 174.9 s, no answer. Percent-of-total over a top-N subset is a core analytical pattern and it does not work.
- Repair is capped at one attempt, which is correct policy, but when generation is failing due to provider errors the repair burns another full fallback walk.
- Semantic validation is rule-based; novel phrasings can slip through with syntactically valid but semantically wrong SQL.

## 15. Session isolation risks

Design is sound: one DuckDB `:memory:` connection per session, per-session lock, 1800 s TTL, eviction, and cache keys that include `session_id`. No cross-session leak was found.

Risks: all sessions live in a single process, so one heavy session competes for CPU with others; expired-session cleanup is TTL-driven, so abandoned sessions hold memory until TTL; there is no cap on concurrent sessions, and on a free-tier instance memory exhaustion is plausible before the TTL fires. **No concurrency or load test exists**, so isolation under load is unproven.

## 16. Performance risks

- p95 of **284 s** exceeds every reasonable client and proxy timeout. Vercel's `maxDuration` is 300 s — a single expert question nearly hits the platform ceiling.
- No global timeout on the LLM call chain; a single question can occupy a worker for two minutes per node.
- No LLM response cache, so repeated prompts re-burn quota.
- Free-tier Render plus free-tier Groq means the measured p50 is what real users would get today.

## 17. UX risks

- 133 s median response with no partial output or streaming. Users will assume the app is broken.
- Ambiguous input fails badly: "Show me sales" returned **"Analysis Failed"** after 126 s instead of asking which metric was meant. The ambiguity-clarification behavior described in the design is not what the pipeline actually does.
- Production frontends load but cannot analyze anything, because no backend is reachable.
- 1.6 MB gzipped JS bundle delays first paint on slow connections.
- A production build without `VITE_API_BASE_URL` silently targets `localhost:8000`.

---

## 18. P0 issues

| # | Issue | Evidence |
|---|---|---|
| P0-1 | **Production backend is down.** Render suspended (503), no working Vercel API (404). The deployed product cannot answer a single question. | Live probes |
| P0-2 | **LLM fallback chain is dead or exhausted.** `qwen/qwen3.6-27b` 404, `gemini-2.0-flash` 404 (and it is the configured production default), `gemini-1.5-flash` 404, `gemini-3.6-flash`/`flash-latest` 429 after ~36 s each. No working fallback exists. | Per-model probes |
| P0-3 | **p50 133 s / p95 284 s**, driven by 429 retry storms across dead candidates — up to ~120 s for one logical call. No timeout caps this. | 10-question live run + node timings |
| P0-4 | **Token budget exhausted in ~15 questions** (5.6 calls × ~2.3k tokens vs 200k/day), which is what triggers P0-3 and the failing test. | Prompt sizes + 429 body |
| P0-5 | **No end-to-end NL→SQL accuracy measurement.** Existing 100% figures measure the SQL harness, not the AI. | Benchmark source review |

## 19. P1 issues

| # | Issue | Evidence |
|---|---|---|
| P1-1 | Percent-of-total-over-top-N questions fail entirely after repair. | Live run, question 6 |
| P1-2 | Ambiguous questions return "Analysis Failed" instead of a clarification. | Live run, question 10 |
| P1-3 | One test depends on live LLM quota and fails when exhausted. | `test_lead_analyze` |
| P1-4 | Deterministic fast path still spends 1–2 LLM calls on `supervisor`/`validator`. | Per-node call attribution |
| P1-5 | Complexity classification does not track real difficulty. | Live run labels |
| P1-6 | `/health` returns 200 with `agent_ready: False`; not a readiness probe, yet Render uses it as one. | Health body + `render.yaml` |
| P1-7 | No LLM response cache; identical prompts re-burn quota. | Code review |
| P1-8 | No Python lint or type gate (`ruff`/`mypy` absent). | Tooling probe |
| P1-9 | Frontend ships 5.5 MB in one chunk. | Build output |

## 20. P2 issues

| # | Issue |
|---|---|
| P2-1 | `SANDBOX_MEMORY_LIMIT_MB` configured but not enforced; code comments confirm no cgroup limit. |
| P2-2 | CORS `allow_methods=["*"]` / `allow_headers=["*"]` broader than necessary. |
| P2-3 | No frontend tests. |
| P2-4 | No load or concurrency tests; session isolation under load unproven. |
| P2-5 | `API_BASE` silently defaults to `localhost:8000` in production builds. |
| P2-6 | Dead code in `config.py` — a no-op `for … : pass` loop above the model-candidate list. |
| P2-7 | Abstention and hard failure both surface as `success: true` / generic failure text; response semantics are muddled. |
| P2-8 | No authentication on any endpoint; rate limiting is the sole abuse control. |

---

## 21. Recommended repair order

Ordered so that each step makes the next one measurable. Nothing here has been executed.

**Stage 1 — make the system usable again (P0-2, P0-3, P0-4)**
1. Prune dead models from the candidate chains; keep only models that respond. Update `GEMINI_FALLBACK_MODEL` in `render.yaml` off `gemini-2.0-flash`.
2. Add per-call and per-request timeouts plus fail-fast on 429 so a rate-limited provider is abandoned in seconds, not minutes. Disable client-side retry storms.
3. Cut LLM calls per question from 5.6 toward 2–3: skip `supervisor`/`validator` calls when the deterministic path already produced a grounded answer, and make visualization generation deterministic where the chart type is obvious.
4. Add an LLM response cache keyed by prompt hash.

Expected effect: p50 and p95 collapse toward the deterministic path's 1–2 s, and daily quota stretches roughly 2–3×. Re-measure before claiming anything.

**Stage 2 — restore production (P0-1, P1-6)**
5. Bring up a reachable backend, set `CORS_ALLOWED_ORIGINS` and `VITE_API_BASE_URL` explicitly, and make `/health` reflect real readiness including `agent_ready`.
6. Re-run the live probes and record results.

**Stage 3 — establish real accuracy evidence (P0-5)**
7. Build the 150-question NL→SQL suite with independently computed ground truth, across multiple schemas so it cannot overfit the demo dataset.
8. Publish per-difficulty accuracy, requirement coverage, hallucination rate, and abstention correctness — clearly separated from the existing SQL-harness numbers.

**Stage 4 — fix known correctness and UX failures (P1-1, P1-2, P1-5, P1-3)**
9. Add a validated percent-of-total-over-top-N pattern to the SQL pattern library, with a regression test.
10. Route ambiguous questions to an explicit clarification response instead of a failure.
11. Recalibrate the complexity router against the new benchmark.
12. Make the lead-analyze test hermetic by mocking the provider; keep a separate opt-in live smoke test.

**Stage 5 — hardening and polish (P1-8, P1-9, P2-\*)**
13. Add `ruff` + `mypy` to dev requirements and CI.
14. Code-split the frontend bundle.
15. Enforce the sandbox memory limit or remove the setting that implies it is enforced.
16. Narrow CORS methods/headers; add concurrency tests for session isolation.

---

## Bottom line

The analytical core is in good shape: DuckDB answers 200 benchmark questions correctly in sub-millisecond time, question discovery is 100% schema-valid and executable across 8 datasets, session isolation and SQL safety are properly implemented, and the two live answers I checked against independent ground truth were numerically exact.

The failure is entirely at the LLM boundary. A dead fallback chain and an exhausted token budget turn 1-second work into 133-second median responses, and production has no reachable backend at all. Stage 1 and Stage 2 of the repair order address problems that are configuration and call-budget issues rather than architectural ones — which is the good news buried in these numbers.

**Phase 0 complete. No production code was modified. Awaiting approval before Phase 1.**
