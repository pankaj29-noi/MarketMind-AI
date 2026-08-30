"""
Generic deterministic analytics fallback for DEMO MODE.

Supports:
  - MarketMind multi-table marketplace demos
  - Single-table uploaded CSV sessions

This is NOT an LLM. It inspects schema + question intent and emits safe
read-only DuckDB SQL templates. Prefer the real LLM pipeline whenever a
valid API key is configured.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.marketplace.demo_data import MARKETPLACE_DATASET_ID, is_marketplace_dataset
from backend.marketplace.sql_fallback import (
    FallbackResult,
    resolve_marketplace_fallback,
    unsupported_user_message as marketplace_unsupported_message,
)

logger = logging.getLogger(__name__)

ANALYSIS_SOURCE_FALLBACK = "deterministic_fallback"
ANALYSIS_SOURCE_LLM = "llm"  # legacy alias
ANALYSIS_SOURCE_GROQ = "groq"
ANALYSIS_SOURCE_GEMINI = "gemini"


@dataclass
class ColumnRoleMap:
    table: str
    columns: List[str]
    metrics: Dict[str, str]  # role -> column
    dimensions: Dict[str, str]
    date_col: Optional[str]


_METRIC_ALIASES: Dict[str, Tuple[str, ...]] = {
    "sales": ("sales_amount", "sales", "revenue", "amount", "order_value", "gmv", "total_sales"),
    "profit": ("profit", "margin", "net_profit"),
    "quantity": ("quantity", "qty", "units", "unit_count"),
    "orders": ("order_id", "orders", "order_count"),
    "rating": ("rating", "avg_rating", "score"),
    "discount": ("discount_rate", "discount", "discount_pct", "discount_percent"),
}

_DIM_ALIASES: Dict[str, Tuple[str, ...]] = {
    "category": ("category", "product_category", "category_name"),
    "product": ("product", "product_name", "item", "sku_name"),
    "supplier": ("supplier", "supplier_name", "vendor"),
    "city": ("city", "town"),
    "region": ("region", "state", "province"),
    "segment": ("customer_segment", "segment", "buyer_segment"),
    "channel": ("sales_channel", "channel", "source"),
    "customer": ("customer_id", "buyer_id", "customer"),
}

_DATE_ALIASES = (
    "order_date",
    "date",
    "created_at",
    "timestamp",
    "event_date",
    "sale_date",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _limit(q: str, default: int = 20) -> int:
    m = re.search(r"\btop\s+(\d+)\b", q)
    if m:
        return max(1, min(50, int(m.group(1))))
    m = re.search(r"\b(\d+)\s+(products?|categories|cities|regions|suppliers|segments|channels)\b", q)
    if m:
        return max(1, min(50, int(m.group(1))))
    return default


def _quote_ident(name: str) -> str:
    # DuckDB-safe identifier quoting
    return '"' + name.replace('"', '""') + '"'


def _ident(name: str) -> str:
    """Quote only when the identifier is not a plain SQL name."""
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or ""):
        return name
    return _quote_ident(name)


def _find_column(columns: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in columns}
    for alias in aliases:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    # fuzzy contains
    for alias in aliases:
        for c in columns:
            cl = c.lower()
            if alias.lower() in cl or cl in alias.lower():
                return c
    return None


def map_columns(table: str, columns: Sequence[str]) -> ColumnRoleMap:
    metrics: Dict[str, str] = {}
    for role, aliases in _METRIC_ALIASES.items():
        col = _find_column(columns, aliases)
        if col:
            metrics[role] = col
    dims: Dict[str, str] = {}
    for role, aliases in _DIM_ALIASES.items():
        col = _find_column(columns, aliases)
        if col:
            dims[role] = col
    date_col = _find_column(columns, _DATE_ALIASES)
    return ColumnRoleMap(
        table=table,
        columns=list(columns),
        metrics=metrics,
        dimensions=dims,
        date_col=date_col,
    )


def _pick_metric(q: str, roles: ColumnRoleMap) -> Optional[Tuple[str, str]]:
    """Return (role, column) for the metric mentioned in the question."""
    preference = []
    if re.search(r"\bprofit", q):
        preference.append("profit")
    if re.search(r"\b(sales|revenue|gmv|order value)\b", q):
        preference.append("sales")
    if re.search(r"\b(quantity|qty|units)\b", q):
        preference.append("quantity")
    if re.search(r"\brating\b", q):
        preference.append("rating")
    if re.search(r"\borders?\b", q) and not re.search(r"\border value\b", q):
        preference.append("orders")

    for role in preference:
        if role in roles.metrics:
            return role, roles.metrics[role]
    # defaults
    for role in ("sales", "profit", "quantity", "orders", "rating"):
        if role in roles.metrics:
            return role, roles.metrics[role]
    return None


def _pick_dimension(q: str, roles: ColumnRoleMap) -> Optional[Tuple[str, str]]:
    checks = [
        ("category", r"\bcategor"),
        ("product", r"\bproducts?\b"),
        ("supplier", r"\bsuppliers?\b"),
        ("city", r"\bcit(y|ies)\b"),
        ("region", r"\b(region|state|location)s?\b"),
        ("segment", r"\bsegment"),
        ("channel", r"\bchannel"),
        ("customer", r"\bcustomers?\b"),
    ]
    for role, pat in checks:
        if re.search(pat, q) and role in roles.dimensions:
            return role, roles.dimensions[role]
    # "by X" without explicit keyword — try common dims present
    if re.search(r"\bby\b", q):
        for role in ("category", "product", "city", "region", "segment", "channel", "supplier"):
            if role in roles.dimensions:
                return role, roles.dimensions[role]
    return None


def _agg_fn(q: str, metric_role: Optional[str]) -> str:
    if re.search(r"\b(average|avg|mean)\b", q):
        return "AVG"
    if re.search(r"\b(minimum|min|lowest|least)\b", q):
        return "MIN"
    if re.search(r"\b(maximum|max|highest|most|top|best)\b", q) and metric_role != "orders":
        # ranking uses SUM/COUNT + ORDER BY; for explicit max of a metric use MAX
        if re.search(r"\b(max|maximum)\b", q):
            return "MAX"
    if re.search(r"\b(count|how many|number of|total orders)\b", q) or metric_role == "orders":
        return "COUNT"
    if re.search(r"\b(sum|total|generated|revenue|sales|profit)\b", q):
        return "SUM"
    return "SUM" if metric_role in ("sales", "profit", "quantity") else "COUNT"


def _is_out_of_domain(q: str, roles: ColumnRoleMap) -> bool:
    marketplace_ish = bool(
        re.search(
            r"\b(categor(y|ies)|products?|suppliers?|buyers?|leads?|orders?|sales|"
            r"revenue|profit|cit(y|ies)|regions?|states?|segments?|channels?|"
            r"customers?|quantity|rating|gmv|discount|margin)\b",
            q,
        )
    )
    if marketplace_ish:
        return False
    # weather/sports/etc.
    if re.search(r"\b(weather|temperature|forecast|cricket|football|movie|news)\b", q):
        return True
    # no overlap with known columns tokens
    tokens = set(re.findall(r"[a-z0-9_]+", q))
    col_tokens = set()
    for c in roles.columns:
        col_tokens.update(re.findall(r"[a-z0-9_]+", c.lower()))
    if tokens & col_tokens:
        return False
    return not marketplace_ish


def _single_table_sql(question: str, roles: ColumnRoleMap) -> FallbackResult:
    q = _norm(question)
    if not q:
        return FallbackResult(None, "ambiguous", ANALYSIS_SOURCE_FALLBACK)

    if _is_out_of_domain(q, roles):
        return FallbackResult(None, "unsupported_domain", ANALYSIS_SOURCE_FALLBACK)

    # Predictive / causal questions are outside deterministic descriptive fallback
    if re.search(
        r"\b(predict|forecast|will become|next year|next month|what caused)\b"
        r"|\bcaus(?:e|ed|es)\b",
        q,
    ):
        return FallbackResult(None, "unsupported_schema", ANALYSIS_SOURCE_FALLBACK)

    table = _ident(roles.table)
    lim = _limit(q)
    sales_col = roles.metrics.get("sales")
    profit_col = roles.metrics.get("profit")
    discount_col = roles.metrics.get("discount")

    # Build optional WHERE from explicit filter phrases (matches requirement extraction)
    where_bits: List[str] = []
    city_filter = re.search(
        r"\bin\s+(delhi|mumbai|jaipur|pune|chennai|bangalore|bengaluru|hyderabad|kolkata)\b",
        q,
    )
    if city_filter and "city" in roles.dimensions:
        where_bits.append(
            f"LOWER(CAST({_ident(roles.dimensions['city'])} AS VARCHAR)) = '{city_filter.group(1)}'"
        )
    segment_filter = re.search(
        r"\bamong\s+(corporate|consumer|home\s+office|small\s+business)\b"
        r"|\b(corporate|consumer|home\s+office)\s+customers?\b",
        q,
    )
    if segment_filter and "segment" in roles.dimensions:
        seg = (segment_filter.group(1) or segment_filter.group(2) or "").strip()
        where_bits.append(
            f"LOWER(CAST({_ident(roles.dimensions['segment'])} AS VARCHAR)) LIKE '%{seg}%'"
        )
    channel_filter = re.search(
        r"\b(?:through|via|on|using)\s+(?:the\s+)?(online|retail|partner)\s+channel\b",
        q,
    )
    if channel_filter and "channel" in roles.dimensions:
        where_bits.append(
            f"LOWER(CAST({_ident(roles.dimensions['channel'])} AS VARCHAR)) = '{channel_filter.group(1)}'"
        )
    where_sql = (" WHERE " + " AND ".join(where_bits)) if where_bits else ""

    # Discount × profitability across categories (category-level, not global only)
    if (
        discount_col
        and profit_col
        and sales_col
        and re.search(r"\bdiscount", q)
        and re.search(r"\b(profit|margin|profitab)", q)
        and re.search(r"\bcategor", q)
        and "category" in roles.dimensions
    ):
        d = _ident(roles.dimensions["category"])
        disc = _ident(discount_col)
        s = _ident(sales_col)
        p = _ident(profit_col)
        sql = f"""
SELECT {d} AS category,
       ROUND(AVG({disc}), 4) AS avg_discount_rate,
       ROUND(SUM({s}), 2) AS total_sales,
       ROUND(SUM({p}), 2) AS total_profit,
       ROUND(SUM({p}) / NULLIF(SUM({s}), 0), 4) AS profit_margin
FROM {table}
GROUP BY {d}
ORDER BY avg_discount_rate DESC, profit_margin ASC
LIMIT {lim}
""".strip()
        # Inject filter if present
        if where_sql:
            sql = sql.replace(f"FROM {table}\nGROUP BY", f"FROM {table}{where_sql}\nGROUP BY")
        return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # Full per-dimension metrics (sales + profit + margin) without filtering
    if (
        sales_col
        and profit_col
        and re.search(r"\b(sales|revenue)\b", q)
        and re.search(r"\bprofit", q)
        and re.search(r"\b(each|for each|every|all segments|all categor|calculate total)\b", q)
    ):
        dim_role, dim_col = None, None
        for role in ("segment", "category", "city", "region", "channel", "product"):
            if role in roles.dimensions and (
                re.search(rf"\b{role}", q)
                or (role == "segment" and re.search(r"\bsegment", q))
                or (role == "category" and re.search(r"\bcategor", q))
                or (role == "city" and re.search(r"\bcit", q))
                or (role == "region" and re.search(r"\bregion", q))
            ):
                dim_role, dim_col = role, roles.dimensions[role]
                break
        if dim_col:
            d = _ident(dim_col)
            s = _ident(sales_col)
            p = _ident(profit_col)
            sql = f"""
SELECT {d} AS {dim_role},
       ROUND(SUM({s}), 2) AS total_sales,
       ROUND(SUM({p}), 2) AS total_profit,
       ROUND(SUM({p}) / NULLIF(SUM({s}), 0), 4) AS profit_margin
FROM {table}
GROUP BY {d}
ORDER BY total_sales DESC, profit_margin ASC
LIMIT {lim}
""".strip()
            return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # Top N by sales ∩ bottom N by profit margin (before generic high/low contrast)
    top_m = re.search(r"\btop\s+(\d+)\b", q)
    bot_m = re.search(r"\bbottom\s+(\d+)\b", q)
    if (
        sales_col
        and profit_col
        and top_m
        and bot_m
        and re.search(r"\b(sales|revenue)\b", q)
        and re.search(r"\b(profit|margin)\b", q)
    ):
        top_n = max(1, min(50, int(top_m.group(1))))
        bot_n = max(1, min(50, int(bot_m.group(1))))
        dim_role, dim_col = None, None
        for role in ("category", "city", "product", "region", "segment"):
            if role in roles.dimensions and (
                re.search(rf"\b{role}", q)
                or (role == "category" and re.search(r"\bcategor", q))
            ):
                dim_role, dim_col = role, roles.dimensions[role]
                break
        if dim_col is None and "category" in roles.dimensions:
            dim_role, dim_col = "category", roles.dimensions["category"]
        if dim_col:
            d = _ident(dim_col)
            s = _ident(sales_col)
            p = _ident(profit_col)
            sql = f"""
WITH base AS (
  SELECT {d} AS {dim_role},
         ROUND(SUM({s}), 2) AS total_sales,
         ROUND(SUM({p}), 2) AS total_profit,
         ROUND(SUM({p}) / NULLIF(SUM({s}), 0), 4) AS profit_margin
  FROM {table}{where_sql}
  GROUP BY {d}
),
ranked AS (
  SELECT *,
         RANK() OVER (ORDER BY total_sales DESC) AS sales_rank,
         RANK() OVER (ORDER BY profit_margin ASC) AS margin_rank
  FROM base
)
SELECT {dim_role}, total_sales, total_profit, profit_margin, sales_rank, margin_rank
FROM ranked
WHERE sales_rank <= {top_n}
  AND margin_rank <= {bot_n}
ORDER BY sales_rank, margin_rank
""".strip()
            return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # High sales / low profit contrast (must include BOTH metrics + margin)
    if (
        sales_col
        and profit_col
        and re.search(r"\b(sales|revenue)\b", q)
        and re.search(r"\bprofit", q)
        and re.search(r"\b(high|low|relative|compar|but|versus|vs|margin|strong|weak)\b", q)
    ):
        dim_role, dim_col = None, None
        for role in ("city", "category", "region", "segment", "channel", "product"):
            if role in roles.dimensions and (
                re.search(rf"\b{role}", q)
                or (role == "city" and re.search(r"\bcit", q))
                or (role == "category" and re.search(r"\bcategor", q))
                or (role == "segment" and re.search(r"\bsegment", q))
                or (role == "region" and re.search(r"\bregion", q))
            ):
                dim_role, dim_col = role, roles.dimensions[role]
                break
        if dim_col is None:
            for role in ("city", "category", "region", "segment", "product"):
                if role in roles.dimensions:
                    dim_role, dim_col = role, roles.dimensions[role]
                    break
        if dim_col:
            d = _ident(dim_col)
            s = _ident(sales_col)
            p = _ident(profit_col)
            sql = f"""
WITH city_metrics AS (
  SELECT {d} AS {dim_role},
         ROUND(SUM({s}), 2) AS total_sales,
         ROUND(SUM({p}), 2) AS total_profit,
         ROUND(SUM({p}) / NULLIF(SUM({s}), 0), 4) AS profit_margin
  FROM {table}{where_sql}
  GROUP BY {d}
),
stats AS (
  SELECT
    AVG(total_sales) AS avg_sales,
    AVG(profit_margin) AS avg_margin
  FROM city_metrics
)
SELECT c.{dim_role}, c.total_sales, c.total_profit, c.profit_margin
FROM city_metrics c, stats s
WHERE c.total_sales >= s.avg_sales
  AND c.profit_margin <= s.avg_margin
ORDER BY c.total_sales DESC, c.profit_margin ASC
LIMIT {lim}
""".strip()
            return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    metric = _pick_metric(q, roles)
    dim = _pick_dimension(q, roles)
    agg = _agg_fn(q, metric[0] if metric else None)

    # Total / count with no dimension
    if re.search(r"\b(how many|total|count|number of)\b", q) and not dim:
        if metric and metric[0] == "orders":
            col = _ident(metric[1])
            sql = f"SELECT COUNT(DISTINCT {col}) AS total_orders FROM {table}"
        elif metric and agg in ("SUM", "AVG", "MIN", "MAX"):
            col = _ident(metric[1])
            sql = f"SELECT ROUND({agg}({col}), 2) AS metric_value FROM {table}"
        else:
            sql = f"SELECT COUNT(*) AS row_count FROM {table}"
        return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # Monthly / quarterly / over-time (must run before generic top-N product fallback)
    if roles.date_col and re.search(
        r"\b(month|monthly|quarter|quarterly|over time|trend|daily|yearly)\b", q
    ):
        date_col = _ident(roles.date_col)
        if re.search(r"\bquarter", q):
            trunc = "%Y-Q"  # DuckDB strftime may need alternative; use date_trunc
            period_expr = f"CAST(date_trunc('quarter', CAST({date_col} AS DATE)) AS DATE)"
        elif re.search(r"\bdaily|day\b", q):
            period_expr = f"strftime(CAST({date_col} AS DATE), '%Y-%m-%d')"
        elif re.search(r"\byearly|year\b", q) and not re.search(r"\bmonth", q):
            period_expr = f"strftime(CAST({date_col} AS DATE), '%Y')"
        else:
            period_expr = f"strftime(CAST({date_col} AS DATE), '%Y-%m')"

        if re.search(r"\bprofit\s*margin|profitability|margin\b", q) and sales_col and profit_col:
            s = _ident(sales_col)
            p = _ident(profit_col)
            metric_expr = f"ROUND(SUM({p}) / NULLIF(SUM({s}), 0), 4)"
            alias = "profit_margin"
        elif metric:
            mcol = _ident(metric[1])
            metric_expr = f"ROUND(SUM({mcol}), 2)" if agg != "COUNT" else f"COUNT({mcol})"
            alias = "total_sales" if metric[0] == "sales" else "metric_value"
        else:
            metric_expr = "COUNT(*)"
            alias = "row_count"

        if re.search(r"\b(highest|lowest|largest|decline|drop)\b", q):
            order = f"ORDER BY {alias} DESC"
            if re.search(r"\b(lowest|decline|drop)\b", q) and not re.search(r"\bhighest\b", q):
                # For decline questions still return chronologically ordered periods with metric
                order = "ORDER BY period"
        else:
            order = "ORDER BY period"

        sql = f"""
SELECT {period_expr} AS period,
       {metric_expr} AS {alias}
FROM {table}{where_sql}
GROUP BY period
{order}
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # Grouped ranking / aggregation
    if dim:
        dcol = _ident(dim[1])
        # Prefer profit_margin when explicitly requested
        if (
            re.search(r"\bprofit\s*margin|profitability\b", q)
            and sales_col
            and profit_col
            and dim[0] in ("product", "category", "segment", "city", "region", "channel")
        ):
            s = _ident(sales_col)
            p = _ident(profit_col)
            order = "ASC" if re.search(r"\b(lowest|least|minimum|min|worst)\b", q) else "DESC"
            sql = f"""
SELECT {dcol} AS {dim[0]},
       ROUND(SUM({s}), 2) AS total_sales,
       ROUND(SUM({p}), 2) AS total_profit,
       ROUND(SUM({p}) / NULLIF(SUM({s}), 0), 4) AS profit_margin
FROM {table}{where_sql}
GROUP BY {dcol}
ORDER BY profit_margin {order}
LIMIT {lim}
""".strip()
            return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

        if metric:
            mcol = _ident(metric[1])
            if agg == "COUNT":
                expr = f"COUNT({mcol})"
            else:
                expr = f"ROUND({agg}({mcol}), 2)"
            alias = f"{agg.lower()}_{metric[0]}"
        else:
            expr = "COUNT(*)"
            alias = "row_count"

        order = "ASC" if re.search(r"\b(lowest|least|minimum|min|worst)\b", q) else "DESC"
        sql = f"""
SELECT {dcol} AS {dim[0]},
       {expr} AS {alias}
FROM {table}{where_sql}
GROUP BY {dcol}
ORDER BY {alias} {order}
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # Top N rows by metric without explicit dimension (use product/category if present)
    if metric and re.search(r"\b(top|highest|most|best)\b", q):
        # Prefer product/category as label
        label_role = None
        for cand in ("product", "category", "supplier", "city"):
            if cand in roles.dimensions:
                label_role = cand
                break
        mcol = _ident(metric[1])
        if label_role:
            dcol = _ident(roles.dimensions[label_role])
            sql = f"""
SELECT {dcol} AS {label_role},
       ROUND(SUM({mcol}), 2) AS total_{metric[0]}
FROM {table}
GROUP BY {dcol}
ORDER BY total_{metric[0]} DESC
LIMIT {lim}
""".strip()
        else:
            sql = f"""
SELECT *
FROM {table}
ORDER BY {mcol} DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    # Compare channels / segments phrasing without "by"
    if re.search(r"\bcompare\b", q):
        for role in ("channel", "segment", "region", "category"):
            if role in roles.dimensions and "sales" in roles.metrics:
                dcol = _ident(roles.dimensions[role])
                mcol = _ident(roles.metrics["sales"])
                sql = f"""
SELECT {dcol} AS {role},
       ROUND(SUM({mcol}), 2) AS total_sales
FROM {table}
GROUP BY {dcol}
ORDER BY total_sales DESC
LIMIT {lim}
""".strip()
                return FallbackResult(sql, "answerable", ANALYSIS_SOURCE_FALLBACK)

    return FallbackResult(None, "unsupported_schema", ANALYSIS_SOURCE_FALLBACK)


def _columns_from_schema(schema_profile: Dict[str, Any], dataset_id: str) -> Tuple[str, List[str]]:
    """Return (table_name, column_names) from a schema profile."""
    if schema_profile.get("multi_table") or is_marketplace_dataset(dataset_id):
        return MARKETPLACE_DATASET_ID, []

    cols = schema_profile.get("columns") or []
    names = [c["name"] if isinstance(c, dict) else str(c) for c in cols]
    table = schema_profile.get("dataset_id") or dataset_id
    return str(table), names


def resolve_analytics_fallback(
    question: str,
    schema_profile: Optional[Dict[str, Any]],
    dataset_id: Optional[str],
) -> FallbackResult:
    """
    Entry point for DEMO MODE analytics SQL generation.
    """
    schema_profile = schema_profile or {}
    dataset_id = dataset_id or schema_profile.get("dataset_id") or ""

    # Multi-table marketplace
    if schema_profile.get("multi_table") or is_marketplace_dataset(dataset_id):
        return resolve_marketplace_fallback(question)

    table, columns = _columns_from_schema(schema_profile, dataset_id)
    if not table or not columns:
        # Attempt marketplace fallback anyway if id suggests it
        if is_marketplace_dataset(dataset_id):
            return resolve_marketplace_fallback(question)
        return FallbackResult(None, "ambiguous", ANALYSIS_SOURCE_FALLBACK)

    roles = map_columns(table, columns)
    return _single_table_sql(question, roles)


def unsupported_analytics_message(
    reason: str,
    schema_profile: Optional[Dict[str, Any]] = None,
    dataset_id: Optional[str] = None,
) -> str:
    schema_profile = schema_profile or {}
    if schema_profile.get("multi_table") or is_marketplace_dataset(dataset_id or ""):
        return marketplace_unsupported_message(reason)

    cols = [c["name"] if isinstance(c, dict) else str(c) for c in (schema_profile.get("columns") or [])]
    col_preview = ", ".join(cols[:12]) if cols else "the loaded CSV columns"
    return (
        "I can analyze the currently loaded dataset, but this question requires information "
        "that is not present in it (or could not be mapped safely).\n\n"
        f"Available columns include: {col_preview}.\n\n"
        "Try asking about totals, averages, top-N rankings, or breakdowns by category, "
        "city, region, segment, or channel."
    )
