"""Deterministic question templates bound to real columns + proof SQL.

Easy / medium / hard shapes only when the production NL→SQL path
(pattern library + analytics fallback) can answer them on click.
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
    wants_chart: bool = False


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
    Build schema-grounded candidates the analytics pipeline can answer.

    Preferred shapes:
      - total / average of a numeric column (easy)
      - record count / distinct counts (easy)
      - highest / lowest / top-N / group-by (easy–medium)
      - monthly / yearly trend when a date column exists (medium)
      - percent of total from top-N (hard — pattern library)
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
    time_dims = list(getattr(capabilities, "time_dimensions", None) or [])[:2]

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

    for measure in measures[:3]:
        mlabel = _human(measure)
        mconf = conf_map.get(measure, 0.75)
        m_sem = sem_by.get(measure)
        m_low = measure.lower()
        use_avg = bool(
            (m_sem and getattr(m_sem, "semantic_type", "") in {"rate_measure", "ratio_measure"})
            or any(tok in m_low for tok in ("rate", "ratio", "percent", "pct", "margin", "score"))
        )
        agg_fn = "AVG" if use_avg else "SUM"
        agg_alias = f"{'avg' if use_avg else 'total'}_{measure}"
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
                        f"{agg_fn}({_ident(measure)}) AS {agg_alias} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY {agg_alias} DESC LIMIT 1"
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
                        f"{agg_fn}({_ident(measure)}) AS {agg_alias} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY {agg_alias} ASC LIMIT 1"
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
                    difficulty="medium",
                    intent="group_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"{agg_fn}({_ident(measure)}) AS {agg_alias} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY {agg_alias} DESC LIMIT 25"
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
                    difficulty="medium",
                    intent="top_n_by_measure",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"{agg_fn}({_ident(measure)}) AS {agg_alias} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY {agg_alias} DESC LIMIT 5"
                    ),
                    confidence=dconf,
                    columns_used=[dim, measure],
                )
            )
            if not use_avg:
                _add(
                    QuestionCandidate(
                        id=_qid("pct_top", dim, measure),
                        text=(
                            f"What percentage of total {mlabel} comes from the "
                            f"top 5 {dlabel} values?"
                        ),
                        category="concentration",
                        difficulty="hard",
                        intent="concentration_top_n",
                        proof_sql=(
                            f"WITH g AS ("
                            f"SELECT {_ident(dim)} AS dim_val, "
                            f"SUM({_ident(measure)}) AS total_m "
                            f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                            f"GROUP BY 1), "
                            f"t AS (SELECT SUM(total_m) AS top_total FROM "
                            f"(SELECT total_m FROM g ORDER BY total_m DESC LIMIT 5)), "
                            f"a AS (SELECT SUM(total_m) AS grand FROM g) "
                            f"SELECT ROUND(100.0 * t.top_total / NULLIF(a.grand, 0), 2) "
                            f"AS pct_of_total FROM t CROSS JOIN a"
                        ),
                        confidence=dconf * 0.92,
                        columns_used=[dim, measure],
                    )
                )

    for dim in dimensions[:3]:
        dlabel = _human(dim)
        _add(
            QuestionCandidate(
                id=_qid("count", "per", dim),
                text=f"How many records belong to each {dlabel}?",
                category="overview",
                difficulty="medium",
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
        _add(
            QuestionCandidate(
                id=_qid("distinct", "list", dim),
                text=f"List distinct {dlabel}.",
                category="overview",
                difficulty="medium",
                intent="distinct_dimension",
                proof_sql=(
                    f"SELECT DISTINCT {_ident(dim)} AS value FROM {table} "
                    f"WHERE {_ident(dim)} IS NOT NULL ORDER BY 1 LIMIT 50"
                ),
                confidence=conf_map.get(dim, 0.8),
                columns_used=[dim],
            )
        )

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

    for time_col in time_dims[:1]:
        tlabel = _human(time_col)
        for measure in measures[:2]:
            mlabel = _human(measure)
            mconf = min(conf_map.get(measure, 0.75), conf_map.get(time_col, 0.8))
            _add(
                QuestionCandidate(
                    id=_qid("trend", "month", time_col, measure),
                    text=f"Show monthly total {mlabel} using {tlabel}.",
                    category="trend",
                    difficulty="medium",
                    intent="monthly_trend",
                    proof_sql=(
                        f"SELECT strftime(CAST({_ident(time_col)} AS DATE), '%Y-%m') AS month, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(time_col)} IS NOT NULL "
                        f"GROUP BY 1 ORDER BY 1 LIMIT 36"
                    ),
                    confidence=mconf,
                    columns_used=[time_col, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("trend", "year", time_col, measure),
                    text=f"Show yearly total {mlabel} using {tlabel}.",
                    category="trend",
                    difficulty="medium",
                    intent="yearly_trend",
                    proof_sql=(
                        f"SELECT strftime(CAST({_ident(time_col)} AS DATE), '%Y') AS year, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(time_col)} IS NOT NULL "
                        f"GROUP BY 1 ORDER BY 1 LIMIT 20"
                    ),
                    confidence=mconf,
                    columns_used=[time_col, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("chart", "line", time_col, measure),
                    text=f"Plot a line chart of monthly {mlabel} using {tlabel}.",
                    category="chart",
                    difficulty="hard",
                    intent="chart_monthly_trend",
                    proof_sql=(
                        f"SELECT strftime(CAST({_ident(time_col)} AS DATE), '%Y-%m') AS month, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(time_col)} IS NOT NULL "
                        f"GROUP BY 1 ORDER BY 1 LIMIT 36"
                    ),
                    confidence=mconf * 0.95,
                    columns_used=[time_col, measure],
                    wants_chart=True,
                )
            )

    # Hard / chart shapes that map onto production pattern library templates
    for measure in measures[:2]:
        mlabel = _human(measure)
        mconf = conf_map.get(measure, 0.75)
        m_low = measure.lower()
        if any(tok in m_low for tok in ("rate", "ratio", "percent", "pct", "margin", "score")):
            continue
        for dim in dimensions[:3]:
            dlabel = _human(dim)
            dconf = min(mconf, conf_map.get(dim, 0.75))
            _add(
                QuestionCandidate(
                    id=_qid("chart", "bar", dim, measure),
                    text=f"Show a bar chart of total {mlabel} by {dlabel}.",
                    category="chart",
                    difficulty="hard",
                    intent="chart_group_by",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{measure} DESC LIMIT 25"
                    ),
                    confidence=dconf * 0.95,
                    columns_used=[dim, measure],
                    wants_chart=True,
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("chart", "top10", dim, measure),
                    text=f"Create a chart of the top 10 {dlabel} values by {mlabel}.",
                    category="chart",
                    difficulty="hard",
                    intent="chart_top_n",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(measure)}) AS total_{measure} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{measure} DESC LIMIT 10"
                    ),
                    confidence=dconf * 0.94,
                    columns_used=[dim, measure],
                    wants_chart=True,
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("adv", "above_avg", dim, measure),
                    text=f"Which {dlabel} have above-average {mlabel}?",
                    category="above_average",
                    difficulty="hard",
                    intent="above_overall_average",
                    proof_sql=(
                        f"WITH g AS (SELECT {_ident(dim)} AS dim, "
                        f"SUM({_ident(measure)}) AS total FROM {table} "
                        f"WHERE {_ident(dim)} IS NOT NULL GROUP BY 1) "
                        f"SELECT dim, total FROM g "
                        f"WHERE total > (SELECT AVG(total) FROM g) "
                        f"ORDER BY total DESC LIMIT 25"
                    ),
                    confidence=dconf * 0.93,
                    columns_used=[dim, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("adv", "below_avg", dim, measure),
                    text=f"Which {dlabel} have below-average {mlabel}?",
                    category="below_average",
                    difficulty="hard",
                    intent="below_overall_average",
                    proof_sql=(
                        f"WITH g AS (SELECT {_ident(dim)} AS dim, "
                        f"SUM({_ident(measure)}) AS total FROM {table} "
                        f"WHERE {_ident(dim)} IS NOT NULL GROUP BY 1) "
                        f"SELECT dim, total FROM g "
                        f"WHERE total < (SELECT AVG(total) FROM g) "
                        f"ORDER BY total ASC LIMIT 25"
                    ),
                    confidence=dconf * 0.93,
                    columns_used=[dim, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("adv", "share", dim, measure),
                    text=f"What is each {dlabel}'s share of total {mlabel}?",
                    category="contribution",
                    difficulty="hard",
                    intent="share_of_total",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS dim, "
                        f"ROUND(100.0 * SUM({_ident(measure)}) / "
                        f"NULLIF((SELECT SUM({_ident(measure)}) FROM {table}), 0), 2) AS pct "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY 1 ORDER BY pct DESC LIMIT 25"
                    ),
                    confidence=dconf * 0.92,
                    columns_used=[dim, measure],
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("adv", "min_sample", dim, measure),
                    text=(
                        f"Among {dlabel} values with at least 5 records, "
                        f"what are the top 10 by total {mlabel}?"
                    ),
                    category="min_sample",
                    difficulty="hard",
                    intent="top_n_min_sample",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS dim_val, "
                        f"SUM({_ident(measure)}) AS total_m, COUNT(*) AS n "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY 1 HAVING COUNT(*) >= 5 "
                        f"ORDER BY total_m DESC, dim_val LIMIT 10"
                    ),
                    confidence=dconf * 0.91,
                    columns_used=[dim, measure],
                )
            )

    if len(measures) >= 2:
        m1, m2 = measures[0], measures[1]
        for dim in dimensions[:2]:
            dconf = min(
                conf_map.get(dim, 0.75),
                conf_map.get(m1, 0.75),
                conf_map.get(m2, 0.75),
            )
            _add(
                QuestionCandidate(
                    id=_qid("adv", "dual", dim, m1, m2),
                    text=(
                        f"Show a bar chart of total {_human(m1)} and total "
                        f"{_human(m2)} by {_human(dim)}."
                    ),
                    category="chart",
                    difficulty="hard",
                    intent="multi_metric_group",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(m1)}) AS total_{m1}, "
                        f"SUM({_ident(m2)}) AS total_{m2} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{m1} DESC LIMIT 25"
                    ),
                    confidence=dconf * 0.9,
                    columns_used=[dim, m1, m2],
                    wants_chart=True,
                )
            )
            _add(
                QuestionCandidate(
                    id=_qid("chart", "dual", dim, m1, m2),
                    text=(
                        f"Create a chart comparing total {_human(m1)} and "
                        f"total {_human(m2)} by {_human(dim)}."
                    ),
                    category="chart",
                    difficulty="hard",
                    intent="chart_multi_metric",
                    proof_sql=(
                        f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                        f"SUM({_ident(m1)}) AS total_{m1}, "
                        f"SUM({_ident(m2)}) AS total_{m2} "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"GROUP BY {_ident(dim)} "
                        f"ORDER BY total_{m1} DESC LIMIT 15"
                    ),
                    confidence=dconf * 0.9,
                    columns_used=[dim, m1, m2],
                    wants_chart=True,
                )
            )

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
