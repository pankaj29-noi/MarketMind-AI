"""Dataset capability map derived from semantic columns."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from backend.services.adaptive_questions.profiler import DatasetProfile
from backend.services.adaptive_questions.semantics import SemanticColumn

MEASURE_TYPES = {
    "monetary_measure",
    "numeric_measure",
    "score_measure",
    "percentage_measure",
}
DIM_TYPES = {
    "categorical_dimension",
    "geographic_dimension",
    "entity_dimension",
}


@dataclass
class DatasetCapabilityMap:
    dimensions: List[str] = field(default_factory=list)
    measures: List[str] = field(default_factory=list)
    additive_measures: List[str] = field(default_factory=list)
    time_dimensions: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    supported_operations: List[str] = field(default_factory=list)
    column_confidence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Measures that can be meaningfully SUMmed
ADDITIVE_TYPES = {"monetary_measure", "numeric_measure"}
# Name fragments that look like a period/year encoded as a number
_PSEUDO_TIME_TOKENS = ("year", "period", "month", "quarter", "week", "day", "yr")
# Strongly additive business measures (summing them is meaningful)
_ADDITIVE_NAME_BOOST = (
    "revenue",
    "sales",
    "profit",
    "gmv",
    "amount",
    "total",
    "spend",
    "cost",
    "income",
    "salary",
    "quantity",
    "qty",
    "units",
    "orders",
    "volume",
)
# Per-unit / ratio-like measures (summing them is misleading)
_NON_ADDITIVE_NAME_PENALTY = (
    "price",
    "rate",
    "ratio",
    "margin",
    "pct",
    "percent",
    "share",
    "avg",
    "average",
    "median",
    "score",
    "rating",
    "index",
    "per_",
    "_per",
)


def _measure_rank(
    name: str,
    stype: str,
    confidence: float,
    col_index: Dict[str, Any],
) -> float:
    base = {
        "monetary_measure": 1.0,
        "numeric_measure": 0.85,
        "score_measure": 0.6,
        "percentage_measure": 0.45,
    }.get(stype, 0.5)
    score = base * (0.5 + confidence / 2)
    low = name.lower()
    if any(tok in low for tok in _ADDITIVE_NAME_BOOST):
        score += 0.35
    if any(tok in low for tok in _NON_ADDITIVE_NAME_PENALTY):
        score -= 0.4
    if any(tok in low for tok in _PSEUDO_TIME_TOKENS):
        score -= 0.45
    col = col_index.get(name)
    if col is not None:
        if (col.unique_count or 0) <= 3:
            score -= 0.2
        if (col.null_pct or 0) > 0.5:
            score -= 0.2
    return score


def _dimension_rank(
    name: str,
    stype: str,
    confidence: float,
    col_index: Dict[str, Any],
    row_count: int,
) -> float:
    base = {
        "geographic_dimension": 1.0,
        "categorical_dimension": 0.95,
        "entity_dimension": 0.9,
    }.get(stype, 0.6)
    score = base * (0.5 + confidence / 2)
    col = col_index.get(name)
    if col is not None:
        uniq = col.unique_count or 0
        if uniq <= 1:
            score -= 1.0
        elif 2 <= uniq <= 60:
            score += 0.25
        elif uniq <= 400:
            score += 0.05
        else:
            score -= 0.3
        if row_count and uniq >= row_count * 0.8:
            score -= 0.4
        if (col.null_pct or 0) > 0.5:
            score -= 0.2
    return score


def build_capabilities(
    profile: DatasetProfile,
    semantics: List[SemanticColumn],
    *,
    min_confidence: float = 0.7,
) -> DatasetCapabilityMap:
    dims: List[str] = []
    measures: List[str] = []
    times: List[str] = []
    entities: List[str] = []
    conf: Dict[str, float] = {}

    for s in semantics:
        conf[s.column] = s.confidence
        if s.confidence < min_confidence and s.semantic_type in MEASURE_TYPES | DIM_TYPES:
            # Keep low-confidence out of generation-critical slots
            continue
        if s.semantic_type in DIM_TYPES:
            dims.append(s.column)
        elif s.semantic_type in MEASURE_TYPES:
            measures.append(s.column)
        elif s.semantic_type == "temporal_dimension":
            times.append(s.column)
        elif s.semantic_type == "entity_identifier":
            entities.append(s.column)

    # Fallback: if filters removed everything, loosen for numbers/strings
    if not measures:
        for s in semantics:
            if s.semantic_type in MEASURE_TYPES:
                measures.append(s.column)
    if not dims:
        for s in semantics:
            if s.semantic_type in DIM_TYPES:
                dims.append(s.column)

    # Rank by analytical usefulness so downstream patterns bind the best columns
    col_index = {c.name: c for c in profile.columns}
    stype_by = {s.column: s.semantic_type for s in semantics}
    measures.sort(
        key=lambda n: _measure_rank(n, stype_by.get(n, ""), conf.get(n, 0.7), col_index),
        reverse=True,
    )
    dims.sort(
        key=lambda n: _dimension_rank(
            n, stype_by.get(n, ""), conf.get(n, 0.7), col_index, profile.row_count
        ),
        reverse=True,
    )
    additive = [m for m in measures if stype_by.get(m) in ADDITIVE_TYPES]

    ops = ["count"]
    if measures:
        ops.extend(["sum", "average", "ranking", "comparison", "grouping"])
    if times and measures:
        ops.append("trend")
    if dims and measures:
        ops.append("percentage")
    if len(measures) >= 2:
        ops.append("relationship")

    return DatasetCapabilityMap(
        dimensions=dims,
        measures=measures,
        additive_measures=additive,
        time_dimensions=times,
        entities=entities,
        supported_operations=sorted(set(ops)),
        column_confidence=conf,
    )
