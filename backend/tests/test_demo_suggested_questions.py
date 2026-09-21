"""Curated demo suggested questions must be answerable on their schemas."""
from __future__ import annotations

import uuid

from backend.marketplace.demo_data import (
    ANALYTICS_DEMO_DATASET_ID,
    ANALYTICS_DEMO_SUGGESTED_QUESTIONS,
    get_demo_example_questions,
    get_marketplace_suggested_questions,
    load_analytics_demo,
    load_marketplace_demo,
    verify_analytics_demo_suggested_questions,
)
from backend.marketplace.sql_fallback import EXAMPLE_QUESTIONS, resolve_marketplace_fallback
from backend.mcp.data_access import run_query
from backend.services.analytics_fallback import resolve_analytics_fallback
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.services.requirement_coverage import check_requirement_coverage
from backend.services.sql.sql_quality_validator import validate_sql


def test_analytics_demo_examples_exclude_failure_traps():
    cats = get_demo_example_questions()
    assert "Reliability Checks" not in cats
    flat = [q for qs in cats.values() for q in qs]
    assert flat == ANALYTICS_DEMO_SUGGESTED_QUESTIONS
    joined = " ".join(flat).lower()
    assert "delete" not in joined
    assert "employee satisfaction" not in joined


def test_analytics_demo_suggested_questions_verify_and_execute():
    sid = f"analytics-sug-{uuid.uuid4()}"
    load_analytics_demo(sid)
    suggested = verify_analytics_demo_suggested_questions(sid)
    assert 6 <= len(suggested) <= 8
    profile = get_or_build_csv_schema_profile(sid, ANALYTICS_DEMO_DATASET_ID)
    for item in suggested:
        q = item["question"]
        fb = resolve_analytics_fallback(q, profile, ANALYTICS_DEMO_DATASET_ID)
        assert fb.sql, q
        ok, miss = check_requirement_coverage(q, fb.sql, columns=None)
        vf = validate_sql(fb.sql, profile, q)
        out = run_query(sid, ANALYTICS_DEMO_DATASET_ID, fb.sql)
        assert ok and vf.get("is_valid") and out.get("success"), (q, miss, vf, out.get("error"))


def test_marketplace_suggested_questions_match_example_templates():
    suggested = get_marketplace_suggested_questions()
    texts = [s["question"] for s in suggested]
    assert texts == list(EXAMPLE_QUESTIONS[: len(texts)])
    sid = f"mkt-sug-{uuid.uuid4()}"
    load_marketplace_demo(sid)
    for q in texts:
        fb = resolve_marketplace_fallback(q)
        assert fb.sql
        out = run_query(sid, "marketplace", fb.sql)
        assert out.get("success"), (q, out.get("error"))
