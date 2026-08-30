"""STEP 4: planner requirement contract + deterministic plan self-check."""
from unittest.mock import patch
import json

from backend.agents.nodes.planner import planner_node
from backend.services.requirement_coverage import (
    build_requirement_aware_plan_steps,
    check_plan_requirement_coverage,
    extract_question_requirements,
    format_semantic_requirement_contract,
)


Q1 = (
    "Which city generates high sales but relatively low profit, "
    "and what business insight can you derive from this?"
)
Q2 = (
    "Analyze the relationship between discount rate and profitability across "
    "product categories."
)
Q3 = (
    "Which customer segment generates the highest sales but has the lowest "
    "profit margin?"
)
Q4 = "Identify categories that rank in the top 3 by sales but bottom 3 by profit margin."


def test_q1_plan_requires_city_sales_profit_margin_comparison():
    req = extract_question_requirements(Q1)
    bad = ["Calculate total profit", "Return the result"]
    ok, missing = check_plan_requirement_coverage(Q1, bad, req)
    assert ok is False
    assert any("city" in m.lower() or "sales" in m.lower() for m in missing)

    good = [
        "Group and compare records across city",
        "Aggregate total sales / sales_amount per group",
        "Aggregate total profit per group",
        "Calculate profit margin using profit relative to sales",
        "Compare groups to identify high sales with relatively low profit",
        "Return enough metric evidence for the report layer to derive the business conclusion",
    ]
    ok2, miss2 = check_plan_requirement_coverage(Q1, good, req)
    assert ok2 is True, miss2


def test_q2_global_correlation_plan_fails_category_plan_passes():
    req = extract_question_requirements(Q2)
    bad = ["Calculate a global correlation between discount and profit"]
    ok, missing = check_plan_requirement_coverage(Q2, bad, req)
    assert ok is False
    assert any("categor" in m.lower() or "dimension" in m.lower() or "relationship" in m.lower() for m in missing)

    good = [
        "Group and compare records across category",
        "Calculate discount metrics (e.g. average discount_rate) per group",
        "Calculate profit margin using profit relative to sales",
        "Aggregate total sales for comparison",
        "Evaluate the relationship across category-level metrics (not only a global correlation)",
    ]
    ok2, miss2 = check_plan_requirement_coverage(Q2, good, req)
    assert ok2 is True, miss2


def test_q3_plan_requires_segment_sales_profit_margin_ranking():
    req = extract_question_requirements(Q3)
    bad = ["Find the best customer segment by sales"]
    ok, missing = check_plan_requirement_coverage(Q3, bad, req)
    assert ok is False

    good = build_requirement_aware_plan_steps(req)
    ok2, miss2 = check_plan_requirement_coverage(Q3, good, req)
    assert ok2 is True, miss2
    blob = " ".join(good).lower()
    assert "segment" in blob
    assert "sales" in blob
    assert "profit" in blob
    assert "margin" in blob


def test_q4_plan_requires_dual_ranking_intersection():
    req = extract_question_requirements(Q4)
    bad = ["Find the top and bottom categories by performance"]
    ok, missing = check_plan_requirement_coverage(Q4, bad, req)
    assert ok is False
    assert any("rank" in m.lower() or "intersect" in m.lower() or "top" in m.lower() for m in missing)

    good = build_requirement_aware_plan_steps(req)
    ok2, miss2 = check_plan_requirement_coverage(Q4, good, req)
    assert ok2 is True, miss2
    blob = " ".join(good).lower()
    assert "top 3" in blob
    assert "bottom 3" in blob
    assert "intersect" in blob


def test_requirement_aware_steps_pass_all_four_questions():
    for q in (Q1, Q2, Q3, Q4):
        req = extract_question_requirements(q)
        steps = build_requirement_aware_plan_steps(req)
        ok, missing = check_plan_requirement_coverage(q, steps, req)
        assert ok is True, (q, missing)


def test_contract_injected_in_demo_planner():
    state = {
        "question": Q2,
        "schema_profile": {
            "columns": [
                {"name": "category", "dtype": "VARCHAR"},
                {"name": "discount_rate", "dtype": "DOUBLE"},
                {"name": "sales_amount", "dtype": "DOUBLE"},
                {"name": "profit", "dtype": "DOUBLE"},
            ]
        },
        "dataset_id": "t",
        "duckdb_table": "t",
        "retry_count": 0,
        "retry_history": [],
        "execution_metadata": [],
        "analysis_artifacts": {},
    }
    with patch(
        "backend.agents.nodes.planner.use_analytics_demo_fallback",
        return_value=True,
    ):
        out = planner_node(state)

    plan = out["plan"]
    assert plan["approach"] == "sql"
    assert out["analysis_artifacts"]["planning_precheck_ok"] is True
    contract = out["analysis_artifacts"]["requirement_contract"]
    assert "SEMANTIC REQUIREMENTS" in contract
    assert "category" in contract
    steps_blob = " ".join(plan["steps"]).lower()
    assert "categor" in steps_blob
    assert "discount" in steps_blob
    assert "margin" in steps_blob or "profit" in steps_blob


def test_planner_regenerates_then_repairs_incomplete_llm_plan():
    """Incomplete LLM plan is regenerated; still-bad plan is requirement-repaired."""
    bad_plan = {
        "steps": ["Calculate a global correlation between discount and profit"],
        "approach": "sql",
        "expected_output_type": "dataframe",
    }
    # Second response still bad → triggers deterministic repair
    calls = {"n": 0}

    def fake_invoke(messages, temperature=0.1):
        calls["n"] += 1
        return {
            "content": json.dumps(bad_plan),
            "provider": "mock",
            "model": "mock",
        }

    state = {
        "question": Q2,
        "schema_profile": {"columns": [{"name": "category", "dtype": "VARCHAR"}, {"name": "discount_rate", "dtype": "DOUBLE"}]},
        "dataset_id": "t",
        "duckdb_table": "t",
        "retry_count": 0,
        "retry_history": [],
        "execution_metadata": [],
        "analysis_artifacts": {},
    }

    with patch(
        "backend.agents.nodes.planner.use_analytics_demo_fallback",
        return_value=False,
    ), patch(
        "backend.agents.nodes.planner.invoke_llm",
        side_effect=fake_invoke,
    ):
        out = planner_node(state)

    assert calls["n"] >= 2
    ok, missing = check_plan_requirement_coverage(Q2, out["plan"]["steps"])
    assert ok is True, missing
    assert out["analysis_artifacts"].get("planning_precheck_ok") is True
    assert "categor" in " ".join(out["plan"]["steps"]).lower()


def test_format_contract_available_for_planner():
    contract = format_semantic_requirement_contract(extract_question_requirements(Q4))
    assert "top 3" in contract.lower() or "INTERSECTION" in contract
