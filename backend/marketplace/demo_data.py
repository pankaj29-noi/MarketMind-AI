"""
MarketMind marketplace demo dataset helpers.

Loads multi-table CSV seed data into an existing DuckDB session and builds
a schema profile (with relationships) for the LangGraph agents.
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Any, Dict, List, Optional

from backend.services.session_manager import session_manager

logger = logging.getLogger(__name__)

MARKETPLACE_DATASET_ID = "marketplace"
MARKETPLACE_DATASET_NAME = "MarketMind Marketplace Demo"

# Ordered table list — stable for UI and schema context
MARKETPLACE_TABLES: List[str] = [
    "categories",
    "suppliers",
    "buyers",
    "products",
    "leads",
    "orders",
]

MARKETPLACE_RELATIONSHIPS: List[Dict[str, str]] = [
    {
        "from_table": "products",
        "from_column": "category_id",
        "to_table": "categories",
        "to_column": "id",
        "description": "products.category_id → categories.id",
    },
    {
        "from_table": "products",
        "from_column": "supplier_id",
        "to_table": "suppliers",
        "to_column": "id",
        "description": "products.supplier_id → suppliers.id",
    },
    {
        "from_table": "leads",
        "from_column": "buyer_id",
        "to_table": "buyers",
        "to_column": "id",
        "description": "leads.buyer_id → buyers.id",
    },
    {
        "from_table": "leads",
        "from_column": "product_id",
        "to_table": "products",
        "to_column": "id",
        "description": "leads.product_id → products.id",
    },
    {
        "from_table": "orders",
        "from_column": "buyer_id",
        "to_table": "buyers",
        "to_column": "id",
        "description": "orders.buyer_id → buyers.id",
    },
    {
        "from_table": "orders",
        "from_column": "supplier_id",
        "to_table": "suppliers",
        "to_column": "id",
        "description": "orders.supplier_id → suppliers.id",
    },
]


def get_marketplace_data_dir() -> str:
    """Absolute path to packaged marketplace CSV seed data."""
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "marketplace")
    )


def is_marketplace_dataset(dataset_id: Optional[str], dataset_name: Optional[str] = None) -> bool:
    """Detect whether a session is backed by the MarketMind demo dataset."""
    if dataset_id == MARKETPLACE_DATASET_ID:
        return True
    if dataset_name and "marketplace" in dataset_name.lower():
        return True
    return False


def _scratch_dir(session_id: str) -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "scratch", session_id)
    )


def _copy_seed_csvs_to_scratch(session_id: str) -> Dict[str, str]:
    """
    Copy seed CSVs into the session scratch directory for TTL restore.
    Returns mapping of table_name → absolute csv path.
    """
    data_dir = get_marketplace_data_dir()
    scratch = _scratch_dir(session_id)
    os.makedirs(scratch, exist_ok=True)

    paths: Dict[str, str] = {}
    for table in MARKETPLACE_TABLES:
        src = os.path.join(data_dir, f"{table}.csv")
        if not os.path.exists(src):
            raise FileNotFoundError(f"Marketplace seed CSV missing: {src}")
        dest = os.path.join(scratch, f"{table}.csv")
        shutil.copy2(src, dest)
        paths[table] = dest
    return paths


def load_marketplace_demo(session_id: str) -> Dict[str, Any]:
    """
    Register all marketplace CSV tables into the DuckDB session.

    Reuses SessionManager.register_csv for each table. Also copies CSVs into
    scratch/{session_id}/ so TTL eviction can restore the full multi-table set.
    """
    paths = _copy_seed_csvs_to_scratch(session_id)
    registered: List[str] = []
    table_stats: List[Dict[str, Any]] = []

    for table, csv_path in paths.items():
        session_manager.register_csv(session_id, csv_path, table)
        registered.append(table)
        count_rows = session_manager.execute_query(
            session_id, f"SELECT COUNT(*) AS cnt FROM {table};"
        )
        row_count = count_rows[0]["cnt"] if count_rows else 0
        schema_rows = session_manager.execute_query(
            session_id, f"PRAGMA table_info({table});"
        )
        columns = [{"name": r["name"], "dtype": r["type"]} for r in schema_rows]
        table_stats.append(
            {
                "name": table,
                "row_count": row_count,
                "columns": columns,
            }
        )
        logger.info(
            "Registered marketplace table %s (%s rows) for session %s",
            table,
            row_count,
            session_id,
        )

    total_rows = sum(t["row_count"] for t in table_stats)
    # Flattened column list for UI backward compatibility (prefix with table.)
    flat_columns = []
    for t in table_stats:
        for col in t["columns"]:
            flat_columns.append(
                {
                    "name": f"{t['name']}.{col['name']}",
                    "dtype": col["dtype"],
                    "table": t["name"],
                }
            )

    return {
        "session_id": session_id,
        "dataset_id": MARKETPLACE_DATASET_ID,
        "dataset_name": MARKETPLACE_DATASET_NAME,
        "tables": registered,
        "table_stats": table_stats,
        "row_count": total_rows,
        "columns": flat_columns,
        "relationships": MARKETPLACE_RELATIONSHIPS,
    }


def restore_marketplace_demo(session_id: str) -> bool:
    """
    Re-register marketplace tables after DuckDB session eviction.
    Returns True if restore succeeded.
    """
    scratch = _scratch_dir(session_id)
    # Prefer scratch copies; fall back to packaged seed data
    data_dir = get_marketplace_data_dir()
    try:
        for table in MARKETPLACE_TABLES:
            scratch_csv = os.path.join(scratch, f"{table}.csv")
            seed_csv = os.path.join(data_dir, f"{table}.csv")
            csv_path = scratch_csv if os.path.exists(scratch_csv) else seed_csv
            if not os.path.exists(csv_path):
                logger.error("Cannot restore marketplace table %s: CSV not found", table)
                return False
            if not os.path.exists(scratch_csv):
                os.makedirs(scratch, exist_ok=True)
                shutil.copy2(csv_path, scratch_csv)
                csv_path = scratch_csv
            session_manager.register_csv(session_id, csv_path, table)
        logger.info("Restored marketplace demo tables for session %s", session_id)
        return True
    except Exception as e:
        logger.error("Failed to restore marketplace demo for session %s: %s", session_id, e)
        return False


def build_marketplace_schema_profile(session_id: str) -> Dict[str, Any]:
    """
    Build a multi-table schema profile including relationships and sample values.
    """
    tables_payload: List[Dict[str, Any]] = []
    total_rows = 0

    for table in MARKETPLACE_TABLES:
        sample_values_map: Dict[str, List[Any]] = {}
        try:
            samples = session_manager.execute_query(
                session_id, f"SELECT * FROM {table} LIMIT 3;"
            )
            for row in samples:
                for col_name, val in row.items():
                    sample_values_map.setdefault(col_name, [])
                    if val is not None and val not in sample_values_map[col_name]:
                        sample_values_map[col_name].append(val)
        except Exception as e:
            logger.warning("Could not sample rows for %s: %s", table, e)

        info = session_manager.execute_query(session_id, f"PRAGMA table_info({table});")
        columns = [
            {
                "name": r["name"],
                "dtype": r["type"],
                "sample_values": sample_values_map.get(r["name"], []),
            }
            for r in info
        ]
        count_rows = session_manager.execute_query(
            session_id, f"SELECT COUNT(*) AS cnt FROM {table};"
        )
        row_count = count_rows[0]["cnt"] if count_rows else 0
        total_rows += row_count
        tables_payload.append(
            {
                "name": table,
                "columns": columns,
                "row_count": row_count,
            }
        )

    # Primary table for single-table backward-compat fields: products
    primary = next((t for t in tables_payload if t["name"] == "products"), tables_payload[0])

    return {
        "dataset_id": MARKETPLACE_DATASET_ID,
        "source": "csv",
        "multi_table": True,
        "tables": tables_payload,
        "relationships": MARKETPLACE_RELATIONSHIPS,
        "columns": primary["columns"],
        "row_count": total_rows,
        "relationship_notes": [
            r["description"] for r in MARKETPLACE_RELATIONSHIPS
        ],
    }


def format_schema_context_for_llm(schema_profile: Dict[str, Any], fallback_table: str = "") -> str:
    """
    Format schema_profile into an LLM-friendly multi-table (or single-table) string.
    Shared by planner and code generator.
    """
    if schema_profile.get("multi_table") and schema_profile.get("tables"):
        parts = [
            "MULTI-TABLE MARKETPLACE SCHEMA",
            "You may JOIN across these DuckDB tables using the relationships below.",
            "",
        ]
        for table in schema_profile["tables"]:
            parts.append(f"Table: {table['name']}  (rows: {table.get('row_count', 'unknown')})")
            for col in table.get("columns", []):
                samples = col.get("sample_values", [])
                samples_str = f" | Samples: {samples}" if samples else ""
                parts.append(f"  - {col['name']} ({col['dtype']}){samples_str}")
            parts.append("")

        rels = schema_profile.get("relationship_notes") or [
            r.get("description", "") for r in schema_profile.get("relationships", [])
        ]
        if rels:
            parts.append("RELATIONSHIPS (use these for JOINs):")
            for rel in rels:
                if rel:
                    parts.append(f"  - {rel}")
            parts.append("")

        parts.append(
            "IMPORTANT: Reference tables by their exact names "
            "(categories, suppliers, buyers, products, leads, orders). "
            "Do NOT invent a single unified table."
        )
        return "\n".join(parts)

    # Single-table fallback (existing CSV upload behaviour)
    table_name = schema_profile.get("dataset_id") or fallback_table
    columns_desc = ""
    for col in schema_profile.get("columns", []):
        samples = col.get("sample_values", [])
        samples_str = f" | Samples: {samples}" if samples else ""
        columns_desc += f"- {col['name']} ({col['dtype']}){samples_str}\n"

    return (
        f"Dataset Table Name: {table_name}\n"
        f"Total Rows: {schema_profile.get('row_count', 'unknown')}\n"
        f"Columns:\n{columns_desc}"
    )
