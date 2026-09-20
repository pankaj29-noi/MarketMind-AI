#!/usr/bin/env python3
"""
Run deterministic SQL ground-truth benchmark for 3k/4k CSV workloads.

Usage:
  .venv/bin/python -m backend.benchmarks.run_csv_benchmark
  .venv/bin/python -m backend.benchmarks.run_csv_benchmark --rows 4000
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from pathlib import Path

from backend.benchmarks.csv_analytics_questions import BENCHMARK_QUESTIONS, TABLE
from backend.services.session_manager import session_manager
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.mcp.data_access import _assert_read_only_sql


def _prepare_csv(rows: int, out_dir: Path) -> Path:
    src = Path("/Users/pankajbishnoi/Desktop/mottta/business_financial_sample_3000_rows.csv")
    if not src.exists():
        # fallback relative to repo
        src = Path(__file__).resolve().parents[2].parent / "business_financial_sample_3000_rows.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"bench_{rows}.csv"
    if rows == 3000:
        dest.write_bytes(src.read_bytes())
        return dest
    import pandas as pd
    df = pd.read_csv(src)
    if rows > len(df):
        extra = df.sample(n=rows - len(df), replace=True, random_state=42)
        df = pd.concat([df, extra], ignore_index=True)
    else:
        df = df.head(rows)
    df.to_csv(dest, index=False)
    return dest


def _normalize_rows(rows):
    out = []
    for r in rows:
        item = {}
        for k, v in r.items():
            if hasattr(v, "item"):
                try:
                    v = v.item()
                except Exception:
                    pass
            if isinstance(v, float):
                v = round(v, 6)
            item[str(k)] = v
        out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=3000, choices=[3000, 4000])
    parser.add_argument("--out", type=str, default="scratch/perf_baseline/BENCHMARK_REPORT.md")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = _prepare_csv(args.rows, out_path.parent)

    sid = f"bench_{uuid.uuid4().hex[:8]}"
    did = f"bench_ds_{args.rows}"

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
    failures = []

    for item in BENCHMARK_QUESTIONS:
        sql = item["expected_sql"].replace(TABLE, did)
        try:
            _assert_read_only_sql(sql)
        except Exception as e:
            failures.append({"id": item["id"], "stage": "readonly", "error": str(e)})
            results.append({**item, "ok": False, "error": f"readonly: {e}", "ms": None, "rows": 0})
            continue
        t0 = time.perf_counter()
        try:
            rows = session_manager.execute_query(sid, sql)
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            results.append(
                {
                    "id": item["id"],
                    "difficulty": item["difficulty"],
                    "question": item["question"],
                    "ok": True,
                    "ms": round(ms, 3),
                    "rows": len(rows),
                    "preview": _normalize_rows(rows)[:3],
                }
            )
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            failures.append({"id": item["id"], "stage": "exec", "error": str(e)})
            results.append(
                {
                    "id": item["id"],
                    "difficulty": item["difficulty"],
                    "question": item["question"],
                    "ok": False,
                    "error": str(e),
                    "ms": round(ms, 3),
                    "rows": 0,
                }
            )

    ok = sum(1 for r in results if r["ok"])
    n = len(results)
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0)

    by_diff = {}
    for r in results:
        d = r["difficulty"]
        by_diff.setdefault(d, {"ok": 0, "n": 0, "ms": []})
        by_diff[d]["n"] += 1
        if r["ok"]:
            by_diff[d]["ok"] += 1
            if r.get("ms") is not None:
                by_diff[d]["ms"].append(r["ms"])

    report = f"""# BENCHMARK_REPORT — CSV Analytics (deterministic SQL ground truth)

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Rows:** {args.rows}  
**Questions:** {n} (10 easy / 10 medium / 15 hard / 15 very_hard)  
**Session:** `{sid}` table `{did}`  

## Pipeline micro timings

| Stage | ms |
|---|---:|
| DuckDB register CSV | {register_ms:.2f} |
| Rich schema profile (cold) | {profile_ms:.2f} |
| Rich schema profile (cached) | {profile_cached_ms:.2f} |
| Profile fingerprint | `{profile.get('fingerprint')}` |

## Accuracy (ground-truth SQL execution)

| Metric | Value |
|---|---:|
| Executed OK | **{ok}/{n}** ({100.0*ok/n:.1f}%) |
| Failure rate | {100.0*(n-ok)/n:.1f}% |
| Avg SQL latency | {statistics.mean(latencies):.3f} ms |
| p95 SQL latency | {p95:.3f} ms |
| Max SQL latency | {max(latencies) if latencies else 0:.3f} ms |

### By difficulty

| Difficulty | OK | Avg ms |
|---|---:|---:|
"""
    for d in ("easy", "medium", "hard", "very_hard"):
        b = by_diff.get(d, {"ok": 0, "n": 0, "ms": []})
        avg = statistics.mean(b["ms"]) if b["ms"] else 0
        report += f"| {d} | {b['ok']}/{b['n']} | {avg:.3f} |\n"

    report += """
## Notes

- This report measures **DuckDB SQL correctness + latency** for the 50-question suite.
- Expected answers are produced by the listed `expected_sql` (deterministic), not by an LLM.
- End-to-end NL→SQL LLM accuracy / LLM-calls-per-question are tracked separately when running the agent pipeline.
- Cache hit rate for NL answers: N/A in this SQL-only harness (schema cache cold/cached shown above).

## Failures
"""
    if not failures:
        report += "\nNone.\n"
    else:
        for f in failures:
            report += f"\n- `{f['id']}` ({f['stage']}): {f['error']}\n"

    report += "\n## Per-question results\n\n"
    for r in results:
        status = "OK" if r["ok"] else "FAIL"
        report += f"- **{r['id']}** [{r['difficulty']}] {status} {r.get('ms')}ms rows={r.get('rows')} — {r['question']}\n"
        if not r["ok"]:
            report += f"  - error: `{r.get('error')}`\n"

    out_path.write_text(report)
    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "rows": args.rows,
                "register_ms": register_ms,
                "profile_ms": profile_ms,
                "profile_cached_ms": profile_cached_ms,
                "ok": ok,
                "n": n,
                "avg_ms": statistics.mean(latencies) if latencies else None,
                "p95_ms": p95,
                "failures": failures,
                "results": results,
            },
            indent=2,
            default=str,
        )
    )
    print(report.split("## Per-question")[0])
    print(f"Wrote {out_path}")
    print(f"Wrote {json_path}")
    session_manager.evict_session(sid)
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
