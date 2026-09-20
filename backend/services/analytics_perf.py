"""Session-scoped analytics helpers: rich schema profiles, complexity, result cache."""
from __future__ import annotations

import hashlib
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Rich schema profile (reuse adaptive profiler; shape for LangGraph agents)
# ---------------------------------------------------------------------------

def rich_profile_to_schema_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert adaptive DatasetProfile.to_dict() into the schema_profile shape
    expected by planner / code_generator / format_schema_context_for_llm.
    """
    columns_out: List[Dict[str, Any]] = []
    for col in profile.get("columns") or []:
        columns_out.append(
            {
                "name": col.get("name"),
                "dtype": col.get("dtype") or "string",
                "sample_values": list(col.get("sample_values") or [])[:8],
                "null_count": col.get("null_count", 0),
                "null_pct": col.get("null_pct", 0.0),
                "unique_count": col.get("unique_count", 0),
                "cardinality_ratio": col.get("cardinality_ratio", 0.0),
                "min": col.get("min_value"),
                "max": col.get("max_value"),
                "mean": col.get("avg_value"),
                "top_values": col.get("top_values") or [],
                "analytical_role": col.get("analytical_role") or "categorical",
            }
        )
    return {
        "dataset_id": profile.get("dataset_id"),
        "source": "csv",
        "row_count": profile.get("row_count", 0),
        "column_count": profile.get("column_count", len(columns_out)),
        "fingerprint": profile.get("fingerprint"),
        "date_range": profile.get("date_range"),
        "columns": columns_out,
        "rich": True,
    }


def get_or_build_csv_schema_profile(session_id: str, dataset_id: str) -> Dict[str, Any]:
    """
    Build (or return cached) rich schema profile for an in-process DuckDB CSV table.
    Never invokes MCP — MCP stdio cannot see in-memory DuckDB sessions.
    """
    from backend.services.session_manager import session_manager
    from backend.services.adaptive_questions.profiler import profile_dataset

    session = session_manager.get_session(session_id)
    cached = getattr(session, "schema_profile_cache", None) or {}
    entry = cached.get(dataset_id)
    if isinstance(entry, dict) and entry.get("rich") and entry.get("columns"):
        return entry

    rich = profile_dataset(session_id, dataset_id).to_dict()
    schema = rich_profile_to_schema_profile(rich)
    if not hasattr(session, "schema_profile_cache") or session.schema_profile_cache is None:
        session.schema_profile_cache = {}
    session.schema_profile_cache[dataset_id] = schema
    return schema


# ---------------------------------------------------------------------------
# Question complexity (minimize pipeline / LLM use)
# ---------------------------------------------------------------------------

_VERY_COMPLEX_MARKERS = (
    "share of total",
    "percentage of total",
    "% of total",
    "compared to overall",
    "vs overall",
    "versus overall",
    "previous year",
    "year over year",
    "yoy",
    "within each",
    "per group",
    "partition",
    "window",
    "exclude",
    "fewer than",
    "at least",
    "contribution",
    "conditional",
    "having",
    "subquery",
    "cte",
)

_COMPLEX_MARKERS = (
    "rank",
    "top ",
    "bottom ",
    "percent",
    "ratio",
    "average",
    "compare",
    "trend",
    "month",
    "quarter",
    "year",
    "group",
    "by ",
    "highest",
    "lowest",
    "share",
)

_SIMPLE_MARKERS = (
    "count",
    "sum",
    "total",
    "list",
    "show",
    "how many",
    "filter",
    "where",
)


def classify_question_complexity(question: str) -> str:
    """Return SIMPLE | COMPLEX | VERY_COMPLEX."""
    q = (question or "").lower().strip()
    if not q:
        return "SIMPLE"
    very_hits = sum(1 for m in _VERY_COMPLEX_MARKERS if m in q)
    if very_hits >= 2 or ("top" in q and "share" in q) or ("exclude" in q and "top" in q):
        return "VERY_COMPLEX"
    if very_hits >= 1:
        return "VERY_COMPLEX"
    complex_hits = sum(1 for m in _COMPLEX_MARKERS if m in q)
    if complex_hits >= 2:
        return "COMPLEX"
    if complex_hits >= 1:
        return "COMPLEX"
    if any(m in q for m in _SIMPLE_MARKERS):
        return "SIMPLE"
    return "COMPLEX"


# ---------------------------------------------------------------------------
# Safe per-session query-result cache (never cross sessions)
# ---------------------------------------------------------------------------

_RESULT_CACHE: Dict[str, Dict[str, Tuple[float, Dict[str, Any]]]] = {}
_RESULT_CACHE_LOCK = threading.Lock()
_RESULT_TTL_SECONDS = 600.0
_RESULT_MAX_PER_SESSION = 64


def _normalize_question(question: str) -> str:
    q = (question or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def make_cache_key(
    session_id: str,
    dataset_id: str,
    fingerprint: str,
    question: str,
) -> str:
    raw = f"{session_id}|{dataset_id}|{fingerprint}|{_normalize_question(question)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_analysis_result(
    session_id: str,
    dataset_id: str,
    fingerprint: str,
    question: str,
) -> Optional[Dict[str, Any]]:
    if not session_id or not dataset_id or not fingerprint:
        return None
    key = make_cache_key(session_id, dataset_id, fingerprint, question)
    now = time.time()
    with _RESULT_CACHE_LOCK:
        bucket = _RESULT_CACHE.get(session_id) or {}
        hit = bucket.get(key)
        if not hit:
            return None
        ts, payload = hit
        if now - ts > _RESULT_TTL_SECONDS:
            bucket.pop(key, None)
            return None
        return dict(payload)


def put_cached_analysis_result(
    session_id: str,
    dataset_id: str,
    fingerprint: str,
    question: str,
    payload: Dict[str, Any],
) -> None:
    if not session_id or not dataset_id or not fingerprint:
        return
    key = make_cache_key(session_id, dataset_id, fingerprint, question)
    with _RESULT_CACHE_LOCK:
        bucket = _RESULT_CACHE.setdefault(session_id, {})
        if len(bucket) >= _RESULT_MAX_PER_SESSION:
            # Drop oldest
            oldest_key = min(bucket.items(), key=lambda kv: kv[1][0])[0]
            bucket.pop(oldest_key, None)
        bucket[key] = (time.time(), dict(payload))


def clear_session_analysis_cache(session_id: str) -> None:
    with _RESULT_CACHE_LOCK:
        _RESULT_CACHE.pop(session_id, None)


def cache_stats() -> Dict[str, Any]:
    with _RESULT_CACHE_LOCK:
        return {
            "sessions": len(_RESULT_CACHE),
            "entries": sum(len(b) for b in _RESULT_CACHE.values()),
        }
