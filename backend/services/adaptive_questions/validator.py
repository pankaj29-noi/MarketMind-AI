"""Validate candidates: schema refs + production SQL path + DuckDB execution."""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from backend.mcp.data_access import run_query
from backend.services.adaptive_questions.profiler import DatasetProfile
from backend.services.adaptive_questions.templates import QuestionCandidate
from backend.services.sql.sql_quality_validator import validate_sql

logger = logging.getLogger(__name__)


def _schema_dict(profile: DatasetProfile) -> dict:
    return {
        "dataset_id": profile.dataset_id,
        "columns": [{"name": c.name, "dtype": c.dtype} for c in profile.columns],
        "row_count": profile.row_count,
    }


def _schema_profile_for_codegen(profile: DatasetProfile) -> dict:
    return {
        "dataset_id": profile.dataset_id,
        "duckdb_table": profile.table,
        "row_count": profile.row_count,
        "columns": [
            {
                "name": c.name,
                "dtype": c.dtype,
                "sample_values": list(getattr(c, "sample_values", None) or [])[:3],
            }
            for c in profile.columns
        ],
        "fingerprint": profile.fingerprint,
    }


def _generate_sql_via_pipeline(
    session_id: str,
    profile: DatasetProfile,
    question: str,
) -> Optional[str]:
    """
    Use the same code_generator path as /analyze (patterns → SQLCoder → fallback).

    force_complexity=SIMPLE keeps suggestions fast and high-success.
    """
    try:
        from backend.agents.nodes.code_generator import code_generator_node

        state = {
            "session_id": session_id,
            "dataset_id": profile.dataset_id,
            "duckdb_table": profile.table,
            "question": question,
            "plan": {"approach": "sql", "steps": ["answer simple question"]},
            "schema_profile": _schema_profile_for_codegen(profile),
            "retry_count": 0,
            "retry_history": [],
            "execution_metadata": [],
            "analysis_artifacts": {
                "force_complexity": "SIMPLE",
                # Skip LLM/SQLCoder during upload verify — patterns + proof_sql
                # are enough; click still uses the full /analyze pipeline.
                "suggestion_verify": True,
            },
        }
        out = code_generator_node(state)
        code = (out.get("generated_code") or "").strip()
        if code and not out.get("failure_summary"):
            return code
    except Exception as exc:
        logger.info("Suggestion SQL via pipeline failed for %r: %s", question[:80], exc)
    return None


def _sql_is_valid(
    sql: str,
    profile: DatasetProfile,
    question: str,
    *,
    category: str,
) -> Tuple[bool, str]:
    quality = validate_sql(sql, schema=_schema_dict(profile), question=question)
    blocking = []
    for issue in quality.get("critical_issues") or []:
        if "Missing LIMIT" in issue and category == "overview":
            continue
        if "Incorrect ORDER BY" in issue:
            continue
        if "Misuse of SELECT *" in issue:
            continue
        if "missing a meaningful alias" in issue.lower():
            continue
        blocking.append(issue)
    if blocking:
        return False, "; ".join(blocking)
    return True, ""


def validate_candidate(
    session_id: str,
    profile: DatasetProfile,
    candidate: QuestionCandidate,
) -> Tuple[bool, str]:
    known = {c.name for c in profile.columns}
    for col in candidate.columns_used:
        if col not in known:
            return False, f"Unknown column: {col}"

    # Prefer SQL from the production NL→SQL path; fall back to template proof SQL.
    pipeline_sql = _generate_sql_via_pipeline(session_id, profile, candidate.text)
    sql_candidates: List[str] = []
    if pipeline_sql:
        sql_candidates.append(pipeline_sql)
    if candidate.proof_sql and candidate.proof_sql not in sql_candidates:
        sql_candidates.append(candidate.proof_sql)

    last_reason = "no sql"
    for sql in sql_candidates:
        ok, reason = _sql_is_valid(
            sql, profile, candidate.text, category=candidate.category
        )
        if not ok:
            last_reason = reason
            continue
        result = run_query(session_id, profile.dataset_id, sql)
        if not result.get("success"):
            last_reason = str(result.get("error") or "execution failed")
            continue
        if int(result.get("row_count") or 0) < 1 and candidate.intent != "row_count":
            # Empty non-count results are not useful suggestions
            last_reason = "empty result"
            continue
        # Persist the SQL that actually worked for debugging / optional UI
        candidate.proof_sql = sql
        return True, ""

    return False, last_reason


def validate_candidates(
    session_id: str,
    profile: DatasetProfile,
    candidates: List[QuestionCandidate],
) -> Tuple[List[QuestionCandidate], int]:
    valid: List[QuestionCandidate] = []
    rejected = 0
    for c in candidates:
        ok, reason = validate_candidate(session_id, profile, c)
        if ok:
            valid.append(c)
        else:
            rejected += 1
            logger.info("Rejected suggested question %s: %s", c.id, reason)
    return valid, rejected
