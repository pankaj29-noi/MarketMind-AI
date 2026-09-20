"""Orchestrate profile → semantics → candidates → validate → rank."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.services.adaptive_questions import cache as qcache
from backend.services.adaptive_questions.capabilities import build_capabilities
from backend.services.adaptive_questions.profiler import profile_dataset
from backend.services.adaptive_questions.ranking import select_diverse
from backend.services.adaptive_questions.semantics import build_semantics
from backend.services.adaptive_questions.templates import generate_candidates
from backend.services.adaptive_questions.validator import validate_candidates

logger = logging.getLogger(__name__)


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

    profile = profile_dataset(session_id, dataset_id)
    fingerprint = profile.fingerprint

    if not refresh:
        cached = qcache.get_cached(session_id, dataset_id, fingerprint)
        if cached:
            qs = [q for q in cached.get("questions", []) if q.get("id") not in exclude_ids]
            if exclude_ids:
                # pull more from cached pool if present
                pool = cached.get("question_pool") or cached.get("questions") or []
                extra = [q for q in pool if q.get("id") not in exclude_ids and q not in qs]
                qs = (qs + extra)[:count]
            else:
                qs = qs[:count]
            return {
                **{k: v for k, v in cached.items() if k != "question_pool"},
                "questions": qs,
                "cache_hit": True,
                "generation_ms": round((time.time() - started) * 1000, 2),
            }

    semantics = build_semantics(profile)
    capabilities = build_capabilities(profile, semantics)

    if profile.row_count == 0 or profile.column_count == 0:
        payload = {
            "dataset_id": dataset_id,
            "fingerprint": fingerprint,
            "profile_summary": {
                "row_count": profile.row_count,
                "column_count": profile.column_count,
                "dimensions": capabilities.dimensions,
                "measures": capabilities.measures,
                "time_dimensions": capabilities.time_dimensions,
            },
            "questions": [],
            "message": profile.message or "This dataset has limited analytical fields.",
            "cache_hit": False,
            "candidate_count": 0,
            "valid_count": 0,
            "rejected_count": 0,
            "generation_ms": round((time.time() - started) * 1000, 2),
        }
        qcache.set_cached(session_id, dataset_id, fingerprint, payload)
        return payload

    candidates = generate_candidates(profile, capabilities, semantics)
    valid, rejected = validate_candidates(session_id, profile, candidates)
    selected = select_diverse(valid, max(count + len(exclude_ids) + 5, count))
    selected = [c for c in selected if c.id not in exclude_ids][:count]

    questions = [
        {
            "id": c.id,
            "text": c.text,
            "category": c.category,
            "difficulty": c.difficulty,
            "confidence": round(c.confidence, 3),
            "intent": c.intent,
        }
        for c in selected
    ]
    pool = [
        {
            "id": c.id,
            "text": c.text,
            "category": c.category,
            "difficulty": c.difficulty,
            "confidence": round(c.confidence, 3),
            "intent": c.intent,
        }
        for c in valid
    ]

    message = profile.message
    if not questions:
        message = message or "This dataset has limited analytical fields."

    payload = {
        "dataset_id": dataset_id,
        "fingerprint": fingerprint,
        "profile_summary": {
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "dimensions": capabilities.dimensions,
            "measures": capabilities.measures,
            "time_dimensions": capabilities.time_dimensions,
            "entities": capabilities.entities,
            "supported_operations": capabilities.supported_operations,
        },
        "questions": questions,
        "question_pool": pool,
        "message": message,
        "cache_hit": False,
        "candidate_count": len(candidates),
        "valid_count": len(valid),
        "rejected_count": rejected,
        "generation_ms": round((time.time() - started) * 1000, 2),
    }
    qcache.set_cached(session_id, dataset_id, fingerprint, payload)
    logger.info(
        "Suggested questions session=%s dataset=%s candidates=%s valid=%s rejected=%s ms=%s",
        session_id,
        dataset_id,
        len(candidates),
        len(valid),
        rejected,
        payload["generation_ms"],
    )
    # Strip pool from API response
    api_payload = {k: v for k, v in payload.items() if k != "question_pool"}
    return api_payload
