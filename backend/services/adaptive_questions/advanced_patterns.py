"""
Advanced + expert analytical pattern engine (deterministic, schema-bound).

Generates multi-condition / multi-step question candidates ONLY when the
uploaded dataset actually supports the required columns and operations.
Every candidate carries proof SQL that is executed before display.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional

from backend.services.adaptive_questions.capabilities import DatasetCapabilityMap
from backend.services.adaptive_questions.profiler import DatasetProfile
from backend.services.adaptive_questions.semantics import SemanticColumn
from backend.services.adaptive_questions.templates import QuestionCandidate

# Tiers exposed to the UI
TIER_QUICK = "quick"
TIER_ANALYTICS = "analytics"
TIER_ADVANCED = "advanced"
TIER_EXPERT = "expert"

# Map legacy difficulty → tier
DIFFICULTY_TO_TIER = {
    "easy": TIER_QUICK,
    "medium": TIER_ANALYTICS,
    "hard": TIER_ADVANCED,
    "very_hard": TIER_EXPERT,
}


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _human(name: str) -> str:
    return re.sub(r"[_]+", " ", str(name)).strip()


def _qid(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return "q_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _is_count_like(col: str) -> bool:
    c = col.lower()
    return any(t in c for t in ("order", "count", "qty", "quantity", "units", "txn"))


def compute_complexity_score(cap: DatasetCapabilityMap) -> Dict[str, object]:
    """
    Capability score used ONLY to decide how many advanced patterns to attempt.
    Not a data-quality claim.
    """
    n_dim = len(cap.dimensions)
    n_meas = len(cap.measures)
    n_time = len(cap.time_dimensions)
    n_ent = len(cap.entities)

    score = 0
    score += min(n_dim, 6) * 2
    score += min(n_meas, 6) * 3
    score += min(n_time, 2) * 4
    score += min(n_ent, 4) * 1
    if n_dim >= 2 and n_meas >= 2:
        score += 4
    if n_time >= 1 and n_meas >= 1:
        score += 4

    if score >= 26:
        band = "rich"
    elif score >= 15:
        band = "moderate"
    elif score >= 7:
        band = "basic"
    else:
        band = "minimal"

    return {
        "score": score,
        "band": band,
        "dimensions": n_dim,
        "measures": n_meas,
        "time_dimensions": n_time,
        "entities": n_ent,
        "advanced_possible": bool(n_dim >= 1 and n_meas >= 1),
        "expert_possible": bool(
            (n_dim >= 1 and n_meas >= 2) or (n_time >= 1 and n_dim >= 1 and n_meas >= 1)
        ),
    }


def generate_advanced_candidates(
    profile: DatasetProfile,
    capabilities: DatasetCapabilityMap,
    semantics: List[SemanticColumn],
) -> List[QuestionCandidate]:
    """Advanced (multi-condition) + expert (multi-step) candidates."""
    table = _ident(profile.table)
    conf = capabilities.column_confidence
    dims = capabilities.dimensions
    measures = capabilities.additive_measures or capabilities.measures
    times = capabilities.time_dimensions
    out: List[QuestionCandidate] = []

    if not dims or not measures:
        return out

    prim_dims = dims[:3]
    prim_meas = measures[:3]

    # ── PATTERN C/O: above overall average (advanced) ────────────────────
    for dim in prim_dims[:2]:
        for meas in prim_meas[:2]:
            c = min(conf.get(dim, 0.75), conf.get(meas, 0.75))
            out.append(
                QuestionCandidate(
                    id=_qid("adv_above_avg", dim, meas),
                    text=(
                        f"Which {_human(dim)} values have total {_human(meas)} "
                        f"above the overall average?"
                    ),
                    category="above_average",
                    difficulty="hard",
                    intent="above_overall_average",
                    proof_sql=(
                        f"WITH g AS (SELECT {_ident(dim)} AS dim_val, SUM({_ident(meas)}) AS total_m "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL GROUP BY 1), "
                        f"o AS (SELECT AVG(total_m) AS avg_total FROM g) "
                        f"SELECT g.dim_val, g.total_m, o.avg_total FROM g CROSS JOIN o "
                        f"WHERE g.total_m > o.avg_total ORDER BY g.total_m DESC LIMIT 20"
                    ),
                    confidence=c * 0.95,
                    columns_used=[dim, meas],
                )
            )

    # ── PATTERN E/F/X: percent of total + concentration (advanced) ───────
    for dim in prim_dims[:2]:
        meas = prim_meas[0]
        c = min(conf.get(dim, 0.75), conf.get(meas, 0.75))
        out.append(
            QuestionCandidate(
                id=_qid("adv_concentration", dim, meas),
                text=(
                    f"What percentage of total {_human(meas)} comes from the "
                    f"top 10 {_human(dim)} values?"
                ),
                category="concentration",
                difficulty="hard",
                intent="concentration_top_n",
                proof_sql=(
                    f"WITH g AS (SELECT {_ident(dim)} AS dim_val, SUM({_ident(meas)}) AS total_m "
                    f"FROM {table} WHERE {_ident(dim)} IS NOT NULL GROUP BY 1), "
                    f"t AS (SELECT SUM(total_m) AS top_total FROM "
                    f"(SELECT total_m FROM g ORDER BY total_m DESC LIMIT 10)), "
                    f"a AS (SELECT SUM(total_m) AS grand FROM g) "
                    f"SELECT ROUND(100.0 * t.top_total / NULLIF(a.grand, 0), 2) AS top10_share_pct "
                    f"FROM t CROSS JOIN a"
                ),
                confidence=c * 0.93,
                columns_used=[dim, meas],
            )
        )

    # ── PATTERN G/H: minimum sample size + ranking (advanced) ────────────
    for dim in prim_dims[:2]:
        meas = prim_meas[0]
        c = min(conf.get(dim, 0.75), conf.get(meas, 0.75))
        out.append(
            QuestionCandidate(
                id=_qid("adv_min_sample", dim, meas),
                text=(
                    f"Among {_human(dim)} values with at least 5 records, which are "
                    f"the top 10 by total {_human(meas)}?"
                ),
                category="min_sample",
                difficulty="hard",
                intent="top_n_min_sample",
                proof_sql=(
                    f"SELECT {_ident(dim)} AS dim_val, SUM({_ident(meas)}) AS total_m, "
                    f"COUNT(*) AS n FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                    f"GROUP BY 1 HAVING COUNT(*) >= 5 ORDER BY total_m DESC, dim_val LIMIT 10"
                ),
                confidence=c * 0.94,
                columns_used=[dim, meas],
            )
        )

    # ── PATTERN R/S/Z: multi-metric tradeoff (advanced) ──────────────────
    if len(measures) >= 2:
        m1, m2 = measures[0], measures[1]
        for dim in prim_dims[:2]:
            c = min(conf.get(dim, 0.7), conf.get(m1, 0.7), conf.get(m2, 0.7))
            out.append(
                QuestionCandidate(
                    id=_qid("adv_tradeoff", dim, m1, m2),
                    text=(
                        f"Which {_human(dim)} values have above-average {_human(m1)} "
                        f"but below-average {_human(m2)}?"
                    ),
                    category="tradeoff",
                    difficulty="hard",
                    intent="high_low_tradeoff",
                    proof_sql=(
                        f"WITH g AS (SELECT {_ident(dim)} AS dim_val, "
                        f"AVG({_ident(m1)}) AS a1, AVG({_ident(m2)}) AS a2 "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL GROUP BY 1), "
                        f"o AS (SELECT AVG(a1) AS oa1, AVG(a2) AS oa2 FROM g) "
                        f"SELECT g.dim_val, g.a1, g.a2, o.oa1, o.oa2 "
                        f"FROM g CROSS JOIN o WHERE g.a1 > o.oa1 AND g.a2 < o.oa2 "
                        f"ORDER BY g.a1 DESC LIMIT 20"
                    ),
                    confidence=c * 0.9,
                    columns_used=[dim, m1, m2],
                )
            )

    # ── PATTERN N/M: within-group comparison (advanced) ──────────────────
    if len(dims) >= 2:
        outer, inner = dims[0], dims[1]
        meas = prim_meas[0]
        c = min(conf.get(outer, 0.7), conf.get(inner, 0.7), conf.get(meas, 0.7))
        out.append(
            QuestionCandidate(
                id=_qid("adv_group_avg", outer, inner, meas),
                text=(
                    f"Which {_human(inner)} values have total {_human(meas)} above "
                    f"their own {_human(outer)} average?"
                ),
                category="group_average",
                difficulty="hard",
                intent="above_group_average",
                proof_sql=(
                    f"WITH g AS (SELECT {_ident(outer)} AS outer_val, {_ident(inner)} AS inner_val, "
                    f"SUM({_ident(meas)}) AS total_m FROM {table} "
                    f"WHERE {_ident(outer)} IS NOT NULL AND {_ident(inner)} IS NOT NULL "
                    f"GROUP BY 1, 2), "
                    f"ga AS (SELECT outer_val, AVG(total_m) AS avg_m FROM g GROUP BY 1) "
                    f"SELECT g.outer_val, g.inner_val, g.total_m, ga.avg_m "
                    f"FROM g JOIN ga USING (outer_val) WHERE g.total_m > ga.avg_m "
                    f"ORDER BY g.total_m DESC LIMIT 25"
                ),
                confidence=c * 0.9,
                columns_used=[outer, inner, meas],
            )
        )

    # ── PATTERN I/J/T/U: time-based (advanced + expert) ──────────────────
    if times and measures:
        tcol = times[0]
        meas = prim_meas[0]
        c = min(conf.get(tcol, 0.8), conf.get(meas, 0.75))
        out.append(
            QuestionCandidate(
                id=_qid("adv_yoy", tcol, meas),
                text=f"How did total {_human(meas)} change year over year?",
                category="time_comparison",
                difficulty="hard",
                intent="year_over_year",
                proof_sql=(
                    f"WITH y AS (SELECT EXTRACT(YEAR FROM TRY_CAST({_ident(tcol)} AS TIMESTAMP)) AS yr, "
                    f"SUM({_ident(meas)}) AS total_m FROM {table} "
                    f"WHERE TRY_CAST({_ident(tcol)} AS TIMESTAMP) IS NOT NULL GROUP BY 1) "
                    f"SELECT yr, total_m, LAG(total_m) OVER (ORDER BY yr) AS prev_total, "
                    f"ROUND(100.0 * (total_m - LAG(total_m) OVER (ORDER BY yr)) "
                    f"/ NULLIF(LAG(total_m) OVER (ORDER BY yr), 0), 2) AS yoy_pct "
                    f"FROM y ORDER BY yr"
                ),
                confidence=c * 0.92,
                columns_used=[tcol, meas],
            )
        )

        # EXPERT: growth vs decline across two measures
        if len(measures) >= 2 and dims:
            dim = dims[0]
            m1, m2 = measures[0], measures[1]
            c2 = min(conf.get(dim, 0.7), conf.get(m1, 0.7), conf.get(m2, 0.7), conf.get(tcol, 0.8))
            out.append(
                QuestionCandidate(
                    id=_qid("exp_growth_decline", dim, tcol, m1, m2),
                    text=(
                        f"Which {_human(dim)} values increased {_human(m1)} year over year "
                        f"while {_human(m2)} declined?"
                    ),
                    category="growth_decline",
                    difficulty="very_hard",
                    intent="growth_with_decline",
                    proof_sql=(
                        f"WITH y AS (SELECT {_ident(dim)} AS dim_val, "
                        f"EXTRACT(YEAR FROM TRY_CAST({_ident(tcol)} AS TIMESTAMP)) AS yr, "
                        f"SUM({_ident(m1)}) AS m1_total, SUM({_ident(m2)}) AS m2_total "
                        f"FROM {table} WHERE {_ident(dim)} IS NOT NULL "
                        f"AND TRY_CAST({_ident(tcol)} AS TIMESTAMP) IS NOT NULL "
                        f"GROUP BY 1, 2), "
                        f"p AS (SELECT *, LAG(m1_total) OVER (PARTITION BY dim_val ORDER BY yr) AS prev_m1, "
                        f"LAG(m2_total) OVER (PARTITION BY dim_val ORDER BY yr) AS prev_m2 FROM y) "
                        f"SELECT dim_val, yr, m1_total, prev_m1, m2_total, prev_m2 FROM p "
                        f"WHERE prev_m1 IS NOT NULL AND m1_total > prev_m1 AND m2_total < prev_m2 "
                        f"ORDER BY dim_val, yr LIMIT 25"
                    ),
                    confidence=c2 * 0.88,
                    columns_used=[dim, tcol, m1, m2],
                )
            )

        # EXPERT: latest-period top-N with share
        if dims:
            dim = dims[0]
            c3 = min(conf.get(dim, 0.7), conf.get(meas, 0.75), conf.get(tcol, 0.8))
            out.append(
                QuestionCandidate(
                    id=_qid("exp_latest_share", dim, tcol, meas),
                    text=(
                        f"In the latest year, which are the top 10 {_human(dim)} values by "
                        f"{_human(meas)}, and what share of that year's total do they represent?"
                    ),
                    category="expert_multi_step",
                    difficulty="very_hard",
                    intent="latest_year_top_share",
                    proof_sql=(
                        f"WITH base AS (SELECT * FROM {table} "
                        f"WHERE TRY_CAST({_ident(tcol)} AS TIMESTAMP) IS NOT NULL), "
                        f"latest AS (SELECT MAX(EXTRACT(YEAR FROM TRY_CAST({_ident(tcol)} AS TIMESTAMP))) AS y FROM base), "
                        f"cur AS (SELECT b.* FROM base b, latest l "
                        f"WHERE EXTRACT(YEAR FROM TRY_CAST(b.{_ident(tcol)} AS TIMESTAMP)) = l.y), "
                        f"g AS (SELECT {_ident(dim)} AS dim_val, SUM({_ident(meas)}) AS total_m "
                        f"FROM cur WHERE {_ident(dim)} IS NOT NULL GROUP BY 1), "
                        f"a AS (SELECT SUM(total_m) AS grand FROM g) "
                        f"SELECT g.dim_val, g.total_m, "
                        f"ROUND(100.0 * g.total_m / NULLIF(a.grand, 0), 2) AS share_pct "
                        f"FROM g CROSS JOIN a ORDER BY g.total_m DESC, g.dim_val LIMIT 10"
                    ),
                    confidence=c3 * 0.87,
                    columns_used=[dim, tcol, meas],
                )
            )

    # ── EXPERT: top-N per group with min sample ──────────────────────────
    if len(dims) >= 2 and measures:
        outer, inner = dims[0], dims[1]
        meas = prim_meas[0]
        c = min(conf.get(outer, 0.7), conf.get(inner, 0.7), conf.get(meas, 0.7))
        out.append(
            QuestionCandidate(
                id=_qid("exp_topn_group", outer, inner, meas),
                text=(
                    f"What are the top 3 {_human(inner)} values by {_human(meas)} within each "
                    f"{_human(outer)}, excluding those with fewer than 5 records?"
                ),
                category="expert_multi_step",
                difficulty="very_hard",
                intent="top_n_per_group_min_sample",
                proof_sql=(
                    f"WITH g AS (SELECT {_ident(outer)} AS outer_val, {_ident(inner)} AS inner_val, "
                    f"SUM({_ident(meas)}) AS total_m, COUNT(*) AS n FROM {table} "
                    f"WHERE {_ident(outer)} IS NOT NULL AND {_ident(inner)} IS NOT NULL "
                    f"GROUP BY 1, 2 HAVING COUNT(*) >= 5) "
                    f"SELECT outer_val, inner_val, total_m, n FROM g "
                    f"QUALIFY RANK() OVER (PARTITION BY outer_val ORDER BY total_m DESC) <= 3 "
                    f"ORDER BY outer_val, total_m DESC"
                ),
                confidence=c * 0.88,
                columns_used=[outer, inner, meas],
            )
        )

        # EXPERT: dominant leader contribution per group
        out.append(
            QuestionCandidate(
                id=_qid("exp_leader_contrib", outer, inner, meas),
                text=(
                    f"For each {_human(outer)}, which {_human(inner)} has the highest "
                    f"{_human(meas)}, and what percentage of that {_human(outer)}'s total does it represent?"
                ),
                category="expert_multi_step",
                difficulty="very_hard",
                intent="group_leader_contribution",
                proof_sql=(
                    f"WITH g AS (SELECT {_ident(outer)} AS outer_val, {_ident(inner)} AS inner_val, "
                    f"SUM({_ident(meas)}) AS total_m FROM {table} "
                    f"WHERE {_ident(outer)} IS NOT NULL AND {_ident(inner)} IS NOT NULL GROUP BY 1, 2), "
                    f"s AS (SELECT *, SUM(total_m) OVER (PARTITION BY outer_val) AS group_total, "
                    f"RANK() OVER (PARTITION BY outer_val ORDER BY total_m DESC) AS rnk FROM g) "
                    f"SELECT outer_val, inner_val, total_m, group_total, "
                    f"ROUND(100.0 * total_m / NULLIF(group_total, 0), 2) AS contribution_pct "
                    f"FROM s WHERE rnk = 1 ORDER BY outer_val"
                ),
                confidence=c * 0.88,
                columns_used=[outer, inner, meas],
            )
        )

    # ── EXPERT: entity min-sample + above-average AOV ranked by measure ──
    if capabilities.entities and measures:
        ent = capabilities.entities[0]
        meas = prim_meas[0]
        c = min(conf.get(ent, 0.8), conf.get(meas, 0.75))
        out.append(
            QuestionCandidate(
                id=_qid("exp_entity_above_avg", ent, meas),
                text=(
                    f"Among {_human(ent)} values with at least 3 records, which have an average "
                    f"{_human(meas)} above the overall average, ranked by total {_human(meas)}?"
                ),
                category="expert_multi_step",
                difficulty="very_hard",
                intent="entity_min_sample_above_avg",
                proof_sql=(
                    f"WITH e AS (SELECT {_ident(ent)} AS ent_val, COUNT(*) AS n, "
                    f"AVG({_ident(meas)}) AS avg_m, SUM({_ident(meas)}) AS total_m "
                    f"FROM {table} WHERE {_ident(ent)} IS NOT NULL GROUP BY 1), "
                    f"o AS (SELECT AVG(avg_m) AS overall_avg FROM e) "
                    f"SELECT e.ent_val, e.n, e.avg_m, e.total_m, o.overall_avg "
                    f"FROM e CROSS JOIN o WHERE e.n >= 3 AND e.avg_m > o.overall_avg "
                    f"ORDER BY e.total_m DESC LIMIT 20"
                ),
                confidence=c * 0.87,
                columns_used=[ent, meas],
            )
        )

    # ── PATTERN W: cumulative contribution / Pareto (expert) ─────────────
    for dim in prim_dims[:2]:
        meas = prim_meas[0]
        c = min(conf.get(dim, 0.7), conf.get(meas, 0.75))
        out.append(
            QuestionCandidate(
                id=_qid("exp_pareto", dim, meas),
                text=(
                    f"Which {_human(dim)} values together account for the first 80% of "
                    f"cumulative {_human(meas)}?"
                ),
                category="expert_multi_step",
                difficulty="very_hard",
                intent="cumulative_pareto",
                proof_sql=(
                    f"WITH g AS (SELECT {_ident(dim)} AS dim_val, SUM({_ident(meas)}) AS total_m "
                    f"FROM {table} WHERE {_ident(dim)} IS NOT NULL GROUP BY 1), "
                    f"c AS (SELECT dim_val, total_m, "
                    f"SUM(total_m) OVER (ORDER BY total_m DESC, dim_val "
                    f"ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total, "
                    f"SUM(total_m) OVER () AS grand FROM g) "
                    f"SELECT dim_val, total_m, "
                    f"ROUND(100.0 * running_total / NULLIF(grand, 0), 2) AS cumulative_pct "
                    f"FROM c WHERE running_total - total_m < 0.8 * grand "
                    f"ORDER BY total_m DESC, dim_val LIMIT 30"
                ),
                confidence=c * 0.86,
                columns_used=[dim, meas],
            )
        )

    # ── PATTERN L/M + percentile: top quintile within group (expert) ─────
    if len(dims) >= 2 and len(measures) >= 2:
        outer, inner = dims[0], dims[1]
        m1, m2 = measures[0], measures[1]
        c = min(conf.get(outer, 0.7), conf.get(inner, 0.7), conf.get(m1, 0.7), conf.get(m2, 0.7))
        out.append(
            QuestionCandidate(
                id=_qid("exp_percentile", outer, inner, m1, m2),
                text=(
                    f"Which {_human(inner)} values rank in the top 20% of {_human(m1)} within "
                    f"their {_human(outer)} but have below-{_human(outer)}-average {_human(m2)}?"
                ),
                category="expert_multi_step",
                difficulty="very_hard",
                intent="top_quintile_with_weak_second_metric",
                proof_sql=(
                    f"WITH g AS (SELECT {_ident(outer)} AS outer_val, {_ident(inner)} AS inner_val, "
                    f"SUM({_ident(m1)}) AS m1_total, AVG({_ident(m2)}) AS m2_avg FROM {table} "
                    f"WHERE {_ident(outer)} IS NOT NULL AND {_ident(inner)} IS NOT NULL GROUP BY 1, 2), "
                    f"r AS (SELECT *, PERCENT_RANK() OVER (PARTITION BY outer_val ORDER BY m1_total DESC) AS pr, "
                    f"AVG(m2_avg) OVER (PARTITION BY outer_val) AS outer_m2_avg FROM g) "
                    f"SELECT outer_val, inner_val, m1_total, m2_avg, outer_m2_avg "
                    f"FROM r WHERE pr <= 0.2 AND m2_avg < outer_m2_avg "
                    f"ORDER BY outer_val, m1_total DESC LIMIT 25"
                ),
                confidence=c * 0.85,
                columns_used=[outer, inner, m1, m2],
            )
        )

    # ── PATTERN H + G: multi-condition with min sample (expert) ──────────
    if len(measures) >= 2:
        m1, m2 = measures[0], measures[1]
        for dim in prim_dims[:2]:
            c = min(conf.get(dim, 0.7), conf.get(m1, 0.7), conf.get(m2, 0.7))
            out.append(
                QuestionCandidate(
                    id=_qid("exp_multi_condition", dim, m1, m2),
                    text=(
                        f"Among {_human(dim)} values with at least 5 records, which have "
                        f"above-average {_human(m1)} and below-average {_human(m2)}, "
                        f"ranked by total {_human(m1)}?"
                    ),
                    category="expert_multi_step",
                    difficulty="very_hard",
                    intent="multi_condition_min_sample_rank",
                    proof_sql=(
                        f"WITH g AS (SELECT {_ident(dim)} AS dim_val, COUNT(*) AS n, "
                        f"SUM({_ident(m1)}) AS m1_total, AVG({_ident(m1)}) AS m1_avg, "
                        f"AVG({_ident(m2)}) AS m2_avg FROM {table} "
                        f"WHERE {_ident(dim)} IS NOT NULL GROUP BY 1), "
                        f"o AS (SELECT AVG(m1_avg) AS oa1, AVG(m2_avg) AS oa2 FROM g) "
                        f"SELECT g.dim_val, g.n, g.m1_total, g.m1_avg, g.m2_avg "
                        f"FROM g CROSS JOIN o "
                        f"WHERE g.n >= 5 AND g.m1_avg > o.oa1 AND g.m2_avg < o.oa2 "
                        f"ORDER BY g.m1_total DESC LIMIT 20"
                    ),
                    confidence=c * 0.85,
                    columns_used=[dim, m1, m2],
                )
            )

    # ── PATTERN Q: outlier detection (advanced) ──────────────────────────    meas = prim_meas[0]
    if profile.row_count >= 30:
        out.append(
            QuestionCandidate(
                id=_qid("adv_outlier", meas),
                text=f"Which records have unusually high {_human(meas)} compared with the rest?",
                category="outlier",
                difficulty="hard",
                intent="outlier_high",
                proof_sql=(
                    f"WITH mstats AS (SELECT AVG({_ident(meas)}) AS mu, "
                    f"STDDEV_SAMP({_ident(meas)}) AS sd "
                    f"FROM {table} WHERE {_ident(meas)} IS NOT NULL) "
                    f"SELECT base.{_ident(meas)} AS outlier_value "
                    f"FROM {table} AS base CROSS JOIN mstats "
                    f"WHERE mstats.sd IS NOT NULL AND mstats.sd > 0 "
                    f"AND base.{_ident(meas)} > mstats.mu + 2 * mstats.sd "
                    f"ORDER BY outlier_value DESC LIMIT 20"
                ),
                confidence=conf.get(meas, 0.75) * 0.85,
                columns_used=[meas],
            )
        )

    # ── PATTERN V: conditional aggregation over a low-cardinality dim ────
    status_dim: Optional[str] = None
    for col in profile.columns:
        if col.name in dims and 2 <= (col.unique_count or 0) <= 12:
            status_dim = col.name
            break
    if status_dim and measures:
        meas = prim_meas[0]
        out.append(
            QuestionCandidate(
                id=_qid("adv_conditional", status_dim, meas),
                text=(
                    f"How does total {_human(meas)} split across {_human(status_dim)}, "
                    f"and what share does each represent?"
                ),
                category="conditional_aggregation",
                difficulty="hard",
                intent="conditional_share",
                proof_sql=(
                    f"SELECT {_ident(status_dim)} AS dim_val, SUM({_ident(meas)}) AS total_m, "
                    f"COUNT(*) AS n, "
                    f"ROUND(100.0 * SUM({_ident(meas)}) / NULLIF(SUM(SUM({_ident(meas)})) OVER (), 0), 2) AS share_pct "
                    f"FROM {table} WHERE {_ident(status_dim)} IS NOT NULL GROUP BY 1 "
                    f"ORDER BY total_m DESC"
                ),
                confidence=min(conf.get(status_dim, 0.75), conf.get(meas, 0.75)) * 0.92,
                columns_used=[status_dim, meas],
            )
        )

    return out


def build_followups(
    result_columns: List[str],
    result_rows: List[Dict[str, object]],
    profile: DatasetProfile,
    capabilities: DatasetCapabilityMap,
) -> List[QuestionCandidate]:
    """
    Result-aware follow-up candidates bound to real columns, each with proof SQL
    so they can be validated before display. Never invents fields.
    """
    dims = capabilities.dimensions
    measures = capabilities.additive_measures or capabilities.measures
    times = capabilities.time_dimensions
    out: List[QuestionCandidate] = []
    if not dims or not measures:
        return out

    table = _ident(profile.table)
    meas = measures[0]
    dim_set = set(dims)

    # Find a concrete entity from the result that maps back to a known dimension
    focus_dim: Optional[str] = None
    focus_value: Optional[str] = None
    if result_rows:
        first = result_rows[0]
        for key, val in first.items():
            if not isinstance(val, str) or not val.strip():
                continue
            if key in dim_set:
                focus_dim, focus_value = key, val.strip()
                break
        if focus_dim is None:
            # Result may alias the dimension (e.g. dim_val); match the value itself
            candidate_vals = [v.strip() for v in first.values() if isinstance(v, str) and v.strip()]
            for d in dims[:4]:
                col = next((c for c in profile.columns if c.name == d), None)
                if not col:
                    continue
                tops = {str(t.get("value")) for t in (col.top_values or [])}
                samples = {str(s) for s in (col.sample_values or [])}
                for v in candidate_vals:
                    if v in tops or v in samples:
                        focus_dim, focus_value = d, v
                        break
                if focus_dim:
                    break

    def _lit(v: str) -> str:
        return "'" + v.replace("'", "''") + "'"

    if focus_dim and focus_value:
        other_dims = [d for d in dims if d != focus_dim][:2]
        for d in other_dims:
            out.append(
                QuestionCandidate(
                    id=_qid("fu_breakdown", focus_dim, focus_value, d, meas),
                    text=(
                        f"Which {_human(d)} values drive {_human(meas)} for "
                        f"{focus_value}?"
                    ),
                    category="group_comparison",
                    difficulty="medium",
                    intent="followup_breakdown",
                    proof_sql=(
                        f"SELECT {_ident(d)} AS dim_val, SUM({_ident(meas)}) AS total_m "
                        f"FROM {table} WHERE {_ident(focus_dim)} = {_lit(focus_value)} "
                        f"AND {_ident(d)} IS NOT NULL GROUP BY 1 ORDER BY total_m DESC LIMIT 10"
                    ),
                    confidence=0.9,
                    columns_used=[focus_dim, d, meas],
                )
            )
        out.append(
            QuestionCandidate(
                id=_qid("fu_compare", focus_dim, focus_value, meas),
                text=(
                    f"How does {focus_value} compare with other {_human(focus_dim)} "
                    f"values by {_human(meas)}?"
                ),
                category="group_comparison",
                difficulty="medium",
                intent="followup_compare",
                proof_sql=(
                    f"SELECT {_ident(focus_dim)} AS dim_val, SUM({_ident(meas)}) AS total_m "
                    f"FROM {table} WHERE {_ident(focus_dim)} IS NOT NULL "
                    f"GROUP BY 1 ORDER BY total_m DESC LIMIT 15"
                ),
                confidence=0.88,
                columns_used=[focus_dim, meas],
            )
        )
        if times:
            tcol = times[0]
            out.append(
                QuestionCandidate(
                    id=_qid("fu_trend", focus_dim, focus_value, tcol, meas),
                    text=f"How has {_human(meas)} changed over time for {focus_value}?",
                    category="time_analysis",
                    difficulty="medium",
                    intent="followup_trend",
                    proof_sql=(
                        f"SELECT DATE_TRUNC('month', TRY_CAST({_ident(tcol)} AS TIMESTAMP)) AS month, "
                        f"SUM({_ident(meas)}) AS total_m FROM {table} "
                        f"WHERE {_ident(focus_dim)} = {_lit(focus_value)} "
                        f"AND TRY_CAST({_ident(tcol)} AS TIMESTAMP) IS NOT NULL GROUP BY 1 ORDER BY 1 LIMIT 48"
                    ),
                    confidence=0.86,
                    columns_used=[focus_dim, tcol, meas],
                )
            )
        if len(measures) >= 2:
            m2 = measures[1]
            out.append(
                QuestionCandidate(
                    id=_qid("fu_tradeoff", focus_dim, focus_value, meas, m2),
                    text=(
                        f"For {focus_value}, how does {_human(meas)} compare with "
                        f"{_human(m2)} across {_human(dims[1] if len(dims) > 1 else focus_dim)}?"
                    ),
                    category="tradeoff",
                    difficulty="hard",
                    intent="followup_tradeoff",
                    proof_sql=(
                        f"SELECT {_ident(dims[1] if len(dims) > 1 else focus_dim)} AS dim_val, "
                        f"SUM({_ident(meas)}) AS m1_total, SUM({_ident(m2)}) AS m2_total "
                        f"FROM {table} WHERE {_ident(focus_dim)} = {_lit(focus_value)} "
                        f"GROUP BY 1 ORDER BY m1_total DESC LIMIT 15"
                    ),
                    confidence=0.82,
                    columns_used=[focus_dim, meas, m2],
                )
            )
    else:
        # No entity in the result — offer deeper analysis on the same measure
        if times:
            out.append(
                QuestionCandidate(
                    id=_qid("fu_trend_all", times[0], meas),
                    text=f"How has {_human(meas)} changed over time?",
                    category="time_analysis",
                    difficulty="medium",
                    intent="followup_trend_all",
                    proof_sql=(
                        f"SELECT DATE_TRUNC('month', TRY_CAST({_ident(times[0])} AS TIMESTAMP)) AS month, "
                        f"SUM({_ident(meas)}) AS total_m FROM {table} "
                        f"WHERE TRY_CAST({_ident(times[0])} AS TIMESTAMP) IS NOT NULL GROUP BY 1 ORDER BY 1 LIMIT 48"
                    ),
                    confidence=0.85,
                    columns_used=[times[0], meas],
                )
            )
        out.append(
            QuestionCandidate(
                id=_qid("fu_share_all", dims[0], meas),
                text=f"What share of total {_human(meas)} comes from each {_human(dims[0])}?",
                category="percentage",
                difficulty="hard",
                intent="followup_share",
                proof_sql=(
                    f"SELECT {_ident(dims[0])} AS dim_val, SUM({_ident(meas)}) AS total_m, "
                    f"ROUND(100.0 * SUM({_ident(meas)}) / NULLIF(SUM(SUM({_ident(meas)})) OVER (), 0), 2) "
                    f"AS share_pct FROM {table} WHERE {_ident(dims[0])} IS NOT NULL "
                    f"GROUP BY 1 ORDER BY total_m DESC LIMIT 20"
                ),
                confidence=0.84,
                columns_used=[dims[0], meas],
            )
        )
        if len(measures) >= 2:
            out.append(
                QuestionCandidate(
                    id=_qid("fu_tradeoff_all", dims[0], measures[0], measures[1]),
                    text=(
                        f"Which {_human(dims[0])} values have above-average {_human(measures[0])} "
                        f"but below-average {_human(measures[1])}?"
                    ),
                    category="tradeoff",
                    difficulty="hard",
                    intent="followup_tradeoff_all",
                    proof_sql=(
                        f"WITH g AS (SELECT {_ident(dims[0])} AS dim_val, "
                        f"AVG({_ident(measures[0])}) AS a1, AVG({_ident(measures[1])}) AS a2 "
                        f"FROM {table} WHERE {_ident(dims[0])} IS NOT NULL GROUP BY 1), "
                        f"o AS (SELECT AVG(a1) AS oa1, AVG(a2) AS oa2 FROM g) "
                        f"SELECT g.dim_val, g.a1, g.a2 FROM g CROSS JOIN o "
                        f"WHERE g.a1 > o.oa1 AND g.a2 < o.oa2 ORDER BY g.a1 DESC LIMIT 15"
                    ),
                    confidence=0.8,
                    columns_used=[dims[0], measures[0], measures[1]],
                )
            )

    # dedupe by text
    seen = set()
    unique: List[QuestionCandidate] = []
    for c in out:
        key = c.text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique[:6]
