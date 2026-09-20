# DEMO_PERFORMANCE_REPORT

**Date:** 2026-09-21 04:03:04  
**Dataset:** 4,000-row MarketMind marketplace orders CSV  

## Measured SQL-path performance

| Metric | Value |
|---|---:|
| Register | 636.06 ms |
| Schema cold | 37.69 ms |
| Schema cached | 0.00 ms |
| Avg query | 0.794 ms |
| p50 | 0.669 ms |
| p95 | 2.030 ms |
| Max | 5.892 ms |
| Pattern-library hits on bank | 26 |

## LLM calls

Not measured in this SQL-only harness. Full NL→SQL LLM call counts require a
controlled provider run against `/analyze` (see `AI_ACCURACY_REPORT.md`).

## Targets (engineering, not guarantees)

| Class | Target wall time |
|---|---|
| Simple | ~1–2 s when infra permits |
| Complex | ~2–5 s when infra permits |
| Very complex | as fast as possible without skipping validation |

## Caching

Schema profile + `/analyze` result cache are session/fingerprint scoped.
Repeated identical questions on an unchanged dataset should cache-hit.
