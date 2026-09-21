"""CSV upload suggestions must be answerable by the production NL→SQL path."""
from __future__ import annotations

import uuid

from backend.marketplace.demo_data import ANALYTICS_DEMO_DATASET_ID, load_analytics_demo
from backend.mcp.data_access import run_query
from backend.services.adaptive_questions.cache import invalidate_session
from backend.services.adaptive_questions.engine import generate_suggested_questions
from backend.services.adaptive_questions.profiler import profile_dataset
from backend.services.adaptive_questions.validator import _resolve_production_sql
from backend.agents.nodes.code_generator import code_generator_node


def test_analytics_csv_suggestions_cross_verify_with_generator():
    sid = f"csv-sug-{uuid.uuid4()}"
    load_analytics_demo(sid)
    invalidate_session(sid)
    result = generate_suggested_questions(
        sid, ANALYTICS_DEMO_DATASET_ID, count=8, refresh=True
    )
    questions = result["questions"]
    assert 5 <= len(questions) <= 10
    assert result.get("generation_version", "").startswith("v5")
    difficulties = {q["difficulty"] for q in questions}
    assert difficulties & {"easy", "medium", "hard"}

    profile = profile_dataset(sid, ANALYTICS_DEMO_DATASET_ID)
    for q in questions:
        text = q["text"]
        prod = _resolve_production_sql(profile, text)
        assert prod, text
        truth = run_query(sid, ANALYTICS_DEMO_DATASET_ID, prod)
        assert truth.get("success"), (text, truth.get("error"))

        out = code_generator_node(
            {
                "session_id": sid,
                "dataset_id": ANALYTICS_DEMO_DATASET_ID,
                "duckdb_table": profile.table,
                "question": text,
                "plan": {
                    "approach": "sql",
                    "steps": ["answer"],
                    "expected_output_type": "chart" if q.get("wants_chart") else "dataframe",
                },
                "schema_profile": profile.to_dict(),
                "retry_count": 0,
                "retry_history": [],
                "execution_metadata": [],
                "analysis_artifacts": {},
            }
        )
        gen = (out.get("generated_code") or "").strip()
        assert gen and not out.get("failure_summary"), (text, out.get("failure_summary"))
        got = run_query(sid, ANALYTICS_DEMO_DATASET_ID, gen)
        assert got.get("success"), (text, got.get("error"))
