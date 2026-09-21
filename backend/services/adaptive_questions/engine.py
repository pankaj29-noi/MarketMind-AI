"""Orchestrate profile → semantics → candidates → validate → rank."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.services.adaptive_questions import cache as qcache
from backend.services.adaptive_questions.advanced_patterns import (
    DIFFICULTY_TO_TIER,
    TIER_ADVANCED,
    TIER_ANALYTICS,
    TIER_EXPERT,
    TIER_QUICK,
    build_followups,
    compute_complexity_score,
)
from backend.services.adaptive_questions.capabilities import build_capabilities
from backend.services.adaptive_questions.profiler import profile_dataset
from backend.services.adaptive_questions.ranking import select_diverse
from backend.services.adaptive_questions.semantics import build_semantics
from backend.services.adaptive_questions.templates import generate_candidates
from backend.services.adaptive_questions.validator import validate_candidates

logger = logging.getLogger(__name__)

# Bump when generation logic changes so old caches are invalidated.
GENERATION_VERSION = "v4-answerable-mix"


_TIER_ORDER = [TIER_QUICK, TIER_ANALYTICS, TIER_ADVANCED, TIER_EXPERT]

_OPERATION_HINTS = {
    "top_group_by_measure": ["aggregation", "ranking"],
    "bottom_group_by_measure": ["aggregation", "ranking"],
    "group_by_measure": ["aggregation", "group"],
    "top_n_by_measure": ["aggregation", "ranking"],
    "count_by_dimension": ["count", "group"],
    "sum_measure": ["aggregation"],
    "avg_measure": ["aggregation"],
    "row_count": ["count"],
    "distinct_entity": ["count", "distinct"],
    "distinct_dimension": ["distinct"],
    "monthly_trend": ["trend", "time"],
    "yearly_trend": ["trend", "time"],
    "concentration_top_n": ["aggregation", "percent", "ranking"],
}


def _tier_targets(complexity: Dict[str, Any], count: int) -> Dict[str, int]:
    """
    Mix easy / medium / hard when the dataset supports it.

    Only seats that validate via production NL→SQL are filled later.
    """
    n = max(1, min(int(count or 8), 10))
    band = str(complexity.get("band") or "basic")
    advanced_possible = bool(complexity.get("advanced_possible"))
    if band in {"rich", "moderate"} and advanced_possible and n >= 6:
        quick = max(3, n // 2)
        hard = 1 if n >= 7 else 0
        medium = max(0, n - quick - hard)
        return {
            TIER_QUICK: quick,
            TIER_ANALYTICS: medium,
            TIER_ADVANCED: hard,
            TIER_EXPERT: 0,
        }
    if band != "minimal" and n >= 5:
        quick = max(3, (n * 2) // 3)
        medium = n - quick
        return {
            TIER_QUICK: quick,
            TIER_ANALYTICS: medium,
            TIER_ADVANCED: 0,
            TIER_EXPERT: 0,
        }
    return {TIER_QUICK: n, TIER_ANALYTICS: 0, TIER_ADVANCED: 0, TIER_EXPERT: 0}


def _to_api(c, tier: str) -> Dict[str, Any]:
    return {
        "id": c.id,
        "text": c.text,
        "category": c.category,
        "difficulty": c.difficulty,
        "tier": tier,
        "confidence": round(c.confidence, 3),
        "intent": c.intent,
        "required_columns": list(c.columns_used),
        "operations": _OPERATION_HINTS.get(c.intent, []),
        "validation_status": "executed",
        "why": (
            "Uses " + ", ".join(col.replace("_", " ") for col in c.columns_used)
            if c.columns_used
            else "Dataset-level overview"
        )
        + " · verified executable SQL before display",
    }


def _select_tiered(
    valid: List[Any],
    targets: Dict[str, int],
    exclude_ids: List[str],
) -> List[Dict[str, Any]]:
    """Diversity-aware selection: unique intent+columns pairs, prefer variety."""
    by_tier: Dict[str, List[Any]] = {t: [] for t in _TIER_ORDER}
    for c in valid:
        tier = DIFFICULTY_TO_TIER.get(c.difficulty, TIER_QUICK)
        by_tier.setdefault(tier, []).append(c)

    picked: List[Dict[str, Any]] = []
    used_keys: set = set()
    used_intents: set = set()
    for tier in _TIER_ORDER:
        want = targets.get(tier, 0)
        if want <= 0:
            continue
        pool = [c for c in by_tier.get(tier, []) if c.id not in exclude_ids]
        ordered = select_diverse(pool, max(want * 3, want))
        taken = 0
        # Pass 1: prefer unique intents
        for c in ordered:
            if taken >= want:
                break
            key = (c.intent, tuple(c.columns_used))
            if key in used_keys or c.intent in used_intents:
                continue
            used_keys.add(key)
            used_intents.add(c.intent)
            picked.append(_to_api(c, tier))
            taken += 1
        # Pass 2: allow same intent with different columns (e.g. total sales + total qty)
        if taken < want:
            for c in ordered:
                if taken >= want:
                    break
                key = (c.intent, tuple(c.columns_used))
                if key in used_keys:
                    continue
                used_keys.add(key)
                picked.append(_to_api(c, tier))
                taken += 1
    return picked

def generate_suggested_questions(
    session_id: str,
    dataset_id: str,
    *,
    count: int = 10,
    refresh: bool = False,
    exclude_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    started = time.time()
    exclude_ids = exclude_ids or []

    # Prefer a cached schema fingerprint so a warm suggestion hit does not re-profile.
    fingerprint: Optional[str] = None
    try:
        from backend.services.session_manager import session_manager

        session = session_manager.get_session(session_id)
        cached_schema = (getattr(session, "schema_profile_cache", None) or {}).get(dataset_id)
        if isinstance(cached_schema, dict) and cached_schema.get("fingerprint"):
            fingerprint = str(cached_schema["fingerprint"])
            cache_key_fp = f"{fingerprint}|{GENERATION_VERSION}"
            if not refresh and not exclude_ids:
                cached = qcache.get_cached(session_id, dataset_id, cache_key_fp)
                if cached:
                    return {
                        **{k: v for k, v in cached.items() if k != "question_pool"},
                        "cache_hit": True,
                        "generation_ms": round((time.time() - started) * 1000, 2),
                    }
    except Exception:
        fingerprint = None

    profile = profile_dataset(session_id, dataset_id)
    fingerprint = profile.fingerprint
    cache_key_fp = f"{fingerprint}|{GENERATION_VERSION}"

    if not refresh and not exclude_ids:
        cached = qcache.get_cached(session_id, dataset_id, cache_key_fp)
        if cached:
            return {
                **{k: v for k, v in cached.items() if k != "question_pool"},
                "cache_hit": True,
                "generation_ms": round((time.time() - started) * 1000, 2),
            }

    cached_pool: List[Dict[str, Any]] = []
    if exclude_ids and not refresh:
        cached = qcache.get_cached(session_id, dataset_id, cache_key_fp)
        if cached:
            cached_pool = list(cached.get("question_pool") or [])

    semantics = build_semantics(profile)
    capabilities = build_capabilities(profile, semantics)
    complexity = compute_complexity_score(capabilities)

    if profile.row_count == 0 or profile.column_count == 0:
        payload = {
            "dataset_id": dataset_id,
            "fingerprint": fingerprint,
            "generation_version": GENERATION_VERSION,
            "profile_summary": {
                "row_count": profile.row_count,
                "column_count": profile.column_count,
                "dimensions": capabilities.dimensions,
                "measures": capabilities.measures,
                "time_dimensions": capabilities.time_dimensions,
            },
            "complexity": complexity,
            "questions": [],
            "tiers": [],
            "message": profile.message or "This dataset has limited analytical fields.",
            "cache_hit": False,
            "candidate_count": 0,
            "valid_count": 0,
            "rejected_count": 0,
            "generation_ms": round((time.time() - started) * 1000, 2),
        }
        qcache.set_cached(session_id, dataset_id, cache_key_fp, payload)
        return payload

    candidates = generate_candidates(profile, capabilities, semantics)
    # Cap candidate volume before expensive validation (pipeline SQL + DuckDB).
    candidates = candidates[:36]

    valid, rejected = validate_candidates(session_id, profile, candidates)

    # Requested count clamped to 5–10 (or fewer if dataset cannot support 5).
    count = max(1, min(int(count or 8), 10))
    targets = _tier_targets(complexity, count)
    questions = _select_tiered(valid, targets, exclude_ids)

    # Backfill from any validated tier so we still return useful starters.
    allowed_tiers = {t for t, n in targets.items() if n > 0} or {TIER_QUICK}
    target_total = min(count, sum(targets.values()) or count, len(valid))
    if len(questions) < target_total:
        chosen = {q["id"] for q in questions} | set(exclude_ids)
        remaining = [
            c
            for c in valid
            if c.id not in chosen
            and DIFFICULTY_TO_TIER.get(c.difficulty, TIER_QUICK) in allowed_tiers
        ]
        for c in select_diverse(remaining, target_total):
            if len(questions) >= target_total:
                break
            questions.append(
                _to_api(c, DIFFICULTY_TO_TIER.get(c.difficulty, TIER_QUICK))
            )
            chosen.add(c.id)
    if len(questions) < min(count, len(valid)):
        chosen = {q["id"] for q in questions} | set(exclude_ids)
        for c in select_diverse(
            [x for x in valid if x.id not in chosen], count
        ):
            if len(questions) >= min(count, len(valid)):
                break
            questions.append(
                _to_api(c, DIFFICULTY_TO_TIER.get(c.difficulty, TIER_QUICK))
            )

    # Never pad with invented questions — show only what validated.
    questions = questions[:count]

    pool = [
        _to_api(c, DIFFICULTY_TO_TIER.get(c.difficulty, TIER_QUICK)) for c in valid
    ]
    if cached_pool:
        known = {p["id"] for p in pool}
        pool += [p for p in cached_pool if p.get("id") not in known]

    tiers = []
    for tier in _TIER_ORDER:
        items = [q for q in questions if q["tier"] == tier]
        if items:
            tiers.append({"tier": tier, "questions": items})

    message = profile.message
    if not questions:
        message = message or "This dataset has limited analytical fields."
    else:
        message = message or (
            f"{len(questions)} starter questions verified against this CSV "
            "(easy/medium/hard — only questions the analytics path can answer)."
        )

    payload = {
        "dataset_id": dataset_id,
        "fingerprint": fingerprint,
        "generation_version": GENERATION_VERSION,
        "profile_summary": {
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "dimensions": capabilities.dimensions,
            "measures": capabilities.measures,
            "time_dimensions": capabilities.time_dimensions,
            "entities": capabilities.entities,
            "supported_operations": capabilities.supported_operations,
        },
        "complexity": complexity,
        "questions": questions,
        "tiers": tiers,
        "question_pool": pool,
        "message": message,
        "cache_hit": False,
        "candidate_count": len(candidates),
        "valid_count": len(valid),
        "rejected_count": rejected,
        "generation_ms": round((time.time() - started) * 1000, 2),
    }
    if not exclude_ids:
        qcache.set_cached(session_id, dataset_id, cache_key_fp, payload)
    logger.info(
        "Suggested questions session=%s dataset=%s candidates=%s valid=%s rejected=%s "
        "band=%s tiers=%s ms=%s",
        session_id,
        dataset_id,
        len(candidates),
        len(valid),
        rejected,
        complexity.get("band"),
        {t["tier"]: len(t["questions"]) for t in tiers},
        payload["generation_ms"],
    )
    # Strip pool from API response
    api_payload = {k: v for k, v in payload.items() if k != "question_pool"}
    return api_payload


def generate_followup_questions(
    session_id: str,
    dataset_id: str,
    *,
    question: str = "",
    result_columns: Optional[List[str]] = None,
    result_rows: Optional[List[Dict[str, Any]]] = None,
    count: int = 3,
) -> Dict[str, Any]:
    """
    Result-aware follow-up questions, grounded in the dataset schema and the
    rows the user just saw. Every follow-up is proven by read-only execution.
    """
    started = time.time()
    profile = profile_dataset(session_id, dataset_id)
    semantics = build_semantics(profile)
    capabilities = build_capabilities(profile, semantics)

    candidates = build_followups(
        list(result_columns or []),
        list(result_rows or [])[:5],
        profile,
        capabilities,
    )
    valid, rejected = validate_candidates(session_id, profile, candidates)

    seen_text = {(question or "").strip().lower()}
    questions: List[Dict[str, Any]] = []
    for c in valid:
        key = c.text.strip().lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        questions.append(_to_api(c, DIFFICULTY_TO_TIER.get(c.difficulty, TIER_ANALYTICS)))
        if len(questions) >= count:
            break

    return {
        "dataset_id": dataset_id,
        "fingerprint": profile.fingerprint,
        "questions": questions,
        "rejected_count": rejected,
        "generation_ms": round((time.time() - started) * 1000, 2),
    }
