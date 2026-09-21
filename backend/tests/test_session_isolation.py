"""Session isolation: Session A must never see Session B's data, cache, or DuckDB state.

Baseline gap: only analyze-result cache isolation was tested. DuckDB connections and
suggested-question caches also need hard boundaries across sessions.
"""
from __future__ import annotations

import csv
import tempfile
import uuid
from pathlib import Path

from backend.services.adaptive_questions import cache as qcache
from backend.services.analytics_perf import (
    get_cached_analysis_result,
    put_cached_analysis_result,
)
from backend.services.session_manager import session_manager


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_duckdb_sessions_cannot_read_each_others_tables():
    with tempfile.TemporaryDirectory() as tmp:
        a_csv = Path(tmp) / "a.csv"
        b_csv = Path(tmp) / "b.csv"
        _write_csv(a_csv, [{"secret_a": 1, "label": "alpha"}])
        _write_csv(b_csv, [{"secret_b": 99, "label": "beta"}])

        sid_a, sid_b = str(uuid.uuid4()), str(uuid.uuid4())
        session_manager.register_csv(sid_a, str(a_csv), "dataset_a")
        session_manager.register_csv(sid_b, str(b_csv), "dataset_b")

        rows_a = session_manager.execute_query(sid_a, "SELECT * FROM dataset_a")
        rows_b = session_manager.execute_query(sid_b, "SELECT * FROM dataset_b")
        assert rows_a[0]["secret_a"] == 1
        assert rows_b[0]["secret_b"] == 99

        try:
            session_manager.execute_query(sid_a, "SELECT * FROM dataset_b")
            raised = False
        except Exception:
            raised = True
        assert raised, "session A must not see session B's DuckDB table"

        try:
            session_manager.execute_query(sid_b, "SELECT secret_a FROM dataset_a")
            raised = False
        except Exception:
            raised = True
        assert raised, "session B must not see session A's columns"

        session_manager.evict_session(sid_a)
        session_manager.evict_session(sid_b)


def test_analyze_cache_is_session_scoped():
    fp = "fingerprint-isolation-test"
    put_cached_analysis_result("session-a", "ds", fp, "total revenue", {"answer": "from A"})
    put_cached_analysis_result("session-b", "ds", fp, "total revenue", {"answer": "from B"})

    assert get_cached_analysis_result("session-a", "ds", fp, "total revenue")["answer"] == "from A"
    assert get_cached_analysis_result("session-b", "ds", fp, "total revenue")["answer"] == "from B"
    # A different session must not receive the other session's payload.
    assert get_cached_analysis_result("session-a", "ds", "other-fp", "total revenue") is None
    clear_a = get_cached_analysis_result("session-a", "ds", fp, "total revenue")
    clear_b = get_cached_analysis_result("session-b", "ds", fp, "total revenue")
    assert clear_a["answer"] != clear_b["answer"]


def test_suggestion_cache_cleared_on_reupload():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data.csv"
        _write_csv(path, [{"revenue": 10, "region": "North"}])
        sid = str(uuid.uuid4())
        session_manager.register_csv(sid, str(path), "ds1")
        qcache.set_cached(sid, "ds1", "fp-old", {"questions": [{"id": "stale"}]})
        assert qcache.get_cached(sid, "ds1", "fp-old") is not None

        # Re-registering a CSV for the same session must drop stale suggestions.
        _write_csv(path, [{"revenue": 20, "region": "South"}])
        session_manager.register_csv(sid, str(path), "ds1")
        assert qcache.get_cached(sid, "ds1", "fp-old") is None

        session_manager.evict_session(sid)


def test_eviction_clears_suggestion_cache():
    sid = str(uuid.uuid4())
    qcache.set_cached(sid, "ds", "fp", {"questions": []})
    session_manager.get_session(sid)  # ensure session exists
    session_manager.evict_session(sid)
    assert qcache.get_cached(sid, "ds", "fp") is None
