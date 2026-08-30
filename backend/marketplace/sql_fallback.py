"""
Deterministic SQL fallbacks for MarketMind marketplace demo questions.

Used only when the LLM provider is unavailable (missing/invalid API key)
so Workspace analytics can still answer common demo questions against DuckDB.
"""
from __future__ import annotations

import re
from typing import Optional


def resolve_marketplace_sql(question: str) -> Optional[str]:
    """
    Return a read-only DuckDB SQL string for a well-known marketplace demo question,
    or None if no pattern matches.
    """
    q = (question or "").strip().lower()
    if not q:
        return None

    # Highest order value by product category (split order amount across supplier products)
    if (
        "categor" in q
        and ("order value" in q or "order_value" in q or "gmv" in q)
        and ("highest" in q or "top" in q or "most" in q or "generated" in q)
    ):
        return """
SELECT c.name AS category,
       ROUND(SUM(o.amount / NULLIF(cnt.n, 0)), 2) AS total_order_value
FROM orders o
JOIN (
    SELECT supplier_id, COUNT(*) AS n
    FROM products
    GROUP BY supplier_id
) cnt ON cnt.supplier_id = o.supplier_id
JOIN products p ON p.supplier_id = o.supplier_id
JOIN categories c ON c.id = p.category_id
GROUP BY c.name
ORDER BY total_order_value DESC
LIMIT 20
""".strip()

    # States with most buyer enquiries / leads
    if (
        ("state" in q or "states" in q)
        and (
            "enquir" in q
            or "lead" in q
            or "buyer" in q
        )
        and ("most" in q or "top" in q or "highest" in q or "generate" in q or "compare" in q)
    ):
        return """
SELECT state, COUNT(*) AS enquiry_count
FROM leads
GROUP BY state
ORDER BY enquiry_count DESC
LIMIT 20
""".strip()

    # Lead conversion by category
    if "conversion" in q and "categor" in q:
        return """
SELECT c.name AS category,
       COUNT(*) AS total_leads,
       SUM(CASE WHEN LOWER(l.status) IN ('won', 'converted', 'closed') THEN 1 ELSE 0 END) AS won_leads,
       ROUND(
         100.0 * SUM(CASE WHEN LOWER(l.status) IN ('won', 'converted', 'closed') THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*), 0),
         2
       ) AS conversion_rate_pct
FROM leads l
JOIN products p ON l.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY c.name
ORDER BY conversion_rate_pct DESC
LIMIT 20
""".strip()

    # Monthly GMV trends
    if "monthly" in q and ("gmv" in q or "trend" in q or "order" in q):
        return """
SELECT strftime(order_date, '%Y-%m') AS month,
       ROUND(SUM(amount), 2) AS gmv
FROM orders
GROUP BY month
ORDER BY month
""".strip()

    # Fastest supplier response times
    if "supplier" in q and ("response" in q or "fastest" in q):
        return """
SELECT name AS supplier,
       response_time_hours,
       rating,
       verified
FROM suppliers
ORDER BY response_time_hours ASC
LIMIT 20
""".strip()

    # High rating, low order volume suppliers
    if "rating" in q and "supplier" in q and ("low" in q or "order" in q):
        return """
SELECT s.name AS supplier,
       s.rating,
       COALESCE(SUM(o.amount), 0) AS order_volume
FROM suppliers s
LEFT JOIN orders o ON o.supplier_id = s.id
GROUP BY s.name, s.rating
HAVING s.rating >= 4.0
ORDER BY order_volume ASC, s.rating DESC
LIMIT 20
""".strip()

    # Top products by demand (leads)
    if "product" in q and ("demand" in q or "top" in q):
        return """
SELECT p.name AS product,
       c.name AS category,
       COUNT(l.id) AS enquiry_count,
       ROUND(SUM(l.estimated_value), 2) AS total_estimated_value
FROM leads l
JOIN products p ON l.product_id = p.id
JOIN categories c ON p.category_id = c.id
GROUP BY p.name, c.name
ORDER BY enquiry_count DESC
LIMIT 20
""".strip()

    # Generic category ranking fallback
    if re.search(r"\bcategor", q) and ("order" in q or "value" in q or "gmv" in q):
        return """
SELECT c.name AS category,
       ROUND(SUM(o.amount / NULLIF(cnt.n, 0)), 2) AS total_order_value
FROM orders o
JOIN (
    SELECT supplier_id, COUNT(*) AS n
    FROM products
    GROUP BY supplier_id
) cnt ON cnt.supplier_id = o.supplier_id
JOIN products p ON p.supplier_id = o.supplier_id
JOIN categories c ON c.id = p.category_id
GROUP BY c.name
ORDER BY total_order_value DESC
LIMIT 20
""".strip()

    return None
