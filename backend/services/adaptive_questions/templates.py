"""Deterministic question templates bound to real columns + proof SQL."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional

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
    table = _ident(profile.table)
    out: List[QuestionCandidate] = []
    conf_map = capabilities.column_confidence
    sem_by = {s.column: s for s in semantics}

    # Overview
    out.append(
        QuestionCandidate(
            id=_qid("overview", "rows", profile.table),
            text="How many records are in this dataset?",
            category="overview",
            difficulty="easy",
            intent="row_count",
            proof_sql=f"SELECT COUNT(*) AS record_count FROM {table}",
            confidence=1.0,
            columns_used=[],
        )
    )

    if capabilities.dimensions:
        dim = capabilities.dimensions[0]
        out.append(
            QuestionCandidate(
                id=_qid("overview", "dims", dim),
                text=f"What are the distinct values of {_human(dim)}?",
                category="overview",
                difficulty="easy",
                intent="distinct_dimension",
                proof_sql=(
                    f"SELECT DISTINCT {_ident(dim)} AS {_ident(dim)} FROM {table} "
                    f"WHERE {_ident(dim)} IS NOT NULL LIMIT 50"
                ),
                confidence=conf_map.get(dim, 0.8),
                columns_used=[dim],
            )
        )

    # Aggregation / ranking / grouping
    for measure in capabilities.measures[:4]:
        mconf = conf_map.get(measure, 0.75)
        mlabel = _human(measure)
        out.append(
            QuestionCandidate(
                id=_qid("agg", "sum", measure),
                text=f"What is the total {_human(measure)} across all records?",
                category="aggregation",
                difficulty="easy",
                intent="sum_measure",
                proof_sql=f"SELECT SUM({_ident(measure)}) AS total_{measure} FROM {table}",
                confidence=mconf,
                columns_used=[measure],
            )
        )
        out.append(
            QuestionCandidate(
                id=_qid("agg", "avg", measure),
                text=f"What is the average {_human(measure)}?",
                category="aggregation",
                difficulty="easy",
                intent="avg_measure",
                proof_sql=f"SELECT AVG({_ident(measure)}) AS avg_{measure} FROM {table}",
                confidence=mconf,
                columns_used=[measure],
            )
        )

        for dim in capabilities.dimensions[:3]:
            dconf = min(mconf, conf_map.get(dim, 0.75))
            out.append(
                QuestionCandidate(
                    id=_qid("rank", dim, measure),
                    text=f"Which {_human(dim)} has the highest total {_human(measure)}?",
                    category="ranking",
                    difficulty="medium",
                    intent="top_group_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} ORDER BY total_{measure} DESC LIMIT 10"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )
            out.append(
                QuestionCandidate(
                    id=_qid("compare", dim, measure),
                    text=f"How does total {_human(measure)} compare across {_human(dim)}?",
                    category="group_comparison",
                    difficulty="medium",
                    intent="group_compare",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure}, "
                        f"COUNT(*) AS row_count "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} ORDER BY total_{measure} DESC LIMIT 25"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )
            out.append(
                QuestionCandidate(
                    id=_qid("pct", dim, measure),
                    text=f"What share of total {_human(measure)} comes from each {_human(dim)}?",
                    category="percentage",
                    difficulty="hard",
                    intent="pct_contribution",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure}, "
                        f"ROUND(100.0 * SUM({_ident(measure)}) / NULLIF((SELECT SUM({_ident(measure)}) FROM {table}), 0), 2) "
                        f"AS pct_of_total "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} ORDER BY total_{measure} DESC LIMIT 25"
                    ),
                    confidence=dconf * 0.95,
                    columns_used=[dim, measure],
                )
            )

    # Time trends
    for tcol in capabilities.time_dimensions[:2]:
        for measure in capabilities.measures[:2]:
            conf = min(conf_map.get(tcol, 0.85), conf_map.get(measure, 0.75))
            out.append(
                QuestionCandidate(
                    id=_qid("trend", tcol, measure),
                    text=f"How has {_human(measure)} changed over time by month?",
                    category="time_analysis",
                    difficulty="medium",
                    intent="monthly_trend",
                    proof_sql=(
                        f"SELECT DATE_TRUNC('month', TRY_CAST({_ident(tcol)} AS TIMESTAMP)) AS month, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE TRY_CAST({_ident(tcol)} AS TIMESTAMP) IS NOT NULL "
                        f"GROUP BY 1 ORDER BY 1 LIMIT 48"
                    ),
                    confidence=conf,
                    columns_used=[tcol, measure],
                )
            )

    # Conditional / above average
    for measure in capabilities.measures[:2]:
        for dim in capabilities.dimensions[:2]:
            conf = min(conf_map.get(measure, 0.75), conf_map.get(dim, 0.75))
            out.append(
                QuestionCandidate(
                    id=_qid("cond", dim, measure),
                    text=f"Which {_human(dim)} values have above-average {_human(measure)}?",
                    category="conditional",
                    difficulty="hard",
                    intent="above_average_group",
                    proof_sql=(
                        f"WITH grp AS ("
                        f"  SELECT {_ident(dim)} AS dim_val, AVG({_ident(measure)}) AS avg_m "
                        f"  FROM {table} WHERE {_ident(dim)} IS NOT NULL GROUP BY 1"
                        f"), overall AS (SELECT AVG({_ident(measure)}) AS o FROM {table}) "
                        f"SELECT g.dim_val AS {_ident(dim)}, g.avg_m AS avg_{measure} "
                        f"FROM grp g, overall o WHERE g.avg_m > o.o "
                        f"ORDER BY g.avg_m DESC LIMIT 20"
                    ),
                    confidence=conf * 0.9,
                    columns_used=[dim, measure],
                )
            )

    # Multi-metric relationship (no causation wording)
    if len(capabilities.measures) >= 2:
        m1, m2 = capabilities.measures[0], capabilities.measures[1]
        out.append(
            QuestionCandidate(
                id=_qid("rel", m1, m2),
                text=f"Is there a relationship between {_human(m1)} and {_human(m2)}?",
                category="relationship",
                difficulty="hard",
                intent="corr_pair",
                proof_sql=(
                    f"SELECT CORR(CAST({_ident(m1)} AS DOUBLE), CAST({_ident(m2)} AS DOUBLE)) "
                    f"AS correlation FROM {table} "
                    f"WHERE {_ident(m1)} IS NOT NULL AND {_ident(m2)} IS NOT NULL"
                ),
                confidence=min(conf_map.get(m1, 0.7), conf_map.get(m2, 0.7)),
                columns_used=[m1, m2],
            )
        )

    # Entity counts
    for ent in capabilities.entities[:2]:
        out.append(
            QuestionCandidate(
                id=_qid("entity", ent),
                text=f"How many unique {_human(ent)} values are there?",
                category="overview",
                difficulty="easy",
                intent="distinct_entity",
                proof_sql=f"SELECT COUNT(DISTINCT {_ident(ent)}) AS unique_{ent} FROM {table}",
                confidence=conf_map.get(ent, 0.85),
                columns_used=[ent],
            )
        )

    # Drop questions that reference low-confidence ambiguous monetary "value/amount/total" alone
    filtered: List[QuestionCandidate] = []
    for c in out:
        skip = False
        for col in c.columns_used:
            s = sem_by.get(col)
            if s and s.semantic_type == "monetary_measure" and s.confidence < 0.75:
                if s.column.lower() in {"value", "amount", "total"} and c.intent in {
                    "sum_measure",
                    "top_group_by_measure",
                }:
                    skip = True
        if not skip:
            filtered.append(c)
    return filtered
