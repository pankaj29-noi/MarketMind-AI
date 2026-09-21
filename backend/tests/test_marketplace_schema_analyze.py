"""Marketplace multi-table schema must validate join SQL (analyze path regression)."""
from __future__ import annotations

import uuid

from backend.marketplace.demo_data import (
    build_marketplace_schema_profile,
    load_marketplace_demo,
)
from backend.marketplace.sql_fallback import EXAMPLE_QUESTIONS, resolve_marketplace_fallback
from backend.services.analytics_perf import get_or_build_csv_schema_profile
from backend.services.requirement_coverage import check_requirement_coverage
from backend.services.sql.sql_quality_validator import validate_sql


def test_marketplace_schema_accepts_example_sql():
    sid = f"mkt-schema-{uuid.uuid4()}"
    load_marketplace_demo(sid)
    profile = build_marketplace_schema_profile(sid)
    assert profile.get("multi_table") is True
    assert len(profile.get("tables") or []) >= 6

    # Logical id must not hit single-table profiler
    via_perf = get_or_build_csv_schema_profile(sid, "marketplace")
    assert via_perf.get("multi_table") is True

    for q in EXAMPLE_QUESTIONS:
        fb = resolve_marketplace_fallback(q)
        assert fb.sql, q
        ok, miss = check_requirement_coverage(q, fb.sql, columns=None)
        vf = validate_sql(fb.sql, profile, q)
        assert ok, (q, miss)
        assert vf.get("is_valid"), (q, vf.get("critical_issues"), vf.get("diagnostics"))
