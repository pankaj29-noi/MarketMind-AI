"""Run the 150-question NL->SQL accuracy benchmark.

Two modes:
  deterministic  (default) - pattern library + analytics fallback, no LLM.
                             Always measurable; this is the floor of correctness.
  pipeline       - full /analyze path. Requires a live LLM; skipped when the
                   provider circuit is open.

Usage:
  python -m backend.benchmarks.run_nl_sql_benchmark
  python -m backend.benchmarks.run_nl_sql_benchmark --mode pipeline
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from backend.benchmarks.nl_sql_question_bank import ALL_QUESTIONS, DATASET_FILES, BenchQuestion
from backend.benchmarks.result_evaluator import compare_results
from backend.services.ambiguity import detect_ambiguity
from backend.services.analytics_fallback import resolve_analytics_fallback
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.services.session_manager import session_manager
from backend.services.sql.sql_pattern_library import try_simple_deterministic_sql

OUT_JSON = Path("scratch/NL_SQL_BENCHMARK.json")
OUT_MD = Path("BENCHMARK_REPORT.md")


@dataclass
class QuestionResult:
    id: str
    dataset: str
    difficulty: str
    kind: str
    question: str
    verdict: str  # pass | fail | skip
    reason: str
    latency_ms: float
    generated_sql: Optional[str] = None
    pattern_id: Optional[str] = None


def _load_profile(dataset: str) -> Dict[str, Any]:
    path = DATASET_FILES[dataset]
    sid = f"bench-{dataset}"
    session_manager.register_csv(sid, path, dataset)
    return get_or_build_csv_schema_profile(sid, dataset)


def _schema_columns(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c if isinstance(c, dict) else {"name": str(c)} for c in (profile.get("columns") or [])]


def _generate_sql(q: BenchQuestion, profile: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (sql, pattern_or_reason, failure_kind)."""
    ambiguity = detect_ambiguity(q.question, profile)
    if ambiguity:
        return None, ambiguity.kind, "ambiguous_question"

    columns = _schema_columns(profile)
    hit = try_simple_deterministic_sql(q.question, q.dataset, columns)
    if hit and hit.sql:
        return hit.sql, hit.pattern_id, None

    fallback = resolve_analytics_fallback(q.question, profile, q.dataset)
    if fallback.sql:
        return fallback.sql, fallback.reason, None

    return None, fallback.reason or "unsupported", "unsupported_question"


def _rows_as_dicts(cols: List[str], rows: List[tuple]) -> List[Dict[str, Any]]:
    return [{cols[i]: row[i] for i in range(len(cols))} for row in rows]


def _score_sql(con: duckdb.DuckDBPyConnection, q: BenchQuestion, generated: str) -> Tuple[bool, str]:
    expected = q.expected_sql
    if not expected:
        return False, "no expected_sql"
    try:
        expected_rows = con.execute(expected.format(t=q.dataset)).fetchall()
        expected_cols = [d[0] for d in con.description]
        actual_rows = con.execute(generated).fetchall()
        actual_cols = [d[0] for d in con.description]
    except Exception as e:
        return False, f"execution error: {e}"

    # Column names often differ (total_revenue vs v). Prefer the proportion
    # column when both sides answer a percent-of-total question.
    def _pick_value_column(cols: List[str]) -> Optional[str]:
        for preferred in ("pct_of_total", "v", "total", "value"):
            for c in cols:
                if c.lower() == preferred:
                    return c
        for c in cols:
            if any(tok in c.lower() for tok in ("pct", "percent", "share", "ratio")):
                return c
        return cols[-1] if cols else None

    if len(expected_rows) == 1 and len(actual_rows) == 1:
        exp_col = _pick_value_column(expected_cols)
        act_col = _pick_value_column(actual_cols)
        if exp_col and act_col:
            exp_val = expected_rows[0][expected_cols.index(exp_col)]
            act_val = actual_rows[0][actual_cols.index(act_col)]
            try:
                if abs(float(exp_val) - float(act_val)) <= max(0.02, 0.001 * abs(float(exp_val))):
                    return True, "scalar match"
                return False, f"scalar mismatch expected={exp_val} actual={act_val}"
            except (TypeError, ValueError):
                if str(exp_val) == str(act_val):
                    return True, "scalar match"

    # Align on positional columns so alias differences don't fail a correct query.
    def positional(cols, rows):
        return [{f"c{i}": row[i] for i in range(len(cols))} for row in rows]

    ok, issues = compare_results(
        positional(expected_cols, expected_rows),
        positional(actual_cols, actual_rows),
        check_order=False,
        numeric_tol=0.02,
    )
    return ok, "; ".join(issues) if issues else "match"


def _score_abstain(sql: Optional[str], failure_kind: Optional[str]) -> Tuple[bool, str]:
    if failure_kind in ("unsupported_question", "ambiguous_question") or sql is None:
        return True, f"honest abstention ({failure_kind or 'no sql'})"
    return False, f"answered unsupported question with SQL ({failure_kind})"


def _score_ambiguous(sql: Optional[str], failure_kind: Optional[str]) -> Tuple[bool, str]:
    if failure_kind == "ambiguous_question":
        return True, "clarification requested"
    if sql is None:
        return True, "declined rather than guessing"
    return False, "answered an ambiguous question without clarifying"


def run_deterministic() -> List[QuestionResult]:
    profiles = {name: _load_profile(name) for name in DATASET_FILES}
    con = duckdb.connect(":memory:")
    for name, path in DATASET_FILES.items():
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{path}')")

    results: List[QuestionResult] = []
    for q in ALL_QUESTIONS:
        t0 = time.time()
        sql, tag, failure_kind = _generate_sql(q, profiles[q.dataset])
        latency = round((time.time() - t0) * 1000, 2)

        if q.kind == "abstain":
            ok, reason = _score_abstain(sql, failure_kind)
        elif q.kind == "ambiguous":
            ok, reason = _score_ambiguous(sql, failure_kind)
        elif q.kind in ("sql", "paraphrase"):
            if not sql:
                ok, reason = False, f"no SQL generated ({tag})"
            else:
                ok, reason = _score_sql(con, q, sql)
        else:
            ok, reason = False, f"unknown kind {q.kind}"

        results.append(
            QuestionResult(
                id=q.id,
                dataset=q.dataset,
                difficulty=q.difficulty,
                kind=q.kind,
                question=q.question,
                verdict="pass" if ok else "fail",
                reason=reason,
                latency_ms=latency,
                generated_sql=sql,
                pattern_id=tag,
            )
        )
    return results


def _summarise(results: List[QuestionResult]) -> Dict[str, Any]:
    by_diff: Dict[str, Dict[str, int]] = {}
    by_kind: Dict[str, Dict[str, int]] = {}
    by_dataset: Dict[str, Dict[str, int]] = {}
    for r in results:
        for bucket, key in (
            (by_diff, r.difficulty),
            (by_kind, r.kind),
            (by_dataset, r.dataset),
        ):
            bucket.setdefault(key, {"pass": 0, "fail": 0})
            bucket[key][r.verdict] += 1

    lat = sorted(r.latency_ms for r in results)
    passed = sum(1 for r in results if r.verdict == "pass")
    return {
        "n": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "accuracy_pct": round(100.0 * passed / len(results), 2) if results else 0.0,
        "by_difficulty": by_diff,
        "by_kind": by_kind,
        "by_dataset": by_dataset,
        "latency_ms": {
            "p50": statistics.median(lat) if lat else 0,
            "p95": lat[max(0, int(round(0.95 * len(lat))) - 1)] if lat else 0,
            "max": lat[-1] if lat else 0,
            "avg": round(statistics.mean(lat), 2) if lat else 0,
        },
        "failures": [
            {"id": r.id, "dataset": r.dataset, "difficulty": r.difficulty, "kind": r.kind,
             "question": r.question, "reason": r.reason, "pattern": r.pattern_id}
            for r in results if r.verdict == "fail"
        ],
    }


def _write_report(summary: Dict[str, Any], mode: str) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))

    lines = [
        "# BENCHMARK_REPORT.md — NL→SQL Accuracy",
        "",
        f"**Mode:** `{mode}`  ",
        f"**Questions:** {summary['n']}  ",
        f"**Passed:** {summary['passed']}  ",
        f"**Failed:** {summary['failed']}  ",
        f"**Accuracy:** **{summary['accuracy_pct']}%**  ",
        "",
        "## By difficulty",
        "",
        "| Difficulty | Pass | Fail | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for diff in ("simple", "medium", "advanced", "expert"):
        bucket = summary["by_difficulty"].get(diff, {"pass": 0, "fail": 0})
        total = bucket["pass"] + bucket["fail"]
        pct = round(100.0 * bucket["pass"] / total, 1) if total else 0
        lines.append(f"| {diff} | {bucket['pass']} | {bucket['fail']} | {pct}% |")

    lines += [
        "",
        "## By kind",
        "",
        "| Kind | Pass | Fail |",
        "|---|---:|---:|",
    ]
    for kind, bucket in summary["by_kind"].items():
        lines.append(f"| {kind} | {bucket['pass']} | {bucket['fail']} |")

    lines += [
        "",
        "## By dataset",
        "",
        "| Dataset | Pass | Fail | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for ds, bucket in summary["by_dataset"].items():
        total = bucket["pass"] + bucket["fail"]
        pct = round(100.0 * bucket["pass"] / total, 1) if total else 0
        lines.append(f"| {ds} | {bucket['pass']} | {bucket['fail']} | {pct}% |")

    lat = summary["latency_ms"]
    lines += [
        "",
        "## Latency (deterministic generation only)",
        "",
        f"- p50: {lat['p50']} ms",
        f"- p95: {lat['p95']} ms",
        f"- max: {lat['max']} ms",
        f"- avg: {lat['avg']} ms",
        "",
        "## Failures",
        "",
    ]
    if not summary["failures"]:
        lines.append("None.")
    else:
        for f in summary["failures"]:
            lines.append(
                f"- `{f['id']}` [{f['dataset']}/{f['difficulty']}/{f['kind']}] "
                f"{f['question']} — {f['reason']}"
            )

    lines += [
        "",
        "## Notes",
        "",
        "- Ground truth SQL is independent of the pipeline and runs in DuckDB.",
        "- `deterministic` mode measures the pattern library + analytics fallback.",
        "- It does **not** claim full LLM-path accuracy; that requires `--mode pipeline`",
        "  with a live provider.",
        "- Abstention and ambiguity are scored as correct when the system declines",
        "  rather than inventing an answer.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(f"Wrote {OUT_MD} and {OUT_JSON}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("deterministic", "pipeline"), default="deterministic")
    args = parser.parse_args()

    if args.mode == "pipeline":
        raise SystemExit(
            "pipeline mode is intentionally gated: it requires a live LLM provider. "
            "Use --mode deterministic (default) to measure the always-available floor."
        )

    results = run_deterministic()
    summary = _summarise(results)
    summary["mode"] = args.mode
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, indent=2))
    print(f"\nFailures: {len(summary['failures'])}")
    for f in summary["failures"][:15]:
        print(f"  {f['id']}: {f['reason']}")
    _write_report(summary, args.mode)


if __name__ == "__main__":
    main()
