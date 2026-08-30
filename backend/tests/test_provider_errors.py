import pytest
from backend.agents.nodes.code_generator import code_generator_node
from backend.agents.nodes.validator import validator_node
from backend.agents.nodes.reflection import reflection_node
from backend.services.requirement_coverage import check_requirement_coverage
from unittest.mock import patch, MagicMock


def test_provider_429_skips_retries():
    """Provider failure on SQL → try fallback; weather → unsupported (no retry loop)."""
    state = {
        "plan": {"approach": "sql", "steps": []},
        "retry_count": 0,
        "question": "What is the weather in Jaipur?",
        "schema_profile": {
            "columns": [
                {"name": "order_id", "dtype": "VARCHAR"},
                {"name": "sales_amount", "dtype": "DOUBLE"},
            ]
        },
        "dataset_id": "test_dataset",
    }

    with patch("backend.agents.nodes.code_generator.use_analytics_demo_fallback", return_value=False), \
         patch("backend.agents.nodes.code_generator.invoke_llm") as mock_inv:
        mock_inv.side_effect = RuntimeError("All LLM providers failed: groq:HTTP 429 Resource Exhausted")
        cg_res = code_generator_node(state)

    assert cg_res["generated_code"] == ""
    assert "failure_summary" in cg_res
    assert cg_res["failure_summary"]["failure_type"] == "unsupported_question"
    assert "GROQ" not in (cg_res["failure_summary"]["error_message"] or "").upper()

    state.update(cg_res)
    state["execution_success"] = False

    val_res = validator_node(state)
    assert not val_res["validation_passed"]
    assert val_res["failure_summary"]["failure_type"] == "unsupported_question"

    state.update(val_res)

    ref_res = reflection_node(state)
    assert ref_res["graceful_failure"] is True
    assert ref_res["last_worker_result"]["routing_hint"] == "REPORT"


def test_provider_429_python_still_provider_error():
    """Non-SQL approach cannot use SQL fallback → provider_error + skip retries."""
    state = {
        "plan": {"approach": "python", "steps": []},
        "retry_count": 0,
        "question": "plot sales",
        "schema_profile": {},
        "dataset_id": "test_dataset",
    }

    with patch("backend.agents.nodes.code_generator.use_analytics_demo_fallback", return_value=False), \
         patch("backend.agents.nodes.code_generator.invoke_llm") as mock_inv:
        mock_inv.side_effect = RuntimeError("All LLM providers failed: groq:HTTP 429 Resource Exhausted")
        cg_res = code_generator_node(state)

    assert cg_res["failure_summary"]["failure_type"] == "provider_error"

    state.update(cg_res)
    state["execution_success"] = False
    val_res = validator_node(state)
    state.update(val_res)
    ref_res = reflection_node(state)
    assert ref_res["graceful_failure"] is True
    assert ref_res["last_worker_result"]["routing_hint"] == "REPORT"


def test_invalid_sql_retries_normally():
    state = {
        "plan": {"approach": "sql"},
        "retry_count": 0,
        "generated_code": "SELECT * FROM t",
        "execution_success": False,
        "output_summary": {"error": "syntax error"},
        "expected_output_type": "dataframe"
    }

    val_res = validator_node(state)
    assert val_res["failure_summary"]["failure_type"] in ["runtime", "timeout"]

    state.update(val_res)
    ref_res = reflection_node(state)
    assert ref_res["graceful_failure"] is False
    assert ref_res["retry_count"] == 1
    assert ref_res["last_worker_result"]["routing_hint"] == "SQL"


def test_python_execution_failure_retries_normally():
    state = {
        "plan": {"approach": "python"},
        "retry_count": 0,
        "generated_code": "print(1/0)",
        "execution_success": False,
        "output_summary": {"error": "ZeroDivisionError"},
        "expected_output_type": "dataframe"
    }

    val_res = validator_node(state)
    assert val_res["failure_summary"]["failure_type"] in ["runtime", "timeout"]

    state.update(val_res)
    ref_res = reflection_node(state)
    assert ref_res["graceful_failure"] is False
    assert ref_res["retry_count"] == 1
    assert ref_res["last_worker_result"]["routing_hint"] == "PYTHON_ANALYSIS"


def test_coverage_rejects_profit_only_for_sales_profit_question():
    q = "Which city generates high sales but relatively low profit?"
    ok, missing = check_requirement_coverage(
        q,
        'SELECT city, SUM(profit) AS total_profit FROM t GROUP BY city',
        ["city", "total_profit"],
    )
    assert ok is False
    assert any("sales" in m.lower() for m in missing)


def test_coverage_accepts_sales_and_profit():
    q = "Which city generates high sales but relatively low profit?"
    ok, missing = check_requirement_coverage(
        q,
        """
        SELECT city, SUM(sales_amount) AS total_sales, SUM(profit) AS total_profit,
               SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
        FROM t GROUP BY city
        """,
        ["city", "total_sales", "total_profit", "profit_margin"],
    )
    assert ok is True
    assert missing == []


def test_validator_marks_semantic_incomplete_on_global_correlation():
    """Executed-but-incomplete SQL must fail validation as semantic_incomplete."""
    q = (
        "Analyze the relationship between discount rate and profitability across "
        "product categories. Identify the category where higher discounts are "
        "associated with lower profit margins, and compare its sales volume with "
        "other categories."
    )
    state = {
        "question": q,
        "plan": {"approach": "sql", "steps": ["correlate discount and profit"]},
        "generated_code": "SELECT corr(discount_rate, profit) AS correlation FROM t",
        "execution_success": True,
        "expected_output_type": "dataframe",
        "output_summary": {
            "columns": ["correlation"],
            "row_count": 1,
            "preview": [{"correlation": -0.2}],
        },
        "retry_count": 0,
        "execution_metadata": [],
        "analysis_artifacts": {},
    }

    with patch("backend.config.invoke_llm") as mock_inv:
        # Coverage gate must reject before LLM is needed; if called, force pass
        mock_inv.return_value = {"content": '{"answers_question": true, "confidence_score": "High", "reason": "ok", "checks": {}, "suggested_retry_target": "none", "suggested_retry_strategy": ""}'}
        val_res = validator_node(state)

    assert val_res["validation_passed"] is False
    assert val_res["failure_summary"]["failure_type"] == "semantic_incomplete"
    assert "semantic_incomplete" in (val_res["failure_summary"]["error_message"] or "")
    assert val_res["analysis_artifacts"].get("coverage_ok") is False
