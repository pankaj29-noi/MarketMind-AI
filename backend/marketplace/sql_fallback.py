"""
Schema-aware deterministic SQL for MarketMind marketplace analytics DEMO MODE.

This is NOT an LLM. It maps question *intent × entity* patterns onto safe
read-only DuckDB templates over the demo tables:

  categories, suppliers, buyers, products, leads, orders

Activated only when the live LLM provider is unavailable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set


MARKETPLACE_TABLES = (
    "categories",
    "suppliers",
    "buyers",
    "products",
    "leads",
    "orders",
)

EXAMPLE_QUESTIONS = (
    "Which product categories generated the highest order value?",
    "Which states generate the most buyer enquiries?",
    "Which suppliers have the highest number of orders?",
    "Which cities have the highest number of buyers?",
    "Which categories have the most leads?",
    "Which suppliers have the best average rating?",
)


@dataclass(frozen=True)
class FallbackResult:
    sql: Optional[str]
    """SQL to run, or None if the question cannot be answered safely."""
    reason: str
    """answerable | unsupported_domain | unsupported_schema | ambiguous"""
    analysis_source: str = "deterministic_fallback"


def _norm(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().lower())


def _limit(q: str, default: int = 20) -> int:
    m = re.search(r"\btop\s+(\d+)\b", q)
    if m:
        return max(1, min(50, int(m.group(1))))
    m = re.search(r"\b(\d+)\s+(products|suppliers|categories|cities|states|buyers)\b", q)
    if m:
        return max(1, min(50, int(m.group(1))))
    return default


def _has_any(q: str, words: Set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", q) for w in words)


def is_marketplace_domain_question(question: str) -> bool:
    """True when the question appears to target marketplace entities/metrics."""
    q = _norm(question)
    domain = {
        "category", "categories", "supplier", "suppliers", "buyer", "buyers",
        "product", "products", "lead", "leads", "enquiry", "enquiries", "inquiry",
        "inquiries", "order", "orders", "gmv", "sales", "revenue", "rating",
        "ratings", "city", "cities", "state", "states", "location", "locations",
        "marketplace", "conversion", "response",
    }
    return _has_any(q, domain)


def _entities(q: str) -> Set[str]:
    found: Set[str] = set()
    mapping = {
        "category": {"category", "categories"},
        "supplier": {"supplier", "suppliers"},
        "buyer": {"buyer", "buyers"},
        "product": {"product", "products"},
        "lead": {"lead", "leads", "enquiry", "enquiries", "inquiry", "inquiries"},
        "order": {"order", "orders", "gmv", "sales", "revenue"},
        "city": {"city", "cities"},
        "state": {"state", "states"},
        "location": {"location", "locations"},
        "rating": {"rating", "ratings"},
    }
    for ent, words in mapping.items():
        if _has_any(q, words):
            found.add(ent)
    # "sales/revenue" without product/supplier still implies order metric
    if _has_any(q, {"sales", "revenue", "gmv", "order value", "order_value"}):
        found.add("order")
    return found


def _wants_average(q: str) -> bool:
    return _has_any(q, {"average", "avg", "mean"})


def _wants_top(q: str) -> bool:
    return bool(
        re.search(r"\b(top|highest|most|best|largest|greatest|rank)\b", q)
        or re.search(r"\bgenerate[ds]?\b", q)
    )


def resolve_marketplace_sql(question: str) -> Optional[str]:
    """Backward-compatible helper — returns SQL or None. """
    return resolve_marketplace_fallback(question).sql


def resolve_marketplace_fallback(question: str) -> FallbackResult:
    """
    Map a natural-language question to a safe marketplace SQL template.

    Patterns are intent-based (count / sum / avg × entity), not a fixed FAQ list.
    """
    q = _norm(question)
    if not q:
        return FallbackResult(None, "ambiguous")

    # Clearly out-of-domain (weather, sports, etc.)
    if not is_marketplace_domain_question(q):
        return FallbackResult(None, "unsupported_domain")

    ents = _entities(q)
    lim = _limit(q)
    wants_avg = _wants_average(q)
    wants_top = _wants_top(q)

    # ── Category × order value / GMV / AOV ───────────────────────────────────
    if "category" in ents and ("order" in ents or _has_any(q, {"gmv", "sales", "revenue", "value"})):
        if wants_avg:
            sql = f"""
SELECT c.name AS category,
       ROUND(AVG(o.amount / NULLIF(cnt.n, 0)), 2) AS average_order_value
FROM orders o
JOIN (
    SELECT supplier_id, COUNT(*) AS n FROM products GROUP BY supplier_id
) cnt ON cnt.supplier_id = o.supplier_id
JOIN products p ON p.supplier_id = o.supplier_id
JOIN categories c ON c.id = p.category_id
GROUP BY c.name
ORDER BY average_order_value DESC
LIMIT {lim}
""".strip()
        else:
            sql = f"""
SELECT c.name AS category,
       ROUND(SUM(o.amount / NULLIF(cnt.n, 0)), 2) AS total_order_value
FROM orders o
JOIN (
    SELECT supplier_id, COUNT(*) AS n FROM products GROUP BY supplier_id
) cnt ON cnt.supplier_id = o.supplier_id
JOIN products p ON p.supplier_id = o.supplier_id
JOIN categories c ON c.id = p.category_id
GROUP BY c.name
ORDER BY total_order_value DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Category × leads ─────────────────────────────────────────────────────
    if "category" in ents and "lead" in ents:
        sql = f"""
SELECT c.name AS category,
       COUNT(l.id) AS lead_count
FROM leads l
JOIN products p ON l.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY c.name
ORDER BY lead_count DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── State × enquiries / leads / buyers ───────────────────────────────────
    if "state" in ents:
        if "lead" in ents or re.search(r"enquir|inquir", q):
            sql = f"""
SELECT state, COUNT(*) AS enquiry_count
FROM leads
GROUP BY state
ORDER BY enquiry_count DESC
LIMIT {lim}
""".strip()
            return FallbackResult(sql, "answerable")
        if "buyer" in ents:
            sql = f"""
SELECT state, COUNT(*) AS buyer_count
FROM buyers
GROUP BY state
ORDER BY buyer_count DESC
LIMIT {lim}
""".strip()
            return FallbackResult(sql, "answerable")

    # ── City × buyers ────────────────────────────────────────────────────────
    if "city" in ents and ("buyer" in ents or wants_top):
        sql = f"""
SELECT city, COUNT(*) AS buyer_count
FROM buyers
GROUP BY city
ORDER BY buyer_count DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Location × sales (prefer buyer state via orders) ─────────────────────
    if "location" in ents and "order" in ents:
        sql = f"""
SELECT b.state AS location,
       ROUND(SUM(o.amount), 2) AS total_sales
FROM orders o
JOIN buyers b ON o.buyer_id = b.id
GROUP BY b.state
ORDER BY total_sales DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Supplier × order count ───────────────────────────────────────────────
    if "supplier" in ents and "order" in ents and not _has_any(q, {"rating", "response"}):
        sql = f"""
SELECT s.name AS supplier,
       COUNT(o.id) AS order_count,
       ROUND(SUM(o.amount), 2) AS total_order_value
FROM orders o
JOIN suppliers s ON o.supplier_id = s.id
GROUP BY s.name
ORDER BY order_count DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Supplier × rating ────────────────────────────────────────────────────
    if "supplier" in ents and ("rating" in ents or _has_any(q, {"best", "highest", "top"})):
        if _has_any(q, {"response", "fastest"}):
            sql = f"""
SELECT name AS supplier, response_time_hours, rating, verified
FROM suppliers
ORDER BY response_time_hours ASC
LIMIT {lim}
""".strip()
        else:
            sql = f"""
SELECT name AS supplier, rating, verified, response_time_hours
FROM suppliers
ORDER BY rating DESC, response_time_hours ASC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Supplier response time ───────────────────────────────────────────────
    if "supplier" in ents and _has_any(q, {"response", "fastest"}):
        sql = f"""
SELECT name AS supplier, response_time_hours, rating, verified
FROM suppliers
ORDER BY response_time_hours ASC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Product popularity / revenue proxy via leads ─────────────────────────
    # Demo orders are supplier-scoped (no product_id); use leads for product metrics.
    if "product" in ents and (
        "order" in ents
        or "lead" in ents
        or _has_any(q, {"revenue", "sales", "demand", "top", "most"})
    ):
        if _has_any(q, {"revenue", "sales", "value", "gmv"}):
            sql = f"""
SELECT p.name AS product,
       c.name AS category,
       ROUND(SUM(l.estimated_value), 2) AS estimated_revenue
FROM leads l
JOIN products p ON l.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY p.name, c.name
ORDER BY estimated_revenue DESC
LIMIT {lim}
""".strip()
        else:
            sql = f"""
SELECT p.name AS product,
       c.name AS category,
       COUNT(l.id) AS enquiry_count
FROM leads l
JOIN products p ON l.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY p.name, c.name
ORDER BY enquiry_count DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Lead conversion by category ──────────────────────────────────────────
    if "conversion" in q and "category" in ents:
        sql = f"""
SELECT c.name AS category,
       COUNT(*) AS total_leads,
       SUM(CASE WHEN LOWER(l.status) IN ('won', 'converted', 'closed') THEN 1 ELSE 0 END) AS won_leads,
       ROUND(
         100.0 * SUM(CASE WHEN LOWER(l.status) IN ('won', 'converted', 'closed') THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*), 0), 2
       ) AS conversion_rate_pct
FROM leads l
JOIN products p ON l.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY c.name
ORDER BY conversion_rate_pct DESC
LIMIT {lim}
""".strip()
        return FallbackResult(sql, "answerable")

    # ── Monthly GMV ──────────────────────────────────────────────────────────
    if "monthly" in q and ("order" in ents or _has_any(q, {"gmv", "trend", "sales"})):
        sql = """
SELECT strftime(order_date, '%Y-%m') AS month,
       ROUND(SUM(amount), 2) AS gmv
FROM orders
GROUP BY month
ORDER BY month
""".strip()
        return FallbackResult(sql, "answerable")

    # Marketplace-flavored but no safe template
    return FallbackResult(None, "unsupported_schema")


def unsupported_user_message(reason: str) -> str:
    examples = "\n".join(f"• {q}" for q in EXAMPLE_QUESTIONS[:5])
    tables = ", ".join(MARKETPLACE_TABLES)
    if reason == "unsupported_domain":
        return (
            "I couldn't answer this question using the currently loaded marketplace dataset. "
            f"Available tables: {tables}. Try asking about products, suppliers, buyers, leads, orders, or categories.\n\n"
            f"Examples:\n{examples}"
        )
    return (
        "I couldn't complete this analysis with the current marketplace schema and available join paths. "
        f"Available tables: {tables}.\n\n"
        f"Try questions like:\n{examples}"
    )
