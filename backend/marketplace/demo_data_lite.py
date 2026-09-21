"""
Built-in single-table Demo Data helpers.

Loads a small (~40-row) marketplace-style CSV only when requested.
Suggested questions are derived from the real schema and verified by executing
read-only SQL against the session DuckDB — never hardcoded answers.
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.services.session_manager import session_manager

logger = logging.getLogger(__name__)

DEMO_DATA_DATASET_ID = "demo_data"
DEMO_DATA_DATASET_NAME = "Demo Data"
DEMO_DATA_CSV = "demo_data.csv"
DEMO_DATA_KIND = "builtin_demo_data"


def get_demo_data_csv_path() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", DEMO_DATA_CSV)
    )


def is_demo_data_dataset(
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
) -> bool:
    if dataset_id == DEMO_DATA_DATASET_ID:
        return True
    if dataset_name and dataset_name.strip().lower() == DEMO_DATA_DATASET_NAME.lower():
        return True
    return False


def _scratch_dir(session_id: str) -> str:
    from backend.config import get_scratch_root

    return os.path.abspath(os.path.join(str(get_scratch_root()), session_id))


def load_demo_data(session_id: str) -> Dict[str, Any]:
    """
    Load packaged Demo Data CSV into a fresh DuckDB session and warm-start schema.

    Does NOT precompute answers. Questions still run through POST /analyze.
    """
    src = get_demo_data_csv_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"Demo Data CSV missing: {src}")

    scratch = _scratch_dir(session_id)
    os.makedirs(scratch, exist_ok=True)
    dest = os.path.join(scratch, DEMO_DATA_CSV)
    shutil.copy2(src, dest)

    table = DEMO_DATA_DATASET_ID
    session_manager.register_csv(session_id, dest, table)

    from backend.services.analytics_perf import get_or_build_csv_schema_profile

    profile = get_or_build_csv_schema_profile(session_id, table)
    columns = profile.get("columns") or []
    return {
        "session_id": session_id,
        "dataset_id": table,
        "dataset_name": DEMO_DATA_DATASET_NAME,
        "tables": [table],
        "table_stats": [
            {
                "name": table,
                "row_count": profile.get("row_count", 0),
                "columns": [
                    {"name": c.get("name"), "dtype": c.get("dtype")} for c in columns
                ],
            }
        ],
        "row_count": profile.get("row_count", 0),
        "columns": columns,
        "relationships": [],
        "fingerprint": profile.get("fingerprint"),
        "demo_kind": DEMO_DATA_KIND,
        "is_demo_data": True,
        "warm_start": {
            "schema_profiled": True,
            "column_count": profile.get("column_count") or len(columns),
        },
    }


def _col_map(columns: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Lowercase name → actual column name."""
    out: Dict[str, str] = {}
    for c in columns:
        name = c.get("name") if isinstance(c, dict) else None
        if isinstance(name, str) and name:
            out[name.lower()] = name
    return out


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def build_schema_grounded_candidates(
    columns: Sequence[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """
    Build candidate questions only from columns that exist.

    Returns dicts: {id, question, intent} — no SQL answers.
    """
    cols = _col_map(columns)
    candidates: List[Dict[str, str]] = []

    def has(*names: str) -> bool:
        return all(n.lower() in cols for n in names)

    if has("revenue"):
        candidates.append(
            {
                "id": "total_revenue",
                "intent": "aggregate",
                "question": f"What is the total {cols['revenue']}?",
            }
        )
    if has("profit"):
        candidates.append(
            {
                "id": "total_profit",
                "intent": "aggregate",
                "question": f"What is the total {cols['profit']}?",
            }
        )
    if has("product", "revenue"):
        candidates.append(
            {
                "id": "top_product",
                "intent": "top_n",
                "question": (
                    f"Which {cols['product']} has the highest total {cols['revenue']}?"
                ),
            }
        )
    if has("region", "revenue"):
        candidates.append(
            {
                "id": "best_region",
                "intent": "top_n",
                "question": (
                    f"Which {cols['region']} has the highest total {cols['revenue']}?"
                ),
            }
        )
    if has("supplier", "revenue"):
        candidates.append(
            {
                "id": "best_supplier",
                "intent": "top_n",
                "question": (
                    f"Which {cols['supplier']} has the highest total {cols['revenue']}?"
                ),
            }
        )
    if has("category", "revenue"):
        candidates.append(
            {
                "id": "sales_by_category",
                "intent": "group_by",
                "question": (
                    f"What is total {cols['revenue']} by {cols['category']}?"
                ),
            }
        )
    if has("order_date", "revenue"):
        candidates.append(
            {
                "id": "revenue_by_month",
                "intent": "time_series",
                "question": (
                    f"Show total {cols['revenue']} by month using {cols['order_date']}."
                ),
            }
        )
    if has("quantity"):
        candidates.append(
            {
                "id": "avg_quantity",
                "intent": "aggregate",
                "question": f"What is the average {cols['quantity']} per order?",
            }
        )
    # Cap at 8
    return candidates[:8]


def _verification_sql_for_candidate(
    candidate_id: str,
    columns: Sequence[Dict[str, Any]],
    table: str,
) -> Optional[str]:
    """
    Schema-safe verification SQL for suggestion gating only.

    Final user answers still go through /analyze (SQLCoder + DuckDB).
    """
    cols = _col_map(columns)
    t = _qident(table)

    def c(name: str) -> str:
        return _qident(cols[name])

    if candidate_id == "total_revenue" and "revenue" in cols:
        return f"SELECT SUM({c('revenue')}) AS total_revenue FROM {t}"
    if candidate_id == "total_profit" and "profit" in cols:
        return f"SELECT SUM({c('profit')}) AS total_profit FROM {t}"
    if candidate_id == "top_product" and "product" in cols and "revenue" in cols:
        return (
            f"SELECT {c('product')} AS product, SUM({c('revenue')}) AS total_revenue "
            f"FROM {t} GROUP BY {c('product')} ORDER BY total_revenue DESC LIMIT 1"
        )
    if candidate_id == "best_region" and "region" in cols and "revenue" in cols:
        return (
            f"SELECT {c('region')} AS region, SUM({c('revenue')}) AS total_revenue "
            f"FROM {t} GROUP BY {c('region')} ORDER BY total_revenue DESC LIMIT 1"
        )
    if candidate_id == "best_supplier" and "supplier" in cols and "revenue" in cols:
        return (
            f"SELECT {c('supplier')} AS supplier, SUM({c('revenue')}) AS total_revenue "
            f"FROM {t} GROUP BY {c('supplier')} ORDER BY total_revenue DESC LIMIT 1"
        )
    if candidate_id == "sales_by_category" and "category" in cols and "revenue" in cols:
        return (
            f"SELECT {c('category')} AS category, SUM({c('revenue')}) AS total_revenue "
            f"FROM {t} GROUP BY {c('category')} ORDER BY total_revenue DESC"
        )
    if candidate_id == "revenue_by_month" and "order_date" in cols and "revenue" in cols:
        return (
            f"SELECT date_trunc('month', CAST({c('order_date')} AS DATE)) AS month, "
            f"SUM({c('revenue')}) AS total_revenue FROM {t} "
            f"GROUP BY 1 ORDER BY 1"
        )
    if candidate_id == "avg_quantity" and "quantity" in cols:
        return f"SELECT AVG({c('quantity')}) AS avg_quantity FROM {t}"
    return None


def verify_demo_suggested_questions(
    session_id: str,
    dataset_id: str,
    schema_profile: Optional[Dict[str, Any]] = None,
    *,
    max_questions: int = 8,
) -> List[Dict[str, Any]]:
    """
    Derive candidates from schema, validate SQL, execute against session DuckDB.

    Returns verified suggestion payloads WITHOUT numerical answers
    (answers come from /analyze only).
    """
    from backend.services.sql.sql_quality_validator import validate_sql
    from backend.mcp.data_access import _assert_read_only_sql

    if schema_profile is None:
        from backend.services.analytics_perf import get_or_build_csv_schema_profile

        schema_profile = get_or_build_csv_schema_profile(session_id, dataset_id)

    columns = schema_profile.get("columns") or []
    schema_for_val = dict(schema_profile)
    schema_for_val.setdefault("dataset_id", dataset_id)

    verified: List[Dict[str, Any]] = []
    for cand in build_schema_grounded_candidates(columns):
        if len(verified) >= max_questions:
            break
        sql = _verification_sql_for_candidate(cand["id"], columns, dataset_id)
        if not sql:
            continue
        try:
            _assert_read_only_sql(sql)
        except Exception as e:
            logger.warning("Demo suggestion rejected (not read-only): %s", e)
            continue

        quality = validate_sql(sql, schema_for_val, cand["question"])
        if not quality.get("is_valid"):
            logger.warning(
                "Demo suggestion %s failed schema validation: %s",
                cand["id"],
                quality.get("diagnostics"),
            )
            continue

        try:
            rows = session_manager.execute_query(session_id, sql)
        except Exception as e:
            logger.warning("Demo suggestion %s failed execution: %s", cand["id"], e)
            continue

        if not rows:
            logger.warning("Demo suggestion %s returned empty result", cand["id"])
            continue

        verified.append(
            {
                "id": cand["id"],
                "question": cand["question"],
                "intent": cand["intent"],
                "verified": True,
                "tier": "quick",
                # Provenance only — never include computed answer values here
                "verification": {
                    "row_count": len(rows),
                    "columns": list(rows[0].keys()) if rows else [],
                    "sql_validated": True,
                },
            }
        )

    return verified


def independent_ground_truth(
    session_id: str,
    dataset_id: str,
    metric: str,
) -> Any:
    """DuckDB ground truth for tests — never used as a hardcoded UI answer."""
    t = _qident(dataset_id)
    if metric == "total_revenue":
        rows = session_manager.execute_query(
            session_id, f"SELECT SUM(revenue) AS v FROM {t}"
        )
        return rows[0]["v"] if rows else None
    if metric == "total_profit":
        rows = session_manager.execute_query(
            session_id, f"SELECT SUM(profit) AS v FROM {t}"
        )
        return rows[0]["v"] if rows else None
    if metric == "top_product":
        rows = session_manager.execute_query(
            session_id,
            f"SELECT product AS v FROM {t} GROUP BY product "
            f"ORDER BY SUM(revenue) DESC LIMIT 1",
        )
        return rows[0]["v"] if rows else None
    raise ValueError(metric)
