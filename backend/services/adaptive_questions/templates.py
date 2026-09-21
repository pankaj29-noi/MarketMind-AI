"""Deterministic simple question templates bound to real columns + proof SQL.

Only easy, practical questions — no advanced / multi-step / expert intents.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List

from backend.services.adaptive_questions.capabilities import DatasetCapabilityMap
from backend.services.adaptive_questions.profiler import DatasetProfile
from backend.services.adaptive_questions.semantics import SemanticColumn


@dataclass
class QuestionCandidate:
    id: str
    text: str
    category: str
    difficulty: str
    intent: str
    proof_sql: str
    confidence: float
    columns_used: List[str]


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _human(name: str) -> str:
    return re.sub(r"[_]+", " ", name).strip()


def _qid(*parts: str) -> str:
    raw = "|".join(parts)
    return "q_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def generate_candidates(
    profile: DatasetProfile,
    capabilities: DatasetCapabilityMap,
    semantics: List[SemanticColumn],
) -> List[QuestionCandidate]:
    """
    Build ONLY simple schema-grounded candidates.

    Preferred shapes:
      - total / average of a numeric column
      - record count
      - highest / lowest category by metric
      - metric by category
      - top 5 items by metric
      - counts per category
    """
    table = _ident(profile.table)
    out: List[QuestionCandidate] = []
    conf_map = capabilities.column_confidence
    sem_by = {s.column: s for s in semantics}
    seen_text: set[str] = set()

    def _add(c: QuestionCandidate) -> None:
        key = c.text.strip().lower()
        if key in seen_text:
            return
        seen_text.add(key)
        out.append(c)

    # How many records?
    _add(
        QuestionCandidate(
            id=_qid("overview", "rows", profile.table),
            text="How many records are there?",
            category="overview",
            difficulty="easy",
            intent="row_count",
            proof_sql=f"SELECT COUNT(*) AS record_count FROM {table}",
            confidence=1.0,
            columns_used=[],
        )
    )

    measures = list(capabilities.measures[:4])
    dimensions = list(capabilities.dimensions[:4])

    # Total / average of each numeric measure
    for measure in measures:
        mconf = conf_map.get(measure, 0.75)
        mlabel = _human(measure)
        _add(
            QuestionCandidate(
                id=_qid("agg", "sum", measure),
                text=f"What is the total {mlabel}?",
                category="aggregation",
                difficulty="easy",
                intent="sum_measure",
                proof_sql=f"SELECT SUM({_ident(measure)}) AS total_{measure} FROM {table}",
                confidence=mconf,
                columns_used=[measure],
            )
        )
        _add(
            QuestionCandidate(
                id=_qid("agg", "avg", measure),
                text=f"What is the average {mlabel}?",
                category="aggregation",
                difficulty="easy",
                intent="avg_measure",
                proof_sql=f"SELECT AVG({_ident(measure)}) AS avg_{measure} FROM {table}",
                confidence=mconf,
                columns_used=[measure],
            )
        )

    # Category × metric: highest, lowest, by-category, top 5, counts
    for measure in measures[:3]:
        mlabel = _human(measure)
        mconf = conf_map.get(measure, 0.75)
        for dim in dimensions[:3]:
            dlabel = _human(dim)
            dconf = min(mconf, conf_map.get(dim, 0.75))
            _add(
                QuestionCandidate(
                    id=_qid("rank", "high", dim, measure),
                    text=f"Which {dlabel} has the highest {mlabel}?",
                    category="ranking",
                    difficulty="easy",
                    intent="top_group_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{measure} DESC LIMIT 1"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("rank", "low", dim, measure),
                    text=f"Which {dlabel} has the lowest {mlabel}?",
                    category="ranking",
                    difficulty="easy",
                    intent="bottom_group_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{measure} ASC LIMIT 1"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("group", dim, measure),
                    text=f"Show {mlabel} by {dlabel}.",
                    category="grouping",
                    difficulty="easy",
                    intent="group_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{measure} DESC LIMIT 25"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("top5", dim, measure),
                    text=f"What are the top 5 {_human(dim)} values by {mlabel}?",
                    category="ranking",
                    difficulty="easy",
                    intent="top_n_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{measure} DESC LIMIT 5"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )

    # How many records per category
    for dim in dimensions[:3]:
        dlabel = _human(dim)
        _add(
            QuestionCandidate(
                id=_qid("count", "per", dim),
                text=f"How many records belong to each {dlabel}?",
                category="overview",
                difficulty="easy",
                intent="count_by_dimension",
                proof_sql=(
                    f"SELECT {_ident(dim)} AS {_ident(dim)}, COUNT(*) AS record_count "
                    f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                    f"GROUP BY {_ident(dim)} ORDER BY record_count DESC LIMIT 25"
                ),
                confidence=conf_map.get(dim, 0.8),
                columns_used=[dim],
            )
        )

    # Unique entity count (still simple)
    for ent in capabilities.entities[:2]:
        if ent in dimensions:
            continue
        _add(
            QuestionCandidate(
                id=_qid("entity", ent),
                text=f"How many unique {_human(ent)} values are there?",
                category="overview",
                difficulty="easy",
                intent="distinct_entity",
                proof_sql=(
                    f"SELECT COUNT(DISTINCT {_ident(ent)}) AS unique_{ent} FROM {table}"
                ),
                confidence=conf_map.get(ent, 0.85),
                columns_used=[ent],
            )
        )

    # Drop low-confidence ambiguous monetary columns
    filtered: List[QuestionCandidate] = []
    for c in out:
        skip = False
        for col in c.columns_used:
            s = sem_by.get(col)
            if (
                s
                and s.semantic_type == "monetary_measure"
                and s.confidence < 0.75
                and s.column.lower() in {"value", "amount", "total"}
                and c.intent in {"sum_measure", "top_group_by_measure"}
            ):
                skip = True
        if not skip:
            filtered.append(c)
    return filtered
