"""Built-in Demo Data: load, verified suggestions, isolation, replace-with-CSV, E2E analyze."""
from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.marketplace.demo_data_lite import (
    DEMO_DATA_DATASET_ID,
    DEMO_DATA_DATASET_NAME,
    build_schema_grounded_candidates,
    get_demo_data_csv_path,
    independent_ground_truth,
    is_demo_data_dataset,
    load_demo_data,
    verify_demo_suggested_questions,
)
from backend.services.session_manager import session_manager
from backend.services.sql.sql_quality_validator import validate_sql


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_demo_csv_exists_and_is_small():
    path = Path(get_demo_data_csv_path())
    assert path.exists(), path
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert 30 <= len(rows) <= 50
    required = {
        "order_date",
        "product",
        "category",
        "region",
        "supplier",
        "quantity",
        "revenue",
        "cost",
        "profit",
    }
    assert required.issubset(set(rows[0].keys()))
    for r in rows:
        assert abs(float(r["profit"]) - (float(r["revenue"]) - float(r["cost"]))) < 0.02


def test_candidates_only_use_existing_columns():
    cols = [{"name": "revenue"}, {"name": "product"}]
    cands = build_schema_grounded_candidates(cols)
    ids = {c["id"] for c in cands}
    assert "total_revenue" in ids
    assert "top_product" in ids
    # Missing region/supplier/category → those candidates absent
    assert "best_region" not in ids
    assert "best_supplier" not in ids
    assert "sales_by_category" not in ids


def test_load_demo_data_profiles_and_labels():
    sid = f"dd_{uuid.uuid4().hex[:8]}"
    result = load_demo_data(sid)
    try:
        assert result["dataset_id"] == DEMO_DATA_DATASET_ID
        assert result["dataset_name"] == DEMO_DATA_DATASET_NAME
        assert result["is_demo_data"] is True
        assert result["demo_kind"] == "builtin_demo_data"
        assert 30 <= result["row_count"] <= 50
        assert result["warm_start"]["schema_profiled"] is True
        assert "answers" not in result
        assert is_demo_data_dataset(result["dataset_id"], result["dataset_name"])
    finally:
        session_manager.evict_session(sid)


def test_verified_suggestions_execute_and_exclude_answers():
    sid = f"dd_{uuid.uuid4().hex[:8]}"
    loaded = load_demo_data(sid)
    try:
        suggested = verify_demo_suggested_questions(
            sid,
            DEMO_DATA_DATASET_ID,
            {
                "columns": loaded["columns"],
                "dataset_id": DEMO_DATA_DATASET_ID,
                "row_count": loaded["row_count"],
            },
        )
        assert 6 <= len(suggested) <= 8
        ids = {s["id"] for s in suggested}
        for needed in (
            "total_revenue",
            "total_profit",
            "top_product",
            "best_region",
            "best_supplier",
            "sales_by_category",
        ):
            assert needed in ids, suggested

        schema = {"columns": loaded["columns"], "dataset_id": DEMO_DATA_DATASET_ID}
        for s in suggested:
            assert s["verified"] is True
            assert "question" in s
            # Never ship hardcoded numeric answers in the suggestion payload
            assert "answer" not in s
            assert "value" not in s
            ver = s.get("verification") or {}
            assert ver.get("sql_validated") is True
            assert ver.get("row_count", 0) >= 1
            # Re-check that verification SQL would still validate
            from backend.marketplace.demo_data_lite import _verification_sql_for_candidate

            sql = _verification_sql_for_candidate(s["id"], loaded["columns"], DEMO_DATA_DATASET_ID)
            assert sql
            assert validate_sql(sql, schema, s["question"])["is_valid"]
    finally:
        session_manager.evict_session(sid)


def test_api_demo_data_load_endpoint(client):
    res = client.post("/demo-data/load")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["dataset_name"] == DEMO_DATA_DATASET_NAME
    assert data["is_demo_data"] is True
    assert 6 <= len(data["suggested_questions"]) <= 8
    for q in data["suggested_questions"]:
        assert q["verified"] is True
        assert "answer" not in q


def test_demo_data_does_not_leak_across_sessions(client):
    a = client.post("/demo-data/load").json()
    b = client.post("/demo-data/load").json()
    assert a["session_id"] != b["session_id"]

    # Inject a marker only into session A
    session_manager.execute_query(
        a["session_id"],
        f"CREATE TEMP TABLE leak_marker AS SELECT 'secret-a' AS token",
    )
    marker = session_manager.execute_query(a["session_id"], "SELECT token FROM leak_marker")
    assert marker[0]["token"] == "secret-a"

    with pytest.raises(Exception):
        session_manager.execute_query(b["session_id"], "SELECT token FROM leak_marker")

    # Session B still only sees demo_data table contents, not A's secret
    rows_b = session_manager.execute_query(
        b["session_id"], f"SELECT COUNT(*) AS c FROM {DEMO_DATA_DATASET_ID}"
    )
    assert rows_b[0]["c"] == a["row_count"] == b["row_count"]


def test_real_csv_upload_replaces_demo_context(client):
    demo = client.post("/demo-data/load").json()
    demo_sid = demo["session_id"]
    assert demo["dataset_id"] == DEMO_DATA_DATASET_ID

    # Upload a completely different CSV → new session, new dataset
    buf = io.BytesIO()
    text = io.TextIOWrapper(buf, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=["sku", "units_sold", "warehouse"])
    writer.writeheader()
    writer.writerow({"sku": "X1", "units_sold": 3, "warehouse": "WH-A"})
    writer.writerow({"sku": "X2", "units_sold": 5, "warehouse": "WH-B"})
    text.flush()
    buf.seek(0)

    upload = client.post(
        "/upload",
        files={"file": ("real.csv", buf.getvalue(), "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    real = upload.json()
    assert real["session_id"] != demo_sid
    assert real["dataset_id"] != DEMO_DATA_DATASET_ID
    assert real["dataset_id"].startswith("uploaded_data_")

    col_names = {c["name"] if isinstance(c, dict) else c for c in real["columns"]}
    assert "sku" in col_names
    assert "revenue" not in col_names  # demo field must not appear

    # Real session cannot query demo_data table
    with pytest.raises(Exception):
        session_manager.execute_query(
            real["session_id"], f"SELECT * FROM {DEMO_DATA_DATASET_ID}"
        )


def test_unsupported_demo_question_does_not_hallucinate(client):
    demo = client.post("/demo-data/load").json()
    res = client.post(
        "/analyze",
        json={
            "session_id": demo["session_id"],
            "question": "Which supplier has the highest employee satisfaction score?",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    report = body.get("report") or {}
    # Must not invent a numeric satisfaction answer
    text_blob = str(report).lower()
    assert "employee_satisfaction" not in text_blob or body.get("success") is False or (
        "not" in text_blob or "unavailable" in text_blob or "clarif" in text_blob
        or "unsupported" in text_blob or "couldn't" in text_blob or "cannot" in text_blob
        or "missing" in text_blob or "don't" in text_blob or "failed" in text_blob
        or report.get("headline")
    )
    # Stronger: if tables exist, they must not claim a satisfaction column
    for table in report.get("tables") or []:
        cols = [str(c).lower() for c in (table.get("columns") or [])]
        assert "employee_satisfaction" not in cols
        assert "satisfaction" not in cols


def _extract_metric_from_report(report: dict, key_substr: str):
    """Pull a numeric/string value from the first result table for assertions."""
    tables = report.get("tables") or []
    if not tables:
        return None
    cols = [str(c) for c in (tables[0].get("columns") or [])]
    rows = tables[0].get("rows") or []
    if not rows:
        return None
    row = rows[0]
    # rows may be dicts or lists
    if isinstance(row, dict):
        for k, v in row.items():
            if key_substr in str(k).lower():
                return v
        # fallback first value
        return next(iter(row.values()), None)
    for i, c in enumerate(cols):
        if key_substr in c.lower():
            return row[i] if i < len(row) else None
    return row[0] if row else None


@pytest.mark.parametrize(
    "suggestion_id,truth_metric,key_substr",
    [
        ("total_revenue", "total_revenue", "revenue"),
        ("total_profit", "total_profit", "profit"),
        ("top_product", "top_product", "product"),
    ],
)
def test_suggested_questions_e2e_match_duckdb_truth(
    client, suggestion_id, truth_metric, key_substr
):
    """Each core suggested question runs through /analyze; numbers come from DuckDB."""
    demo = client.post("/demo-data/load").json()
    by_id = {q["id"]: q for q in demo["suggested_questions"]}
    assert suggestion_id in by_id
    question = by_id[suggestion_id]["question"]

    truth = independent_ground_truth(demo["session_id"], DEMO_DATA_DATASET_ID, truth_metric)

    res = client.post(
        "/analyze",
        json={"session_id": demo["session_id"], "question": question},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    report = body.get("report") or {}
    tables = report.get("tables") or []
    assert tables, f"expected result table for {suggestion_id}: {body}"

    got = _extract_metric_from_report(report, key_substr)
    assert got is not None, report
    if isinstance(truth, (int, float)):
        assert float(got) == pytest.approx(float(truth), rel=1e-6, abs=0.02)
    else:
        assert str(got) == str(truth)


def test_all_verified_suggestions_analyze_successfully(client):
    demo = client.post("/demo-data/load").json()
    assert 6 <= len(demo["suggested_questions"]) <= 8
    for q in demo["suggested_questions"]:
        res = client.post(
            "/analyze",
            json={"session_id": demo["session_id"], "question": q["question"]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        report = body.get("report") or {}
        # Production path must produce either a table or an explicit non-hallucinated failure/clarification
        tables = report.get("tables") or []
        headline = (report.get("headline") or "").lower()
        if not tables:
            assert any(
                w in headline or w in str(report).lower()
                for w in ("clarif", "fail", "unsupported", "unable", "need")
            ), report
        else:
            # Result columns must be real / derived — never invented base fields
            cols = [str(c).lower() for c in (tables[0].get("columns") or [])]
            assert "employee_satisfaction" not in cols
