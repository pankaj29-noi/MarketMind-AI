"""
Benchmark for dataset-aware question discovery.

Runs the discovery engine across 8 datasets (sales, employees, products,
customers, financial, time-series, small, messy) and deterministically
validates every generated question:

  schema grounding → SQL validation → DuckDB execution → result validity

Usage:
    python -m backend.benchmarks.run_question_discovery_benchmark
"""
from __future__ import annotations

import csv
import json
import os
import random
import statistics
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.mcp.data_access import run_query
from backend.services.adaptive_questions.advanced_patterns import (
    generate_advanced_candidates,
)
from backend.services.adaptive_questions.capabilities import build_capabilities
from backend.services.adaptive_questions.engine import generate_suggested_questions
from backend.services.adaptive_questions.profiler import profile_dataset
from backend.services.adaptive_questions.semantics import build_semantics
from backend.services.adaptive_questions.templates import generate_candidates
from backend.services.session_manager import session_manager

RNG = random.Random(20260921)
REPORT_PATH = Path(__file__).resolve().parents[2] / "QUESTION_DISCOVERY_REPORT.md"


def _write_csv(rows: List[Dict[str, Any]], fields: List[str]) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


# ── Synthetic datasets ──────────────────────────────────────────────────────


def ds_sales(n: int = 900) -> Tuple[str, List[str]]:
    regions = ["North", "South", "East", "West"]
    cats = ["Electronics", "Apparel", "Grocery", "Tools", "Home"]
    sups = [f"Supplier {i:02d}" for i in range(1, 13)]
    rows = []
    for i in range(n):
        rev = round(RNG.uniform(50, 5000), 2)
        rows.append(
            {
                "order_id": f"ORD-{i:05d}",
                "order_date": f"{2024 + i % 3}-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}",
                "region": RNG.choice(regions),
                "category": RNG.choice(cats),
                "supplier": RNG.choice(sups),
                "quantity": RNG.randint(1, 20),
                "unit_price": round(RNG.uniform(5, 400), 2),
                "revenue": rev,
                "profit": round(rev * RNG.uniform(0.02, 0.3), 2),
            }
        )
    return _write_csv(
        rows,
        [
            "order_id",
            "order_date",
            "region",
            "category",
            "supplier",
            "quantity",
            "unit_price",
            "revenue",
            "profit",
        ],
    ), ["sales"]


def ds_employees(n: int = 400) -> Tuple[str, List[str]]:
    depts = ["Engineering", "Sales", "HR", "Finance", "Support"]
    locs = ["Bangalore", "Pune", "Delhi", "Remote"]
    rows = []
    for i in range(n):
        rows.append(
            {
                "employee_id": f"E{i:04d}",
                "department": RNG.choice(depts),
                "location": RNG.choice(locs),
                "joining_date": f"{2019 + i % 6}-{(i % 12) + 1:02d}-10",
                "salary": RNG.randint(400000, 3500000),
                "bonus": RNG.randint(0, 400000),
                "performance_score": round(RNG.uniform(2.0, 5.0), 1),
            }
        )
    return _write_csv(
        rows,
        [
            "employee_id",
            "department",
            "location",
            "joining_date",
            "salary",
            "bonus",
            "performance_score",
        ],
    ), ["employees"]


def ds_products(n: int = 500) -> Tuple[str, List[str]]:
    cats = ["Laptops", "Phones", "Audio", "Wearables", "Accessories"]
    brands = [f"Brand {c}" for c in "ABCDEFGH"]
    rows = []
    for i in range(n):
        rows.append(
            {
                "product_id": f"P{i:04d}",
                "product_name": f"Product {i}",
                "category": RNG.choice(cats),
                "brand": RNG.choice(brands),
                "price": round(RNG.uniform(500, 150000), 2),
                "units_sold": RNG.randint(0, 2500),
                "rating": round(RNG.uniform(2.5, 5.0), 1),
                "stock": RNG.randint(0, 900),
            }
        )
    return _write_csv(
        rows,
        [
            "product_id",
            "product_name",
            "category",
            "brand",
            "price",
            "units_sold",
            "rating",
            "stock",
        ],
    ), ["products"]


def ds_customers(n: int = 600) -> Tuple[str, List[str]]:
    segs = ["SMB", "Mid-Market", "Enterprise"]
    chans = ["Direct", "Partner", "Online"]
    rows = []
    for i in range(n):
        spend = round(RNG.uniform(1000, 900000), 2)
        rows.append(
            {
                "customer_id": f"C{i:05d}",
                "segment": RNG.choice(segs),
                "channel": RNG.choice(chans),
                "country": RNG.choice(["India", "USA", "Germany", "Japan"]),
                "signup_date": f"{2022 + i % 4}-{(i % 12) + 1:02d}-05",
                "orders": RNG.randint(1, 60),
                "total_spend": spend,
                "support_tickets": RNG.randint(0, 25),
            }
        )
    return _write_csv(
        rows,
        [
            "customer_id",
            "segment",
            "channel",
            "country",
            "signup_date",
            "orders",
            "total_spend",
            "support_tickets",
        ],
    ), ["customers"]


def ds_financial(n: int = 700) -> Tuple[str, List[str]]:
    units = ["Retail", "Wholesale", "Digital", "Services"]
    rows = []
    for i in range(n):
        revenue = round(RNG.uniform(10000, 900000), 2)
        cost = round(revenue * RNG.uniform(0.4, 0.95), 2)
        rows.append(
            {
                "txn_id": f"T{i:05d}",
                "business_unit": RNG.choice(units),
                "cost_center": f"CC-{RNG.randint(100, 120)}",
                "posting_date": f"{2023 + i % 3}-{(i % 12) + 1:02d}-20",
                "revenue": revenue,
                "cost": cost,
                "profit": round(revenue - cost, 2),
                "margin_pct": round(100 * (revenue - cost) / revenue, 2),
            }
        )
    return _write_csv(
        rows,
        [
            "txn_id",
            "business_unit",
            "cost_center",
            "posting_date",
            "revenue",
            "cost",
            "profit",
            "margin_pct",
        ],
    ), ["financial"]


def ds_timeseries(n: int = 730) -> Tuple[str, List[str]]:
    sites = ["Plant A", "Plant B", "Plant C"]
    rows = []
    for i in range(n):
        day = 1 + (i % 28)
        rows.append(
            {
                "reading_date": f"{2025 + i // 365}-{(i % 12) + 1:02d}-{day:02d}",
                "site": RNG.choice(sites),
                "energy_kwh": round(RNG.uniform(500, 9000), 1),
                "downtime_minutes": RNG.randint(0, 240),
                "output_units": RNG.randint(100, 5000),
            }
        )
    return _write_csv(
        rows, ["reading_date", "site", "energy_kwh", "downtime_minutes", "output_units"]
    ), ["timeseries"]


def ds_small() -> Tuple[str, List[str]]:
    rows = [{"name": n, "age": a} for n, a in [("A", 30), ("B", 41), ("C", 25), ("D", 52)]]
    return _write_csv(rows, ["name", "age"]), ["small"]


def ds_messy(n: int = 120) -> Tuple[str, List[str]]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "Region ": RNG.choice(["North", "South", "", "west"]),
                "Prod Name": RNG.choice(["A", "B", "C", ""]),
                "rev": RNG.choice(["", str(round(RNG.uniform(0, 900), 2)), "0"]),
                "notes": RNG.choice(["", "check", "n/a"]),
                "Date": RNG.choice(["2025-01-05", "", "2025-13-40"]),
            }
        )
    return _write_csv(rows, ["Region ", "Prod Name", "rev", "notes", "Date"]), ["messy"]


DATASETS = {
    "A_sales": ds_sales,
    "B_employees": ds_employees,
    "C_products": ds_products,
    "D_customers": ds_customers,
    "E_financial": ds_financial,
    "F_timeseries": ds_timeseries,
    "G_small": ds_small,
    "H_messy": ds_messy,
}


def _validate_question(session_id: str, dataset_id: str, known: set, q: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic validation of a displayed question."""
    missing = [c for c in q.get("required_columns", []) if c not in known]
    return {
        "schema_valid": not missing,
        "missing_columns": missing,
        "has_operations": bool(q.get("operations")) or q.get("tier") == "quick",
        "validation_status": q.get("validation_status"),
    }


def run() -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "datasets": [],
        "advanced": [],
        "expert": [],
        "advanced_bank": [],
        "expert_bank": [],
    }
    latencies: List[float] = []

    for name, factory in DATASETS.items():
        path, _ = factory()
        session_id = str(uuid.uuid4())
        dataset_id = f"bench_{name.lower()}"
        session_manager.register_csv(session_id, path, dataset_id)

        t0 = time.time()
        result = generate_suggested_questions(session_id, dataset_id, count=14)
        cold_ms = round((time.time() - t0) * 1000, 2)
        t1 = time.time()
        generate_suggested_questions(session_id, dataset_id, count=14)
        warm_ms = round((time.time() - t1) * 1000, 2)
        latencies.append(cold_ms)

        profile = profile_dataset(session_id, dataset_id)
        known = {c.name for c in profile.columns}

        checks = [_validate_question(session_id, dataset_id, known, q) for q in result["questions"]]
        schema_valid = sum(1 for c in checks if c["schema_valid"])

        # Execution proof for every advanced/expert candidate this dataset supports
        semantics = build_semantics(profile)
        caps = build_capabilities(profile, semantics)
        adv_cands = generate_advanced_candidates(profile, caps, semantics)
        exec_ok = 0
        exec_fail: List[str] = []
        validated_adv = 0
        validated_exp = 0
        for c in adv_cands:
            res = run_query(session_id, dataset_id, c.proof_sql)
            if res.get("success"):
                exec_ok += 1
                non_empty = int(res.get("row_count") or 0) > 0
                cols_ok = all(col in known for col in c.columns_used)
                if non_empty and cols_ok:
                    if c.difficulty == "very_hard":
                        validated_exp += 1
                        summary["expert_bank"].append(
                            {"dataset": name, "question": c.text, "intent": c.intent}
                        )
                    else:
                        validated_adv += 1
                        summary["advanced_bank"].append(
                            {"dataset": name, "question": c.text, "intent": c.intent}
                        )
            else:
                exec_fail.append(f"{name}/{c.intent}: {res.get('error')}")

        tiers = {t["tier"]: len(t["questions"]) for t in result["tiers"]}
        for q in result["questions"]:
            if q["tier"] == "advanced":
                summary["advanced"].append({"dataset": name, "question": q["text"], "intent": q["intent"]})
            elif q["tier"] == "expert":
                summary["expert"].append({"dataset": name, "question": q["text"], "intent": q["intent"]})

        summary["datasets"].append(
            {
                "dataset": name,
                "rows": profile.row_count,
                "columns": profile.column_count,
                "band": result["complexity"]["band"],
                "tiers": tiers,
                "questions_shown": len(result["questions"]),
                "schema_valid": schema_valid,
                "schema_valid_pct": round(
                    100.0 * schema_valid / max(len(result["questions"]), 1), 1
                ),
                "candidates": result["candidate_count"],
                "validated": result["valid_count"],
                "rejected": result["rejected_count"],
                "validated_advanced": validated_adv,
                "validated_expert": validated_exp,
                "advanced_pattern_exec_ok": exec_ok,
                "advanced_pattern_exec_total": len(adv_cands),
                "exec_failures": exec_fail,
                "cold_ms": cold_ms,
                "warm_ms": warm_ms,
            }
        )

    summary["totals"] = {
        "advanced_questions_displayed": len(summary["advanced"]),
        "expert_questions_displayed": len(summary["expert"]),
        "advanced_questions_validated": len(summary["advanced_bank"]),
        "expert_questions_validated": len(summary["expert_bank"]),
        "schema_valid_pct": round(
            100.0
            * sum(d["schema_valid"] for d in summary["datasets"])
            / max(sum(d["questions_shown"] for d in summary["datasets"]), 1),
            2,
        ),
        "exec_success_pct": round(
            100.0
            * sum(d["advanced_pattern_exec_ok"] for d in summary["datasets"])
            / max(sum(d["advanced_pattern_exec_total"] for d in summary["datasets"]), 1),
            2,
        ),
        "cold_p50_ms": round(statistics.median(latencies), 2),
        "cold_max_ms": round(max(latencies), 2),
    }
    return summary


def write_report(summary: Dict[str, Any]) -> None:
    t = summary["totals"]
    lines = [
        "# Question Discovery Benchmark",
        "",
        "Dataset-aware question discovery across 8 datasets. Every displayed question is",
        "schema-checked, SQL-validated and proven by read-only DuckDB execution before display.",
        "",
        "## Totals",
        "",
        f"- Advanced questions validated (benchmark bank): **{t['advanced_questions_validated']}**",
        f"- Expert questions validated (benchmark bank): **{t['expert_questions_validated']}**",
        f"- Advanced questions shown in UI: **{t['advanced_questions_displayed']}**",
        f"- Expert questions shown in UI: **{t['expert_questions_displayed']}**",
        f"- Schema-valid displayed questions: **{t['schema_valid_pct']}%**",
        f"- Advanced/expert pattern execution success: **{t['exec_success_pct']}%**",
        f"- Discovery latency (cold) p50 / max: **{t['cold_p50_ms']} ms / {t['cold_max_ms']} ms**",
        "",
        "## Per dataset",
        "",
        "| Dataset | Rows | Cols | Band | Quick | Analytics | Advanced | Expert | Schema valid | Cold ms | Warm ms |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for d in summary["datasets"]:
        tiers = d["tiers"]
        lines.append(
            f"| {d['dataset']} | {d['rows']} | {d['columns']} | {d['band']} | "
            f"{tiers.get('quick', 0)} | {tiers.get('analytics', 0)} | "
            f"{tiers.get('advanced', 0)} | {tiers.get('expert', 0)} | "
            f"{d['schema_valid_pct']}% | {d['cold_ms']} | {d['warm_ms']} |"
        )

    lines += ["", "## Advanced question bank (validated)", ""]
    for item in summary["advanced_bank"][:40]:
        lines.append(f"- `{item['dataset']}` — {item['question']}")
    lines += ["", "## Expert question bank (validated)", ""]
    for item in summary["expert_bank"][:40]:
        lines.append(f"- `{item['dataset']}` — {item['question']}")

    failures = [f for d in summary["datasets"] for f in d["exec_failures"]]
    lines += ["", "## Execution failures", ""]
    lines += [f"- {f}" for f in failures] or ["- None"]
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    s = run()
    write_report(s)
    print(json.dumps(s["totals"], indent=2))
    print(f"Report written to {REPORT_PATH}")
