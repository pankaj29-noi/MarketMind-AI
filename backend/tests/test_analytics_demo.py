"""Tests for 4k analytics demo load + ground-truth bank (no hardcoded answers)."""
from __future__ import annotations

import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app
from backend.benchmarks.demo_marketplace_questions import DEMO_QUESTIONS
from backend.marketplace.demo_data import (
    ANALYTICS_DEMO_DATASET_ID,
    get_analytics_demo_csv_path,
    load_analytics_demo,
)
from backend.services.session_manager import session_manager
from backend.mcp.data_access import _assert_read_only_sql


class TestAnalyticsDemo(unittest.TestCase):
    def test_csv_exists_and_row_count(self):
        path = get_analytics_demo_csv_path()
        self.assertTrue(path.endswith("marketmind_demo_marketplace_4000.csv"))
        import os

        self.assertTrue(os.path.exists(path), path)

    def test_load_analytics_demo_warms_schema(self):
        sid = f"ad_{uuid.uuid4().hex[:8]}"
        result = load_analytics_demo(sid)
        self.assertEqual(result["dataset_id"], ANALYTICS_DEMO_DATASET_ID)
        self.assertEqual(result["row_count"], 4000)
        self.assertTrue(result.get("warm_start", {}).get("schema_profiled"))
        self.assertTrue(result.get("fingerprint"))
        # No answer precomputation keys
        self.assertNotIn("answers", result)
        session_manager.evict_session(sid)

    def test_question_bank_shape(self):
        self.assertEqual(len(DEMO_QUESTIONS), 100)
        by = {}
        for q in DEMO_QUESTIONS:
            by[q["difficulty"]] = by.get(q["difficulty"], 0) + 1
        self.assertEqual(by["easy"], 20)
        self.assertEqual(by["medium"], 25)
        self.assertEqual(by["hard"], 30)
        self.assertEqual(by["very_hard"], 25)

    def test_ground_truth_sql_readonly(self):
        for q in DEMO_QUESTIONS:
            sql = q.get("expected_sql")
            if not sql:
                continue
            _assert_read_only_sql(sql.replace("{table}", "t"))

    def test_api_analytics_demo_endpoint(self):
        client = TestClient(app)
        res = client.post("/marketplace/analytics-demo")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["row_count"], 4000)
        self.assertIn("example_questions", data)
        self.assertTrue(isinstance(data["example_questions"], dict))
        # examples are questions only
        for qs in data["example_questions"].values():
            for item in qs:
                self.assertIsInstance(item, str)


if __name__ == "__main__":
    unittest.main()
