"""The deterministic fallback must not invent an answer for a missing metric.

Baseline: "Which supplier has the highest employee satisfaction?" returned a
revenue ranking of suppliers with reason='answerable'. That is a hallucination
— the dataset has no satisfaction column.
"""
from backend.services.analytics_fallback import resolve_analytics_fallback

SCHEMA = {
    "dataset_id": "marketplace_orders",
    "columns": [
        {"name": "supplier_name"},
        {"name": "customer_region"},
        {"name": "revenue"},
        {"name": "profit"},
        {"name": "rating"},
    ],
}


def test_missing_satisfaction_is_rejected():
    result = resolve_analytics_fallback(
        "Which supplier has the highest employee satisfaction?",
        SCHEMA,
        "marketplace_orders",
    )
    assert result.sql is None
    assert "unsupported_metric" in (result.reason or "")


def test_missing_credit_score_is_rejected():
    result = resolve_analytics_fallback(
        "What is the average customer credit score?",
        SCHEMA,
        "marketplace_orders",
    )
    assert result.sql is None


def test_real_metric_still_answers():
    result = resolve_analytics_fallback(
        "What are the top 5 suppliers by revenue?",
        SCHEMA,
        "marketplace_orders",
    )
    assert result.sql is not None
    assert "revenue" in result.sql.lower()


def test_existing_rating_column_is_not_blocked():
    """A dataset that actually has a rating column may answer rating questions."""
    result = resolve_analytics_fallback(
        "Which supplier has the highest rating?",
        SCHEMA,
        "marketplace_orders",
    )
    # May or may not produce SQL depending on templates, but must not claim
    # unsupported_metric:rating when the column exists.
    assert "unsupported_metric:rating" not in (result.reason or "")
