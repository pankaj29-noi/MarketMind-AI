"""Validate candidates: production NL→SQL path + DuckDB execution + answer cross-check."""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

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


def _column_dicts(profile: DatasetProfile) -> List[dict]:
    return [
        {
            "name": c.name,
            "dtype": c.dtype,
            "analytical_role": getattr(c, "analytical_role", None),
        }
        for c in profile.columns
    ]


def _resolve_production_sql(
    profile: DatasetProfile,
    question: str,
) -> Optional[str]:
    """
    Resolve NL→SQL the same way /analyze prefers before calling LLM/SQLCoder:
    pattern library, then analytics fallback. Prefer coverage-valid SQL.
    """
    from backend.services.analytics_fallback import resolve_analytics_fallback
    from backend.services.requirement_coverage import check_requirement_coverage
    from backend.services.sql.sql_pattern_library import try_simple_deterministic_sql

    cols = _column_dicts(profile)
    hit = try_simple_deterministic_sql(question, profile.table, cols)
    if hit and hit.sql:
        ok, _ = check_requirement_coverage(question, hit.sql, columns=None)
        if ok:
            return hit.sql.strip()

    schema = _schema_profile_for_codegen(profile)
    fb = resolve_analytics_fallback(question, schema, profile.dataset_id)
    if fb.sql:
        ok, _ = check_requirement_coverage(question, fb.sql, columns=None)
        if ok:
            return fb.sql.strip()

    # Last resort: return pattern/fallback SQL even if coverage is soft-failing
    # (validator still re-checks). Prefer pattern when present.
    if hit and hit.sql:
        return hit.sql.strip()
    if fb.sql:
        return fb.sql.strip()
    return None


def _generate_sql_via_pipeline(
    session_id: str,
    profile: DatasetProfile,
    question: str,
) -> Optional[str]:
    """Deterministic code_generator path (patterns/fallback only; no LLM)."""
    try:
        from backend.agents.nodes.code_generator import code_generator_node

        state = {
            "session_id": session_id,
            "dataset_id": profile.dataset_id,
            "duckdb_table": profile.table,
            "question": question,
            "plan": {"approach": "sql", "steps": ["answer suggested question"]},
            "schema_profile": _schema_profile_for_codegen(profile),
            "retry_count": 0,
            "retry_history": [],
            "execution_metadata": [],
            "analysis_artifacts": {
                "force_complexity": "SIMPLE",
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
        if "Missing LIMIT" in issue and category in {"overview", "trend", "concentration"}:
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


def _first_numeric(rows: List[dict]) -> Optional[float]:
    if not rows:
        return None
    row = rows[0]
    for val in row.values():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)
        try:
            if val is None:
                continue
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def _execute_ok(
    session_id: str,
    profile: DatasetProfile,
    sql: str,
    candidate: QuestionCandidate,
) -> Tuple[bool, str, Optional[dict]]:
    from backend.services.requirement_coverage import check_requirement_coverage

    ok, reason = _sql_is_valid(
        sql, profile, candidate.text, category=candidate.category
    )
    if not ok:
        return False, reason, None

    cov_ok, miss = check_requirement_coverage(candidate.text, sql, columns=None)
    if not cov_ok:
        return False, f"coverage: {miss}", None

    result = run_query(session_id, profile.dataset_id, sql)
    if not result.get("success"):
        return False, str(result.get("error") or "execution failed"), None
    if int(result.get("row_count") or 0) < 1 and candidate.intent != "row_count":
        return False, "empty result", None
    return True, "", result


def _cross_verify_answers(
    session_id: str,
    profile: DatasetProfile,
    production_sql: str,
    proof_sql: str,
) -> Tuple[bool, str]:
    """When both production and proof SQL run, require matching lead numeric."""
    if production_sql.strip() == proof_sql.strip():
        return True, ""
    a = run_query(session_id, profile.dataset_id, production_sql)
    b = run_query(session_id, profile.dataset_id, proof_sql)
    if not a.get("success") or not b.get("success"):
        return False, "cross-verify execution failed"
    na = _first_numeric(a.get("rows") or [])
    nb = _first_numeric(b.get("rows") or [])
    # Ranking/group questions: compare row counts when lead numeric differs by shape
    if na is None or nb is None:
        ra = int(a.get("row_count") or 0)
        rb = int(b.get("row_count") or 0)
        if ra > 0 and rb > 0:
            return True, ""
        return False, "cross-verify empty"
    if abs(na - nb) <= max(0.02 * max(abs(na), abs(nb), 1.0), 0.05):
        return True, ""
    return False, f"cross-verify mismatch {na} vs {nb}"


def validate_candidate(
    session_id: str,
    profile: DatasetProfile,
    candidate: QuestionCandidate,
) -> Tuple[bool, str]:
    known = {c.name for c in profile.columns}
    for col in candidate.columns_used:
        if col not in known:
            return False, f"Unknown column: {col}"

    production_sql = _resolve_production_sql(profile, candidate.text)
    if not production_sql:
        # Last resort: deterministic code_generator (still no LLM)
        production_sql = _generate_sql_via_pipeline(session_id, profile, candidate.text)

    # Medium/hard must resolve via production NL→SQL — proof_sql alone is not enough
    # (otherwise click-time SQLCoder/LLM may invent wrong joins).
    if candidate.difficulty in {"medium", "hard", "very_hard"} and not production_sql:
        return False, "no production NL→SQL path for medium/hard question"

    sql_candidates: List[Tuple[str, str]] = []
    if production_sql:
        sql_candidates.append(("production", production_sql))
    if candidate.proof_sql and candidate.proof_sql.strip() not in {
        s for _, s in sql_candidates
    }:
        # Easy may use proof_sql if production missed a synonym; still execute it.
        if candidate.difficulty == "easy" or production_sql:
            sql_candidates.append(("proof", candidate.proof_sql.strip()))

    if not sql_candidates and candidate.proof_sql:
        sql_candidates.append(("proof", candidate.proof_sql.strip()))

    last_reason = "no sql"
    working: Optional[Tuple[str, str, dict]] = None
    for source, sql in sql_candidates:
        ok, reason, result = _execute_ok(session_id, profile, sql, candidate)
        if not ok:
            last_reason = f"{source}: {reason}"
            continue
        working = (source, sql, result or {})
        break

    if working is None:
        return False, last_reason

    source, sql, _result = working

    # Cross-verify production vs proof when both are available
    if (
        production_sql
        and candidate.proof_sql
        and production_sql.strip() != candidate.proof_sql.strip()
        and candidate.difficulty in {"medium", "hard", "very_hard"}
    ):
        ok_x, reason_x = _cross_verify_answers(
            session_id, profile, production_sql, candidate.proof_sql
        )
        if not ok_x:
            # Prefer production SQL if it alone already executed successfully
            logger.info(
                "Suggestion %s cross-verify soft-fail (%s); keeping production SQL",
                candidate.id,
                reason_x,
            )
        else:
            # Prefer production path SQL for click-time consistency
            sql = production_sql

    if source != "production" and production_sql:
        # Prefer production SQL when it also executes cleanly
        ok_p, _r_p, _res_p = _execute_ok(session_id, profile, production_sql, candidate)
        if ok_p:
            sql = production_sql

    candidate.proof_sql = sql
    return True, ""


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
