"""
Lightweight observability persistence for MarketMind workflows.

Stores workflow runs, per-node timings, and user feedback in PostgreSQL.
Soft-fails to an in-memory fallback if the database is unavailable.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.database.connection import get_db_connection

logger = logging.getLogger(__name__)

# In-memory fallback for demo / offline Postgres
_MEMORY_RUNS: Dict[str, Dict[str, Any]] = {}
_MEMORY_NODES: List[Dict[str, Any]] = []
_MEMORY_FEEDBACK: List[Dict[str, Any]] = []
_DB_UNAVAILABLE = False


def _db_enabled() -> bool:
    return not _DB_UNAVAILABLE


def _mark_db_unavailable(exc: Exception) -> None:
    global _DB_UNAVAILABLE
    if not _DB_UNAVAILABLE:
        logger.warning("Observability Postgres unavailable; using in-memory store: %s", exc)
    _DB_UNAVAILABLE = True


def sanitize_error_message(message: Optional[str], max_len: int = 500) -> Optional[str]:
    """Strip secrets / oversized noise from error strings before persistence or API return."""
    if not message:
        return None
    text = str(message)
    # Redact common secret patterns
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    text = re.sub(r"gsk_[A-Za-z0-9]+", "gsk_[REDACTED]", text)
    text = re.sub(r"AIza[0-9A-Za-z_-]+", "AIza[REDACTED]", text)
    text = re.sub(r"sk-[A-Za-z0-9]+", "sk-[REDACTED]", text)
    # Drop raw traceback bodies if accidentally included
    if "Traceback (most recent call last)" in text:
        text = text.split("Traceback (most recent call last)")[0].strip() or "Internal workflow error"
    text = text.strip()
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text or None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_workflow_run(
    *,
    workflow_name: str,
    session_id: Optional[str],
    input_summary: str,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    rid = run_id or str(uuid.uuid4())
    started = _utcnow()
    record = {
        "run_id": rid,
        "session_id": session_id,
        "workflow_name": workflow_name,
        "input_summary": (input_summary or "")[:500],
        "started_at": started,
        "completed_at": None,
        "latency_ms": None,
        "final_status": "running",
        "product_matches_count": 0,
        "supplier_matches_count": 0,
        "error_message": None,
        "created_at": started,
    }
    query = """
        INSERT INTO workflow_runs (
            run_id, session_id, workflow_name, input_summary,
            started_at, final_status, product_matches_count, supplier_matches_count
        ) VALUES (%s, %s, %s, %s, %s, %s, 0, 0)
        RETURNING *;
    """
    try:
        if not _db_enabled():
            raise RuntimeError("Postgres marked unavailable")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        rid,
                        session_id,
                        workflow_name,
                        record["input_summary"],
                        started,
                        "running",
                    ),
                )
                row = cur.fetchone()
                if row:
                    _MEMORY_RUNS[rid] = dict(row)
                    return dict(row)
    except Exception as e:
        _mark_db_unavailable(e)

    _MEMORY_RUNS[rid] = record
    return dict(record)


def complete_workflow_run(
    run_id: str,
    *,
    final_status: str,
    latency_ms: float,
    product_matches_count: int = 0,
    supplier_matches_count: int = 0,
    error_message: Optional[str] = None,
    node_executions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    completed = _utcnow()
    safe_error = sanitize_error_message(error_message)
    query = """
        UPDATE workflow_runs
        SET completed_at = %s,
            latency_ms = %s,
            final_status = %s,
            product_matches_count = %s,
            supplier_matches_count = %s,
            error_message = %s
        WHERE run_id = %s
        RETURNING *;
    """
    row: Optional[Dict[str, Any]] = None
    try:
        if not _db_enabled():
            raise RuntimeError("Postgres marked unavailable")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        completed,
                        latency_ms,
                        final_status,
                        product_matches_count,
                        supplier_matches_count,
                        safe_error,
                        run_id,
                    ),
                )
                row = cur.fetchone()
                if node_executions:
                    _persist_node_executions(cur, run_id, node_executions)
    except Exception as e:
        _mark_db_unavailable(e)

    mem = _MEMORY_RUNS.get(run_id, {"run_id": run_id})
    mem.update(
        {
            "completed_at": completed,
            "latency_ms": latency_ms,
            "final_status": final_status,
            "product_matches_count": product_matches_count,
            "supplier_matches_count": supplier_matches_count,
            "error_message": safe_error,
        }
    )
    _MEMORY_RUNS[run_id] = mem

    if node_executions:
        # Replace any prior memory nodes for this run
        global _MEMORY_NODES
        _MEMORY_NODES = [n for n in _MEMORY_NODES if n.get("run_id") != run_id]
        for n in node_executions:
            entry = {"run_id": run_id, **n}
            _MEMORY_NODES.append(entry)

    return dict(row) if row else dict(mem)


def _persist_node_executions(cur, run_id: str, nodes: List[Dict[str, Any]]) -> None:
    cur.execute("DELETE FROM workflow_node_runs WHERE run_id = %s;", (run_id,))
    insert = """
        INSERT INTO workflow_node_runs (run_id, node_name, execution_order, duration_ms, status, error_message)
        VALUES (%s, %s, %s, %s, %s, %s);
    """
    for n in nodes:
        cur.execute(
            insert,
            (
                run_id,
                n.get("node_name"),
                n.get("execution_order"),
                n.get("duration_ms"),
                n.get("status") or "success",
                sanitize_error_message(n.get("error_message")),
            ),
        )


def save_workflow_feedback(
    run_id: str,
    rating: str,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    rating_norm = (rating or "").strip().lower()
    if rating_norm not in ("helpful", "not_helpful"):
        raise ValueError("rating must be 'helpful' or 'not_helpful'")

    # Ensure run exists (Postgres or memory)
    if not get_workflow_run(run_id):
        raise ValueError(f"Unknown run_id: {run_id}")

    query = """
        INSERT INTO workflow_feedback (run_id, rating, comment)
        VALUES (%s, %s, %s)
        RETURNING *;
    """
    try:
        if not _db_enabled():
            raise RuntimeError("Postgres marked unavailable")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id, rating_norm, (comment or "")[:2000] or None))
                row = cur.fetchone()
                if row:
                    _MEMORY_FEEDBACK.append(dict(row))
                    return dict(row)
    except Exception as e:
        _mark_db_unavailable(e)

    record = {
        "id": len(_MEMORY_FEEDBACK) + 1,
        "run_id": run_id,
        "rating": rating_norm,
        "comment": (comment or "")[:2000] or None,
        "created_at": _utcnow(),
    }
    _MEMORY_FEEDBACK.append(record)
    return dict(record)


def get_workflow_run(run_id: str) -> Optional[Dict[str, Any]]:
    try:
        if _db_enabled():
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM workflow_runs WHERE run_id = %s;", (run_id,))
                    row = cur.fetchone()
                    if row:
                        return dict(row)
    except Exception as e:
        _mark_db_unavailable(e)
    return _MEMORY_RUNS.get(run_id)


def list_workflow_runs(limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    try:
        if _db_enabled():
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT run_id, session_id, workflow_name, input_summary,
                               started_at, completed_at, latency_ms, final_status,
                               product_matches_count, supplier_matches_count,
                               error_message, created_at
                        FROM workflow_runs
                        ORDER BY COALESCE(started_at, created_at) DESC
                        LIMIT %s;
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall() or []
                    if rows:
                        return [dict(r) for r in rows]
    except Exception as e:
        _mark_db_unavailable(e)

    runs = sorted(
        _MEMORY_RUNS.values(),
        key=lambda r: r.get("started_at") or r.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return [dict(r) for r in runs[:limit]]


def get_node_executions(run_id: str) -> List[Dict[str, Any]]:
    try:
        if _db_enabled():
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT node_name, execution_order, duration_ms, status, error_message
                        FROM workflow_node_runs
                        WHERE run_id = %s
                        ORDER BY execution_order ASC;
                        """,
                        (run_id,),
                    )
                    rows = cur.fetchall() or []
                    if rows:
                        return [dict(r) for r in rows]
    except Exception as e:
        _mark_db_unavailable(e)

    return [dict(n) for n in _MEMORY_NODES if n.get("run_id") == run_id]


def get_observability_summary() -> Dict[str, Any]:
    """
    Aggregate metrics for Agent Monitoring dashboard.

    success_rate = complete runs / total finished runs (excludes still-running)
    helpful_feedback_rate = helpful / total feedback
    """
    try:
        if _db_enabled():
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*) AS total_runs,
                            COUNT(*) FILTER (WHERE final_status = 'complete') AS complete_count,
                            COUNT(*) FILTER (
                                WHERE final_status IN ('failed', 'no_products', 'no_suppliers', 'needs_info')
                            ) AS failure_count,
                            COUNT(*) FILTER (WHERE final_status = 'running') AS running_count,
                            AVG(latency_ms) FILTER (WHERE latency_ms IS NOT NULL) AS avg_latency_ms
                        FROM workflow_runs;
                        """
                    )
                    run_stats = cur.fetchone() or {}
                    cur.execute(
                        """
                        SELECT
                            COUNT(*) AS total_feedback,
                            COUNT(*) FILTER (WHERE rating = 'helpful') AS helpful_count
                        FROM workflow_feedback;
                        """
                    )
                    fb_stats = cur.fetchone() or {}
                    return _compute_summary_dict(run_stats, fb_stats)
    except Exception as e:
        _mark_db_unavailable(e)

    runs = list(_MEMORY_RUNS.values())
    complete_count = sum(1 for r in runs if r.get("final_status") == "complete")
    failure_count = sum(
        1
        for r in runs
        if r.get("final_status") in ("failed", "no_products", "no_suppliers", "needs_info")
    )
    running_count = sum(1 for r in runs if r.get("final_status") == "running")
    latencies = [float(r["latency_ms"]) for r in runs if r.get("latency_ms") is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    helpful = sum(1 for f in _MEMORY_FEEDBACK if f.get("rating") == "helpful")
    return _compute_summary_dict(
        {
            "total_runs": len(runs),
            "complete_count": complete_count,
            "failure_count": failure_count,
            "running_count": running_count,
            "avg_latency_ms": avg_latency,
        },
        {"total_feedback": len(_MEMORY_FEEDBACK), "helpful_count": helpful},
    )


def _compute_summary_dict(run_stats: Dict[str, Any], fb_stats: Dict[str, Any]) -> Dict[str, Any]:
    total = int(run_stats.get("total_runs") or 0)
    complete = int(run_stats.get("complete_count") or 0)
    failure = int(run_stats.get("failure_count") or 0)
    running = int(run_stats.get("running_count") or 0)
    finished = max(total - running, 0)
    avg_latency = float(run_stats.get("avg_latency_ms") or 0.0)
    total_fb = int(fb_stats.get("total_feedback") or 0)
    helpful = int(fb_stats.get("helpful_count") or 0)
    return {
        "total_runs": total,
        "complete_count": complete,
        "failure_count": failure,
        "running_count": running,
        "success_rate": round(complete / finished, 4) if finished else 0.0,
        "average_latency_ms": round(avg_latency, 2),
        "total_feedback": total_fb,
        "helpful_feedback_count": helpful,
        "helpful_feedback_rate": round(helpful / total_fb, 4) if total_fb else 0.0,
    }


def serialize_run(row: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-friendly run dict."""
    out = dict(row)
    for key in ("started_at", "completed_at", "created_at"):
        val = out.get(key)
        if hasattr(val, "isoformat"):
            out[key] = val.isoformat()
    if out.get("latency_ms") is not None:
        out["latency_ms"] = round(float(out["latency_ms"]), 2)
    return out
