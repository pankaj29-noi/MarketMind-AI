"""Expanded SQLCoder + SQL pipeline audit tests (mocked + validator)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.agents.nodes.code_generator import code_generator_node
from backend.services.sql.sql_quality_validator import (
    find_unknown_column_references,
    validate_sql,
)
from backend.services.sql.sqlcoder_service import (
    ANALYSIS_SOURCE_SQLCODER,
    SQLCoderResult,
    extract_sql_from_completion,
)


SCHEMA = {
    "dataset_id": "sales_ds",
    "columns": [
        {"name": "order_date", "dtype": "VARCHAR", "sample_values": ["2023-01-15"]},
        {"name": "city", "dtype": "VARCHAR"},
        {"name": "category", "dtype": "VARCHAR"},
        {"name": "customer_segment", "dtype": "VARCHAR"},
        {"name": "sales_amount", "dtype": "DOUBLE"},
        {"name": "profit", "dtype": "DOUBLE"},
        {"name": "discount_rate", "dtype": "DOUBLE"},
    ],
}


def _base_state(question: str) -> dict:
    return {
        "question": question,
        "plan": {"approach": "sql", "steps": ["aggregate"]},
        "schema_profile": SCHEMA,
        "dataset_id": "sales_ds",
        "duckdb_table": "sales_ds",
        "retry_count": 0,
        "retry_history": [],
        "execution_metadata": [],
        "analysis_artifacts": {},
    }


def _patch_complex(sql: str | None = None, *, error: str | None = None):
    result = SQLCoderResult(
        sql=sql or "",
        model="mock-gguf",
        error=error,
    )
    return (
        patch(
            "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
            return_value=False,
        ),
        patch(
            "backend.services.analytics_perf.classify_question_complexity",
            return_value="COMPLEX",
        ),
        patch(
            "backend.services.question_ir.build_question_ir",
            return_value=MagicMock(complexity="COMPLEX", to_dict=lambda: {}),
        ),
        patch("backend.services.question_ir.format_ir_for_llm", return_value=""),
        patch(
            "backend.services.sql.sqlcoder_service.should_try_sqlcoder_first",
            return_value=True,
        ),
        patch(
            "backend.services.sql.sqlcoder_service.generate_sql_with_sqlcoder",
            return_value=result,
        ),
    )


# --- Schema hallucination / safety ---


def test_rejects_unquoted_hallucinated_column():
    sql = "SELECT revenue FROM sales_ds"
    issues = find_unknown_column_references(sql, SCHEMA)
    assert any("revenue" in i for i in issues)
    assert validate_sql(sql, SCHEMA, "total revenue")["is_valid"] is False


def test_accepts_valid_unquoted_columns_with_alias():
    sql = (
        "SELECT city, SUM(sales_amount) AS total_sales "
        "FROM sales_ds GROUP BY city ORDER BY total_sales DESC"
    )
    assert find_unknown_column_references(sql, SCHEMA) == []
    assert validate_sql(sql, SCHEMA, "sales by city")["is_valid"] is True


def test_rejects_write_sql_safety():
    for sql in (
        "DROP TABLE sales_ds",
        "DELETE FROM sales_ds WHERE city='Austin'",
        "INSERT INTO sales_ds VALUES (1)",
        "COPY sales_ds TO '/tmp/x.csv'",
        "ATTACH 'evil.db'",
    ):
        assert validate_sql(sql, SCHEMA)["is_valid"] is False


def test_malformed_model_output_extracts_empty():
    assert extract_sql_from_completion("I do not know") == ""
    assert extract_sql_from_completion("Sure, here is nothing useful.") == ""
    assert extract_sql_from_completion("```\nnot sql\n```") == ""


def test_code_generator_rejects_hallucinated_sqlcoder_column(monkeypatch):
    monkeypatch.setenv("SQLCODER_ENABLED", "true")
    bad = "SELECT revenue, city FROM sales_ds GROUP BY city"
    good_api = (
        "SELECT city, SUM(sales_amount) AS total_sales "
        "FROM sales_ds GROUP BY city"
    )
    question = "What are total sales by city?"

    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.config.has_valid_llm_api_key",
        return_value=True,
    ), patch(
        "backend.services.analytics_perf.classify_question_complexity",
        return_value="COMPLEX",
    ), patch(
        "backend.services.question_ir.build_question_ir",
        return_value=MagicMock(complexity="COMPLEX", to_dict=lambda: {}),
    ), patch(
        "backend.services.question_ir.format_ir_for_llm",
        return_value="",
    ), patch(
        "backend.services.sql.sqlcoder_service.should_try_sqlcoder_first",
        return_value=True,
    ), patch(
        "backend.services.sql.sqlcoder_service.generate_sql_with_sqlcoder",
        return_value=SQLCoderResult(sql=bad, model="mock"),
    ), patch(
        "backend.agents.nodes.code_generator.invoke_llm",
        return_value={
            "content": good_api,
            "provider": "Groq",
            "model": "mock",
            "analysis_source": "groq",
        },
    ):
        result = code_generator_node(_base_state(question))

    assert result.get("failure_summary") is None
    assert "sales_amount" in result["generated_code"]
    assert "revenue" not in result["generated_code"].lower()
    assert result["analysis_artifacts"]["analysis_source"] == "groq"


def test_code_generator_malformed_sqlcoder_falls_back_to_api(monkeypatch):
    monkeypatch.setenv("SQLCODER_ENABLED", "true")
    good_api = "SELECT SUM(sales_amount) AS total_sales FROM sales_ds"
    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.config.has_valid_llm_api_key",
        return_value=True,
    ), patch(
        "backend.services.analytics_perf.classify_question_complexity",
        return_value="COMPLEX",
    ), patch(
        "backend.services.question_ir.build_question_ir",
        return_value=MagicMock(complexity="COMPLEX", to_dict=lambda: {}),
    ), patch(
        "backend.services.question_ir.format_ir_for_llm",
        return_value="",
    ), patch(
        "backend.services.sql.sqlcoder_service.should_try_sqlcoder_first",
        return_value=True,
    ), patch(
        "backend.services.sql.sqlcoder_service.generate_sql_with_sqlcoder",
        return_value=SQLCoderResult(sql="", model="mock", error="no usable SQL"),
    ), patch(
        "backend.agents.nodes.code_generator.invoke_llm",
        return_value={
            "content": good_api,
            "provider": "Groq",
            "model": "mock",
            "analysis_source": "groq",
        },
    ):
        result = code_generator_node(_base_state("What is total sales?"))

    assert result["generated_code"].strip()
    assert result["analysis_artifacts"]["analysis_source"] == "groq"


def test_unsupported_sqlcoder_idk_falls_back_deterministic(monkeypatch):
    monkeypatch.setenv("SQLCODER_ENABLED", "true")
    from backend.services.analytics_fallback import FallbackResult, ANALYSIS_SOURCE_FALLBACK

    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.config.has_valid_llm_api_key",
        return_value=False,
    ), patch(
        "backend.services.analytics_perf.classify_question_complexity",
        return_value="COMPLEX",
    ), patch(
        "backend.services.question_ir.build_question_ir",
        return_value=MagicMock(complexity="COMPLEX", to_dict=lambda: {}),
    ), patch(
        "backend.services.question_ir.format_ir_for_llm",
        return_value="",
    ), patch(
        "backend.services.sql.sqlcoder_service.should_try_sqlcoder_first",
        return_value=True,
    ), patch(
        "backend.services.sql.sqlcoder_service.generate_sql_with_sqlcoder",
        return_value=SQLCoderResult(sql="", model="mock", error="I do not know"),
    ), patch(
        "backend.services.analytics_fallback.resolve_analytics_fallback",
        return_value=FallbackResult(
            "SELECT SUM(sales_amount) AS total_sales FROM sales_ds",
            "answerable",
            ANALYSIS_SOURCE_FALLBACK,
        ),
    ):
        result = code_generator_node(_base_state("What is total sales?"))

    assert "sales_amount" in result["generated_code"]
    assert result["analysis_artifacts"]["analysis_source"] == ANALYSIS_SOURCE_FALLBACK


# --- Query categories ---

QUERY_CASES = [
    (
        "simple",
        "What is the total sales?",
        "SELECT SUM(sales_amount) AS total_sales FROM sales_ds",
    ),
    (
        "filter",
        "Total sales for Austin",
        "SELECT SUM(sales_amount) AS total_sales FROM sales_ds WHERE city = 'Austin'",
    ),
    (
        "grouping",
        "Total sales by category",
        "SELECT category, SUM(sales_amount) AS total_sales FROM sales_ds GROUP BY category",
    ),
    (
        "sorting",
        "List cities by sales descending",
        (
            "SELECT city, SUM(sales_amount) AS total_sales FROM sales_ds "
            "GROUP BY city ORDER BY total_sales DESC"
        ),
    ),
    (
        "top_n",
        "Top 5 cities by sales",
        (
            "SELECT city, SUM(sales_amount) AS total_sales FROM sales_ds "
            "GROUP BY city ORDER BY total_sales DESC LIMIT 5"
        ),
    ),
    (
        "bottom_n",
        "Bottom 3 categories by profit",
        (
            "SELECT category, SUM(profit) AS total_profit FROM sales_ds "
            "GROUP BY category ORDER BY total_profit ASC LIMIT 3"
        ),
    ),
    (
        "date",
        "Show monthly sales for 2023",
        (
            "SELECT date_trunc('month', strptime(order_date, '%Y-%m-%d')) AS month, "
            "SUM(sales_amount) AS total_sales FROM sales_ds "
            "WHERE strptime(order_date, '%Y-%m-%d') >= DATE '2023-01-01' "
            "AND strptime(order_date, '%Y-%m-%d') < DATE '2024-01-01' "
            "GROUP BY 1 ORDER BY 1"
        ),
    ),
    (
        "ranking",
        "Rank cities by sales",
        (
            "SELECT city, SUM(sales_amount) AS total_sales, "
            "RANK() OVER (ORDER BY SUM(sales_amount) DESC) AS sales_rank "
            "FROM sales_ds GROUP BY city"
        ),
    ),
    (
        "advanced",
        "Which city generates high sales but relatively low profit?",
        (
            "SELECT city, SUM(sales_amount) AS total_sales, SUM(profit) AS total_profit, "
            "SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin "
            "FROM sales_ds GROUP BY city"
        ),
    ),
    (
        "multi_filter",
        "Sales for Electronics in Austin with discount above 0.1",
        (
            "SELECT city, category, SUM(sales_amount) AS total_sales FROM sales_ds "
            "WHERE category = 'Electronics' AND city = 'Austin' AND discount_rate > 0.1 "
            "GROUP BY city, category"
        ),
    ),
]


@pytest.mark.parametrize("kind,question,sql", QUERY_CASES)
def test_pipeline_query_categories(monkeypatch, kind, question, sql):
    monkeypatch.setenv("SQLCODER_ENABLED", "true")
    assert validate_sql(sql, SCHEMA, question)["is_valid"], kind

    with patch(
        "backend.agents.nodes.code_generator.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.services.analytics_perf.classify_question_complexity",
        return_value="COMPLEX",
    ), patch(
        "backend.services.question_ir.build_question_ir",
        return_value=MagicMock(complexity="COMPLEX", to_dict=lambda: {}),
    ), patch(
        "backend.services.question_ir.format_ir_for_llm",
        return_value="",
    ), patch(
        "backend.services.sql.sqlcoder_service.should_try_sqlcoder_first",
        return_value=True,
    ), patch(
        "backend.services.sql.sqlcoder_service.generate_sql_with_sqlcoder",
        return_value=SQLCoderResult(sql=sql, model="mock-gguf"),
    ), patch(
        "backend.agents.nodes.code_generator.invoke_llm",
    ) as mock_llm:
        result = code_generator_node(_base_state(question))

    assert result.get("failure_summary") is None, f"{kind}: {result.get('failure_summary')}"
    assert result["analysis_artifacts"]["analysis_source"] == ANALYSIS_SOURCE_SQLCODER
    mock_llm.assert_not_called()


def test_sandbox_sets_structural_failure_on_schema_reject():
    from backend.agents.nodes.sandbox_executor import sandbox_executor_node

    state = {
        "session_id": "s1",
        "dataset_id": "sales_ds",
        "plan": {"approach": "sql"},
        "generated_code": "SELECT revenue FROM sales_ds",
        "schema_profile": SCHEMA,
        "question": "total revenue",
        "retry_count": 0,
        "execution_metadata": [],
    }
    out = sandbox_executor_node(state)
    assert out["execution_success"] is False
    assert out["failure_summary"]["failure_type"] == "structural"
    assert "revenue" in (out["failure_summary"]["error_message"] or "").lower() or \
        "Invalid column" in (out["failure_summary"]["error_message"] or "")


def test_should_try_sqlcoder_first_when_no_api(monkeypatch):
    monkeypatch.setenv("SQLCODER_ENABLED", "true")
    monkeypatch.setenv("SQLCODER_PREFER_OVER_API", "false")
    from backend.services.sql import sqlcoder_service as scs

    with patch("backend.config.has_valid_llm_api_key", return_value=False):
        assert scs.should_try_sqlcoder_first() is True
    with patch("backend.config.has_valid_llm_api_key", return_value=True):
        assert scs.should_try_sqlcoder_first() is False
        assert scs.should_try_sqlcoder_as_fallback() is True
