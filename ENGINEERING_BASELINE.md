# MarketMind AI — ENGINEERING_BASELINE

**Captured:** 2026-09-21
**Git HEAD:** `206473315b66971511face0a55fc738772c7a328` (`main` tracking `origin/main`)
**Working tree:** clean except `M frontend/.gitignore` (uncommitted)
**Environment:** local macOS, project `.venv` (Python 3.13), frontend npm scripts

**No application source was modified during this baseline capture** (docs may be updated as audit artifacts only).

---

## Backend tests

**Command:** `python -m pytest -q`

| Metric | Count |
|---:|---:|
| Passed | **184** |
| Failed | **1** |
| Skipped | **0** |
| Warnings | 1 (Starlette TestClient / httpx deprecation) |
| Duration | ~17.05s |

### Failure (exact)

```
FAILED backend/tests/test_marketplace_lead.py::TestMarketplaceAPI::test_lead_analyze
assert 404 == 200
```

**Classification:** Application regression (route missing), **not** a flaky env-only failure.
Root cause documented in `AUDIT_REPORT.md` **P0-1** (`backend/main.py` Lead handler overwritten when adding suggested-questions).

---

## Frontend

| Check | Command | Result |
|---|---|---|
| Lint | `npm run lint` (`oxlint`) | **Exit 0** — 11 warnings, **0 errors** |
| Typecheck + Build | `npm run build` (`tsc -b && vite build`) | **PASS** |
| Unit/E2E | — | **None configured** in `package.json` |

### Build artifacts

- JS: ~**5,466.53 kB** (gzip ~1,635.89 kB) — chunk size warning
- CSS: ~125.59 kB (gzip ~20.09 kB)
- Vite build ~1.32s

---

## Deployment / live probes

| Target | Result |
|---|---|
| `GET https://marketmind-ai-93u1.onrender.com/health` | **200** `{"status":"ok","service":"marketmind-api","agent_ready":true}` |
| `GET https://marketmind-ai-pankaj.vercel.app/` | **200** |
| Live OpenAPI path count | **12** |
| Live paths include `/marketplace/lead/analyze` | **NO** |
| Live paths include `/session/{session_id}/suggested-questions` | **NO** |
| `POST .../session/x/suggested-questions` | **404** `{"detail":"Not Found"}` |

**Interpretation:** Render is healthy but **not serving current GitHub `main` feature set**. Local tree also currently lacks a registered Lead route (P0-1).

---

## Local route registration check (TestClient)

Registered marketplace-related routes observed during diagnosis:

- `POST /marketplace/demo`
- `POST /session/{session_id}/suggested-questions`
- `POST /marketplace/feedback`
- `GET /marketplace/observability/runs`
- `GET /marketplace/observability/summary`

**Missing:** `POST /marketplace/lead/analyze`

---

## Security probe notes (baseline, not a full pen-test)

AST validator (`python_quality_validator.py`) accepted:

- `open('/etc/passwd')`
- `os.system('id')`
- `getattr(__builtins__,'eval')('1')`

Rejected: `import pathlib` (allowlist).

---

## Baseline quality-gate interpretation

- Frontend builds cleanly; lint warnings only.
- Backend is **almost** green; the single failure is a **blocking product regression** for Lead Intelligence.
- Live Render health ≠ feature parity with GitHub.
- Do not treat “184 passed” as “production ready” until P0-1 and deploy sync are fixed.

This baseline is the reference for the upcoming repair cycle (awaiting approval).
