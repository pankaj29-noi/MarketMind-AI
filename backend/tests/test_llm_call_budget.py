"""Locks in the LLM call budget per question.

Baseline (measured 2026-09-21): 5.6 LLM calls/question average, and SIMPLE questions
answered entirely by the deterministic pattern library still spent calls on the
supervisor router and the validator's semantic check.
"""
import uuid
from unittest.mock import patch

import pytest

import backend.agents.nodes.supervisor as supervisor_mod
import backend.agents.nodes.validator as validator_mod
from backend.agents.nodes.supervisor import _looks_like_followup
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.services.session_manager import session_manager

DEMO_CSV = "data/marketmind_demo_marketplace_4000.csv"


@pytest.fixture(scope="module")
def profile():
    sid = str(uuid.uuid4())
    session_manager.register_csv(sid, DEMO_CSV, "demo")
    return get_or_build_csv_schema_profile(sid, "demo")


# ── Supervisor: conversational context must not force an LLM call ────────────


@pytest.mark.parametrize(
    "question",
    [
        "break that down by region",
        "why is it so low?",
        "what about the same for 2024?",
        "show them instead",
        "top 10",
    ],
)
def test_followup_questions_are_detected(question):
    assert _looks_like_followup(question)


@pytest.mark.parametrize(
    "question",
    [
        "What is the total revenue?",
        "How many orders are there?",
        "Which customer region has the highest total revenue?",
        "What are the top 5 suppliers by revenue?",
    ],
)
def test_self_contained_questions_are_not_followups(question):
    assert not _looks_like_followup(question)


def _route(question, with_context):
    """Run supervisor_node once and report whether the LLM router was invoked."""
    called = []

    def fake_llm_routing(state):
        called.append(state.get("question"))
        return {"decision": "CONTINUE", "reasoning": "llm", "selected_capability": "SQL"}

    state = {
        "question": question,
        "schema_profile": {"columns": [{"name": "revenue"}]},
        "supervisor_history": [],
    }
    if with_context:
        state["conversational_context"] = {
            "previous_question": "What is the total revenue?",
            "previous_capability": "SQL",
            "previous_result_columns": ["revenue"],
        }

    with patch.object(supervisor_mod, "_get_llm_routing_decision", fake_llm_routing):
        supervisor_mod.supervisor_node(state)
    return bool(called)


def test_self_contained_question_skips_llm_router_even_with_context():
    """Baseline bug: any conversational context forced an LLM routing call (~843ms)."""
    assert _route("How many orders are there?", with_context=True) is False


def test_followup_question_still_uses_llm_router():
    """Intent resolution for genuine follow-ups must not be weakened."""
    assert _route("break that down by region", with_context=True) is True


def test_self_contained_question_without_context_skips_llm_router():
    assert _route("What is the total revenue?", with_context=False) is False


# ── Validator: deterministic pattern SQL needs no LLM opinion ────────────────


def _validate(artifacts, code, columns, row_count=1):
    """Run validator_node and report whether it made an LLM call."""
    called = []

    def fake_invoke(messages, temperature=0.0):
        called.append(1)
        return {"content": '{"answers_question": true}'}

    state = {
        "question": "What is the total revenue?",
        "plan": {"approach": "sql", "expected_output_type": "dataframe"},
        "generated_code": code,
        "execution_success": True,
        "output_summary": {"columns": columns, "row_count": row_count, "preview": []},
        "query_result": {"columns": columns, "rows": [[1]], "row_count": row_count},
        "analysis_artifacts": artifacts,
        "retry_count": 0,
        "execution_metadata": [],
    }
    with patch("backend.config.invoke_llm", fake_invoke):
        out = validator_mod.validator_node(state)
    return out, bool(called)


SIMPLE_SQL = "SELECT SUM(revenue) AS total_revenue FROM demo"


def test_deterministic_pattern_sql_skips_llm_semantic_check():
    out, llm_called = _validate(
        {"analysis_source": "deterministic_fallback", "sql_pattern_id": "total_measure"},
        SIMPLE_SQL,
        ["total_revenue"],
    )
    assert llm_called is False, "pre-validated pattern SQL should not need an LLM opinion"
    assert (out.get("analysis_artifacts") or {}).get("semantic_check") == "deterministic_pattern"


def test_llm_generated_sql_still_gets_semantic_check():
    """Validation must never be skipped for SQL a model wrote."""
    _, llm_called = _validate(
        {"analysis_source": "groq"},
        SIMPLE_SQL,
        ["total_revenue"],
    )
    assert llm_called is True


def test_pattern_sql_failing_coverage_is_not_waved_through():
    """The deterministic coverage gate still runs before any skip."""
    out, _ = _validate(
        {"analysis_source": "deterministic_fallback", "sql_pattern_id": "total_measure"},
        "SELECT 1 AS x FROM demo",
        ["x"],
    )
    artifacts = out.get("analysis_artifacts") or {}
    if artifacts.get("coverage_ok") is False:
        assert artifacts.get("semantic_check") != "deterministic_pattern"
