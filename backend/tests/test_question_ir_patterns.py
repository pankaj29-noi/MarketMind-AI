"""Tests for question IR and SQL pattern fast-path."""
from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from backend.services.question_ir import build_question_ir
from backend.services.sql.sql_pattern_library import (
    detect_patterns,
    try_simple_deterministic_sql,
)
from backend.services.session_manager import session_manager
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.agents.nodes.reflection import reflection_node


class TestQuestionIR(unittest.TestCase):
    def test_builds_structured_ir(self):
        ir = build_question_ir(
            "Show the top 5 regions by revenue in 2025 and compare them with 2024."
        )
        self.assertIn(ir.complexity, ("MEDIUM", "COMPLEX", "VERY_COMPLEX"))
        self.assertTrue(ir.intent)
        self.assertIsInstance(ir.requirements, dict)
        self.assertTrue(ir.requirement_ids or ir.requirements)

    def test_profit_without_column_noted(self):
        schema = {
            "columns": [
                {"name": "revenue", "dtype": "number"},
                {"name": "region", "dtype": "string"},
            ]
        }
        ir = build_question_ir("Which supplier had the highest profit?", schema)
        self.assertTrue(
            any("profit" in n.lower() for n in ir.unsupported_notes)
            or ir.concept_to_column.get("profit") is None
        )


class TestSqlPatternLibrary(unittest.TestCase):
    def test_detect_patterns(self):
        hits = detect_patterns("What is the share of total revenue for top suppliers?")
        self.assertIn("PERCENT_OF_TOTAL", hits)

    def test_simple_count_sql(self):
        cols = [{"name": "a", "dtype": "number", "analytical_role": "measure"}]
        hit = try_simple_deterministic_sql("How many rows are in the dataset?", "t1", cols)
        self.assertIsNotNone(hit)
        self.assertIn("COUNT(*)", hit.sql)

    def test_sum_named_column(self):
        cols = [
            {"name": "Data_value", "dtype": "number", "analytical_role": "measure"},
            {"name": "region", "dtype": "string", "analytical_role": "categorical"},
        ]
        hit = try_simple_deterministic_sql("What is the sum of Data_value?", "t1", cols)
        self.assertIsNotNone(hit)
        self.assertIn("SUM", hit.sql)
        self.assertIn("Data_value", hit.sql)

    def test_fast_path_on_real_csv(self):
        sid = f"pat_{uuid.uuid4().hex[:8]}"
        did = "ds_pat"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.csv"
            p.write_text("a,b\n1,x\n2,y\n3,x\n")
            session_manager.register_csv(sid, str(p), did)
            profile = get_or_build_csv_schema_profile(sid, did)
            hit = try_simple_deterministic_sql(
                "How many rows are there?", did, profile["columns"]
            )
            self.assertIsNotNone(hit)
            rows = session_manager.execute_query(sid, hit.sql)
            self.assertEqual(rows[0][list(rows[0].keys())[0]], 3)
            session_manager.evict_session(sid)


class TestOneShotRepair(unittest.TestCase):
    def test_repair_limit_is_one(self):
        state = {
            "validation_passed": False,
            "retry_count": 1,
            "failure_summary": {
                "failure_type": "semantic",
                "error_message": "missing filter",
                "code_context": "",
                "expected_vs_actual": "",
            },
            "retry_history": [],
            "execution_metadata": [],
            "plan": {"approach": "sql"},
        }
        out = reflection_node(state)
        self.assertEqual(out["last_worker_result"]["routing_hint"], "REPORT")
        self.assertTrue(out.get("graceful_failure"))


if __name__ == "__main__":
    unittest.main()
