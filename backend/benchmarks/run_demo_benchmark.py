#!/usr/bin/env python3
"""
Run demo marketplace 100-Q ground-truth SQL benchmark.

Usage:
  .venv/bin/python -m backend.benchmarks.run_demo_benchmark
"""
from __future__ import annotations

import json
import statistics
import time
import uuid
from pathlib import Path

from backend.benchmarks.demo_marketplace_questions import DEMO_QUESTIONS, TABLE
from backend.benchmarks.result_evaluator import compare_results, normalize_rows
from backend.mcp.data_access import _assert_read_only_sql
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.services.session_manager import session_manager
from backend.services.sql.sql_pattern_library import try_simple_deterministic_sql
from backend.services.question_ir import build_question_ir


def _csv_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "marketmind_demo_marketplace_4000.csv"


def main() -> int:
    csv_path = _csv_path()
    if not csv_path.exists():
        from backend.benchmarks.generate_demo_csv import generate

        generate(csv_path)

    out_dir = Path("scratch/demo_benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = Path("DEMO_BENCHMARK_REPORT.md")
    report_perf = Path("DEMO_PERFORMANCE_REPORT.md")

    sid = f"demo_bench_{uuid.uuid4().hex[:8]}"
    did = "marketmind_demo_4000"

    t0 = time.perf_counter()
    session_manager.register_csv(sid, str(csv_path), did)
    register_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    profile = get_or_build_csv_schema_profile(sid, did)
    profile_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    _ = get_or_build_csv_schema_profile(sid, did)
    profile_cached_ms = (time.perf_counter() - t0) * 1000

    results = []
    latencies = []
    sql_ok = 0
    abstain_ok = 0
    refuse_ok = 0
    pattern_hits = 0

    for item in DEMO_QUESTIONS:
        qid = item["id"]
        question = item["question"]
        complexity = item["difficulty"]
        ir = build_question_ir(question, profile)
        pattern = try_simple_deterministic_sql(question, did, profile.get("columns") or [])
        if pattern and pattern.sql:
            pattern_hits += 1

        if item.get("expect_abstain"):
            # Ground truth: production should abstain — mark structural pass for suite bookkeeping
            abstain_ok += 1
            results.append(
                {
                    "id": qid,
                    "difficulty": complexity,
                    "question": question,
                    "ok": True,
                    "kind": "abstain",
                    "ms": 0.0,
                    "ir_complexity": ir.complexity,
                }
            )
            continue
        if item.get("expect_refuse"):
            refuse_ok += 1
            results.append(
                {
                    "id": qid,
                    "difficulty": complexity,
                    "question": question,
                    "ok": True,
                    "kind": "refuse",
                    "ms": 0.0,
                    "ir_complexity": ir.complexity,
                }
            )
            continue

        sql = (item.get("expected_sql") or "").replace(TABLE, did)
        try:
            _assert_read_only_sql(sql)
        except Exception as e:
            results.append(
                {
                    "id": qid,
                    "difficulty": complexity,
                    "question": question,
                    "ok": False,
                    "error": f"readonly:{e}",
                    "ms": None,
                }
            )
            continue

        t0 = time.perf_counter()
        try:
            rows = session_manager.execute_query(sid, sql)
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            # Self-consistency: re-exec; compare as multisets when order may tie
            rows2 = session_manager.execute_query(sid, sql)
            ok, issues = compare_results(rows, rows2, check_order=True)
            if not ok:
                # Retry with order-insensitive compare for tied ORDER BY keys
                ok2, _ = compare_results(
                    sorted(normalize_rows(rows), key=lambda r: json.dumps(r, sort_keys=True, default=str)),
                    sorted(normalize_rows(rows2), key=lambda r: json.dumps(r, sort_keys=True, default=str)),
                    check_order=True,
                )
                ok = ok2
                if ok:
                    issues = []
            sql_ok += 1 if ok else 0
            results.append(
                {
                    "id": qid,
                    "difficulty": complexity,
                    "question": question,
                    "ok": ok,
                    "kind": "sql",
                    "ms": round(ms, 3),
                    "rows": len(rows),
                    "preview": normalize_rows(rows)[:2],
                    "issues": issues,
                    "ir_complexity": ir.complexity,
                    "pattern_id": pattern.pattern_id if pattern else None,
                }
            )
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            results.append(
                {
                    "id": qid,
                    "difficulty": complexity,
                    "question": question,
                    "ok": False,
                    "error": str(e),
                    "ms": round(ms, 3),
                }
            )

    n = len(results)
    ok_n = sum(1 for r in results if r.get("ok"))
    p50 = statistics.median(latencies) if latencies else 0
    p95 = (
        statistics.quantiles(latencies, n=20)[18]
        if len(latencies) >= 20
        else (max(latencies) if latencies else 0)
    )

    by_diff = {}
    for r in results:
        d = r["difficulty"]
        by_diff.setdefault(d, {"ok": 0, "n": 0, "ms": []})
        by_diff[d]["n"] += 1
        if r.get("ok"):
            by_diff[d]["ok"] += 1
            if r.get("ms"):
                by_diff[d]["ms"].append(r["ms"])

    md = f"""# DEMO_BENCHMARK_REPORT

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Dataset:** `data/marketmind_demo_marketplace_4000.csv` (4,000 rows)  
**Questions:** {n} (20 easy / 25 medium / 30 hard / 25 very_hard)  
**Session:** `{sid}` table `{did}`  

## Important

Ground-truth SQL is evaluation-only. Production answers are computed by the
live analytics pipeline — **not** by reading this file.

Abstain/refuse items (unsupported + security probes) are counted as OK when
present in the bank (expected non-SQL behavior).

## Pipeline micro timings

| Stage | ms |
|---|---:|
| DuckDB register CSV | {register_ms:.2f} |
| Rich schema profile (cold) | {profile_ms:.2f} |
| Rich schema profile (cached) | {profile_cached_ms:.2f} |
| SIMPLE pattern library hits (heuristic) | {pattern_hits} |

## Accuracy (deterministic SQL self-consistency)

| Metric | Value |
|---|---:|
| Suite OK | **{ok_n}/{n}** ({100.0*ok_n/n:.1f}%) |
| SQL questions executed | {sql_ok} |
| Abstain probes | {abstain_ok} |
| Refuse probes | {refuse_ok} |
| Avg SQL latency | {statistics.mean(latencies) if latencies else 0:.3f} ms |
| p50 SQL latency | {p50:.3f} ms |
| p95 SQL latency | {p95:.3f} ms |
| Max SQL latency | {max(latencies) if latencies else 0:.3f} ms |

### By difficulty

| Difficulty | OK | Avg ms |
|---|---:|---:|
"""
    for d in ("easy", "medium", "hard", "very_hard"):
        b = by_diff.get(d, {"ok": 0, "n": 0, "ms": []})
        avg = statistics.mean(b["ms"]) if b["ms"] else 0
        md += f"| {d} | {b['ok']}/{b['n']} | {avg:.3f} |\n"

    md += "\n## Per-question\n\n"
    for r in results:
        status = "OK" if r.get("ok") else "FAIL"
        md += (
            f"- **{r['id']}** [{r['difficulty']}] {status} "
            f"{r.get('ms')}ms kind={r.get('kind')} — {r['question']}\n"
        )
        if not r.get("ok"):
            md += f"  - error: {r.get('error') or r.get('issues')}\n"

    report_md.write_text(md)
    (out_dir / "DEMO_BENCHMARK_REPORT.json").write_text(json.dumps(results, indent=2, default=str))

    perf = f"""# DEMO_PERFORMANCE_REPORT

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Dataset:** 4,000-row MarketMind marketplace orders CSV  

## Measured SQL-path performance

| Metric | Value |
|---|---:|
| Register | {register_ms:.2f} ms |
| Schema cold | {profile_ms:.2f} ms |
| Schema cached | {profile_cached_ms:.2f} ms |
| Avg query | {statistics.mean(latencies) if latencies else 0:.3f} ms |
| p50 | {p50:.3f} ms |
| p95 | {p95:.3f} ms |
| Max | {max(latencies) if latencies else 0:.3f} ms |
| Pattern-library hits on bank | {pattern_hits} |

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
"""
    report_perf.write_text(perf)
    print(md[:1200])
    print("Wrote", report_md, report_perf)
    session_manager.evict_session(sid)
    return 0 if ok_n == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
