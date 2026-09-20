"""Deterministic ranking + diversity selection."""
from __future__ import annotations

from typing import Dict, List, Set

from backend.services.adaptive_questions.templates import QuestionCandidate

DIFFICULTY_WEIGHT = {"easy": 1.0, "medium": 1.05, "hard": 1.1, "very_hard": 1.15}
CATEGORY_PRIORITY = [
    "overview",
    "ranking",
    "time_analysis",
    "group_comparison",
    "tradeoff",
    "concentration",
    "above_average",
    "min_sample",
    "percentage",
    "time_comparison",
    "group_average",
    "expert_multi_step",
    "growth_decline",
    "conditional",
    "conditional_aggregation",
    "outlier",
    "relationship",
    "aggregation",
]


def _score(c: QuestionCandidate) -> float:
    return (
        float(c.confidence)
        + DIFFICULTY_WEIGHT.get(c.difficulty, 1.0) * 0.05
        + min(0.15, 0.04 * len(c.columns_used))
    )


def dedupe(candidates: List[QuestionCandidate]) -> List[QuestionCandidate]:
    seen_intent: Set[str] = set()
    seen_text: Set[str] = set()
    out: List[QuestionCandidate] = []
    for c in sorted(candidates, key=_score, reverse=True):
        key = f"{c.intent}|{','.join(sorted(c.columns_used))}"
        text_key = c.text.strip().lower()
        if key in seen_intent or text_key in seen_text:
            continue
        seen_intent.add(key)
        seen_text.add(text_key)
        out.append(c)
    return out


def select_diverse(candidates: List[QuestionCandidate], count: int) -> List[QuestionCandidate]:
    if count <= 0:
        return []
    pool = dedupe(candidates)
    selected: List[QuestionCandidate] = []
    used_cats: Dict[str, int] = {}

    # Round-robin categories for diversity
    by_cat: Dict[str, List[QuestionCandidate]] = {}
    for c in pool:
        by_cat.setdefault(c.category, []).append(c)
    for cat in by_cat:
        by_cat[cat].sort(key=_score, reverse=True)

    order = [c for c in CATEGORY_PRIORITY if c in by_cat] + [
        c for c in by_cat.keys() if c not in CATEGORY_PRIORITY
    ]

    # Target difficulty mix ~30/40/30 across difficulties actually present
    present = {c.difficulty for c in pool}
    if len(present) <= 1:
        budgets = {d: count for d in present}
    else:
        easy_n = max(1, int(round(count * 0.3))) if "easy" in present else 0
        hard_pool = present & {"hard", "very_hard"}
        hard_n = max(1, int(round(count * 0.3))) if hard_pool else 0
        medium_n = max(0, count - easy_n - hard_n)
        budgets = {
            "easy": easy_n,
            "medium": medium_n,
            "hard": hard_n if "hard" in present else 0,
            "very_hard": hard_n if "very_hard" in present else 0,
        }
        if "medium" not in present:
            # redistribute unused medium budget to the hardest tier available
            for d in ("hard", "very_hard", "easy"):
                if budgets.get(d):
                    budgets[d] += medium_n
                    break
            budgets["medium"] = 0

    def take_from(cat: str) -> bool:
        bucket = by_cat.get(cat) or []
        while bucket:
            c = bucket.pop(0)
            if budgets.get(c.difficulty, 0) <= 0 and sum(budgets.values()) > 0:
                # try later if we still need other difficulties
                continue
            if any(c.id == s.id for s in selected):
                continue
            selected.append(c)
            used_cats[cat] = used_cats.get(cat, 0) + 1
            if c.difficulty in budgets and budgets[c.difficulty] > 0:
                budgets[c.difficulty] -= 1
            return True
        return False

    # First pass: one per category
    for cat in order:
        if len(selected) >= count:
            break
        take_from(cat)

    # Fill remaining by score
    remaining = [c for c in pool if all(c.id != s.id for s in selected)]
    remaining.sort(key=_score, reverse=True)
    for c in remaining:
        if len(selected) >= count:
            break
        selected.append(c)

    return selected[:count]
