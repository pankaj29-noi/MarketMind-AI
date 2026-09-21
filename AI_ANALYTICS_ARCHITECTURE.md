# MarketMind AI — Analytics Architecture

**Captured:** 2026-09-21  
**Repo:** `DataAgent-Pro` / MarketMind AI  
**Scope:** Natural-language CSV analytics (3k–4k rows) + related surfaces  
**Principle:** DuckDB results are the source of truth; the LLM is planner/interpreter only.

This document describes the **actual** implementation, not an aspirational redesign.

---

## 1. System surfaces

| Surface | Stack | Entry |
|---|---|---|
| Frontend | React + Vite (`frontend/`) | Upload → `/analyze` chat; Lead; Monitoring |
| Analytics API | FastAPI (`backend/main.py`) | `/upload`, `/analyze`, `/session/{id}/suggested-questions` |
| Lead Intelligence | Separate LangGraph (`backend/marketplace/lead/`) | `/marketplace/lead/analyze` |
| Data plane | Per-session in-memory DuckDB (`session_manager.py`) | `register_csv` / `execute_query` |
| Checkpointer | PostgresSaver if pool up, else MemorySaver | LangGraph thread = `session_id` |
| LLM | Local SQLCoder (primary) → Groq → Gemini → deterministic SQL | `sqlcoder_service` + `config.invoke_llm` |
| Deploy | Render API + Vercel FE | `render.yaml`, `vercel.json` |

---

## 2. End-to-end analytics flow (actual)

```
USER QUESTION  (POST /analyze)
    │
    ├─ session lookup (memory-first; Postgres soft-fail)
    ├─ optional RESULT CACHE hit (session + dataset fingerprint + normalized Q)
    │       └─ return cached AnalysisResponse (0 LLM)
    │
    ▼
SUPERVISOR  (entry of LangGraph)
    │
    ├─ if no schema_profile → SCHEMA
    │       schema_profiler_node
    │         • marketplace: multi-table profile
    │         • CSV: get_or_build_csv_schema_profile (rich, NO MCP)
    │         • cache on session.schema_profile_cache[dataset_id]
    │       └─ back to SUPERVISOR
    │
    ├─ deterministic capability routing (keyword heuristics)
    │       SQL | ANALYSIS | PYTHON_ANALYSIS
    │   else LLM supervisor routing (follow-up resolution)
    │
    ▼
QUESTION UNDERSTANDING (distributed today)
    • supervisor may set resolved_question for follow-ups
    • classify_question_complexity → SIMPLE | COMPLEX | VERY_COMPLEX
    • requirement_coverage.extract_* used in planner / codegen / validator / report
    │
    ▼
ANALYTICAL PLAN  (SQL capability)
    planner_node
      → structured plan steps
      → check_plan_requirement_coverage
    │
    ▼
SQL / PYTHON GENERATION
    code_generator_node  (SQL + schema-grounded prompts + deterministic fallback)
      OR python_analyst_node
    │
    ▼
VALIDATION (pre-exec quality)
    sql_quality_validator / python_quality_validator
    check_requirement_coverage on generated SQL
    │
    ▼
DUCKDB EXECUTION
    sandbox_executor_node → session_manager / read-only SQL guard
    │
    ▼
RESULT + SEMANTIC VALIDATION
    validator_node
      → structural checks, requirement coverage, empty-result handling
    reflection_node
      → success → REPORT (or VISUALIZATION if chartable)
      → fail → retry (cap 3) OR graceful REPORT
      → provider_error / unsupported → no retry, REPORT
    │
    ▼
VISUALIZATION (optional)
    skipped for SIMPLE ≤5-row results
    else: visualization_generator → executor → reflection
    │
    ▼
ANSWER GROUNDING
    report_agent_node
      → check_requirement_coverage
      → check_report_grounding (facts must appear in result rows)
      → executive summary + tables (≤200 rows) + charts + PDF
    │
    ▼
FINAL RESPONSE  (AnalysisResponse JSON)
    + put_cached_analysis_result on success
```

Lead Intelligence is a **separate** graph (`run_lead_analysis`) with deterministic supplier ranking — not part of the CSV analytics graph.

---

## 3. LangGraph topology

**File:** `backend/agents/graph.py` → `create_agent_graph(pool)`

```
supervisor ──conditional──► schema_profiler ──► supervisor
                         ├► planner → code_generator → sandbox_executor → validator → reflection → supervisor
                         ├► python_analyst ───────────► sandbox_executor → …
                         ├► analysis_engine ──► supervisor
                         ├► visualization_generator → visualization_executor → visualization_reflection → supervisor
                         └► report_agent ──► supervisor ──► END
```

Capabilities (`capability_registry.py`): `SCHEMA`, `SQL`, `ANALYSIS`, `VISUALIZATION`, `PYTHON_ANALYSIS`, `REPORT`.

---

## 4. Layer map (what exists vs gaps)

| Layer | Existing modules | Status |
|---|---|---|
| CSV ingest once/session | `session_manager.register_csv` (`read_csv_auto`) | ✅ |
| Rich schema profile | `adaptive_questions/profiler.py` + `analytics_perf.get_or_build_csv_schema_profile` | ✅ (cache) |
| Semantic column types | `adaptive_questions/semantics.py`, `analytical_roles.py` | ⚠️ partial (not full concept→column IR) |
| Complexity router | `classify_question_complexity` | ⚠️ SIMPLE/COMPLEX/VERY_COMPLEX; no MEDIUM; fast-path incomplete |
| Requirement extraction | `requirement_coverage.py` | ✅ heavy, used in multiple nodes |
| SQL quality + read-only | `sql_quality_validator.py`, `_assert_read_only_sql` | ✅ |
| Deterministic SQL fallback | `analytics_fallback.py`, marketplace `sql_fallback` | ✅ |
| Report grounding | `report_grounding.py` | ✅ |
| Result cache | `analytics_perf` + wired in `/analyze` | ✅ |
| Adaptive suggested Qs | `adaptive_questions/*` + FE panel | ✅ local; Render sync lag |
| 50-Q SQL ground truth | `benchmarks/csv_analytics_questions.py` | ✅; need **100** + NL scoring |
| Analytics request observability | node `execution_metadata` | ⚠️ no unified analytics telemetry record |
| Structured question IR | — | ❌ target for upgrade |
| SQL pattern library (generic) | templates in adaptive_questions + fallback | ⚠️ expand |
| Max 1 repair (mandate) | reflection cap **3** | ⚠️ tighten for SQL semantic repairs |

---

## 5. Data & session isolation

- Each `session_id` owns a dedicated DuckDB `:memory:` connection + lock.
- Tables registered only in that session; scratch CSV under session dir for restore.
- Schema cache: `session.schema_profile_cache[dataset_id]`.
- Result cache key: `sha256(session|dataset|fingerprint|normalized_question)` — never cross-session.
- Invalidation on `register_csv` / `evict_session`.

---

## 6. Frontend request flow

1. Upload → `POST /upload` → session + schema card + optional suggested-questions.
2. Ask → `POST /analyze` (guarded by `isAnalyzing`).
3. While analyzing, poll `GET /execution/{session_id}/trace` every 1.5s.
4. Render `Report` + paginated `ResultsTableCard` (10/page); backend caps tables at 200 rows.

---

## 7. Security boundaries

- Generated SQL: SELECT-only denylist (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/ATTACH/COPY/…).
- Python sandbox: AST allowlist (remaining gaps documented in `AUDIT_REPORT.md`).
- CORS allowlist; rate limits on expensive endpoints; upload size/row caps.

---

## 8. Environment

See `.env.example`: `GROQ_API_KEY`, `GOOGLE_API_KEY`, `GROQ_MODEL`, `GEMINI_FALLBACK_MODEL`, `DATABASE_URL`, `DEMO_MODE`, sandbox limits.

---

## 9. Upgrade north star (aligned to this architecture)

Keep the supervisor graph. Improve **inside** existing seams:

1. Structured question IR before planner  
2. Stronger concept→column mapping into prompts (never rename physical cols)  
3. Complexity-aware fast path (skip planner LLM / viz when deterministic)  
4. One-shot repair policy for SQL semantic failures  
5. Expand ground-truth suite to 100+ with paraphrase/adversarial cases  
6. Unified analytics telemetry (no secrets)

**DATABASE RESULT > LLM MEMORY** remains non-negotiable.
