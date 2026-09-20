# Adaptive Questions — Test Report

**Date:** 2026-09-21

## Automated

```
python -m pytest backend/tests/test_adaptive_questions.py backend/tests/test_sql_readonly_guard.py -q
→ 15 passed
```

| Test | Result |
|---|---|
| Sales CSV generates sales/region questions, invents no salary/profit | PASS |
| Employee CSV generates salary/department questions, invents no revenue | PASS |
| Cross-dataset isolation (sales session ≠ salary session) | PASS |
| Empty CSV returns message, no fake questions | PASS |
| SQL read-only guards (COPY/DROP/etc.) | PASS |

## Frontend

```
npm run build  → PASS (tsc -b && vite build)
```

## Manual acceptance (local / post-deploy)

1. Upload sales-like CSV → cards reference real columns only.
2. Click a card → `/analyze` runs (same pipeline).
3. Generate more → new IDs, no duplicates from exclude list.
4. Load Marketplace Demo → curated questions (not adaptive).
5. Upload employee CSV → previous sales suggestions gone.

## Performance note

Generation runs profile + N proof queries. Typical small CSV < 1s locally.
Render free cold start dominates first request latency.
