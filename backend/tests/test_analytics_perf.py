"""Regression tests for CSV analytics performance helpers."""
from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.services.session_manager import session_manager
from backend.services.analytics_perf import (
    classify_question_complexity,
    get_or_build_csv_schema_profile,
    get_cached_analysis_result,
    put_cached_analysis_result,
    clear_session_analysis_cache,
    make_cache_key,
    truncate_table_rows,
    MAX_REPORT_TABLE_ROWS,
)
from backend.services.sql.sql_quality_validator import validate_sql
from backend.agents.nodes.schema_profiler import schema_profiler_node


def _write_csv(path: Path, rows: int = 100) -> None:
    lines = ["a,b,c\n"]
    for i in range(rows):
        lines.append(f"{i % 5},val{i % 3},{i * 1.5}\n")
    path.write_text("".join(lines))


class TestAnalyticsPerf(unittest.TestCase):
    def test_complexity_classification(self):
        self.assertEqual(
            classify_question_complexity("How many rows are there?"),
            "SIMPLE",
        )
        self.assertIn(
            classify_question_complexity("Show top 5 industries by average Data_value"),
            ("MEDIUM", "COMPLEX", "VERY_COMPLEX"),
        )
        self.assertEqual(
            classify_question_complexity(
                "Find top 10 by revenue share of total, exclude fewer than 5 orders"
            ),
            "VERY_COMPLEX",
        )

    def test_rich_schema_profile_cached_and_no_mcp(self):
        sid = f"t_{uuid.uuid4().hex[:8]}"
        did = "ds_perf"
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "t.csv"
            _write_csv(csv_path, rows=200)
            session_manager.register_csv(sid, str(csv_path), did)

            with patch("backend.mcp.client.invoke_mcp_tool_sync") as mcp:
                p1 = get_or_build_csv_schema_profile(sid, did)
                p2 = get_or_build_csv_schema_profile(sid, did)
                mcp.assert_not_called()

            self.assertTrue(p1.get("rich"))
            self.assertEqual(p1.get("row_count"), 200)
            self.assertEqual(len(p1.get("columns") or []), 3)
            self.assertEqual(p1.get("fingerprint"), p2.get("fingerprint"))
            # Cached object identity on session
            sess = session_manager.get_session(sid)
            self.assertIs(sess.schema_profile_cache[did], p2)
            session_manager.evict_session(sid)

    def test_schema_profiler_node_skips_mcp(self):
        sid = f"t_{uuid.uuid4().hex[:8]}"
        did = "ds_node"
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "t.csv"
            _write_csv(csv_path, rows=50)
            session_manager.register_csv(sid, str(csv_path), did)
            state = {
                "session_id": sid,
                "dataset_id": did,
                "schema_profile": {},
                "retry_count": 0,
                "execution_metadata": [],
            }
            with patch("backend.mcp.client.invoke_mcp_tool_sync") as mcp:
                out = schema_profiler_node(state)
                mcp.assert_not_called()
            self.assertEqual(out["last_worker_result"]["status"], "success")
            self.assertTrue(out["schema_profile"].get("rich"))
            self.assertLess(out["last_worker_result"]["duration_ms"], 2000)
            session_manager.evict_session(sid)

    def test_cache_isolation_across_sessions(self):
        clear_session_analysis_cache("s1")
        clear_session_analysis_cache("s2")
        put_cached_analysis_result("s1", "d1", "fpA", "q1", {"answer": 1})
        put_cached_analysis_result("s2", "d1", "fpA", "q1", {"answer": 2})
        self.assertEqual(
            get_cached_analysis_result("s1", "d1", "fpA", "q1")["answer"], 1
        )
        self.assertEqual(
            get_cached_analysis_result("s2", "d1", "fpA", "q1")["answer"], 2
        )
        # Different fingerprint must miss
        self.assertIsNone(get_cached_analysis_result("s1", "d1", "fpB", "q1"))
        # Different dataset must miss
        self.assertIsNone(get_cached_analysis_result("s1", "d2", "fpA", "q1"))
        clear_session_analysis_cache("s1")
        self.assertIsNone(get_cached_analysis_result("s1", "d1", "fpA", "q1"))
        # s2 untouched
        self.assertEqual(
            get_cached_analysis_result("s2", "d1", "fpA", "q1")["answer"], 2
        )
        clear_session_analysis_cache("s2")

    def test_window_topn_accepted_without_limit(self):
        q = "Show top 5 industries by total Data_value"
        sql = '''
        WITH agg AS (
          SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
          FROM t GROUP BY 1
        )
        SELECT industry, total FROM agg
        QUALIFY RANK() OVER (ORDER BY total DESC) <= 5
        '''
        result = validate_sql(sql, schema={"columns": [{"name": "Series_title_2"}, {"name": "Data_value"}], "dataset_id": "t"}, question=q)
        self.assertTrue(result["is_valid"], result["diagnostics"])
        self.assertFalse(any("Missing LIMIT" in c for c in result["critical_issues"]))

    def test_cache_key_includes_session(self):
        k1 = make_cache_key("a", "d", "f", "Hello World")
        k2 = make_cache_key("b", "d", "f", "Hello World")
        self.assertNotEqual(k1, k2)

    def test_truncate_table_rows(self):
        rows = [[i] for i in range(MAX_REPORT_TABLE_ROWS + 50)]
        capped, truncated, original = truncate_table_rows(rows)
        self.assertTrue(truncated)
        self.assertEqual(original, MAX_REPORT_TABLE_ROWS + 50)
        self.assertEqual(len(capped), MAX_REPORT_TABLE_ROWS)
        small, truncated2, original2 = truncate_table_rows([[1], [2]])
        self.assertFalse(truncated2)
        self.assertEqual(original2, 2)
        self.assertEqual(small, [[1], [2]])

    def test_schema_profiler_cold_under_2s_on_3k(self):
        """Regression: CSV schema must not take the old ~10s MCP fail path."""
        src = Path(__file__).resolve().parents[2] / "scratch" / "perf_baseline" / "sample_3000.csv"
        if not src.exists():
            self.skipTest("sample_3000.csv missing")
        sid = f"t3k_{uuid.uuid4().hex[:8]}"
        did = "ds_3k"
        session_manager.register_csv(sid, str(src), did)
        state = {
            "session_id": sid,
            "dataset_id": did,
            "schema_profile": {},
            "retry_count": 0,
            "execution_metadata": [],
        }
        with patch("backend.mcp.client.invoke_mcp_tool_sync") as mcp:
            out = schema_profiler_node(state)
            mcp.assert_not_called()
        self.assertTrue(out["schema_profile"].get("rich"))
        self.assertEqual(out["schema_profile"].get("row_count"), 3000)
        self.assertLess(out["last_worker_result"]["duration_ms"], 2000)
        session_manager.evict_session(sid)


if __name__ == "__main__":
    unittest.main()
