# MarketMind AI — ENGINEERING_BASELINE

**Captured:** 2026-09-21  
**Git HEAD:** `4d420e8` on `main`  
**Command environment:** local macOS, Python 3.13 venv, Node (frontend package scripts)

---

## Backend tests

**Command:** `python -m pytest -q`

| Metric | Count |
|---|---:|
| Passed | **153** |
| Failed | **6** |
| Warnings | 2 |
| Duration | ~22.3s |

### Failures (exact)

1. `backend/tests/test_fallback.py::test_fallback_behavior_no_google_key`
2. `backend/tests/test_fallback.py::test_fallback_configured`
3. `backend/tests/test_fallback.py::test_fallback_success`
4. `backend/tests/test_fallback.py::test_primary_success`
5. `backend/tests/test_mcp.py::test_mcp_tool_discovery`
6. `backend/tests/test_visualization_integration.py::test_malformed_spec_handling`

### Failure classification (Phase 0/1 analysis)

| Failure | Class | Notes |
|---|---|---|
| `test_fallback.py` ×4 | **Stale tests** vs newer `has_valid_*_key()` | Patches use short keys like `test_groq_key`; `get_llm()` now raises `ValueError` |
| `test_mcp.py` | **Dependency / env** | `@pytest.mark.asyncio` without `pytest-asyncio` registered |
| `test_malformed_spec_handling` | **Expected-behavior mismatch** | Test expects `None`; validator returns structured rejection dict |

### Warnings

- Starlette `TestClient` / httpx deprecation
- Unknown pytest mark `asyncio`

---

## Frontend

| Check | Command | Result |
|---|---|---|
| Install | (existing `node_modules`) | Not re-run; deps already present |
| Lint | `npm run lint` (`oxlint`) | **Exit 0** — 11 warnings (fast-refresh / exhaustive-deps / unused catch), **0 errors** |
| Typecheck + Build | `npm run build` (`tsc -b && vite build`) | **PASS** |
| Unit/E2E tests | — | **None configured** in `package.json` |

### Build artifacts (baseline)

- `dist/assets/index-*.js` ≈ **5,461.70 kB** (gzip ≈ 1,634.52 kB) — oversized chunk warning (>500 kB)
- `dist/assets/index-*.css` ≈ 125.38 kB (gzip ≈ 20.07 kB)
- Build wall time ≈ 1.36s (vite)

---

## Live deployment probe (baseline)

| Target | Result |
|---|---|
| `GET https://marketmind-ai-93u1.onrender.com/health` | **200** `{"status":"ok","service":"marketmind-api","agent_ready":true}` |
| `GET https://marketmind-ai-pankaj.vercel.app/` | **200** |

---

## Git working tree at baseline capture

```
## main...origin/main
 M frontend/.gitignore
?? docs/MarketMind_AI_FULL_CONTEXT.md
?? AUDIT_REPORT.md   (created in Phase 0)
?? ENGINEERING_BASELINE.md (this file)
```

No secrets staged. `.env` remains untracked (gitignored).

---

## Baseline quality gate interpretation

- **App builds and most backend tests pass** — not a greenfield rewrite candidate.
- **6 failing tests are known / classified** — treat as P1 (fix before claiming CI green).
- **Frontend ships but JS bundle is very large** (~5.5MB) — P2 performance, not blocking correctness.
- **Live stack is up** at audit time — cold starts on Render free still expected.

This baseline is the reference for the engineering changelog after fixes.
