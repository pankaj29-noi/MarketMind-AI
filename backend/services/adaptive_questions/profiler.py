"""Compact DuckDB profiling for uploaded single-table CSVs."""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from backend.services.session_manager import session_manager
from backend.mcp.data_access import run_query
from backend.services.adaptive_questions.fingerprint import (
    compute_fingerprint,
    sample_digest_from_values,
)
from backend.utils.analytical_roles import infer_analytical_roles

logger = logging.getLogger(__name__)


def _exec(session_id: str, sql: str) -> List[Dict[str, Any]]:
    """Session-local DuckDB exec (supports PRAGMA). Prefer for profiling."""
    try:
        return session_manager.execute_query(session_id, sql) or []
    except Exception as e:
        logger.warning("profile query failed: %s | %s", sql[:120], e)
        return []


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    null_count: int = 0
    null_pct: float = 0.0
    unique_count: int = 0
    cardinality_ratio: float = 0.0
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    avg_value: Optional[float] = None
    median_value: Optional[float] = None
    sample_values: List[Any] = field(default_factory=list)
    top_values: List[Dict[str, Any]] = field(default_factory=list)
    analytical_role: str = "categorical"
    normalized_name: str = ""
    semantic_type: str = "unknown"
    semantic_confidence: float = 0.0


@dataclass
class DatasetProfile:
    session_id: str
    dataset_id: str
    table: str
    row_count: int
    column_count: int
    columns: List[ColumnProfile]
    fingerprint: str
    date_range: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "dataset_id": self.dataset_id,
            "table": self.table,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "fingerprint": self.fingerprint,
            "date_range": self.date_range,
            "message": self.message,
            "columns": [asdict(c) for c in self.columns],
        }


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _normalize_dtype(raw: str) -> str:
    t = (raw or "").upper()
    if any(x in t for x in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "HUGEINT", "REAL")):
        return "number"
    if any(x in t for x in ("DATE", "TIME", "TIMESTAMP")):
        return "datetime"
    if "BOOL" in t:
        return "boolean"
    return "string"


def profile_dataset(session_id: str, dataset_id: str) -> DatasetProfile:
    """
    Profile a single DuckDB table once. Uses aggregates + LIMIT samples.
    Never ships full CSV contents to an LLM.
    """
    table = dataset_id
    col_rows = _exec(session_id, f"PRAGMA table_info({table})")
    if not col_rows:
        col_rows = _exec(session_id, f"PRAGMA table_info({_ident(table)})")

    columns_meta = []
    for r in col_rows:
        name = r.get("name") or r.get("column_name")
        dtype_raw = r.get("type") or r.get("dtype") or "VARCHAR"
        if not name:
            continue
        columns_meta.append({"name": name, "dtype": _normalize_dtype(str(dtype_raw)), "raw_type": dtype_raw})

    count_rows = _exec(session_id, f"SELECT COUNT(*) AS cnt FROM {_ident(table)}")
    if not count_rows:
        count_rows = _exec(session_id, f"SELECT COUNT(*) AS cnt FROM {table}")
    row_count = int((count_rows[0].get("cnt") if count_rows else 0) or 0)

    dtypes = {c["name"]: c["dtype"] for c in columns_meta}
    roles = infer_analytical_roles(list(dtypes.keys()), dtypes)

    profiles: List[ColumnProfile] = []
    samples_for_fp: Dict[str, List[Any]] = {}
    date_range = None

    for meta in columns_meta:
        name = meta["name"]
        dtype = meta["dtype"]
        col_id = _ident(name)
        tbl = _ident(table)

        null_rows = _exec(session_id, f"SELECT COUNT(*) AS n FROM {tbl} WHERE {col_id} IS NULL")
        null_count = int((null_rows[0].get("n") if null_rows else 0) or 0)
        null_pct = (null_count / row_count) if row_count else 0.0

        uniq_rows = _exec(session_id, f"SELECT COUNT(DISTINCT {col_id}) AS u FROM {tbl}")
        unique_count = int((uniq_rows[0].get("u") if uniq_rows else 0) or 0)
        card = (unique_count / row_count) if row_count else 0.0

        min_v = max_v = avg_v = median_v = None
        if dtype == "number" and row_count:
            stats = _exec(
                session_id,
                f"SELECT MIN({col_id}) AS mn, MAX({col_id}) AS mx, AVG({col_id}) AS av, "
                f"MEDIAN({col_id}) AS md FROM {tbl}",
            )
            if stats:
                row = stats[0]
                min_v, max_v, avg_v = row.get("mn"), row.get("mx"), row.get("av")
                median_v = row.get("md")
                try:
                    avg_v = float(avg_v) if avg_v is not None else None
                except (TypeError, ValueError):
                    avg_v = None
                try:
                    median_v = float(median_v) if median_v is not None else None
                except (TypeError, ValueError):
                    median_v = None
        elif dtype == "datetime" and row_count:
            stats = _exec(
                session_id,
                f"SELECT MIN({col_id}) AS mn, MAX({col_id}) AS mx FROM {tbl}",
            )
            if stats:
                row = stats[0]
                min_v, max_v = row.get("mn"), row.get("mx")
                date_range = {"column": name, "min": min_v, "max": max_v}

        sample_rows = _exec(
            session_id,
            f"SELECT {col_id} AS v FROM {tbl} WHERE {col_id} IS NOT NULL LIMIT 8",
        )
        sample_values = [r.get("v") for r in sample_rows if "v" in r]
        samples_for_fp[name] = sample_values

        top_values: List[Dict[str, Any]] = []
        if dtype in ("string", "boolean") and unique_count and unique_count <= 50 and row_count:
            top_rows = _exec(
                session_id,
                f"SELECT {col_id} AS val, COUNT(*) AS cnt FROM {tbl} "
                f"WHERE {col_id} IS NOT NULL GROUP BY {col_id} ORDER BY cnt DESC LIMIT 5",
            )
            top_values = [{"value": r.get("val"), "count": r.get("cnt")} for r in top_rows]

        role = roles.get(name, "categorical")
        # Build provisional profile for semantic classifier
        provisional = ColumnProfile(
            name=name,
            dtype=dtype,
            null_count=null_count,
            null_pct=round(null_pct, 4),
            unique_count=unique_count,
            cardinality_ratio=round(card, 4),
            min_value=min_v,
            max_value=max_v,
            avg_value=avg_v,
            median_value=median_v,
            sample_values=sample_values,
            top_values=top_values,
            analytical_role=role,
            normalized_name=re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
        )
        try:
            from backend.services.adaptive_questions.semantics import classify_column
            sem = classify_column(provisional)
            provisional.semantic_type = sem.semantic_type
            provisional.semantic_confidence = float(sem.confidence)
        except Exception:
            pass
        profiles.append(provisional)

    digest = sample_digest_from_values(samples_for_fp)
    fp = compute_fingerprint(columns=columns_meta, row_count=row_count, sample_digest=digest)

    message = None
    if row_count == 0:
        message = "This dataset has 0 rows — limited analytics are available."
    elif len(profiles) <= 1:
        message = "This dataset has limited analytical fields."

    return DatasetProfile(
        session_id=session_id,
        dataset_id=dataset_id,
        table=table,
        row_count=row_count,
        column_count=len(profiles),
        columns=profiles,
        fingerprint=fp,
        date_range=date_range,
        message=message,
    )
