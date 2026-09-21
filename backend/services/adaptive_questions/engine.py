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
    generate_advanced_candidates,
)
from backend.services.adaptive_questions.capabilities import build_capabilities
from backend.services.adaptive_questions.profiler import profile_dataset
from backend.services.adaptive_questions.ranking import select_diverse
from backend.services.adaptive_questions.semantics import build_semantics
from backend.services.adaptive_questions.templates import generate_candidates
from backend.services.adaptive_questions.validator import validate_candidates

logger = logging.getLogger(__name__)

# Bump when generation logic changes so old caches are invalidated.
GENERATION_VERSION = "v2-tiered"

_TIER_ORDER = [TIER_QUICK, TIER_ANALYTICS, TIER_ADVANCED, TIER_EXPERT]

_OPERATION_HINTS = {
    "above_overall_average": ["aggregation", "comparison", "above_average"],
    "concentration_top_n": ["aggregation", "percent_of_total", "ranking"],
    "top_n_min_sample": ["aggregation", "having", "ranking", "min_sample"],
    "high_low_tradeoff": ["aggregation", "comparison", "multi_metric"],
    "above_group_average": ["aggregation", "group_average", "comparison"],
    "year_over_year": ["time_analysis", "window", "comparison"],
    "growth_with_decline": ["time_analysis", "window", "multi_metric", "comparison"],
    "latest_year_top_share": ["time_analysis", "ranking", "percent_of_total"],
    "top_n_per_group_min_sample": ["window", "ranking", "min_sample", "group"],
    "group_leader_contribution": ["window", "ranking", "percent_of_total"],
    "entity_min_sample_above_avg": ["aggregation", "min_sample", "comparison", "ranking"],
    "cumulative_pareto": ["window", "cumulative", "percent_of_total", "concentration"],
    "top_quintile_with_weak_second_metric": [
        "window",
        "percentile",
        "multi_metric",
        "group_average",
    ],
    "multi_condition_min_sample_rank": [
        "aggregation",
        "min_sample",
        "multi_metric",
        "comparison",
        "ranking",
    ],
    "outlier_high": ["statistics", "outlier"],
    "conditional_share": ["conditional_aggregation", "percent_of_total"],
    "top_group_by_measure": ["aggregation", "ranking"],
    "pct_contribution": ["aggregation", "percent_of_total"],
    "monthly_trend": ["time_analysis", "aggregation"],
    "above_average_group": ["aggregation", "comparison"],
    "sum_measure": ["aggregation"],
    "avg_measure": ["aggregation"],
    "row_count": ["count"],
    "distinct_entity": ["count", "distinct"],
    "distinct_dimension": ["distinct"],
    "group_compare": ["aggregation", "comparison"],
    "corr_pair": ["statistics", "relationship"],
}


def _tier_targets(complexity: Dict[str, Any], count: int) -> Dict[str, int]:
    """Adaptive per-tier targets based on dataset capability band."""
    band = complexity.get("band")
    if band == "rich":
        base = {TIER_QUICK: 3, TIER_ANALYTICS: 3, TIER_ADVANCED: 5, TIER_EXPERT: 3}
    elif band == "moderate":
        base = {TIER_QUICK: 3, TIER_ANALYTICS: 3, TIER_ADVANCED: 4, TIER_EXPERT: 2}
    elif band == "basic":
        base = {TIER_QUICK: 3, TIER_ANALYTICS: 3, TIER_ADVANCED: 2, TIER_EXPERT: 0}
    else:
        base = {TIER_QUICK: 3, TIER_ANALYTICS: 2, TIER_ADVANCED: 0, TIER_EXPERT: 0}

    if not complexity.get("advanced_possible"):
        base[TIER_ADVANCED] = 0
    if not complexity.get("expert_possible"):
        base[TIER_EXPERT] = 0

    total = sum(base.values()) or 1
    # Only scale down to respect a smaller requested count; never inflate a
    # limited dataset into more questions than its capabilities justify.
    if count and count < total:
        scale = count / total
        scaled = {k: int(round(v * scale)) for k, v in base.items()}
        for k, v in base.items():
            if v > 0 and scaled.get(k, 0) == 0:
                scaled[k] = 1
        base = scaled
    return base


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
        ),
    }


_INTENT_FAMILY = {
    "above_overall_average": "above_average",
    "above_average_group": "above_average",
    "top_group_by_measure": "ranking",
    "group_compare": "ranking",
    "pct_contribution": "share",
    "conditional_share": "share",
    "concentration_top_n": "concentration",
    "monthly_trend": "time",
    "year_over_year": "time",
    "sum_measure": "totals",
    "avg_measure": "totals",
}


def _family(intent: str) -> str:
    return _INTENT_FAMILY.get(intent, intent)


def _select_tiered(
    valid: List[Any],
    targets: Dict[str, int],
    exclude_ids: List[str],
) -> List[Dict[str, Any]]:
    """Diversity-aware selection per tier (never repeats analytical families)."""
    by_tier: Dict[str, List[Any]] = {t: [] for t in _TIER_ORDER}
    for c in valid:
        tier = DIFFICULTY_TO_TIER.get(c.difficulty, TIER_ANALYTICS)
        by_tier.setdefault(tier, []).append(c)

    picked: List[Dict[str, Any]] = []
    used_intents: set = set()
    used_families: set = set()
    for tier in _TIER_ORDER:
        want = targets.get(tier, 0)
        if want <= 0:
            continue
        pool = [c for c in by_tier.get(tier, []) if c.id not in exclude_ids]
        ordered = select_diverse(pool, max(want * 3, want))
        taken = 0
        for c in ordered:
            if taken >= want:
                break
            if c.intent in used_intents or _family(c.intent) in used_families:
                continue
            used_intents.add(c.intent)
            used_families.add(_family(c.intent))
            picked.append(_to_api(c, tier))
            taken += 1
        # Backfill within tier if the diversity filter was too strict
        if taken < want:
            for c in ordered:
                if taken >= want:
                    break
                if c.intent in used_intents:
                    continue
                used_intents.add(c.intent)
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
    candidates += generate_advanced_candidates(profile, capabilities, semantics)

    valid, rejected = validate_candidates(session_id, profile, candidates)

    targets = _tier_targets(complexity, count)
    questions = _select_tiered(valid, targets, exclude_ids)

    # Backfill only within tiers this dataset actually supports — never force
    # advanced/expert questions onto a simple dataset.
    allowed_tiers = {t for t, n in targets.items() if n > 0}
    target_total = min(count, sum(targets.values()))
    if len(questions) < target_total:
        chosen = {q["id"] for q in questions} | set(exclude_ids)
        remaining = [
            c
            for c in valid
            if c.id not in chosen
            and DIFFICULTY_TO_TIER.get(c.difficulty, TIER_ANALYTICS) in allowed_tiers
        ]
        for c in select_diverse(remaining, target_total):
            if len(questions) >= target_total:
                break
            questions.append(_to_api(c, DIFFICULTY_TO_TIER.get(c.difficulty, TIER_ANALYTICS)))
            chosen.add(c.id)

    pool = [_to_api(c, DIFFICULTY_TO_TIER.get(c.difficulty, TIER_ANALYTICS)) for c in valid]
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
    elif not complexity.get("expert_possible") and complexity.get("band") in {"basic", "minimal"}:
        message = message or (
            "This dataset supports mostly direct questions — "
            "advanced multi-step analysis needs more measures or a date column."
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
