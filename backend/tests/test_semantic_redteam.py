"""
STEP 6 — Semantic red-team tests (deterministic; no live LLM / API keys).

Classifies and guards remaining semantic failure modes across extraction,
coverage, fallback SQL, report grounding, and metadata/confidence.
"""
from __future__ import annotations

import csv
import tempfile
import uuid
from pathlib import Path

import pytest

from backend.mcp.data_access import run_query
from backend.services.analytics_fallback import (
    ANALYSIS_SOURCE_FALLBACK,
    resolve_analytics_fallback,
)
from backend.services.requirement_coverage import (
    check_requirement_coverage,
    confidence_from_coverage,
    extract_question_requirements,
)
from backend.services.reporting.report_grounding import check_report_grounding
from backend.services.session_manager import session_manager


SCHEMA_COLS = [
    "order_id",
    "order_date",
    "customer_id",
    "customer_segment",
    "product",
    "category",
    "quantity",
    "unit_price",
    "discount_rate",
    "sales_amount",
    "profit",
    "city",
    "region",
    "sales_channel",
    "payment_method",
]


def _schema(dataset_id: str = "ds"):
    return {
        "dataset_id": dataset_id,
        "columns": [{"name": c, "dtype": "VARCHAR"} for c in SCHEMA_COLS],
        "multi_table": False,
    }


# ── A. Multi-metric ─────────────────────────────────────────────────────────


def test_A1_city_sales_profit_margin_not_profit_only():
    q = (
        "Which city generates high sales but relatively low profit? "
        "Calculate total sales, total profit, and profit margin."
    )
    bad_ok, _ = check_requirement_coverage(
        q,
        "SELECT city, SUM(profit) AS total_profit FROM t GROUP BY city",
        ["city", "total_profit"],
    )
    assert bad_ok is False

    good_sql = """
    SELECT city, SUM(sales_amount) AS total_sales, SUM(profit) AS total_profit,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY city
    """
    ok, missing = check_requirement_coverage(
        q, good_sql, ["city", "total_sales", "total_profit", "profit_margin"]
    )
    assert ok is True, missing


def test_A2_segment_profit_vs_profit_margin():
    q = "Which customer segment has the highest sales but the lowest profit margin?"
    req = extract_question_requirements(q)
    assert "segment" in req.dimensions
    assert "profit_margin" in req.derived_metrics
    assert "profit_margin" not in req.metrics
    assert "profit" in req.metrics


# ── B. Dimension-specific relationships ─────────────────────────────────────


def test_B1_global_corr_fails_category_level_passes():
    q = (
        "Analyze the relationship between discount rate and profitability across "
        "product categories. Identify the category where higher discounts are "
        "associated with lower profit margins, and compare its sales volume with "
        "other categories."
    )
    ok_bad, _ = check_requirement_coverage(
        q, "SELECT corr(discount_rate, profit) AS c FROM t", ["c"]
    )
    assert ok_bad is False

    ok, missing = check_requirement_coverage(
        q,
        """
        SELECT category, AVG(discount_rate) AS avg_discount_rate,
               SUM(sales_amount) AS total_sales,
               SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
        FROM t GROUP BY category
        """,
        ["category", "avg_discount_rate", "total_sales", "profit_margin"],
        row_count=5,
    )
    assert ok is True, missing


# ── C. Rank intersection ────────────────────────────────────────────────────


def test_C1_limit3_fails_dual_rank_passes():
    q = "Identify categories that rank in the top 3 by sales but bottom 3 by profit margin."
    ok_bad, _ = check_requirement_coverage(
        q,
        "SELECT category, SUM(sales_amount) AS total_sales FROM t "
        "GROUP BY category ORDER BY total_sales DESC LIMIT 3",
        ["category", "total_sales"],
    )
    assert ok_bad is False

    ok, missing = check_requirement_coverage(
        q,
        """
        WITH ranked AS (
          SELECT category,
                 SUM(sales_amount) AS total_sales,
                 SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin,
                 RANK() OVER (ORDER BY SUM(sales_amount) DESC) AS sales_rank,
                 RANK() OVER (ORDER BY SUM(profit)/NULLIF(SUM(sales_amount),0) ASC) AS margin_rank
          FROM t GROUP BY category
        )
        SELECT * FROM ranked WHERE sales_rank <= 3 AND margin_rank <= 3
        """,
        ["category", "total_sales", "profit_margin", "sales_rank", "margin_rank"],
    )
    assert ok is True, missing


# ── D. Comparative ──────────────────────────────────────────────────────────


def test_D_channel_and_region_comparison_coverage():
    q1 = (
        "Which region should the company prioritize if it has high sales but "
        "weak profitability compared with other regions?"
    )
    req1 = extract_question_requirements(q1)
    assert "region" in req1.dimensions
    assert "prioritization_recommendation" in req1.requested_conclusions

    q2 = "Which sales channel has strong revenue but below-average profit margin?"
    sql = """
    SELECT sales_channel AS channel, SUM(sales_amount) AS total_sales,
           SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin
    FROM t GROUP BY sales_channel
    """
    ok, missing = check_requirement_coverage(
        q2, sql, ["channel", "total_sales", "profit_margin"]
    )
    assert ok is True, missing


# ── E. Time / trend ─────────────────────────────────────────────────────────


def test_E_month_not_product_fallback_and_time_coverage():
    q = "Which month had the highest sales?"
    fb = resolve_analytics_fallback(q, _schema(), "ds")
    assert fb.reason == "answerable"
    assert "order_date" in (fb.sql or "").lower() or "period" in (fb.sql or "").lower()
    assert "group by product" not in (fb.sql or "").lower()
    ok, missing = check_requirement_coverage(q, fb.sql, None)
    assert ok is True, missing


def test_E_profit_margin_over_time_fallback():
    q = "How did profit margin change over time?"
    fb = resolve_analytics_fallback(q, _schema(), "ds")
    assert fb.sql
    assert "profit_margin" in fb.sql.lower()
    assert "period" in fb.sql.lower()


# ── F. Filter + aggregation ─────────────────────────────────────────────────


def test_F_delhi_corporate_online_filters_in_fallback_sql():
    cases = [
        (
            "Which category generated the highest sales in Delhi?",
            "delhi",
            "category",
        ),
        (
            "Among Corporate customers, which product has the highest profit margin?",
            "corporate",
            "profit_margin",
        ),
        (
            "Which region had the highest sales through the Online channel?",
            "online",
            "region",
        ),
    ]
    for q, token, must_have in cases:
        req = extract_question_requirements(q)
        assert req.filters, q
        fb = resolve_analytics_fallback(q, _schema(), "ds")
        assert fb.sql, q
        assert token in fb.sql.lower(), (q, fb.sql)
        assert must_have in fb.sql.lower(), (q, fb.sql)
        ok, missing = check_requirement_coverage(q, fb.sql, None)
        assert ok is True, (q, missing)


def test_F_missing_filter_fails_coverage():
    q = "Which category generated the highest sales in Delhi?"
    ok, missing = check_requirement_coverage(
        q,
        "SELECT category, SUM(sales_amount) AS total_sales FROM t GROUP BY category",
        ["category", "total_sales"],
    )
    assert ok is False
    assert any("filter" in m.lower() and "delhi" in m.lower() for m in missing)


# ── G. Unsupported predictive / causal ─────────────────────────────────────


@pytest.mark.parametrize(
    "q",
    [
        "What caused profit to decline?",
        "Predict next month's sales.",
        "Which category will become unprofitable next year?",
    ],
)
def test_G_unsupported_predictive_causal(q):
    req = extract_question_requirements(q)
    assert "unsupported_predictive_or_causal" in req.requested_conclusions
    fb = resolve_analytics_fallback(q, _schema(), "ds")
    assert fb.sql is None
    assert fb.reason.startswith("unsupported")
    # Descriptive SQL must not pass coverage for predictive/causal asks
    ok, missing = check_requirement_coverage(
        q,
        "SELECT category, SUM(sales_amount) AS total_sales FROM t GROUP BY category",
        ["category", "total_sales"],
    )
    assert ok is False
    assert any("unsupported" in m.lower() for m in missing)
    assert confidence_from_coverage(coverage_ok=False, missing=missing) == "Low"


# ── I. Practical significance grounding ─────────────────────────────────────


def test_I_practical_significance_not_exaggerated():
    q = (
        "Although Consumer has the lowest margin, the differences appear very small. "
        "Is this practically significant?"
    )
    cols = ["customer_segment", "profit_margin"]
    rows = [
        {"customer_segment": "Consumer", "profit_margin": 0.2848},
        {"customer_segment": "Corporate", "profit_margin": 0.2850},
        {"customer_segment": "Small Business", "profit_margin": 0.2852},
    ]
    ok, issues = check_report_grounding(
        report_text="Consumer has a dramatically severe profitability crisis.",
        result_columns=cols,
        result_rows=rows,
        coverage_ok=True,
        question=q,
    )
    assert ok is False


# ── J. Adversarial paraphrasing ─────────────────────────────────────────────


def test_J_strongest_weakest_paraphrase_keeps_contrast():
    q = "Which city has the strongest revenue but the weakest profitability?"
    req = extract_question_requirements(q)
    assert "city" in req.dimensions
    assert "sales" in req.metrics
    assert "profit_margin" in req.derived_metrics
    assert "high_sales_low_profit" in req.comparisons or "profit_margin" in req.derived_metrics


# ── Metadata / confidence ───────────────────────────────────────────────────


def test_metadata_fallback_source_and_confidence_rules():
    q = "Which city generates high sales but relatively low profit?"
    fb = resolve_analytics_fallback(q, _schema(), "ds")
    assert fb.analysis_source == ANALYSIS_SOURCE_FALLBACK
    assert fb.analysis_source != "groq"
    ok, missing = check_requirement_coverage(q, fb.sql, None)
    assert ok is True, missing
    assert (
        confidence_from_coverage(
            coverage_ok=True, missing=[], analysis_source=ANALYSIS_SOURCE_FALLBACK
        )
        == "High"
    )
    assert (
        confidence_from_coverage(
            coverage_ok=False, missing=["x"], execution_success=True
        )
        == "Low"
    )


# ── Execute fallback SQL on a mini CSV + optional 15k dataset ───────────────


@pytest.fixture()
def csv_session():
    sid = f"redteam-{uuid.uuid4()}"
    dataset_id = f"upload_{uuid.uuid4().hex[:8]}"
    rows = [
        ["o1", "2024-01-15", "c1", "Corporate", "Widget A", "Electronics", "2", "10", "0.1", "500", "120", "Delhi", "North", "Online", "Card"],
        ["o2", "2024-02-20", "c2", "Consumer", "Widget B", "Furniture", "1", "20", "0.2", "200", "40", "Mumbai", "West", "Retail", "Cash"],
        ["o3", "2024-03-10", "c3", "Corporate", "Gadget X", "Electronics", "5", "30", "0.3", "900", "90", "Delhi", "North", "Online", "Card"],
        ["o4", "2024-04-18", "c1", "Corporate", "Widget A", "Electronics", "3", "10", "0.15", "750", "50", "Delhi", "North", "Online", "UPI"],
        ["o5", "2024-05-05", "c4", "Consumer", "Gadget Y", "Furniture", "1", "40", "0.05", "150", "45", "Jaipur", "West", "Partner", "Card"],
        ["o6", "2024-06-22", "c2", "Small Business", "Widget C", "Office", "10", "12", "0.25", "1200", "200", "Pune", "West", "Online", "Card"],
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{dataset_id}.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(SCHEMA_COLS)
            w.writerows(rows)
        session_manager.register_csv(sid, str(path), dataset_id)
        yield sid, dataset_id


def test_execute_redteam_fallback_sql(csv_session):
    sid, dataset_id = csv_session
    schema = _schema(dataset_id)
    questions = [
        "Which month had the highest sales?",
        "Which category generated the highest sales in Delhi?",
        "Among Corporate customers, which product has the highest profit margin?",
        "Which region had the highest sales through the Online channel?",
        "Identify categories that rank in the top 3 by sales but bottom 3 by profit margin.",
        "Analyze the relationship between discount rate and profitability across product categories.",
    ]
    for q in questions:
        fb = resolve_analytics_fallback(q, schema, dataset_id)
        assert fb.sql, q
        out = run_query(sid, dataset_id, fb.sql)
        assert out.get("success") is True, (q, out.get("error"))
        ok, missing = check_requirement_coverage(q, fb.sql, out.get("columns") or [])
        assert ok is True, (q, missing)


def test_H_followup_graceful_without_memory_architecture():
    """Conversational memory is not a STEP 6 feature; ensure we do not invent context."""
    # Standalone follow-up without prior state must still extract what it can
    q = "Compare it with the best-performing segment."
    req = extract_question_requirements(q)
    # Should not hallucinate a concrete segment filter from "it"
    assert not any(f.startswith("segment=") for f in req.filters)
