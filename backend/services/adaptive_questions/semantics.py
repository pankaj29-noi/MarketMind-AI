"""Semantic column typing with confidence scores."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from backend.services.adaptive_questions.profiler import ColumnProfile, DatasetProfile

MONETARY = {
    "revenue", "sales", "amount", "price", "cost", "profit", "gmv", "fee", "salary",
    "wage", "income", "spend", "billing", "payment", "value", "total",
}
QUANTITY = {"quantity", "qty", "units", "count", "volume", "stock", "inventory", "orders"}
SCORE = {"rating", "score", "performance", "nps", "stars"}
PERCENT = {"percent", "percentage", "pct", "rate", "ratio", "margin", "share"}
GEO = {"region", "state", "city", "country", "zone", "territory", "market"}
ENTITY = {"customer", "supplier", "product", "employee", "vendor", "buyer", "user", "client"}
CATEGORY = {"category", "department", "segment", "channel", "type", "status", "industry"}
TEMPORAL = {"date", "datetime", "timestamp", "time", "month", "year", "day", "week", "joining"}


@dataclass
class SemanticColumn:
    column: str
    semantic_type: str
    confidence: float
    display_label: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tokens(name: str) -> List[str]:
    n = name.replace("-", "_").replace(" ", "_")
    n = re.sub(r"(?<!^)(?=[A-Z])", "_", n)
    return [t for t in n.lower().split("_") if t]


def _looks_monetary_samples(samples: List[Any]) -> bool:
    nums = []
    for v in samples:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return False
    # Heuristic: monetary often has decimals or larger magnitudes
    return any(abs(x) >= 1 for x in nums)


def classify_column(col: ColumnProfile) -> SemanticColumn:
    tokens = set(_tokens(col.name))
    label = col.name.replace("_", " ")
    conf = 0.55
    stype = "unknown"

    if col.analytical_role == "identifier" or tokens & {"id", "key", "code", "uuid"}:
        return SemanticColumn(col.name, "entity_identifier", 0.92, label)

    if col.dtype == "datetime" or tokens & TEMPORAL:
        return SemanticColumn(col.name, "temporal_dimension", 0.95 if col.dtype == "datetime" else 0.8, label)

    if tokens & GEO and col.dtype == "string":
        return SemanticColumn(col.name, "geographic_dimension", 0.9, label)

    if tokens & CATEGORY and col.dtype == "string" and col.cardinality_ratio < 0.5:
        return SemanticColumn(col.name, "categorical_dimension", 0.88, label)

    if tokens & SCORE and col.dtype == "number":
        return SemanticColumn(col.name, "score_measure", 0.9, label)

    if tokens & PERCENT and col.dtype == "number":
        return SemanticColumn(col.name, "percentage_measure", 0.86, label)

    if tokens & MONETARY and col.dtype == "number":
        conf = 0.94 if tokens & {"revenue", "sales", "salary", "profit", "gmv", "price"} else 0.78
        if conf < 0.85 and not _looks_monetary_samples(col.sample_values):
            conf = 0.7
        return SemanticColumn(col.name, "monetary_measure", conf, label)

    if tokens & QUANTITY and col.dtype == "number":
        return SemanticColumn(col.name, "numeric_measure", 0.88, label)

    if tokens & ENTITY and col.dtype == "string":
        return SemanticColumn(col.name, "entity_dimension", 0.75, label)

    if col.dtype == "number":
        # High cardinality numbers → measure; low → maybe code
        if col.cardinality_ratio > 0.9 and col.unique_count > 20:
            # likely identifier-like numeric
            return SemanticColumn(col.name, "entity_identifier", 0.6, label)
        return SemanticColumn(col.name, "numeric_measure", 0.72, label)

    if col.dtype == "string":
        if col.cardinality_ratio <= 0.35 or col.unique_count <= 40:
            return SemanticColumn(col.name, "categorical_dimension", 0.8, label)
        return SemanticColumn(col.name, "text_attribute", 0.65, label)

    return SemanticColumn(col.name, stype, conf, label)


def build_semantics(profile: DatasetProfile) -> List[SemanticColumn]:
    return [classify_column(c) for c in profile.columns]
