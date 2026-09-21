"""Tests for adaptive simple suggested-question generation."""
from __future__ import annotations

import csv
import os
import tempfile
import uuid

import pytest

from backend.mcp.data_access import run_query
from backend.services.adaptive_questions.cache import invalidate_session
from backend.services.adaptive_questions.engine import generate_suggested_questions
from backend.services.session_manager import session_manager


def _load_csv(rows: list[dict], fieldnames: list[str]) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    dataset_id = f"uploaded_data_{uuid.uuid4().hex[:8]}"
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    session_manager.register_csv(session_id, path, dataset_id)
    return session_id, dataset_id


@pytest.fixture(autouse=True)
def _cleanup_sessions():
    yield


def test_sales_dataset_questions_reference_real_columns():
    session_id, dataset_id = _load_csv(
        [
            {"customer_id": "c1", "order_date": "2024-01-15", "region": "North", "sales": "100", "quantity": "2"},
            {"customer_id": "c2", "order_date": "2024-02-10", "region": "South", "sales": "250", "quantity": "5"},
            {"customer_id": "c3", "order_date": "2024-03-01", "region": "North", "sales": "180", "quantity": "3"},
            {"customer_id": "c1", "order_date": "2024-03-20", "region": "West", "sales": "90", "quantity": "1"},
        ],
        ["customer_id", "order_date", "region", "sales", "quantity"],
    )
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=8)
    assert result["questions"], result.get("message")
    assert 1 <= len(result["questions"]) <= 10
    texts = " ".join(q["text"].lower() for q in result["questions"])
    assert "sales" in texts or "region" in texts or "quantity" in texts
    assert "salary" not in texts
    assert all("profit" not in q["text"].lower() for q in result["questions"])


def test_employee_dataset_adapts_away_from_sales_language():
    session_id, dataset_id = _load_csv(
        [
            {"employee_id": "1", "department": "Eng", "salary": "120000", "joining_date": "2021-05-01", "performance_score": "4.2"},
            {"employee_id": "2", "department": "Sales", "salary": "90000", "joining_date": "2022-01-10", "performance_score": "3.8"},
            {"employee_id": "3", "department": "Eng", "salary": "130000", "joining_date": "2020-11-20", "performance_score": "4.5"},
            {"employee_id": "4", "department": "HR", "salary": "80000", "joining_date": "2023-03-15", "performance_score": "4.0"},
        ],
        ["employee_id", "department", "salary", "joining_date", "performance_score"],
    )
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=8)
    assert result["questions"]
    texts = " ".join(q["text"].lower() for q in result["questions"])
    assert "salary" in texts or "department" in texts or "performance" in texts
    assert "revenue" not in texts
    assert all("revenue" not in q["text"].lower() for q in result["questions"])


def test_cross_dataset_isolation():
    s1, d1 = _load_csv(
        [{"region": "A", "sales": "10"}, {"region": "B", "sales": "20"}],
        ["region", "sales"],
    )
    s2, d2 = _load_csv(
        [{"department": "X", "salary": "50"}, {"department": "Y", "salary": "80"}],
        ["department", "salary"],
    )
    invalidate_session(s1)
    invalidate_session(s2)
    q1 = generate_suggested_questions(s1, d1, count=6)["questions"]
    q2 = generate_suggested_questions(s2, d2, count=6)["questions"]
    t1 = " ".join(q["text"].lower() for q in q1)
    t2 = " ".join(q["text"].lower() for q in q2)
    assert "sales" in t1 or "region" in t1
    assert "salary" in t2 or "department" in t2
    assert "salary" not in t1
    assert "sales" not in t2


def test_empty_dataset_message():
    session_id, dataset_id = _load_csv([], ["a", "b"])
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=5)
    assert result["questions"] == []
    assert result.get("message")


def _rich_sales_rows(n: int = 80) -> list[dict]:
    regions = ["North", "South", "East", "West"]
    categories = ["Electronics", "Apparel", "Grocery", "Tools"]
    rows = []
    for i in range(n):
        year = 2024 + (i % 2)
        month = (i % 12) + 1
        revenue = 100 + (i * 7) % 900
        rows.append(
            {
                "order_id": f"o{i}",
                "order_date": f"{year}-{month:02d}-15",
                "region": regions[i % len(regions)],
                "category": categories[(i // 3) % len(categories)],
                "quantity": (i % 9) + 1,
                "revenue": revenue,
                "profit": round(revenue * (0.1 + (i % 5) / 50), 2),
            }
        )
    return rows


def _rich_session():
    return _load_csv(
        _rich_sales_rows(),
        ["order_id", "order_date", "region", "category", "quantity", "revenue", "profit"],
    )


def test_answerable_mix_includes_verified_tiers_only():
    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=10)
    assert result["questions"]
    assert 5 <= len(result["questions"]) <= 10
    assert result.get("generation_version", "").startswith("v4")
    tiers = {t["tier"] for t in result["tiers"]}
    assert tiers <= {"quick", "analytics", "advanced"}
    assert "expert" not in tiers
    difficulties = {q["difficulty"] for q in result["questions"]}
    assert difficulties <= {"easy", "medium", "hard", "very_hard"}
    assert any(q["difficulty"] in {"medium", "hard"} for q in result["questions"]) or any(
        q["tier"] in {"analytics", "advanced"} for q in result["questions"]
    )
    for q in result["questions"]:
        assert q["validation_status"] == "executed"


def test_generated_questions_never_reference_unknown_columns():
    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    from backend.services.adaptive_questions.profiler import profile_dataset

    known = {c.name for c in profile_dataset(session_id, dataset_id).columns}
    result = generate_suggested_questions(session_id, dataset_id, count=10)
    for q in result["questions"]:
        for col in q.get("required_columns", []):
            assert col in known, f"hallucinated column {col} in {q['text']}"


def test_simple_dataset_shows_only_valid_questions():
    session_id, dataset_id = _load_csv(
        [{"name": n, "age": a} for n, a in [("A", 30), ("B", 41), ("C", 25), ("D", 52)]],
        ["name", "age"],
    )
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=10)
    tiers = {t["tier"] for t in result["tiers"]}
    assert tiers <= {"quick", "analytics", "advanced"}
    assert "expert" not in tiers
    assert result["questions"], result.get("message")
    assert len(result["questions"]) <= 10
    for q in result["questions"]:
        assert q["validation_status"] == "executed"
        low = q["text"].lower()
        assert "revenue" not in low and "profit" not in low


def test_each_displayed_question_executes_on_duckdb():
    """Every returned suggestion must execute via its validated production SQL."""
    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=8)
    assert result["questions"]
    from backend.services.adaptive_questions.profiler import profile_dataset
    from backend.services.adaptive_questions.validator import (
        _resolve_production_sql,
        validate_candidate,
    )
    from backend.services.adaptive_questions.templates import QuestionCandidate

    profile = profile_dataset(session_id, dataset_id)
    for q in result["questions"]:
        sql = _resolve_production_sql(profile, q["text"])
        assert sql, q["text"]
        res = run_query(session_id, dataset_id, sql)
        assert res.get("success"), (q["text"], res.get("error"))
        cand = QuestionCandidate(
            id=q["id"],
            text=q["text"],
            category=q.get("category") or "aggregation",
            difficulty=q.get("difficulty") or "easy",
            intent=q.get("intent") or "sum_measure",
            proof_sql=sql,
            confidence=1.0,
            columns_used=list(q.get("required_columns") or []),
        )
        ok, reason = validate_candidate(session_id, profile, cand)
        assert ok, (q["text"], reason)


def test_cache_hit_is_fast_and_dataset_scoped():
    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    first = generate_suggested_questions(session_id, dataset_id, count=8)
    second = generate_suggested_questions(session_id, dataset_id, count=8)
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert [q["id"] for q in first["questions"]] == [q["id"] for q in second["questions"]]


def test_refresh_returns_new_questions_without_repeats():
    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    first = generate_suggested_questions(session_id, dataset_id, count=8)
    ids = [q["id"] for q in first["questions"]]
    second = generate_suggested_questions(
        session_id, dataset_id, count=8, refresh=True, exclude_ids=ids
    )
    # May return fewer if pool exhausted — never invent extras
    if second["questions"]:
        assert not (set(ids) & {q["id"] for q in second["questions"]})


def test_followups_are_grounded_in_result_and_schema():
    from backend.services.adaptive_questions import generate_followup_questions
    from backend.services.adaptive_questions.profiler import profile_dataset

    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    res = run_query(
        session_id,
        dataset_id,
        f'SELECT region, SUM(revenue) AS rev FROM "{dataset_id}" GROUP BY 1 ORDER BY rev DESC LIMIT 5',
    )
    assert res["success"]
    fu = generate_followup_questions(
        session_id,
        dataset_id,
        question="Which region has the highest revenue?",
        result_columns=res["columns"],
        result_rows=res["rows"],
        count=3,
    )
    known = {c.name for c in profile_dataset(session_id, dataset_id).columns}
    for q in fu["questions"]:
        for col in q.get("required_columns", []):
            assert col in known
        assert "employee satisfaction" not in q["text"].lower()


def test_generated_proof_sql_is_read_only():
    from backend.services.adaptive_questions.capabilities import build_capabilities
    from backend.services.adaptive_questions.profiler import profile_dataset
    from backend.services.adaptive_questions.semantics import build_semantics
    from backend.services.adaptive_questions.templates import generate_candidates

    session_id, dataset_id = _rich_session()
    profile = profile_dataset(session_id, dataset_id)
    semantics = build_semantics(profile)
    caps = build_capabilities(profile, semantics)
    candidates = generate_candidates(profile, caps, semantics)
    banned = (
        "insert",
        "update ",
        "delete",
        "drop",
        "alter",
        "truncate",
        "attach",
        "copy ",
        "install",
        "load ",
    )
    for c in candidates:
        low = c.proof_sql.lower()
        assert low.strip().startswith(("select", "with"))
        assert not any(b in low for b in banned), c.proof_sql


def test_iot_schema_adapts_without_assuming_sales_columns():
    session_id, dataset_id = _load_csv(
        [
            {"device_id": "d1", "site": "Plant-A", "temp_c": "21.5", "humidity": "40"},
            {"device_id": "d2", "site": "Plant-B", "temp_c": "23.1", "humidity": "55"},
            {"device_id": "d3", "site": "Plant-A", "temp_c": "19.8", "humidity": "48"},
            {"device_id": "d4", "site": "Plant-C", "temp_c": "22.0", "humidity": "51"},
        ],
        ["device_id", "site", "temp_c", "humidity"],
    )
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=8)
    assert result["questions"]
    texts = " ".join(q["text"].lower() for q in result["questions"])
    assert "temp" in texts or "humidity" in texts or "site" in texts or "records" in texts
    for banned in ("revenue", "profit", "product", "sales"):
        assert banned not in texts
    assert len(result["questions"]) <= 10
    for q in result["questions"]:
        assert q["tier"] in {"quick", "analytics", "advanced"}
        assert q["difficulty"] in {"easy", "medium", "hard", "very_hard"}
        assert q["validation_status"] == "executed"


def test_survey_schema_count_and_category_questions():
    session_id, dataset_id = _load_csv(
        [
            {"respondent": "r1", "city": "Austin", "score": "8", "channel": "email"},
            {"respondent": "r2", "city": "Dallas", "score": "6", "channel": "phone"},
            {"respondent": "r3", "city": "Austin", "score": "9", "channel": "email"},
            {"respondent": "r4", "city": "Houston", "score": "7", "channel": "web"},
            {"respondent": "r5", "city": "Dallas", "score": "5", "channel": "web"},
        ],
        ["respondent", "city", "score", "channel"],
    )
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=8)
    assert result["questions"]
    texts = " ".join(q["text"].lower() for q in result["questions"])
    assert "score" in texts or "city" in texts or "channel" in texts or "records" in texts
    assert "revenue" not in texts
    assert all(q["validation_status"] == "executed" for q in result["questions"])


def test_count_clamped_to_ten():
    session_id, dataset_id = _rich_session()
    invalidate_session(session_id)
    result = generate_suggested_questions(session_id, dataset_id, count=50)
    assert len(result["questions"]) <= 10
