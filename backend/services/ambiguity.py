"""Deterministic ambiguity detection for natural-language analytics questions.

Two distinct problems, both of which must produce a clarification rather than a
silent guess or a bare failure:

1. Ambiguous metric — "sales" maps to several columns with no way to choose.
2. Underspecified request — "Show me sales" names a metric but no operation, so
   total / trend / breakdown are all equally valid readings.

Measured baseline: "Show me sales" spent 125.8s and returned "Analysis Failed".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# Concept -> column-name evidence, strongest first. A concept resolves cleanly when
# exactly one strength tier matches; it is ambiguous when a tier has several members.
_CONCEPT_EVIDENCE: Dict[str, Sequence[Sequence[str]]] = {
    "sales": (("revenue", "sales_amount", "gmv", "net_sales"), ("sales",), ("quantity", "units")),
    "amount": (("amount", "total_amount"), ("revenue", "cost", "price")),
    "value": (("value", "total_value"), ("revenue", "price", "amount")),
    "size": (("size",), ("quantity", "amount", "headcount")),
    "cost": (("cost", "total_cost"), ("unit_cost", "expense")),
    "performance": ((), ("revenue", "profit", "rating", "score")),
    "price": (("price", "unit_price"), ("revenue",)),
}

_OPERATION_MARKERS = (
    r"\btotal\b", r"\bsum\b", r"\baverage\b", r"\bavg\b", r"\bmean\b", r"\bmedian\b",
    r"\bcount\b", r"\bhow many\b", r"\bmax\b", r"\bmin\b", r"\bhighest\b", r"\blowest\b",
    r"\btop\b", r"\bbottom\b", r"\brank\b", r"\btrend\b", r"\bover time\b", r"\bby\b",
    r"\bper\b", r"\bcompare\b", r"\bgrowth\b", r"\bpercent", r"\bshare\b", r"\bdistribution\b",
    r"\bbreak\s*down\b", r"\bvs\b", r"\bversus\b", r"\bbetween\b", r"\bchange", r"\beach\b",
)

_BARE_REQUEST = re.compile(
    r"^\s*(?:show|give|display|get|see|view|list|fetch)\s+(?:me\s+)?(?:the\s+)?([a-z0-9_ ]{2,30})\??\s*$",
    re.I,
)


@dataclass
class AmbiguityReport:
    kind: str  # "ambiguous_metric" | "underspecified"
    term: str
    candidates: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def message(self) -> str:
        if self.kind == "ambiguous_metric":
            options = ", ".join(self.candidates)
            return (
                f'"{self.term}" could refer to more than one column in this dataset '
                f"({options}), and the question does not say which one.\n\n"
                "Tell me which to use, for example:\n"
                + "\n".join(f"- {s}" for s in self.suggestions)
            )
        return (
            f'"{self.term}" names a measure but not what to do with it. '
            "Any of these would be a valid reading:\n\n"
            + "\n".join(f"- {s}" for s in self.suggestions)
            + "\n\nPick one and I will run it against the loaded data."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "term": self.term,
            "candidates": list(self.candidates),
            "suggestions": list(self.suggestions),
        }


def _columns(schema_profile: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cols = (schema_profile or {}).get("columns") or []
    return [c if isinstance(c, dict) else {"name": str(c)} for c in cols]


def _is_measure(col: Dict[str, Any]) -> bool:
    role = str(col.get("analytical_role") or "").lower()
    dtype = str(col.get("dtype") or col.get("type") or "").lower()
    return role in ("measure", "derived_measure") or dtype in (
        "number", "int", "integer", "bigint", "double", "float", "decimal"
    )


# Classic analysis dimensions first; operational fields are weaker defaults.
_PRIMARY_DIMENSION_HINTS = ("region", "category", "segment", "channel")
_SECONDARY_DIMENSION_HINTS = ("type", "status", "method", "city")
# Rates and per-unit prices are not additive, so "total" is the wrong verb for them.
_NON_ADDITIVE = re.compile(r"(^|_)(price|rate|ratio|percent|pct|margin|score|rating|avg|average)(_|$)", re.I)


def _aggregate_phrase(column: str) -> str:
    return f"average {column}" if _NON_ADDITIVE.search(column) else f"total {column}"


def _first_dimension(columns: Sequence[Dict[str, Any]]) -> Optional[str]:
    """A dimension worth grouping by — low cardinality beats a per-row label."""
    candidates: List[tuple[int, str]] = []
    for col in columns:
        name = col.get("name")
        role = str(col.get("analytical_role") or "").lower()
        if not name or _is_measure(col):
            continue
        if role not in ("categorical", "dimension") or re.search(r"_id$|^id$", name, re.I):
            continue
        score = 0
        if any(hint in name.lower() for hint in _PRIMARY_DIMENSION_HINTS):
            score += 60
        elif any(hint in name.lower() for hint in _SECONDARY_DIMENSION_HINTS):
            score += 40
        unique = col.get("unique_count") or col.get("cardinality")
        if isinstance(unique, int) and unique > 0:
            score += 30 if unique <= 30 else (10 if unique <= 200 else 0)
        # A "name" column is usually one row per entity, a poor default breakdown.
        if name.lower().endswith("_name"):
            score -= 20
        candidates.append((score, name))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[0], len(c[1])))
    return candidates[0][1]


def _first_time_column(columns: Sequence[Dict[str, Any]]) -> Optional[str]:
    for col in columns:
        name = col.get("name")
        role = str(col.get("analytical_role") or "").lower()
        dtype = str(col.get("dtype") or col.get("type") or "").lower()
        if name and (role == "temporal" or "date" in dtype or "time" in dtype):
            return name
    return None


def _concept_candidates(term: str, measures: Sequence[str]) -> List[str]:
    """Columns that plausibly realise a vague concept, strongest tier only."""
    tiers = _CONCEPT_EVIDENCE.get(term)
    if not tiers:
        return []
    lowered = {m.lower(): m for m in measures}
    for tier in tiers:
        hits = [
            original
            for lower, original in lowered.items()
            if any(token == lower or token in lower.split("_") for token in tier)
        ]
        if hits:
            return sorted(set(hits))
    return []


def detect_ambiguity(
    question: str, schema_profile: Optional[Dict[str, Any]]
) -> Optional[AmbiguityReport]:
    """Return a clarification report, or None when the question is answerable as asked."""
    q = (question or "").strip()
    if not q:
        return None

    columns = _columns(schema_profile)
    if not columns:
        return None
    measures = [c["name"] for c in columns if c.get("name") and _is_measure(c)]
    if not measures:
        return None

    q_lower = q.lower()
    names_lower = {str(c.get("name") or "").lower() for c in columns}

    # An explicitly named column is never ambiguous.
    mentions_real_column = any(
        name and (name in q_lower or name.replace("_", " ") in q_lower) for name in names_lower
    )

    # 1. Ambiguous metric: a vague concept with several equally plausible columns.
    for term, _ in _CONCEPT_EVIDENCE.items():
        if not re.search(rf"\b{re.escape(term)}\b", q_lower):
            continue
        if term in names_lower:
            continue  # the dataset has a column with exactly this name
        candidates = _concept_candidates(term, measures)
        if len(candidates) > 1:
            return AmbiguityReport(
                kind="ambiguous_metric",
                term=term,
                candidates=candidates,
                suggestions=[f"What is the {_aggregate_phrase(c)}?" for c in candidates],
            )

    # 2. Underspecified: names a measure but no operation to perform on it.
    if any(re.search(marker, q_lower) for marker in _OPERATION_MARKERS):
        return None

    bare = _BARE_REQUEST.match(q)
    if not bare and len(q.split()) > 4:
        return None

    subject = (bare.group(1) if bare else q).strip().rstrip("?")
    resolved: Optional[str] = None
    if mentions_real_column:
        for name in measures:
            if name.lower() in q_lower or name.lower().replace("_", " ") in q_lower:
                resolved = name
                break
    else:
        candidates = _concept_candidates(subject.lower(), measures)
        resolved = candidates[0] if len(candidates) == 1 else None

    if not resolved:
        return None

    suggestions = [f"What is the {_aggregate_phrase(resolved)}?"]
    time_col = _first_time_column(columns)
    if time_col:
        suggestions.append(f"How has {resolved} changed over time by month?")
    dimension = _first_dimension(columns)
    if dimension:
        suggestions.append(f"Which {dimension} has the highest {_aggregate_phrase(resolved)}?")

    return AmbiguityReport(
        kind="underspecified",
        term=subject,
        candidates=[resolved],
        suggestions=suggestions,
    )
