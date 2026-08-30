"""
DuckDB product & supplier matching helpers for Lead Intelligence.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.services.session_manager import session_manager

logger = logging.getLogger(__name__)

# Common Indian city → state hints for enrichment (not invention of products)
CITY_STATE_MAP = {
    "jaipur": "Rajasthan",
    "jodhpur": "Rajasthan",
    "udaipur": "Rajasthan",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "noida": "Uttar Pradesh",
    "mumbai": "Maharashtra",
    "pune": "Maharashtra",
    "nagpur": "Maharashtra",
    "bengaluru": "Karnataka",
    "bangalore": "Karnataka",
    "chennai": "Tamil Nadu",
    "coimbatore": "Tamil Nadu",
    "hyderabad": "Telangana",
    "ahmedabad": "Gujarat",
    "surat": "Gujarat",
    "kolkata": "West Bengal",
    "indore": "Madhya Pradesh",
    "lucknow": "Uttar Pradesh",
    "chandigarh": "Chandigarh",
    "kochi": "Kerala",
}


def ensure_marketplace_session(session_id: Optional[str]) -> str:
    """
    Ensure a DuckDB session has marketplace tables loaded.
    Reuses existing session_id when possible; otherwise creates a new demo session.
    """
    import uuid
    from backend.marketplace.demo_data import (
        MARKETPLACE_DATASET_ID,
        MARKETPLACE_DATASET_NAME,
        MARKETPLACE_TABLES,
        is_marketplace_dataset,
        load_marketplace_demo,
        restore_marketplace_demo,
    )
    from backend.database.repository import create_session, get_session

    if session_id:
        # Already have tables in memory?
        try:
            if session_id in session_manager.sessions:
                sess = session_manager.get_session(session_id)
                if all(t in sess.registered_tables for t in MARKETPLACE_TABLES):
                    return session_id
            record = get_session(session_id)
            if record and is_marketplace_dataset(record.get("dataset_id"), record.get("dataset_name")):
                if restore_marketplace_demo(session_id):
                    return session_id
            # Session exists but isn't marketplace — still try restore if tables present
            if session_id in session_manager.sessions:
                sess = session_manager.get_session(session_id)
                if "products" in sess.registered_tables and "suppliers" in sess.registered_tables:
                    return session_id
        except Exception as e:
            logger.warning("Could not reuse session %s: %s", session_id, e)

    new_id = str(uuid.uuid4())
    load_marketplace_demo(new_id)
    create_session(
        session_id=new_id,
        dataset_id=MARKETPLACE_DATASET_ID,
        dataset_name=MARKETPLACE_DATASET_NAME,
    )
    return new_id


def _tokenize(text: str) -> List[str]:
    stop = {
        "a", "an", "the", "for", "my", "our", "to", "in", "of", "and", "or",
        "need", "needs", "looking", "require", "required", "want", "wanted",
        "buy", "purchase", "bulk", "within", "with", "from", "please", "i",
        "we", "me", "some", "any", "high", "quality",
    }
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: List[str] = []
    for t in tokens:
        if len(t) <= 1 or t in stop:
            continue
        # Light plural fold so "pumps" matches "pump", "panels"→"panel"
        if t.endswith("s") and len(t) > 3 and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def _token_overlap_score(query_tokens: List[str], candidate: str) -> float:
    if not query_tokens:
        return 0.0
    cand_tokens = set(_tokenize(candidate))
    if not cand_tokens:
        return 0.0
    qset = set(query_tokens)
    inter = qset & cand_tokens
    if not inter:
        # substring soft match (also try singularized candidate text)
        cl = candidate.lower()
        hits = sum(1 for t in qset if t in cl)
        return hits / max(len(qset), 1) * 0.7
    return len(inter) / max(len(qset), 1)


def _expand_query_tokens(tokens: List[str], product_name: Optional[str], product_category: Optional[str]) -> List[str]:
    """Add light synonym expansions for common B2B phrases."""
    expanded = list(tokens)
    blob = " ".join(filter(None, [product_name, product_category, " ".join(tokens)])).lower()
    synonyms = {
        "pump": ["pump", "centrifugal", "submersible"],
        "packaging": ["packaging", "carton", "box", "corrugated", "wrap"],
        "boxes": ["box", "carton", "packaging"],
        "agricultural": ["agricultural", "agriculture", "farm", "tractor", "weeder", "harrow"],
        "machines": ["machine", "equipment"],
        "solar": ["solar", "panel", "pv", "inverter"],
        "panels": ["panel", "solar"],
    }
    for key, syns in synonyms.items():
        if key in blob or any(key in t for t in tokens):
            for s in syns:
                if s not in expanded:
                    expanded.append(s)
    return expanded


def search_products(
    session_id: str,
    product_name: Optional[str],
    product_category: Optional[str],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """
    Fuzzy/partial product matching via DuckDB ILIKE + token overlap ranking.
    """
    query_bits = " ".join(filter(None, [product_name, product_category])).strip()
    if not query_bits:
        return []

    tokens = _expand_query_tokens(_tokenize(query_bits), product_name, product_category)

    # Multi-pass retrieval so common tokens like "industrial" don't crowd out better matches
    row_map: Dict[int, Dict[str, Any]] = {}

    def _ingest(sql: str, params: List[Any]) -> None:
        try:
            rows = session_manager.execute_query(session_id, sql, params)
        except Exception as e:
            logger.error("Product search query failed: %s", e)
            return
        for row in rows:
            pid = int(row["product_id"])
            if pid not in row_map:
                row_map[pid] = row

    base_select = """
        SELECT
            p.id AS product_id,
            p.name AS name,
            p.category_id AS category_id,
            c.name AS category_name,
            p.supplier_id AS supplier_id,
            p.price AS price,
            p.moq AS moq,
            p.stock AS stock
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
    """

    # Pass 1: full phrase (+ singularized phrase for "pumps" vs "pump")
    phrase = (product_name or query_bits).lower()
    phrases = {phrase}
    if phrase.endswith("s") and len(phrase) > 4:
        phrases.add(phrase[:-1])
    for ph in phrases:
        _ingest(
            base_select + " WHERE LOWER(p.name) LIKE ? OR LOWER(c.name) LIKE ? LIMIT 40",
            [f"%{ph}%", f"%{ph}%"],
        )

    # Pass 2: require all core tokens in name (strong match)
    # Prefer tokens from product_name so category words don't over-constrain
    core_source = product_name or query_bits
    core_tokens = _tokenize(core_source)[:4] or tokens[:4]
    if len(core_tokens) >= 2:
        and_clauses = " AND ".join(["LOWER(p.name) LIKE ?"] * len(core_tokens))
        _ingest(
            base_select + f" WHERE {and_clauses} LIMIT 40",
            [f"%{t}%" for t in core_tokens],
        )

    # Pass 3: OR over tokens (broader recall)
    like_clauses = []
    params: List[Any] = []
    for tok in tokens[:8]:
        like_clauses.append("LOWER(p.name) LIKE ?")
        params.append(f"%{tok}%")
        like_clauses.append("LOWER(c.name) LIKE ?")
        params.append(f"%{tok}%")
    if like_clauses:
        _ingest(
            base_select + f" WHERE {' OR '.join(like_clauses)} LIMIT 120",
            params,
        )

    if not row_map:
        return []

    # Score primarily on product_name so category labels don't drown product intent
    # (e.g. "Industrial Equipment" must not outrank "water pump" name matches).
    score_tokens = _tokenize(product_name or "") or _tokenize(query_bits) or tokens
    # Drop ultra-generic tokens that appear in many industrial SKUs
    generic = {"industrial", "equipment", "product", "products", "material", "materials"}
    distinctive = [t for t in score_tokens if t not in generic]
    if distinctive:
        score_tokens = distinctive

    scored: List[Dict[str, Any]] = []
    for row in row_map.values():
        name = str(row.get("name") or "")
        cat = str(row.get("category_name") or "")
        name_score = _token_overlap_score(score_tokens, name)
        cat_score = 0.0
        if product_category and cat:
            if (
                product_category.lower() in cat.lower()
                or cat.lower() in product_category.lower()
            ):
                cat_score = 0.25  # soft boost only
            else:
                cat_score = _token_overlap_score(_tokenize(product_category), cat) * 0.4
        score = min(1.0, name_score + cat_score)
        if product_name and product_name.lower().rstrip("s") in name.lower():
            score = max(score, 0.95)
        # Soft boost when synonym tokens appear in the product name
        syn_hits = sum(1 for t in tokens if t not in score_tokens and t in name.lower())
        if syn_hits:
            score = min(1.0, score + 0.05 * syn_hits)
        if score < 0.25:
            continue
        reason_parts = []
        if name_score >= cat_score:
            reason_parts.append("name match")
        if cat_score >= 0.2:
            reason_parts.append(f"category '{cat}'")
        scored.append(
            {
                "product_id": int(row["product_id"]),
                "name": name,
                "category_id": row.get("category_id"),
                "category_name": cat or None,
                "supplier_id": int(row["supplier_id"]),
                "price": float(row["price"]) if row.get("price") is not None else None,
                "moq": int(row["moq"]) if row.get("moq") is not None else None,
                "stock": int(row["stock"]) if row.get("stock") is not None else None,
                "match_score": round(float(score), 4),
                "match_reason": ", ".join(reason_parts) or "partial match",
            }
        )

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:limit]


def fetch_supplier_candidates(
    session_id: str,
    matched_products: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Aggregate suppliers linked to matched products + order stats."""
    if not matched_products:
        return []

    supplier_products: Dict[int, List[Dict[str, Any]]] = {}
    for p in matched_products:
        sid = int(p["supplier_id"])
        supplier_products.setdefault(sid, []).append(p)

    supplier_ids = list(supplier_products.keys())
    placeholders = ", ".join(["?"] * len(supplier_ids))

    suppliers_sql = f"""
        SELECT id, name, city, state, rating, verified, response_time_hours
        FROM suppliers
        WHERE id IN ({placeholders})
    """
    suppliers = session_manager.execute_query(session_id, suppliers_sql, supplier_ids)
    supplier_map = {int(s["id"]): s for s in suppliers}

    orders_sql = f"""
        SELECT
            supplier_id,
            COUNT(*) AS total_orders,
            SUM(CASE WHEN LOWER(status) IN ('delivered', 'confirmed', 'shipped') THEN 1 ELSE 0 END) AS good_orders
        FROM orders
        WHERE supplier_id IN ({placeholders})
        GROUP BY supplier_id
    """
    try:
        order_rows = session_manager.execute_query(session_id, orders_sql, supplier_ids)
    except Exception as e:
        logger.warning("Order stats unavailable: %s", e)
        order_rows = []
    order_map = {
        int(r["supplier_id"]): {
            "total_orders": int(r["total_orders"] or 0),
            "good_orders": int(r["good_orders"] or 0),
        }
        for r in order_rows
    }

    candidates: List[Dict[str, Any]] = []
    for sid, products in supplier_products.items():
        s = supplier_map.get(sid)
        if not s:
            continue
        best_match = max(float(p["match_score"]) for p in products)
        stats = order_map.get(sid, {"total_orders": 0, "good_orders": 0})
        verified = s.get("verified")
        if isinstance(verified, str):
            verified_bool = verified.lower() in ("true", "1", "yes")
        else:
            verified_bool = bool(verified)
        candidates.append(
            {
                "supplier_id": sid,
                "name": s.get("name"),
                "city": s.get("city"),
                "state": s.get("state"),
                "rating": float(s["rating"]) if s.get("rating") is not None else None,
                "verified": verified_bool,
                "response_time_hours": (
                    float(s["response_time_hours"])
                    if s.get("response_time_hours") is not None
                    else None
                ),
                "matching_products": [p["name"] for p in products],
                "matching_product_ids": [p["product_id"] for p in products],
                "best_product_match_score": best_match,
                "total_orders": stats["total_orders"],
                "good_orders": stats["good_orders"],
            }
        )
    return candidates
