"""Unit tests for requirement extraction (STEP 1) and semantic coverage (STEP 2)."""
from backend.services.requirement_coverage import (
    check_requirement_coverage,
    confidence_from_coverage,
    coverage_failure_message,
    extract_question_requirements,
    match_requirements_to_schema,
)


Q1 = (
    "Which city generates high sales but relatively low profit, "
    "and what business insight can you derive from this?"
)
Q2 = (
    "Analyze the relationship between discount rate and profitability across "
    "product categories. Identify the category where higher discounts are "
    "associated with lower profit margins, and compare its sales volume with "
    "other categories."
)
Q3 = (
    "Which customer segment generates the highest sales but has the lowest "
    "profit margin? Calculate total sales, total profit, and profit margin "
    "for each segment, then identify the mismatch."
)
Q4 = "Identify categories that rank in the top 3 by sales but bottom 3 by profit margin."


# ── STEP 1: extraction ──────────────────────────────────────────────────────


def test_q1_city_high_sales_low_profit_insight():
    req = extract_question_requirements(Q1)
    d = req.to_dict()

    assert "city" in d["dimensions"]
    assert "sales" in d["metrics"]
    assert "profit" in d["metrics"]
    assert "profit_margin" in d["derived_metrics"]
    assert "high_sales_low_profit" in d["comparisons"]
    assert "business_insight" in d["requested_conclusions"]
    assert "identify_entity" in d["requested_conclusions"]
    assert "profit_margin" not in d["metrics"]


def test_q2_discount_profitability_across_categories():
    req = extract_question_requirements(Q2)
    d = req.to_dict()

    assert "category" in d["dimensions"], "category dimension must not be dropped"
    assert "discount" in d["metrics"]
    assert "profit" in d["metrics"]
    assert "sales" in d["metrics"]
    assert "profit_margin" in d["derived_metrics"]
    assert any("discount" in r for r in d["relationships"])
    assert "across_dimension" in d["relationships"]
    assert "compare_groups" in d["comparisons"] or "group_by_dimension" in d["comparisons"]
    assert d["dimensions"] != []


def test_q3_segment_sales_margin_mismatch():
    req = extract_question_requirements(Q3)
    d = req.to_dict()

    assert "segment" in d["dimensions"]
    assert "sales" in d["metrics"]
    assert "profit" in d["metrics"]
    assert "profit_margin" in d["derived_metrics"]
    assert "profit_margin" not in d["metrics"]
    assert any(x in d["rankings"] for x in ("highest", "lowest"))
    assert "high_sales_low_profit" in d["comparisons"] or "identify_mismatch" in d["comparisons"]
    assert "per_group_breakdown" in d["comparisons"]


def test_q4_top3_bottom3_rank_intersection():
    req = extract_question_requirements(Q4)
    d = req.to_dict()

    assert "category" in d["dimensions"]
    assert "sales" in d["metrics"]
    assert "profit_margin" in d["derived_metrics"]
    assert d["needs_top_n"] == 3
    assert d["needs_bottom_n"] == 3
    assert "rank_intersection" in d["rankings"]


def test_profit_is_not_profit_margin():
    req = extract_question_requirements("Show total profit by city")
    assert "profit" in req.metrics
    assert "profit_margin" not in req.derived_metrics

    req2 = extract_question_requirements("Show profit margin by city")
    assert "profit_margin" in req2.derived_metrics
    assert "sales" in req2.metrics
    assert "profit" in req2.metrics


def test_match_requirements_to_schema_helper():
    req = extract_question_requirements(Q1)
    matched = match_requirements_to_schema(
        req, ["order_id", "sales_amount", "profit", "city", "category", "discount_rate"]
    )
    assert matched.get("city") == "city"
    assert matched.get("sales") == "sales_amount"
    assert matched.get("profit") == "profit"


# ── STEP 2: PASS coverage ───────────────────────────────────────────────────


def test_pass_city_sales_profit_analysis():
    sql = """
    SELECT city,
           SUM(sales_amount) AS total_sales,
           SUM(profit) AS total_profit,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY city
    """
    ok, missing = check_requirement_coverage(
        Q1, sql, ["city", "total_sales", "total_profit", "profit_margin"]
    )
    assert ok is True, missing


def test_pass_category_discount_margin_sales():
    sql = """
    SELECT category,
           AVG(discount_rate) AS avg_discount_rate,
           SUM(sales_amount) AS total_sales,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY category
    """
    ok, missing = check_requirement_coverage(
        Q2,
        sql,
        ["category", "avg_discount_rate", "total_sales", "profit_margin"],
        row_count=5,
    )
    assert ok is True, missing


def test_pass_segment_sales_profit_margin_ranking():
    sql = """
    SELECT customer_segment,
           SUM(sales_amount) AS total_sales,
           SUM(profit) AS total_profit,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY customer_segment
    ORDER BY total_sales DESC
    """
    ok, missing = check_requirement_coverage(
        Q3,
        sql,
        ["customer_segment", "total_sales", "total_profit", "profit_margin"],
        row_count=3,
    )
    assert ok is True, missing


def test_pass_top3_and_bottom3_intersection():
    sql = """
    WITH ranked AS (
      SELECT category,
             SUM(sales_amount) AS total_sales,
             SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin,
             RANK() OVER (ORDER BY SUM(sales_amount) DESC) AS sales_rank,
             RANK() OVER (
               ORDER BY SUM(profit)/NULLIF(SUM(sales_amount),0) ASC
             ) AS margin_rank
      FROM t GROUP BY category
    )
    SELECT category, total_sales, profit_margin, sales_rank, margin_rank
    FROM ranked
    WHERE sales_rank <= 3 AND margin_rank <= 3
    """
    ok, missing = check_requirement_coverage(
        Q4,
        sql,
        ["category", "total_sales", "profit_margin", "sales_rank", "margin_rank"],
    )
    assert ok is True, missing


# ── STEP 2: FAIL coverage ───────────────────────────────────────────────────


def test_fail_global_discount_profit_correlation_for_category_question():
    ok, missing = check_requirement_coverage(
        Q2,
        "SELECT corr(discount_rate, profit) AS correlation FROM t",
        ["correlation"],
    )
    assert ok is False
    assert any("categor" in m.lower() or "dimension" in m.lower() for m in missing)
    msg = coverage_failure_message(
        missing, question=Q2, requirements=extract_question_requirements(Q2)
    )
    assert "semantic_incomplete" in msg


def test_fail_profit_only_when_profit_margin_required():
    ok, missing = check_requirement_coverage(
        Q3,
        "SELECT customer_segment, SUM(profit) AS total_profit FROM t GROUP BY customer_segment",
        ["customer_segment", "total_profit"],
    )
    assert ok is False
    assert any("margin" in m.lower() or "sales" in m.lower() for m in missing)


def test_fail_top3_only_when_intersection_required():
    sql = """
    SELECT category, total_sales, sales_rank FROM (
      SELECT category,
             SUM(sales_amount) AS total_sales,
             RANK() OVER (ORDER BY SUM(sales_amount) DESC) AS sales_rank
      FROM t GROUP BY category
    ) s WHERE sales_rank <= 3
    """
    ok, missing = check_requirement_coverage(
        Q4, sql, ["category", "total_sales", "sales_rank"]
    )
    assert ok is False
    assert any("rank" in m.lower() or "intersection" in m.lower() for m in missing)


def test_fail_single_category_when_comparison_required():
    sql = """
    SELECT category,
           AVG(discount_rate) AS avg_discount_rate,
           SUM(sales_amount) AS total_sales,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY category
    LIMIT 1
    """
    ok, missing = check_requirement_coverage(
        Q2,
        sql,
        ["category", "avg_discount_rate", "total_sales", "profit_margin"],
        row_count=1,
    )
    assert ok is False
    assert any("comparison" in m.lower() for m in missing)


def test_confidence_low_when_coverage_fails():
    assert confidence_from_coverage(coverage_ok=False, missing=["x"]) == "Low"
    assert (
        confidence_from_coverage(coverage_ok=True, missing=[], analysis_source="groq")
        == "High"
    )
    # Fallback is not downgraded solely due to source when coverage passes
    assert (
        confidence_from_coverage(
            coverage_ok=True, missing=[], analysis_source="deterministic_fallback"
        )
        == "High"
    )
    # Execution success alone is not High when coverage fails
    assert (
        confidence_from_coverage(
            coverage_ok=False, missing=["dim"], execution_success=True
        )
        == "Low"
    )
