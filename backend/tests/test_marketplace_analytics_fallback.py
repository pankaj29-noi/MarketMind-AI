"""Deterministic marketplace analytics SQL fallback tests (no LLM required)."""
from __future__ import annotations

import uuid

import pytest

from backend.marketplace.demo_data import load_marketplace_demo
from backend.marketplace.sql_fallback import (
    resolve_marketplace_fallback,
    resolve_marketplace_sql,
)
from backend.mcp.data_access import run_query


QUESTIONS_EXPECT_SQL = [
    "Which product categories generated the highest order value?",
    "Which states generate the most buyer enquiries?",
    "Which suppliers have the highest number of orders?",
    "What are the top 5 products by revenue?",
    "Which cities have the highest number of buyers?",
    "Which categories have the most leads?",
    "What is the average order value by category?",
    "Which suppliers have the best average rating?",
    "Show the top products by number of orders.",
    "Which locations generate the highest total sales?",
]


@pytest.fixture(scope="module")
def marketplace_session_id() -> str:
    sid = f"analytics-test-{uuid.uuid4()}"
    load_marketplace_demo(sid)
    return sid


@pytest.mark.parametrize("question", QUESTIONS_EXPECT_SQL)
def test_fallback_resolves_and_executes(marketplace_session_id, question):
    result = resolve_marketplace_fallback(question)
    assert result.reason == "answerable", question
    assert result.sql
    assert result.analysis_source == "deterministic_fallback"
    assert "SELECT" in result.sql.upper()
    assert "LIMIT" in result.sql.upper() or "month" in result.sql.lower()

    out = run_query(marketplace_session_id, "marketplace", result.sql)
    assert out.get("success") is True, (question, out.get("error"))
    assert out.get("row_count", 0) >= 1, question


def test_weather_is_unsupported_domain():
    result = resolve_marketplace_fallback("What is the weather in Jaipur?")
    assert result.sql is None
    assert result.reason == "unsupported_domain"
    assert resolve_marketplace_sql("What is the weather in Jaipur?") is None


def test_top_n_limit_honored():
    sql = resolve_marketplace_sql("What are the top 5 products by revenue?")
    assert sql and "LIMIT 5" in sql.upper()
