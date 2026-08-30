"""Deterministic analytics fallback for marketplace + uploaded CSV (no LLM)."""
from __future__ import annotations

import csv
import tempfile
import uuid
from pathlib import Path

import pytest

from backend.marketplace.demo_data import load_marketplace_demo
from backend.mcp.data_access import run_query
from backend.services.analytics_fallback import (
    ANALYSIS_SOURCE_FALLBACK,
    resolve_analytics_fallback,
)


MARKETPLACE_QUESTIONS = [
    "Which product categories generated the highest order value?",
    "Which states generate the most buyer enquiries?",
    "Which suppliers have the highest number of orders?",
    "What are the top 5 products by revenue?",
    "Which categories have the most leads?",
]

CSV_QUESTIONS = [
    "How many total orders are there?",
    "Which category generated the highest sales?",
    "What are the top 10 products by sales amount?",
    "Which city generated the highest profit?",
    "What is the average order value by region?",
    "Show monthly sales trends.",
    "Which customer segment is the most profitable?",
    "Compare sales across different sales channels.",
]

CSV_COLUMNS = [
    "order_id",
    "order_date",
    "customer_id",
    "customer_segment",
    "product",
    "category",
    "quantity",
    "sales_amount",
    "profit",
    "city",
    "region",
    "sales_channel",
]

CSV_ROWS = [
    ["o1", "2024-01-15", "c1", "Enterprise", "Widget A", "Electronics", "2", "500", "120", "Mumbai", "West", "Online"],
    ["o2", "2024-01-20", "c2", "SMB", "Widget B", "Electronics", "1", "200", "40", "Delhi", "North", "Retail"],
    ["o3", "2024-02-10", "c3", "Enterprise", "Gadget X", "Home", "5", "900", "300", "Jaipur", "West", "Online"],
    ["o4", "2024-02-18", "c1", "Enterprise", "Widget A", "Electronics", "3", "750", "180", "Mumbai", "West", "Partner"],
    ["o5", "2024-03-05", "c4", "Consumer", "Gadget Y", "Home", "1", "150", "25", "Delhi", "North", "Retail"],
    ["o6", "2024-03-22", "c2", "SMB", "Widget C", "Industrial", "10", "1200", "400", "Pune", "West", "Online"],
]


@pytest.fixture(scope="module")
def marketplace_session_id() -> str:
    sid = f"analytics-demo-{uuid.uuid4()}"
    load_marketplace_demo(sid)
    return sid


@pytest.fixture(scope="module")
def csv_session_and_schema():
    sid = f"csv-demo-{uuid.uuid4()}"
    dataset_id = f"upload_{uuid.uuid4().hex[:8]}"
    from backend.services.session_manager import session_manager

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{dataset_id}.csv"
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerows(CSV_ROWS)

        session_manager.register_csv(sid, str(path), dataset_id)
        schema = {
            "dataset_id": dataset_id,
            "columns": [{"name": c} for c in CSV_COLUMNS],
            "row_count": len(CSV_ROWS),
            "multi_table": False,
        }
        yield sid, dataset_id, schema


@pytest.mark.parametrize("question", MARKETPLACE_QUESTIONS)
def test_marketplace_fallback_executes(marketplace_session_id, question):
    schema = {"multi_table": True, "dataset_id": "marketplace"}
    result = resolve_analytics_fallback(question, schema, "marketplace")
    assert result.reason == "answerable", question
    assert result.sql
    assert result.analysis_source == ANALYSIS_SOURCE_FALLBACK
    out = run_query(marketplace_session_id, "marketplace", result.sql)
    assert out.get("success") is True, (question, out.get("error"))
    assert out.get("row_count", 0) >= 1, question


@pytest.mark.parametrize("question", CSV_QUESTIONS)
def test_csv_fallback_executes(csv_session_and_schema, question):
    sid, dataset_id, schema = csv_session_and_schema
    result = resolve_analytics_fallback(question, schema, dataset_id)
    assert result.reason == "answerable", (question, result.reason)
    assert result.sql, question
    assert result.analysis_source == ANALYSIS_SOURCE_FALLBACK
    out = run_query(sid, dataset_id, result.sql)
    assert out.get("success") is True, (question, result.sql, out.get("error"))
    assert out.get("row_count", 0) >= 1, question


def test_weather_unsupported_marketplace():
    result = resolve_analytics_fallback(
        "What is the weather in Jaipur?",
        {"multi_table": True},
        "marketplace",
    )
    assert result.sql is None
    assert result.reason == "unsupported_domain"


def test_weather_unsupported_csv():
    schema = {
        "dataset_id": "orders_csv",
        "columns": [{"name": c} for c in CSV_COLUMNS],
        "multi_table": False,
    }
    result = resolve_analytics_fallback(
        "What is the weather in Jaipur?",
        schema,
        "orders_csv",
    )
    assert result.sql is None
    assert result.reason == "unsupported_domain"
