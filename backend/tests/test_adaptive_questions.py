"""Tests for adaptive dataset-aware question generation."""
from __future__ import annotations

import csv
import os
import tempfile
import uuid

import pytest

from backend.services.adaptive_questions.engine import generate_suggested_questions
from backend.services.adaptive_questions.cache import invalidate_session
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
    # best-effort: nothing global to clear beyond cache keys we invalidate in tests


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
    texts = " ".join(q["text"].lower() for q in result["questions"])
    assert "sales" in texts or "region" in texts or "quantity" in texts
    assert "salary" not in texts
    assert all("profit" not in q["text"].lower() for q in result["questions"])
    assert all("revenue" not in q["text"].lower() or "sales" in q["text"].lower() for q in result["questions"])


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
