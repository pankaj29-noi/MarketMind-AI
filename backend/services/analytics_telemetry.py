"""In-process analytics request telemetry (no secrets)."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_RECORDS: List[Dict[str, Any]] = []
_MAX = 500


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def record_analytics_event(event: Dict[str, Any]) -> None:
    """Append a sanitized analytics telemetry event."""
    safe = {
        "request_id": event.get("request_id"),
        "session_id": event.get("session_id"),
        "dataset_id": event.get("dataset_id"),
        "question": (event.get("question") or "")[:500],
        "complexity": event.get("complexity"),
        "llm_calls": event.get("llm_calls"),
        "model": event.get("model"),
        "provider": event.get("provider"),
        "schema_ms": event.get("schema_ms"),
        "generation_ms": event.get("generation_ms"),
        "sql_exec_ms": event.get("sql_exec_ms"),
        "validation_ms": event.get("validation_ms"),
        "total_ms": event.get("total_ms"),
        "retry_count": event.get("retry_count"),
        "cache_hit": event.get("cache_hit"),
        "success": event.get("success"),
        "abstention_reason": event.get("abstention_reason"),
        "analysis_source": event.get("analysis_source"),
        "ts": time.time(),
    }
    with _LOCK:
        _RECORDS.append(safe)
        if len(_RECORDS) > _MAX:
            del _RECORDS[: len(_RECORDS) - _MAX]


def recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    with _LOCK:
        return list(_RECORDS[-limit:])


def clear_telemetry() -> None:
    with _LOCK:
        _RECORDS.clear()


def summarize_telemetry() -> Dict[str, Any]:
    with _LOCK:
        rows = list(_RECORDS)
    if not rows:
        return {"n": 0}
    totals = [r["total_ms"] for r in rows if isinstance(r.get("total_ms"), (int, float))]
    hits = sum(1 for r in rows if r.get("cache_hit"))
    ok = sum(1 for r in rows if r.get("success"))
    return {
        "n": len(rows),
        "success_rate": (ok / len(rows)) if rows else 0.0,
        "cache_hit_rate": (hits / len(rows)) if rows else 0.0,
        "avg_total_ms": (sum(totals) / len(totals)) if totals else None,
        "p95_total_ms": sorted(totals)[int(0.95 * (len(totals) - 1))] if len(totals) >= 2 else (totals[0] if totals else None),
    }
