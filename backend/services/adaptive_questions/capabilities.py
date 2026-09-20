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
    time_dimensions: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    supported_operations: List[str] = field(default_factory=list)
    column_confidence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
        time_dimensions=times,
        entities=entities,
        supported_operations=sorted(set(ops)),
        column_confidence=conf,
    )
