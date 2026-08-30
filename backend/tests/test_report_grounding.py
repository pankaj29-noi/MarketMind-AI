"""STEP 5: report grounding, confidence, and anti-hallucination checks."""
from backend.services.reporting.report_grounding import (
    build_evidence_summary,
    check_report_grounding,
    margin_spread_points,
    repair_report_text_for_grounding,
    soften_causation_language,
)
from backend.services.requirement_coverage import confidence_from_coverage


Q_CAT = (
    "Analyze the relationship between discount rate and profitability across "
    "product categories."
)
Q_SEG = (
    "Which customer segment generates the highest sales but has the lowest "
    "profit margin?"
)
Q_CITY = (
    "Which city generates high sales but relatively low profit, "
    "and what business insight can you derive from this?"
)


def test_category_result_must_not_be_declared_missing():
    cols = ["category", "avg_discount_rate", "profit_margin", "total_sales"]
    rows = [
        {"category": "Furniture", "avg_discount_rate": 0.22, "profit_margin": 0.11, "total_sales": 1000},
        {"category": "Technology", "avg_discount_rate": 0.15, "profit_margin": 0.18, "total_sales": 2000},
    ]
    bad = (
        "No category-level data is available, so we cannot identify the category "
        "or compare sales across categories."
    )
    ok, issues = check_report_grounding(
        report_text=bad,
        result_columns=cols,
        result_rows=rows,
        coverage_ok=True,
        question=Q_CAT,
    )
    assert ok is False
    assert any("unavailable" in i.lower() or "evidence" in i.lower() for i in issues)

    headline, summary = repair_report_text_for_grounding(
        summary=bad,
        headline="Cannot analyze categories",
        question=Q_CAT,
        columns=cols,
        rows=rows,
        issues=issues,
    )
    blob = (headline + " " + summary).lower()
    assert "unavailable" not in blob or "contain the requested evidence" in blob
    assert "category" in blob
    assert "avg_discount_rate" in blob or "returned columns" in blob


def test_practical_margin_difference_not_exaggerated():
    cols = ["customer_segment", "total_sales", "total_profit", "profit_margin"]
    rows = [
        {"customer_segment": "Consumer", "total_sales": 5000, "total_profit": 1424, "profit_margin": 0.2848},
        {"customer_segment": "Corporate", "total_sales": 4000, "total_profit": 1140, "profit_margin": 0.2850},
        {"customer_segment": "Small Business", "total_sales": 3000, "total_profit": 855.6, "profit_margin": 0.2852},
    ]
    spread = margin_spread_points(cols, rows)
    assert spread is not None
    assert spread < 0.05  # ~0.04 pp

    exaggerated = (
        "Consumer has dramatically lower profitability and a severe profitability crisis."
    )
    ok, issues = check_report_grounding(
        report_text=exaggerated,
        result_columns=cols,
        result_rows=rows,
        coverage_ok=True,
        question=Q_SEG,
    )
    assert ok is False
    assert any("exaggerat" in i.lower() or "spread" in i.lower() for i in issues)

    evidence = build_evidence_summary(Q_SEG, cols, rows)
    assert "negligible" in evidence.lower() or "spread" in evidence.lower()
    assert "anova" not in evidence.lower()
    assert "statistical significance testing is not required" in evidence.lower()


def test_city_result_grounding_uses_metrics():
    cols = ["city", "total_sales", "total_profit", "profit_margin"]
    rows = [
        {"city": "Jaipur", "total_sales": 9000, "total_profit": 400, "profit_margin": 0.044},
        {"city": "Delhi", "total_sales": 8000, "total_profit": 1200, "profit_margin": 0.15},
    ]
    bad = "Sales and profit metrics are unavailable for cities."
    ok, issues = check_report_grounding(
        report_text=bad,
        result_columns=cols,
        result_rows=rows,
        coverage_ok=True,
        question=Q_CITY,
    )
    assert ok is False

    evidence = build_evidence_summary(Q_CITY, cols, rows)
    assert "city" in evidence.lower()
    assert "total_sales" in evidence
    assert "unavailable" not in evidence.lower()
    assert "insight" in evidence.lower() or "interpretation" in evidence.lower()


def test_confidence_requires_coverage_not_just_execution():
    assert (
        confidence_from_coverage(
            coverage_ok=False, missing=["category"], execution_success=True
        )
        == "Low"
    )
    assert (
        confidence_from_coverage(
            coverage_ok=True, missing=[], analysis_source="deterministic_fallback"
        )
        == "High"
    )
    assert (
        confidence_from_coverage(
            coverage_ok=True, missing=[], evidence_limited=True
        )
        == "Medium"
    )


def test_no_invented_causation_language():
    cols = ["category", "avg_discount_rate", "profit_margin", "total_sales"]
    rows = [
        {"category": "A", "avg_discount_rate": 0.3, "profit_margin": 0.1, "total_sales": 100},
        {"category": "B", "avg_discount_rate": 0.1, "profit_margin": 0.2, "total_sales": 200},
    ]
    causal = "Higher discounts caused lower profit margins across categories."
    ok, issues = check_report_grounding(
        report_text=causal,
        result_columns=cols,
        result_rows=rows,
        coverage_ok=True,
        question=Q_CAT,
    )
    assert ok is False
    assert any("causation" in i.lower() or "association" in i.lower() for i in issues)

    softened = soften_causation_language(causal)
    assert "caused" not in softened.lower()
    assert "associated" in softened.lower()

    allowed = (
        "Higher discounts are associated with lower profit margin in the returned "
        "category-level results."
    )
    ok2, issues2 = check_report_grounding(
        report_text=allowed,
        result_columns=cols,
        result_rows=rows,
        coverage_ok=True,
        question=Q_CAT,
    )
    assert ok2 is True, issues2
