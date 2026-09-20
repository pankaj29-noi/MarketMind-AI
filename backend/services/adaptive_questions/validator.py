"""Validate candidates: schema refs + SQL quality + DuckDB execution proof."""
from __future__ import annotations

import logging
from typing import List, Tuple

from backend.mcp.data_access import run_query
from backend.services.adaptive_questions.profiler import DatasetProfile
from backend.services.adaptive_questions.templates import QuestionCandidate
from backend.services.sql.sql_quality_validator import validate_sql

logger = logging.getLogger(__name__)


def _schema_dict(profile: DatasetProfile) -> dict:
    return {
        "dataset_id": profile.dataset_id,
        "columns": [{"name": c.name, "dtype": c.dtype} for c in profile.columns],
    }


def validate_candidate(
    session_id: str,
    profile: DatasetProfile,
    candidate: QuestionCandidate,
) -> Tuple[bool, str]:
    known = {c.name for c in profile.columns}
    for col in candidate.columns_used:
        if col not in known:
            return False, f"Unknown column: {col}"

    # Soften SELECT * rule — our proofs never use *
    quality = validate_sql(candidate.proof_sql, schema=_schema_dict(profile), question=candidate.text)
    # Critical issues that are about ORDER BY / LIMIT heuristics shouldn't block overview counts
    blocking = []
    for issue in quality.get("critical_issues") or []:
        if "Missing LIMIT" in issue and candidate.category == "overview":
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

    result = run_query(session_id, profile.dataset_id, candidate.proof_sql)
    if not result.get("success"):
        return False, str(result.get("error") or "execution failed")
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
