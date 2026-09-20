# MarketMind AI — Full Technical Context

> Paste this whole file into an LLM when you want architecture review, refactor suggestions, or improvement plans. It is a factual dump of the current repository state, not marketing copy.

---

## 0. TL;DR for a reviewing model

MarketMind AI is an **agentic B2B marketplace intelligence platform**. A React frontend talks to a FastAPI backend that runs **two independent LangGraph workflows**:

1. **Marketplace Analytics** — a supervisor-routed graph that turns natural-language questions into SQL/Python over DuckDB, then produces charts + a narrative report.
2. **Lead Intelligence** — a linear graph that parses a free-text buyer requirement, validates it, matches products and suppliers, and ranks suppliers with a **deterministic formula** (no LLM ranking).

Both write run/node telemetry to an observability layer (PostgreSQL with in-memory fallback).

- Backend: ~16,500 lines of Python
- Frontend: ~10,400 lines of TS/TSX
- Tests: 159 total, **153 pass / 6 fail** (failures documented in §13)

**Live:**
- Frontend (Vercel): https://marketmind-ai-pankaj.vercel.app
- Backend (Render free): https://marketmind-ai-93u1.onrender.com
- Repo: https://github.com/pankaj29-noi/MarketMind-AI

---

## 1. Repository layout

```
MarketMind-AI/
├── backend/
│   ├── main.py                      # FastAPI app, all HTTP endpoints, lifespan
│   ├── config.py                    # env loading, LLM provider resolution, DEMO_MODE
│   ├── agents/                      # Marketplace Analytics LangGraph
│   │   ├── graph.py                 # StateGraph build + checkpointer choice
│   │   ├── state.py                 # AgentState TypedDict
│   │   ├── schemas.py               # Pydantic report/response models
│   │   ├── sandbox.py               # Python execution sandbox
│   │   ├── capability_registry.py   # Supervisor capability → entry node map
│   │   └── nodes/                   # 13 graph nodes (see §4)
│   ├── marketplace/
│   │   ├── demo_data.py             # DuckDB seed load, schema profile
│   │   ├── sql_fallback.py          # Deterministic SQL for known questions
│   │   ├── observability.py         # Runs, node timings, feedback (PG + memory)
│   │   └── lead/                    # Lead Intelligence LangGraph
│   │       ├── graph.py             # 6-node workflow + routing + run wrapper
│   │       ├── nodes.py             # Node implementations + LLM parser prompt
│   │       ├── ranking.py           # Deterministic supplier scoring
│   │       ├── matching.py          # Product/supplier search over DuckDB
│   │       ├── schemas.py           # Pydantic lead models
│   │       └── state.py             # LeadAgentState TypedDict
│   ├── services/
│   │   ├── analytics_fallback.py    # Generic deterministic SQL fallback (649 L)
│   │   ├── requirement_coverage.py  # Semantic requirement extraction/checks (1161 L)
│   │   ├── session_manager.py       # DuckDB per-session connections + TTL
│   │   ├── pdf_generator.py         # ReportLab PDF reports
│   │   ├── statistics.py
│   │   ├── reporting/               # fact_generator, recommendation_engine,
│   │   │                            # report_grounding, report_mode, failure_formatter
│   │   ├── visualization/           # selector, templates, formatter, validator
│   │   ├── sql/sql_quality_validator.py
│   │   └── python/python_quality_validator.py
│   ├── database/
│   │   ├── connection.py            # psycopg pool, init_db, soft-fail
│   │   └── repository.py            # sessions, reports, metrics (+ memory fallback)
│   ├── mcp/                         # data_access + optional MCP client
│   ├── mcp_server/server.py         # Standalone FastMCP server (optional)
│   ├── utils/                       # analytical_roles, json_sanitizer, provider_errors
│   └── tests/                       # 16 pytest files
├── frontend/                        # React 19 + Vite 8 + Tailwind v4
├── data/marketplace/*.csv           # Synthetic seed data
├── docker-compose.yml               # Local Postgres 16
├── start.sh                         # One-command local dev
├── requirements.txt                 # Runtime deps (Render installs this)
├── requirements-dev.txt             # Full deps incl. mcp/pytest/fastmcp
├── requirements-vercel.txt          # Slim experiment (Vercel attempt)
├── render.yaml / Procfile / build.sh
├── vercel.json                      # (legacy API attempt) / frontend/vercel.json
├── pyproject.toml / runtime.txt / pytest.ini
└── README.md
```

---

## 2. Tech stack (actual installed versions)

**Backend** (`requirements.txt`)
```
fastapi>=0.100.0        uvicorn>=0.20.0        duckdb>=0.9.0
langgraph>=0.0.10       langchain-core>=0.1.0  langchain-groq>=0.1.0
langchain-google-genai>=1.0.0                  psycopg[binary,pool]>=3.1.0
plotly>=5.15.0          reportlab>=4.0.0       pandas>=2.0.0
python-dotenv>=1.0.0    pydantic>=2.0.0        python-multipart>=0.0.6
charset-normalizer>=3.0.0                      httpx>=0.27.0
mcp>=1.0.0              langgraph-checkpoint-postgres>=1.0.0
langchain-mcp-adapters>=0.3.0                  fastmcp>=3.4.4
```
Python 3.12.8 on Render; local venv is 3.13.

**Frontend** (`frontend/package.json`)
- react 19.2, react-dom 19.2, typescript ~6.0, vite 8.1
- tailwindcss 4.3 (+ `@tailwindcss/vite`), tw-animate-css
- framer-motion 12.42, lucide-react 1.23
- plotly.js-dist-min 3.7, recharts 3.9
- ~25 `@radix-ui/*` primitives, cmdk, vaul, sonner, zod 4, react-hook-form
- lint: `oxlint`

---

## 3. Data model (synthetic seed CSVs in `data/marketplace/`)

| File | Rows | Columns |
|---|---:|---|
| `categories.csv` | 20 | `id, name, parent_id` |
| `suppliers.csv` | 80 | `id, name, city, state, rating, verified, response_time_hours` |
| `buyers.csv` | 160 | `id, company_name, city, state, industry` |
| `products.csv` | 431 | `id, supplier_id, category_id, name, price, moq, stock` |
| `leads.csv` | 800 | `id, buyer_id, product_id, quantity, city, state, status, created_at, estimated_value` |
| `orders.csv` | 550 | `id, buyer_id, supplier_id, status, order_date, amount` |

Total 2,041 rows. Loaded into **DuckDB per session** (`POST /marketplace/demo` copies seeds to a scratch dir and registers 6 tables). Relationships are declared in `MARKETPLACE_RELATIONSHIPS` (`demo_data.py`) and fed to the LLM as schema context.

**All data is synthetic.** No real customer/supplier records.

---

## 4. Marketplace Analytics graph (`backend/agents/`)

### Nodes registered in `graph.py`
`supervisor`, `schema_profiler`, `planner`, `code_generator`, `python_analyst`, `sandbox_executor`, `validator`, `reflection`, `analysis_engine`, `visualization_generator`, `visualization_executor`, `visualization_reflection`, `report_agent`

### Routing
Entry point is `supervisor`. It emits a `SupervisorDecision` each turn; `route_supervisor()` reads `supervisor_history[-1]`, maps `selected_capability` → entry node via `CAPABILITIES`, and returns `END` on `TERMINATE` or an unknown capability. Worker chains (`schema_profiler`, `reflection`, `analysis_engine`, …) edge back to `supervisor`.

### Capability registry (`capability_registry.py`)
| Capability | Entry node | Purpose |
|---|---|---|
| `SCHEMA` | `schema_profiler` | Table structures, columns, relationships |
| `SQL` | `planner` | Plan → SQL generation → execution |
| `ANALYSIS` | `analysis_engine` | Deterministic stats (correlation, distribution, trend, outliers) |
| `VISUALIZATION` | `visualization_generator` | Plotly chart code |
| `PYTHON_ANALYSIS` | `python_analyst` | Rolling windows, regex, fuzzy matching |
| `REPORT` | `report_agent` | Final structured report + PDF |

### Checkpointer
`PostgresSaver` when a pool exists, else `MemorySaver`. Serializer is `JsonPlusSerializer` with an msgpack allowlist of `[ConfidenceLevel, ChartType]`. The `PostgresSaver` import is **lazy** so deployments without `langgraph-checkpoint-postgres` still boot.

### `AgentState` (key fields, `state.py`)
```
session_id, dataset_id, duckdb_table
schema_profile, question, resolved_question, conversational_context
plan, generated_code, expected_output_type
execution_success, execution_time_ms, output_summary, query_result
validation_passed, failure_summary, retry_count, retry_target, graceful_failure
retry_history: List[FailureSummary]
vis_spec, vis_generated_code, vis_retry_count, vis_retry_history
final_report, execution_metadata
last_worker_result: WorkerResult
supervisor_history: List[SupervisorDecision]
overall_confidence, analysis_artifacts
```
`FailureSummary = {failure_type, error_message, code_context, expected_vs_actual}` where `failure_type ∈ {runtime, structural, semantic, timeout, visualization}`.

`WorkerResult` carries `status`, `confidence`, `summary`, `routing_hint`, `analysis_type`, `duration_ms`, `token_usage`, `estimated_cost`.

### Semantic correctness layer
- `services/requirement_coverage.py` (1,161 lines) extracts `QuestionRequirements` from the question (dimensions, metrics, derived values, operations), builds a **semantic requirement contract** for the prompt, runs a **generation precheck**, checks **plan coverage**, and computes `confidence_from_coverage`.
- `services/reporting/report_grounding.py` verifies report claims against actual result columns/rows, flags missing-claim/causation/exaggeration patterns, softens causal language, and can repair report text.
- `services/sql/sql_quality_validator.py` and `services/python/python_quality_validator.py` gate generated code.

### Deterministic fallbacks
- `marketplace/sql_fallback.py` — handles known marketplace questions without an LLM; also `is_marketplace_domain_question()` and `unsupported_user_message()`.
- `services/analytics_fallback.py` — generic column-role mapping (metric/dimension/date aliases) producing SQL for arbitrary single-table datasets; returns a source tag (`deterministic_fallback` / `groq` / `gemini`).

---

## 5. Lead Intelligence graph (`backend/marketplace/lead/`)

### Flow
```
requirement_parser → validation → product_matcher → supplier_matcher
                                → supplier_ranker → response_formatter → END
```
Conditional early exits all route to `response_formatter`:
- validation → `needs_info` / `failed`
- product_matcher → `no_products`
- supplier_matcher → `no_suppliers`

Every node is wrapped by `_timed_node()`, which records `{node_name, execution_order, duration_ms, status, error_message}` into `state.node_executions` and converts exceptions into a `failed` status instead of crashing the graph.

`run_lead_analysis()` creates a `run_id`, invokes the graph, calls `complete_workflow_run(...)`, and returns a serializable response including `ranking_formula`, `stop_reason`, `latency_ms`, and `node_executions`.

### `LeadAgentState`
```
session_id, requirement_text, run_id
extracted_requirement, validation_result
matched_products, candidate_suppliers, recommended_suppliers
node_executions
workflow_status ∈ {running, needs_info, no_products, no_suppliers, complete, failed}
error, stop_reason
```

### Extraction prompt (`nodes.py`, `PARSER_SYSTEM`)
Returns strict JSON: `product_name, product_category, quantity, unit, city, state, delivery_time, buyer_intent ∈ {purchase, quote, enquiry, bulk_purchase, unknown}, confidence_score`.
Rules explicitly forbid inventing products/cities/quantities, require null for unknowns, and map obvious Indian cities to states.

### Validation rules
- `REQUIRED_FIELDS = ["product_name"]`
- `IMPORTANT_OPTIONAL = ["quantity", "city", "state", "delivery_time"]` → warnings only
- `confidence_score < 0.4` (with no missing required) → low-confidence warning
- Missing required → `needs_info`, `stop_reason="missing_required_fields"`

### Matching (`matching.py`)
- `ensure_marketplace_session()` auto-restores the marketplace dataset if the session lost its DuckDB tables.
- `CITY_STATE_MAP` for location normalization.
- Tokenization + `_token_overlap_score` + `_expand_query_tokens` (uses product name and category) to search products; then `fetch_supplier_candidates()` aggregates supplier attributes and order performance.

### Ranking (`ranking.py`) — deterministic, no LLM
```
final_score =
    0.35 * product_match_score       # best product text/category match, [0,1]
  + 0.20 * rating_score              # supplier.rating / 5.0
  + 0.15 * verified_score            # 1.0 if verified else 0.0
  + 0.15 * response_time_score       # clamp(1 - hours/72)
  + 0.10 * order_performance_score   # delivered/confirmed share + volume
  + 0.05 * location_score            # same city 1.0, same state 0.6, else 0.0
```
`build_explanation()` produces a human-readable breakdown attached to each recommendation.

---

## 6. Observability (`backend/marketplace/observability.py`)

- Tables: workflow runs, node executions, feedback (PostgreSQL).
- Module-level in-memory fallbacks `_MEMORY_RUNS / _MEMORY_NODES / _MEMORY_FEEDBACK`, plus a `_DB_UNAVAILABLE` latch so a dead DB is only probed once.
- `sanitize_error_message()` strips secrets and truncates to 500 chars before persisting or returning.
- API: `create_workflow_run`, `complete_workflow_run`, `save_workflow_feedback`, `get_workflow_run`, `list_workflow_runs`, `get_node_executions`, `get_observability_summary`.
- Summary shape: `total_runs, complete_count, failure_count, running_count, success_rate, average_latency_ms, total_feedback, helpful_feedback_count, helpful_feedback_rate`.

Separately, `database/repository.py` records legacy analytics metrics (`first_try_success`, `retry_success`, `failed`, failure-type histogram) surfaced at `GET /metrics`.

---

## 7. HTTP API (`backend/main.py`, 862 lines)

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{status, service, agent_ready}` — Render health check |
| POST | `/upload` | Single CSV; BOM + charset-normalizer encoding detection |
| POST | `/marketplace/demo` | Loads 6 DuckDB tables, returns `session_id, dataset_id, row_count, tables` |
| POST | `/analyze` | Body `{session_id, question}` — analytics graph |
| POST | `/marketplace/lead/analyze` | Body `{session_id?, requirement}` |
| POST | `/marketplace/feedback` | `{run_id, rating: helpful\|not_helpful, comment?}` |
| GET | `/marketplace/observability/runs?limit=50` | Recent runs |
| GET | `/marketplace/observability/summary` | Aggregate metrics |
| GET | `/execution/{session_id}/trace` | Analytics execution trace |
| GET | `/history/{session_id}` | Session report history |
| GET | `/report/{execution_id}/pdf` | ReportLab PDF |
| GET | `/metrics` | Legacy analytics metrics |
| GET | `/docs` | Swagger UI |

**CORS:** `allow_origins=["*"]`, `allow_credentials=True`, all methods/headers.
⚠️ `*` + credentials is contradictory per spec and is a real hardening item (see §14).

**Lifespan:** initializes the DuckDB session manager, attempts `init_db()` (soft-fails), builds the analytics graph with `PostgresSaver` and retries with `MemorySaver` on failure, and starts a background session-cleanup scheduler.

---

## 8. Configuration (`backend/config.py`, 305 lines)

Loads `.env` from project root explicitly (not CWD-dependent).

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | empty | Postgres URL; absent ⇒ memory fallbacks (no hard failure) |
| `GROQ_API_KEY` | — | Primary LLM |
| `GOOGLE_API_KEY` | — | Gemini fallback |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Retired IDs auto-replaced |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.0-flash` | Candidate list with retirement handling |
| `DEMO_MODE` | `auto` | `auto` / `true` / `false` |
| `SANDBOX_TIMEOUT_SECONDS` | `10` | Python sandbox |
| `SANDBOX_MEMORY_LIMIT_MB` | `256` | Python sandbox |

Guard helpers: `_is_placeholder_key()` (rejects `your_groq_api_key`, `changeme`, `<20` chars, …), `_looks_like_api_key()` (prefixes `gsk_`, `AIza`, `AQ.`, `ya29.`, `sk-`) so a key pasted into a model-name field is caught.

Writable paths adapt to serverless: `get_runtime_data_root()` → `/tmp/marketmind` when `VERCEL` is set, else repo dirs; `get_scratch_root()` / `get_uploads_root()` derive from it.

`get_llm()` builds Groq first, Gemini fallback; `invoke_llm()` raises a clear `ValueError` when no valid key exists and `DEMO_MODE` forbids deterministic paths.

---

## 9. Frontend (`frontend/src`, ~10.4k lines)

### Pages
- `Workspace.tsx` — analytics chat, upload zone, marketplace demo, report render
- `LeadIntelligence.tsx` — requirement input, signal meters, ranked suppliers, feedback
- `AgentMonitoring.tsx` — run history + observability summary
- `Analytics.tsx` — legacy metrics dashboard

### Component groups
- `layout/` — `AppHeader`, `AppSidebar`, `ModuleNavItem`, `SystemStatus`, `ContentViewport`, `IntelligenceBackground`, `RightSidebar`, `WorkspaceLayout`, legacy `Sidebar`
- `analysis/` — `AnalysisPipeline`, `IntelligenceSignal`
- `chat/` — `ChatComposer`, `UserMessage`
- `report/` — `Report`, `ReportCard`, `ExecutiveSummaryCard`, `InsightCard`, `RecommendationCard`, `ChartCard`, `ResultsTableCard`, `SQLViewer`, `DebugPanel`, `ReportActions`
- `lead/` — `SignalMeter`, `OpportunitySignal`, `LeadAnalyzingState`
- `monitoring/` — `ExecutionObservatory`, `RunHistoryList`, `SystemTracePanel`, `missionControl.ts`
- `analytics/` — `AnalyticsKpis`, `AnalyticsCharts`, `RecentExecutionsTable`
- `ui/` — ~50 shadcn-style Radix wrappers
- `PlotlyChart.tsx` — Plotly renderer

### Services / lib / types
- `services/observability.ts` — `fetchObservabilityRuns`, `fetchObservabilitySummary`, `submitWorkflowFeedback`; `WorkflowRun` and `ObservabilitySummary` interfaces
- `services/analytics.ts` — `fetchMetrics`, `computeMetrics`
- `lib/api.ts` — `API_BASE = VITE_API_BASE_URL || "http://localhost:8000"`
- `lib/marketplace.ts`, `lib/pipelineSteps.ts`, `lib/toast.ts`, `lib/utils.ts`
- `hooks/useAnalytics.ts`, `hooks/useCountReveal.ts`, `hooks/use-mobile.tsx`
- `types/` — `analysis`, `analytics`, `chat`, `index`, `lead`, `report`, `plotly.d.ts`

### Design system
Tailwind v4 tokens in `index.css` (~840 changed lines): dark cyan/steel "intelligence command center" palette, glass surfaces, ambient animated background, count-reveal and phase-state motion via framer-motion. Deliberately not generic purple SaaS.

---

## 10. Local development

```bash
./start.sh                        # Postgres (if Docker), backend :8000, frontend :5173
```

Manual:
```bash
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp -n .env.example .env
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
cd frontend && npm install && npm run dev
```

Without Docker/Postgres: marketplace demo, Lead Intelligence, and analytics still work using memory fallbacks and `MemorySaver`.

---

## 11. Production deployment (current)

| Piece | Host | Config |
|---|---|---|
| Frontend | Vercel project `marketmind-ai` | root `frontend/`, Vite, `frontend/vercel.json` SPA rewrite |
| Backend | Render web service (free) | root = repo root, `bash build.sh`, `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`, health `/health` |

- Frontend env: `VITE_API_BASE_URL=https://marketmind-ai-93u1.onrender.com` (Production + Preview). Vite inlines this at build time, so **env changes require a redeploy**.
- Vercel SSO/deployment protection was disabled so the demo is publicly reachable.
- Render env: `GROQ_API_KEY`, `GOOGLE_API_KEY`, `GROQ_MODEL`, `GEMINI_FALLBACK_MODEL`, `DEMO_MODE=auto`, `PYTHON_VERSION=3.12.8`, sandbox limits. **No `DATABASE_URL`** currently → observability/history are in-memory and reset on restart/spin-down.

### Why the backend is not on Vercel
Attempted and abandoned. Failure chain:
1. `memory: 3008` rejected — Hobby max is 2048 → lowered to 1024.
2. Bundle **331.40 MB > 225 MB** limit with a custom pip install command.
3. Removing the custom install, trimming deps, `fluid: true`, `excludeFiles`, and `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` still did not land a successful build; deploys hung.

Root cause: duckdb (~21 MB) + numpy (~17 MB) + pandas (~11 MB) + plotly (~9 MB) + pillow (~7 MB) + psycopg-binary (~5 MB) + langchain/langgraph stack blow past the serverless function size limit, and the agent workloads are long-running. A container/VM host (Render/Railway/Fly) is the correct target. `vercel.json`, `pyproject.toml`, and `requirements-vercel.txt` are leftovers from that attempt.

---

## 12. Tests

```bash
python -m pytest                                        # full suite
python -m pytest backend/tests/test_marketplace_lead.py -v
```

16 test files: `test_analytical_pipeline`, `test_analytics_demo_fallback`, `test_code_generation_semantics`, `test_components`, `test_fallback`, `test_marketplace_analytics_fallback`, `test_marketplace_lead`, `test_mcp`, `test_planner_semantics`, `test_provider_errors`, `test_report_grounding`, `test_report_semantics`, `test_requirement_coverage`, `test_semantic_redteam`, `test_sql_quality_validator`, `test_visualization_integration`.

**Current result: 153 passed, 6 failed, 22s.**

---

## 13. Known failing tests (real, reproducible)

| Test | Error | Likely cause |
|---|---|---|
| `test_fallback.py::test_primary_success` | `ValueError: No valid LLM API key configured` (`config.py:246`) | Tests don't stub `invoke_llm`; provider guard added later now raises before the mock path |
| `test_fallback.py::test_fallback_success` | same | same |
| `test_fallback.py::test_fallback_configured` | same | same |
| `test_fallback.py::test_fallback_behavior_no_google_key` | same | same |
| `test_mcp.py::test_mcp_tool_discovery` | `Failed: async def ... ` | `pytest.mark.asyncio` used without `pytest-asyncio` installed/registered |
| `test_visualization_integration.py::test_malformed_spec_handling` | `assert {...'is_appropriate': False...} is None` | Validator now returns a structured rejection dict; test still expects `None` |

None of these are runtime bugs in the shipped app — they are stale tests that drifted behind later hardening. They should still be fixed.

---

## 14. Known issues, risks, and improvement candidates

**Security / correctness**
1. CORS is `allow_origins=["*"]` **with** `allow_credentials=True`. Restrict to the Vercel origins (and localhost) or drop credentials.
2. LLM API keys were pasted into chat/terminal during deployment. **Rotate the Groq and Google keys.**
3. No authentication on any endpoint — anyone can upload CSVs and consume LLM quota on the public URL. Add at minimum a rate limit or shared-secret header.
4. `/upload` has no explicit size cap visible at the route level; large CSVs on a 512 MB Render instance can OOM.
5. Uploaded CSVs and scratch files persist per session on disk with TTL eviction; on Render's ephemeral disk this is fine, but there's no explicit cleanup guarantee on crash.

**Reliability / architecture**
6. No `DATABASE_URL` in production ⇒ observability, history, and metrics reset on every cold start. Attaching Neon/Supabase Postgres would make Agent Monitoring meaningful in the demo.
7. Render free tier spins down; first request takes ~30–60 s. A keep-alive ping or a paid instance fixes the demo experience.
8. `maxDuration` concerns aside, long analytics runs under 0.1 CPU / 512 MB will be slow; supervisor retry loops amplify this.
9. Two parallel fallback engines (`marketplace/sql_fallback.py` and `services/analytics_fallback.py`) with overlapping responsibility — candidate for consolidation.
10. `requirement_coverage.py` at 1,161 lines and `analytics_fallback.py` at 649 lines are the two biggest complexity hotspots; both are heuristic/regex-heavy and hard to test exhaustively.
11. `report_agent.py` (~972 lines) and `main.py` (862 lines) are large; `main.py` mixes routing, orchestration, and serialization and could be split into routers.
12. MCP integration is half-live: `backend/mcp/client.py` imports lazily and returns `None` when adapters are missing; `mcp_server/` is excluded from deploys. Either finish it or remove it.
13. Dead deployment config (`vercel.json`, `pyproject.toml`, `requirements-vercel.txt`) should be removed now that Render is the API host.
14. `requirements.txt` vs `requirements-dev.txt` split is subtle — Render installs the full list including `pytest` and `fastmcp`, which is heavier than needed.

**Product / UX**
15. No streaming: `/analyze` is a single blocking POST, so the pipeline UI animates on a guess rather than real node events. SSE/WebSocket streaming of node transitions would be a major upgrade.
16. No auth means no per-user history; sessions are opaque UUIDs.
17. Analytics node-level timings are not exposed on the monitoring endpoints (only Lead Intelligence runs are), so Agent Monitoring shows a partial picture.
18. Frontend has no error boundary around report rendering; a malformed Plotly payload can blank the panel.
19. `frontend/src/components/ui/` carries ~50 shadcn primitives, many unused — dead-code trimming would cut bundle size.

---

## 15. Demo script (what to show)

1. Open https://marketmind-ai-pankaj.vercel.app (allow for Render cold start).
2. Click **Load Marketplace Demo** → 6 tables, 2,041 rows.
3. Ask: *Which product categories generated the highest order value?*
4. Show the report: executive summary, insights, chart, results table, SQL, debug trace.
5. Go to **Lead Intelligence** → *Need 500 solar panels in Jaipur within two weeks*.
6. Show extracted requirement, matched products, ranked suppliers, score explanation, node timings, latency.
7. Submit **Helpful** feedback.
8. Open **Agent Monitoring** → run history and summary metrics.
9. Edge cases: *Need xyz unknown widget* → `no_products`; *asdf* → `needs_info`.

**Good analytics questions:** highest order value by category; states with most buyer enquiries; lead conversion rate by category; suppliers with fastest response times.

**Good lead requirements:** industrial water pumps in Delhi; bulk packaging boxes in Mumbai; agricultural machines in Nashik.

---

## 16. Suggested prompt when handing this to a model

> Here is the full technical context of my project, MarketMind AI. Act as a senior engineer reviewing it for a portfolio/interview setting. Identify the highest-impact improvements ranked by effort vs. payoff, focusing on (a) production hardening, (b) architectural simplification of the two fallback engines and the oversized modules, (c) making the agent pipeline observable in real time, and (d) fixing the six failing tests. Give me concrete file-level changes, not general advice.
