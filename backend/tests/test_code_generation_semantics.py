"""STEP 3: requirement contract injection + SQL generation semantic pre-check."""
from unittest.mock import patch

from backend.agents.nodes.code_generator import code_generator_node
from backend.services.requirement_coverage import (
    check_requirement_coverage,
    extract_question_requirements,
    format_semantic_requirement_contract,
)


Q1 = "Which city generates high sales but relatively low profit?"
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

SCHEMA = {
    "columns": [
        {"name": "city", "dtype": "VARCHAR"},
        {"name": "category", "dtype": "VARCHAR"},
        {"name": "customer_segment", "dtype": "VARCHAR"},
        {"name": "sales_amount", "dtype": "DOUBLE"},
        {"name": "profit", "dtype": "DOUBLE"},
        {"name": "discount_rate", "dtype": "DOUBLE"},
    ]
}


def _base_state(question: str) -> dict:
    return {
        "question": question,
        "plan": {"approach": "sql", "steps": ["analyze"]},
        "schema_profile": SCHEMA,
        "dataset_id": "test_ds",
        "duckdb_table": "test_ds",
        "retry_count": 0,
        "retry_history": [],
        "execution_metadata": [],
        "analysis_artifacts": {},
    }


def test_contract_q1_includes_city_sales_profit():
    req = extract_question_requirements(Q1)
    contract = format_semantic_requirement_contract(req)
    assert "SEMANTIC REQUIREMENTS" in contract
    assert "city" in contract
    assert "sales" in contract
    assert "profit" in contract


def test_contract_q2_keeps_category_and_rejects_global_only_guidance():
    req = extract_question_requirements(Q2)
    contract = format_semantic_requirement_contract(req)
    assert "category" in contract
    assert "discount" in contract
    assert "global" in contract.lower() or "CORR" in contract or "correlation" in contract.lower()


def test_contract_q4_requires_intersection():
    req = extract_question_requirements(Q4)
    contract = format_semantic_requirement_contract(req)
    assert "INTERSECTION" in contract or "intersection" in contract.lower()


def test_q1_profit_only_fails_precheck_sales_and_city_pass():
    bad = "SELECT city, SUM(profit) AS total_profit FROM t GROUP BY city"
    ok, missing = check_requirement_coverage(Q1, bad, ["city", "total_profit"])
    assert ok is False
    assert any("sales" in m.lower() for m in missing)

    good = """
    SELECT city, SUM(sales_amount) AS total_sales, SUM(profit) AS total_profit,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY city
    """
    ok2, miss2 = check_requirement_coverage(
        Q1, good, ["city", "total_sales", "total_profit", "profit_margin"]
    )
    assert ok2 is True, miss2


def test_q2_global_corr_fails_category_query_passes():
    bad = "SELECT corr(discount_rate, profit) AS correlation FROM t"
    ok, missing = check_requirement_coverage(Q2, bad, ["correlation"])
    assert ok is False

    good = """
    SELECT category,
           AVG(discount_rate) AS avg_discount_rate,
           SUM(sales_amount) AS total_sales,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY category
    """
    ok2, miss2 = check_requirement_coverage(
        Q2, good, ["category", "avg_discount_rate", "total_sales", "profit_margin"]
    )
    assert ok2 is True, miss2


def test_q3_segment_full_metrics_pass():
    good = """
    SELECT customer_segment,
           SUM(sales_amount) AS total_sales,
           SUM(profit) AS total_profit,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY customer_segment
    """
    ok, missing = check_requirement_coverage(
        Q3, good, ["customer_segment", "total_sales", "total_profit", "profit_margin"]
    )
    assert ok is True, missing


def test_q4_dual_rank_intersection_pass_single_rank_fail():
    bad = """
    SELECT category, total_sales, sales_rank FROM (
      SELECT category, SUM(sales_amount) AS total_sales,
             RANK() OVER (ORDER BY SUM(sales_amount) DESC) AS sales_rank
      FROM t GROUP BY category
    ) s WHERE sales_rank <= 3
    """
    ok, missing = check_requirement_coverage(Q4, bad, ["category", "total_sales", "sales_rank"])
    assert ok is False

    good = """
    WITH ranked AS (
      SELECT category,
             SUM(sales_amount) AS total_sales,
             SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin,
             RANK() OVER (ORDER BY SUM(sales_amount) DESC) AS sales_rank,
             RANK() OVER (ORDER BY SUM(profit)/NULLIF(SUM(sales_amount),0) ASC) AS margin_rank
      FROM t GROUP BY category
    )
    SELECT * FROM ranked WHERE sales_rank <= 3 AND margin_rank <= 3
    """
    ok2, miss2 = check_requirement_coverage(
        Q4, good, ["category", "total_sales", "profit_margin", "sales_rank", "margin_rank"]
    )
    assert ok2 is True, miss2


def test_code_generator_rejects_global_correlation_after_precheck():
    bad_sql = "SELECT corr(discount_rate, profit) AS correlation FROM t"
    state = _base_state(Q2)

    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.agents.nodes.code_generator.invoke_llm",
        return_value={
            "content": bad_sql,
            "provider": "mock",
            "model": "mock",
            "analysis_source": "groq",
        },
    ):
        result = code_generator_node(state)

    assert result["generated_code"] == ""
    assert result["failure_summary"]["failure_type"] == "semantic_incomplete"
    assert result["analysis_artifacts"].get("generation_precheck_ok") is False
    assert "SEMANTIC REQUIREMENTS" in result["analysis_artifacts"].get(
        "requirement_contract", ""
    )
    assert "category" in result["analysis_artifacts"]["requirement_contract"]


def test_code_generator_accepts_category_level_discount_margin_sql():
    good_sql = """
    SELECT category,
           AVG(discount_rate) AS avg_discount_rate,
           SUM(sales_amount) AS total_sales,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM test_ds GROUP BY category
    """
    state = _base_state(Q2)

    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.agents.nodes.code_generator.invoke_llm",
        return_value={
            "content": good_sql,
            "provider": "mock",
            "model": "mock",
            "analysis_source": "groq",
        },
    ):
        result = code_generator_node(state)

    assert result.get("failure_summary") is None
    assert "GROUP BY category" in result["generated_code"]
    assert result["analysis_artifacts"].get("generation_precheck_ok") is True


def test_code_generator_regen_can_fix_incomplete_sql():
    bad_sql = "SELECT city, SUM(profit) AS total_profit FROM test_ds GROUP BY city"
    good_sql = """
    SELECT city,
           SUM(sales_amount) AS total_sales,
           SUM(profit) AS total_profit,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM test_ds GROUP BY city
    """
    state = _base_state(Q1)
    calls = {"n": 0}

    def fake_invoke(messages, temperature=0.0):
        calls["n"] += 1
        content = bad_sql if calls["n"] == 1 else good_sql
        return {
            "content": content,
            "provider": "mock",
            "model": "mock",
            "analysis_source": "groq",
        }

    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.agents.nodes.code_generator.invoke_llm",
        side_effect=fake_invoke,
    ):
        result = code_generator_node(state)

    assert calls["n"] == 2
    assert result.get("failure_summary") is None
    assert "total_sales" in result["generated_code"].lower()
    assert result["analysis_artifacts"].get("generation_precheck_ok") is True


def test_validator_preserves_generation_semantic_incomplete():
    from backend.agents.nodes.validator import validator_node

    state = {
        "question": Q2,
        "plan": {"approach": "sql", "steps": []},
        "generated_code": "",
        "execution_success": False,
        "output_summary": {"error": "No code was generated."},
        "expected_output_type": "dataframe",
        "failure_summary": {
            "failure_type": "semantic_incomplete",
            "error_message": "Missing required category-level grouping.",
            "code_context": "SELECT corr(discount_rate, profit) FROM t",
            "expected_vs_actual": "semantic_incomplete. Missing requirements: ['category']",
        },
        "retry_count": 0,
        "execution_metadata": [],
        "analysis_artifacts": {},
    }
    val = validator_node(state)
    assert val["validation_passed"] is False
    assert val["failure_summary"]["failure_type"] == "semantic_incomplete"
