"""Ambiguous and underspecified questions must be clarified, never guessed at.

Baseline (measured 2026-09-21): "Show me sales" spent 125.8s across 4 LLM calls and
returned "Analysis Failed" with no indication of what was unclear.
"""
import pytest

from backend.services.ambiguity import detect_ambiguity

DEMO_SCHEMA = {
    "columns": [
        {"name": "order_date", "analytical_role": "temporal", "dtype": "date"},
        {"name": "customer_region", "analytical_role": "categorical", "unique_count": 5},
        {"name": "product_name", "analytical_role": "categorical", "unique_count": 240},
        {"name": "sales_channel", "analytical_role": "categorical", "unique_count": 3},
        {"name": "revenue", "analytical_role": "measure", "dtype": "double"},
        {"name": "profit", "analytical_role": "measure", "dtype": "double"},
        {"name": "cost", "analytical_role": "measure", "dtype": "double"},
        {"name": "unit_price", "analytical_role": "measure", "dtype": "double"},
        {"name": "quantity", "analytical_role": "measure", "dtype": "bigint"},
    ]
}


# ── Underspecified requests ──────────────────────────────────────────────────


@pytest.mark.parametrize("question", ["Show me sales", "show me sales", "Show sales"])
def test_bare_metric_request_is_underspecified(question):
    report = detect_ambiguity(question, DEMO_SCHEMA)
    assert report is not None
    assert report.kind == "underspecified"
    assert report.candidates == ["revenue"]


def test_underspecified_suggestions_are_schema_grounded_and_runnable():
    report = detect_ambiguity("Show me sales", DEMO_SCHEMA)
    joined = " ".join(report.suggestions)
    assert "total revenue" in joined
    assert "over time by month" in joined, "a date column exists, so a trend is a valid reading"
    assert "sales_channel" in joined or "customer_region" in joined
    for suggestion in report.suggestions:
        assert suggestion.endswith("?")


def test_clarification_message_names_the_unclear_term():
    message = detect_ambiguity("Show me sales", DEMO_SCHEMA).message()
    assert "sales" in message
    assert "revenue" in message


def test_dataset_without_a_date_column_omits_the_trend_suggestion():
    schema = {"columns": [c for c in DEMO_SCHEMA["columns"] if c["name"] != "order_date"]}
    report = detect_ambiguity("Show me sales", schema)
    assert all("over time" not in s for s in report.suggestions)


def test_non_additive_measures_are_suggested_as_averages():
    schema = {"columns": [{"name": "unit_price", "analytical_role": "measure", "dtype": "double"}]}
    report = detect_ambiguity("Show me price", schema)
    assert report is not None
    assert any("average unit_price" in s for s in report.suggestions)
    assert all("total unit_price" not in s for s in report.suggestions)


# ── Ambiguous metric references ──────────────────────────────────────────────


def test_concept_matching_several_columns_is_ambiguous():
    report = detect_ambiguity("Show me amount", DEMO_SCHEMA)
    assert report is not None
    assert report.kind == "ambiguous_metric"
    assert set(report.candidates) == {"cost", "revenue", "unit_price"}


def test_ambiguous_metric_message_lists_every_candidate():
    message = detect_ambiguity("Show me amount", DEMO_SCHEMA).message()
    for candidate in ("cost", "revenue", "unit_price"):
        assert candidate in message


def test_sales_is_not_ambiguous_when_revenue_is_the_only_strong_match():
    """revenue is the canonical sales measure here, so the metric itself is clear."""
    report = detect_ambiguity("What are total sales by region?", DEMO_SCHEMA)
    assert report is None


# ── Questions that must stay answerable ──────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "What is the total revenue?",
        "Top 5 suppliers by revenue",
        "Which customer region has the highest total revenue?",
        "How has revenue changed over time by month?",
        "What percentage of total revenue comes from the top 10 products?",
        "Which regions have above-average revenue but below-average profit?",
        "How many orders are there?",
    ],
)
def test_well_specified_questions_are_never_blocked(question):
    assert detect_ambiguity(question, DEMO_SCHEMA) is None


def test_named_column_is_never_treated_as_ambiguous():
    assert detect_ambiguity("Show me unit_price", DEMO_SCHEMA) is None or (
        detect_ambiguity("Show me unit_price", DEMO_SCHEMA).kind == "underspecified"
    )


def test_empty_or_schemaless_input_is_ignored():
    assert detect_ambiguity("", DEMO_SCHEMA) is None
    assert detect_ambiguity("Show me sales", {"columns": []}) is None
    assert detect_ambiguity("Show me sales", None) is None


# ── Pipeline wiring ──────────────────────────────────────────────────────────


def test_ambiguity_is_not_retried_by_reflection():
    """Retrying an ambiguous question cannot resolve it; it must go straight to report."""
    from backend.agents.nodes.reflection import reflection_node

    out = reflection_node(
        {
            "failure_summary": {
                "failure_type": "ambiguous_question",
                "error_message": "which measure did you mean?",
            },
            "retry_count": 0,
            "retry_history": [],
            "execution_metadata": [],
        }
    )
    assert out.get("graceful_failure") is True


def test_api_returns_a_clarification_rather_than_a_generic_failure():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        with open("data/marketmind_demo_marketplace_4000.csv", "rb") as fh:
            upload = client.post("/upload", files={"file": ("demo.csv", fh, "text/csv")}).json()
        body = client.post(
            "/analyze",
            json={"session_id": upload["session_id"], "question": "Show me sales"},
        ).json()

    summary = (body.get("report") or {}).get("executive_summary") or {}
    assert summary.get("headline") == "Clarification Needed"
    assert "revenue" in (summary.get("summary") or "")
    assert body.get("success") is False, "a clarification is not a completed analysis"
