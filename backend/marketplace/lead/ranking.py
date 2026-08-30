"""
Deterministic supplier ranking for MarketMind Lead Intelligence.

Scoring formula (weights sum to 1.0):

  final_score =
      0.35 * product_match_score      # best product text/category match in [0,1]
    + 0.20 * rating_score             # supplier.rating / 5.0
    + 0.15 * verified_score           # 1.0 if verified else 0.0
    + 0.15 * response_time_score      # faster response → higher (1 - hours/72 clamped)
    + 0.10 * order_performance_score  # delivered/confirmed order share + volume
    + 0.05 * location_score           # same city=1.0, same state=0.6, else 0.0

All component scores are clamped to [0, 1]. Ranking is fully deterministic —
the LLM is never used to invent scores.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

RANKING_FORMULA_DOC = (
    "final_score = 0.35*product_match + 0.20*rating/5 + 0.15*verified "
    "+ 0.15*response_time + 0.10*order_performance + 0.05*location"
)

WEIGHTS = {
    "product_match": 0.35,
    "rating": 0.20,
    "verified": 0.15,
    "response_time": 0.15,
    "order_performance": 0.10,
    "location": 0.05,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def rating_score(rating: Optional[float]) -> float:
    if rating is None:
        return 0.0
    return _clamp01(float(rating) / 5.0)


def verified_score(verified: Any) -> float:
    if isinstance(verified, bool):
        return 1.0 if verified else 0.0
    if isinstance(verified, str):
        return 1.0 if verified.strip().lower() in ("true", "1", "yes") else 0.0
    return 1.0 if verified else 0.0


def response_time_score(hours: Optional[float]) -> float:
    """Faster response → higher score. 1h ≈ 0.99, 72h+ ≈ 0."""
    if hours is None:
        return 0.3  # unknown → neutral-low
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return 0.3
    return _clamp01(1.0 - (h / 72.0))


def location_score(
    supplier_city: Optional[str],
    supplier_state: Optional[str],
    req_city: Optional[str],
    req_state: Optional[str],
) -> float:
    sc = (supplier_city or "").strip().lower()
    ss = (supplier_state or "").strip().lower()
    rc = (req_city or "").strip().lower()
    rs = (req_state or "").strip().lower()
    if rc and sc and rc == sc:
        return 1.0
    if rs and ss and rs == ss:
        return 0.6
    if rc and sc and (rc in sc or sc in rc):
        return 0.8
    return 0.0


def order_performance_score(
    total_orders: int,
    good_orders: int,
) -> float:
    """
    Blend of reliability (good status share) and experience (order volume).
    good_orders = delivered + confirmed + shipped.
    """
    if total_orders <= 0:
        return 0.15  # no history → slight penalty vs proven suppliers
    reliability = good_orders / max(total_orders, 1)
    volume = _clamp01(total_orders / 20.0)  # saturates around 20 orders
    return _clamp01(0.7 * reliability + 0.3 * volume)


def score_supplier(
    *,
    product_match: float,
    rating: Optional[float],
    verified: Any,
    response_time_hours: Optional[float],
    total_orders: int,
    good_orders: int,
    supplier_city: Optional[str],
    supplier_state: Optional[str],
    req_city: Optional[str],
    req_state: Optional[str],
) -> Dict[str, float]:
    pm = _clamp01(product_match)
    rs = rating_score(rating)
    vs = verified_score(verified)
    rts = response_time_score(response_time_hours)
    ops = order_performance_score(total_orders, good_orders)
    ls = location_score(supplier_city, supplier_state, req_city, req_state)

    final = (
        WEIGHTS["product_match"] * pm
        + WEIGHTS["rating"] * rs
        + WEIGHTS["verified"] * vs
        + WEIGHTS["response_time"] * rts
        + WEIGHTS["order_performance"] * ops
        + WEIGHTS["location"] * ls
    )
    return {
        "product_match_score": round(pm, 4),
        "rating_score": round(rs, 4),
        "verified_score": round(vs, 4),
        "response_time_score": round(rts, 4),
        "order_performance_score": round(ops, 4),
        "location_score": round(ls, 4),
        "final_score": round(_clamp01(final), 4),
    }


def build_explanation(scores: Dict[str, float], verified: Any, rating: Optional[float], response_hours: Optional[float]) -> str:
    parts: List[str] = []
    parts.append(f"Product match {scores['product_match_score']:.0%}")
    if rating is not None:
        parts.append(f"rating {rating}/5")
    if verified_score(verified) >= 1.0:
        parts.append("verified supplier")
    if response_hours is not None:
        parts.append(f"responds in ~{response_hours:g}h")
    if scores["location_score"] >= 0.6:
        parts.append("location proximity")
    if scores["order_performance_score"] >= 0.5:
        parts.append("solid order history")
    return "; ".join(parts) + f". Score {scores['final_score']:.2f}."
