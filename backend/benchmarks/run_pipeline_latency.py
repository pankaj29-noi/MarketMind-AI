"""End-to-end pipeline latency + LLM-call measurement.

Runs a fixed question ladder through the real /analyze pipeline against the 4,000-row
demo CSV and records per-node timings and LLM calls attributed to each agent node.
Results are written to scratch/ so reruns are comparable.

Usage: python -m backend.benchmarks.run_pipeline_latency
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.config as cfg
from backend.main import app

LLM_CALLS = {"n": 0, "by_module": {}}
_real = cfg.invoke_llm

import inspect
import sys

PATCH_TARGETS = ["backend.config.invoke_llm"] + [
    f"{m}.invoke_llm"
    for m in list(sys.modules)
    if m.startswith("backend.agents.nodes") and hasattr(sys.modules[m], "invoke_llm")
]


def make_counter(tag):
    def wrapper(*a, **kw):
        # Attribute the call to the nearest agent node frame
        node = tag
        for fr in inspect.stack()[1:6]:
            mod = fr.frame.f_globals.get("__name__", "")
            if mod.startswith("backend.agents.nodes"):
                node = mod.rsplit(".", 1)[-1]
                break
        LLM_CALLS["n"] += 1
        LLM_CALLS["by_module"][node] = LLM_CALLS["by_module"].get(node, 0) + 1
        return _real(*a, **kw)

    return wrapper


QUESTIONS = [
    ("simple", "What is the total revenue?"),
    ("simple", "How many orders are there?"),
    ("medium", "Which customer region has the highest total revenue?"),
    ("medium", "How has revenue changed over time by month?"),
    ("complex", "Which customer regions have above-average revenue but below-average profit?"),
    ("complex", "What percentage of total revenue comes from the top 10 products?"),
    ("expert", "What are the top 3 suppliers by revenue within each customer region, excluding suppliers with fewer than 5 orders?"),
    ("expert", "Which suppliers increased revenue year over year while their profit declined?"),
    ("unsupported", "Which supplier has the highest employee satisfaction?"),
    ("ambiguous", "Show me sales"),
]

CSV = "data/marketmind_demo_marketplace_4000.csv"
OUT_PATH = Path("scratch/pipeline_latency.json")


def main():
    client_ctx = TestClient(app)
    client = client_ctx.__enter__()
    out = {"upload": {}, "suggested": {}, "analyze": []}

    t0 = time.time()
    with open(CSV, "rb") as f:
        up = client.post("/upload", files={"file": ("demo4k.csv", f, "text/csv")})
    out["upload"] = {
        "status": up.status_code,
        "ms": round((time.time() - t0) * 1000, 1),
        "rows": up.json().get("row_count"),
        "cols": len(up.json().get("columns") or []),
    }
    sid = up.json()["session_id"]
    ds = up.json()["dataset_id"]

    t0 = time.time()
    sq = client.post(f"/session/{sid}/suggested-questions", json={"dataset_id": ds, "count": 14})
    cold = round((time.time() - t0) * 1000, 1)
    t0 = time.time()
    client.post(f"/session/{sid}/suggested-questions", json={"dataset_id": ds, "count": 14})
    warm = round((time.time() - t0) * 1000, 1)
    out["suggested"] = {
        "status": sq.status_code,
        "cold_ms": cold,
        "warm_ms": warm,
        "tiers": {t["tier"]: len(t["questions"]) for t in sq.json().get("tiers", [])},
    }

    patches = [patch(target, make_counter(target.split(".")[-2])) for target in PATCH_TARGETS]
    for p in patches:
        p.start()
    try:
        for tier, q in QUESTIONS:
            LLM_CALLS["n"] = 0
            LLM_CALLS["by_module"] = {}
            t0 = time.time()
            try:
                r = client.post("/analyze", json={"session_id": sid, "question": q})
                total = round((time.time() - t0) * 1000, 1)
                body = r.json()
                dbg = body.get("debug") or {}
                out["analyze"].append(
                    {
                        "tier": tier,
                        "question": q,
                        "status": r.status_code,
                        "success": body.get("success"),
                        "total_ms": total,
                        "llm_calls": LLM_CALLS["n"],
                        "llm_by_node": dict(LLM_CALLS["by_module"]),
                        "retry": (body.get("query") or {}).get("retry_count"),
                        "complexity": dbg.get("question_complexity"),
                        "cache_hit": dbg.get("cache_hit"),
                        "mode": dbg.get("execution_mode"),
                        "source": dbg.get("analysis_source"),
                        "node_ms": dbg.get("node_timings_ms"),
                        "provider": (body.get("query") or {}).get("provider"),
                        "model": (body.get("query") or {}).get("model"),
                        "headline": ((body.get("report") or {}).get("executive_summary") or {}).get("headline"),
                    }
                )
            except Exception as e:
                out["analyze"].append({"tier": tier, "question": q, "error": str(e)[:300]})
            print(json.dumps(out["analyze"][-1])[:600], flush=True)
    finally:
        for p in patches:
            p.stop()

    ok = [a for a in out["analyze"] if a.get("total_ms")]
    lat = sorted(a["total_ms"] for a in ok)
    if lat:
        out["latency_summary"] = {
            "n": len(lat),
            "p50_ms": statistics.median(lat),
            "p95_ms": lat[max(0, int(round(0.95 * len(lat))) - 1)],
            "max_ms": lat[-1],
            "avg_llm_calls": round(statistics.mean(a["llm_calls"] for a in ok), 2),
        }
    print("\n=== SUMMARY ===")
    print(json.dumps({k: v for k, v in out.items() if k != "analyze"}, indent=2))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(str(OUT_PATH), "w") as f:
        json.dump(out, f, indent=2, default=str)
    client_ctx.__exit__(None, None, None)


if __name__ == "__main__":
    main()
