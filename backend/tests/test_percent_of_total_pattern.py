"""Regression tests for percent-of-total-over-top-N.

Baseline failure (measured 2026-09-21): "What percentage of total revenue comes from
the top 10 products?" spent 174.9s and 7 LLM calls across one repair attempt and
still returned "Analysis Failed". The denominator must be the overall total, not the
top-N subtotal, which is the classic way this pattern goes silently wrong.
"""
import duckdb
import pytest

from backend.services.sql.sql_pattern_library import (
    resolve_column,
    try_simple_deterministic_sql,
)

DEMO_CSV = "data/marketmind_demo_marketplace_4000.csv"
TABLE = "demo"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    c.execute(f"CREATE VIEW {TABLE} AS SELECT * FROM read_csv_auto('{DEMO_CSV}')")
    return c


@pytest.fixture(scope="module")
def columns(con):
    return [
        {
            "name": name,
            "dtype": "number" if dtype in ("DOUBLE", "BIGINT") else "string",
            "analytical_role": "measure" if dtype in ("DOUBLE", "BIGINT") else "categorical",
        }
        for name, dtype, *_ in con.execute(f"DESCRIBE {TABLE}").fetchall()
    ]


CASES = [
    (
        "What percentage of total revenue comes from the top 10 products?",
        "product_name",
        "revenue",
        10,
    ),
    ("What share of total profit comes from the top 5 suppliers?", "supplier_name", "profit", 5),
    (
        "What percent of total revenue comes from the top 3 customer regions?",
        "customer_region",
        "revenue",
        3,
    ),
]


@pytest.mark.parametrize("question,dim,measure,limit", CASES)
def test_pattern_matches_and_matches_independent_ground_truth(
    con, columns, question, dim, measure, limit
):
    hit = try_simple_deterministic_sql(question, TABLE, columns)
    assert hit is not None, "percent-of-total-over-top-N must be recognised"
    assert hit.pattern_id == "PERCENT_OF_TOTAL_TOP_N"

    top_n_total, overall_total, pct = con.execute(hit.sql).fetchone()

    # Ground truth written independently of the generated SQL.
    truth = con.execute(
        f"""
        WITH g AS (
            SELECT "{dim}" d, SUM("{measure}") s FROM {TABLE}
            WHERE "{measure}" IS NOT NULL GROUP BY 1
        ), t AS (SELECT s FROM g ORDER BY s DESC LIMIT {limit})
        SELECT ROUND(100.0 * (SELECT SUM(s) FROM t) / (SELECT SUM(s) FROM g), 2)
        """
    ).fetchone()[0]

    assert pct == pytest.approx(truth, abs=0.01)
    assert 0 <= pct <= 100


@pytest.mark.parametrize("question,dim,measure,limit", CASES)
def test_denominator_is_the_overall_total_not_the_top_n_subtotal(
    con, columns, question, dim, measure, limit
):
    hit = try_simple_deterministic_sql(question, TABLE, columns)
    top_n_total, overall_total, pct = con.execute(hit.sql).fetchone()

    full_total = con.execute(
        f'SELECT SUM("{measure}") FROM {TABLE} WHERE "{measure}" IS NOT NULL'
    ).fetchone()[0]

    assert overall_total == pytest.approx(full_total, rel=1e-9)
    assert top_n_total < overall_total, "a top-N subtotal equal to the total means no ranking ran"


def test_pattern_sql_is_read_only(columns):
    hit = try_simple_deterministic_sql(CASES[0][0], TABLE, columns)
    lowered = hit.sql.lower()
    for forbidden in ("insert", "update", "delete", "drop", "alter", "attach", "copy", "truncate"):
        assert forbidden not in lowered


def test_validation_rules_declare_the_denominator_contract(columns):
    hit = try_simple_deterministic_sql(CASES[0][0], TABLE, columns)
    assert "percent_bounds_0_100" in hit.validation_rules
    assert "denominator:overall_total" in hit.validation_rules


def test_plain_total_question_still_uses_the_simple_sum_pattern(columns):
    hit = try_simple_deterministic_sql("What is the total revenue?", TABLE, columns)
    assert hit.pattern_id == "SUM"


def test_percent_question_without_top_n_does_not_use_this_pattern(columns):
    hit = try_simple_deterministic_sql("What percentage of orders are delivered?", TABLE, columns)
    assert hit is None or hit.pattern_id != "PERCENT_OF_TOTAL_TOP_N"


# ── Column resolution ────────────────────────────────────────────────────────


def test_entity_label_column_wins_over_attribute_columns():
    candidates = ["product_id", "product_name", "product_category", "product_subcategory"]
    assert resolve_column("top 10 products by revenue", candidates) == "product_name"


def test_plural_and_singular_both_resolve():
    candidates = ["supplier_name", "supplier_region"]
    assert resolve_column("top 5 suppliers", candidates) == "supplier_name"
    assert resolve_column("top 5 supplier", candidates) == "supplier_name"


def test_exact_multiword_column_is_preferred():
    candidates = ["customer_region", "supplier_region"]
    assert resolve_column("revenue by customer region", candidates) == "customer_region"


def test_unmatched_concept_resolves_to_nothing_rather_than_guessing():
    candidates = ["product_name", "supplier_name"]
    assert resolve_column("what is the weather", candidates) is None


def test_genuinely_ambiguous_reference_returns_none():
    """'region' matches two columns equally well; guessing one would be wrong."""
    assert resolve_column("top 3 regions by revenue", ["customer_region", "supplier_region"]) is None


# ── Requirement coverage must reject a ranking offered as a percentage ───────


def test_coverage_rejects_a_ranking_when_a_percentage_was_asked():
    """The observed regression: a top-10 list was returned with High confidence."""
    from backend.services.requirement_coverage import check_requirement_coverage

    ok, missing = check_requirement_coverage(
        "What percentage of total revenue comes from the top 10 products?",
        "SELECT product_name AS product, SUM(revenue) AS sum_sales FROM demo "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
        ["product", "sum_sales"],
    )
    assert ok is False
    assert any("percent of total missing" in m for m in missing)


def test_coverage_accepts_a_genuine_proportion():
    from backend.services.requirement_coverage import check_requirement_coverage

    ok, missing = check_requirement_coverage(
        "What percentage of total revenue comes from the top 10 products?",
        "WITH grouped AS (SELECT product_name AS dim, SUM(revenue) AS group_total FROM demo GROUP BY 1), "
        "ranked AS (SELECT dim, group_total, ROW_NUMBER() OVER (ORDER BY group_total DESC) rn FROM grouped) "
        "SELECT SUM(CASE WHEN rn<=10 THEN group_total ELSE 0 END) AS top_10_total, "
        "SUM(group_total) AS overall_total, "
        "ROUND(100.0*SUM(CASE WHEN rn<=10 THEN group_total ELSE 0 END)/NULLIF(SUM(group_total),0),2) AS pct_of_total "
        "FROM ranked",
        ["top_10_total", "overall_total", "pct_of_total"],
    )
    assert ok is True, missing


def test_plain_ranking_question_is_unaffected_by_the_percent_gate():
    from backend.services.requirement_coverage import check_requirement_coverage

    ok, _ = check_requirement_coverage(
        "Top 10 products by revenue",
        "SELECT product_name AS product, SUM(revenue) AS sum_sales FROM demo "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
        ["product", "sum_sales"],
    )
    assert ok is True


# ── End-to-end through the real pipeline ─────────────────────────────────────


def test_percent_question_answers_with_a_proportion_end_to_end(con):
    """Guards the wiring: the deterministic fallback must pick the precise pattern."""
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        with open(DEMO_CSV, "rb") as fh:
            upload = client.post("/upload", files={"file": ("demo.csv", fh, "text/csv")}).json()
        response = client.post(
            "/analyze",
            json={
                "session_id": upload["session_id"],
                "question": "What percentage of total revenue comes from the top 10 products?",
            },
        ).json()

    tables = (response.get("report") or {}).get("tables") or []
    assert tables, "the pipeline must return a result table"
    columns = [c.lower() for c in (tables[0].get("columns") or [])]
    assert any("pct" in c or "percent" in c for c in columns), (
        f"a percentage question must return a proportion column, got {columns}"
    )

    row = tables[0]["rows"][0]
    pct = row[columns.index("pct_of_total")]
    truth = con.execute(
        """
        WITH g AS (
            SELECT product_name d, SUM(revenue) s FROM demo WHERE revenue IS NOT NULL GROUP BY 1
        ), t AS (SELECT s FROM g ORDER BY s DESC LIMIT 10)
        SELECT ROUND(100.0 * (SELECT SUM(s) FROM t) / (SELECT SUM(s) FROM g), 2)
        """
    ).fetchone()[0]
    assert pct == pytest.approx(truth, abs=0.01)
