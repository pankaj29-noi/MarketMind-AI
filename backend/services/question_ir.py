"""Structured question understanding IR for CSV analytics.

Deterministic only — no LLM. Wraps requirement_coverage + complexity +
schema concept→column mapping. Never renames physical columns.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from backend.services.analytics_perf import classify_question_complexity
from backend.services.requirement_coverage import (
    QuestionRequirements,
    extract_question_requirements,
    format_semantic_requirement_contract,
    match_requirements_to_schema,
)


@dataclass
class QuestionIR:
    """Compact structured representation of a user analytics question."""

    question: str
    complexity: str  # SIMPLE | MEDIUM | COMPLEX | VERY_COMPLEX
    intent: str
    requirements: Dict[str, Any]
    concept_to_column: Dict[str, Optional[str]]
    ambiguous_concepts: List[str] = field(default_factory=list)
    unsupported_notes: List[str] = field(default_factory=list)
    requirement_ids: List[str] = field(default_factory=list)
    contract_text: str = ""
    visualization_intent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_INTENT_RULES = (
    ("ranking_comparison", r"\b(compare|versus|vs\.?|against)\b.*\b(top|rank|highest)\b"),
    ("percent_of_total", r"\b(share of|percent(age)? of total|% of total|contribution)\b"),
    ("year_over_year", r"\b(year[- ]over[- ]year|yoy|previous year|prior year)\b"),
    ("top_n_per_group", r"\btop\s+\d+\b.*\b(per|each|within|by)\b"),
    ("above_below_average", r"\b(above|below)\s+(the\s+)?(overall\s+)?average\b"),
    ("minimum_sample", r"\b(at least|fewer than|minimum|exclude.*(fewer|less) than)\b"),
    ("ranking", r"\b(top|bottom|rank|highest|lowest)\b"),
    ("aggregation", r"\b(sum|total|average|avg|mean|count|median)\b"),
    ("filter", r"\b(where|only|filter|in \d{4})\b"),
    ("overview", r"\b(how many rows|row count|describe|overview)\b"),
)


def _infer_intent(question: str, req: QuestionRequirements) -> str:
    q = (question or "").lower()
    for name, pat in _INTENT_RULES:
        if re.search(pat, q):
            return name
    if req.needs_top_n or req.rankings:
        return "ranking"
    if req.metrics or req.derived_metrics:
        return "aggregation"
    if req.filters:
        return "filter"
    return "exploratory"


def _ambiguous_metric_concepts(
    question: str,
    concept_map: Dict[str, Optional[str]],
    columns: Sequence[str],
) -> List[str]:
    """Flag concepts that cannot be resolved uniquely from schema evidence."""
    q = (question or "").lower()
    amb: List[str] = []
    if re.search(r"\bsales\b", q) and not concept_map.get("sales"):
        # multiple plausible monetary columns?
        monetary = [
            c
            for c in columns
            if re.search(r"(revenue|amount|sales|gmv|price|value)", c, re.I)
        ]
        if len(monetary) > 1:
            amb.append(
                "sales (ambiguous: multiple monetary columns "
                + ", ".join(monetary[:4])
                + ")"
            )
        elif not monetary:
            amb.append("sales (no matching monetary column in schema)")
    if re.search(r"\bprofit\b", q) and concept_map.get("profit") is None:
        amb.append("profit (no profit column in schema)")
    return amb


def build_question_ir(
    question: str,
    schema_profile: Optional[Dict[str, Any]] = None,
) -> QuestionIR:
    """
    Build structured IR for a question given optional schema profile.

    Physical column names are never renamed — only mapped from concepts.
    """
    q = (question or "").strip()
    req = extract_question_requirements(q)
    complexity = classify_question_complexity(q)

    columns: List[str] = []
    if schema_profile:
        if schema_profile.get("multi_table") and schema_profile.get("tables"):
            for t in schema_profile["tables"]:
                for c in t.get("columns") or []:
                    name = c.get("name") if isinstance(c, dict) else None
                    if name:
                        columns.append(name)
        else:
            for c in schema_profile.get("columns") or []:
                name = c.get("name") if isinstance(c, dict) else None
                if name:
                    columns.append(name)

    concept_map = match_requirements_to_schema(req, columns) if columns else {}
    ambiguous = _ambiguous_metric_concepts(q, concept_map, columns)

    unsupported: List[str] = []
    if "unsupported_predictive_or_causal" in (req.requested_conclusions or []):
        unsupported.append("Predictive/causal questions are not supported by this analytics engine.")
    for concept, col in concept_map.items():
        if col is None and concept in (req.metrics + req.derived_metrics + req.dimensions):
            unsupported.append(f"No schema column confidently maps to concept '{concept}'.")

    # Requirement IDs for coverage verification
    rids: List[str] = []
    for d in req.dimensions:
        rids.append(f"R_dim_{d}")
    for m in req.metrics:
        rids.append(f"R_metric_{m}")
    for m in req.derived_metrics:
        rids.append(f"R_derived_{m}")
    for f in req.filters:
        rids.append(f"R_filter_{f}")
    if req.needs_top_n is not None:
        rids.append(f"R_top_{req.needs_top_n}")
    if req.needs_bottom_n is not None:
        rids.append(f"R_bottom_{req.needs_bottom_n}")
    for c in req.comparisons:
        rids.append(f"R_cmp_{c}")

    viz = bool(re.search(r"\b(chart|plot|graph|visuali[sz]e|show me a)\b", q, re.I))
    contract = format_semantic_requirement_contract(req, schema_columns=columns or None)

    return QuestionIR(
        question=q,
        complexity=complexity,
        intent=_infer_intent(q, req),
        requirements=req.to_dict(),
        concept_to_column=concept_map,
        ambiguous_concepts=ambiguous,
        unsupported_notes=unsupported,
        requirement_ids=rids,
        contract_text=contract,
        visualization_intent=viz,
    )


def format_ir_for_llm(ir: QuestionIR, max_chars: int = 2500) -> str:
    """Compact IR block for prompts — never full dataset."""
    lines = [
        "QUESTION_IR:",
        f"  complexity: {ir.complexity}",
        f"  intent: {ir.intent}",
        f"  visualization_intent: {ir.visualization_intent}",
    ]
    if ir.concept_to_column:
        mapped = {k: v for k, v in ir.concept_to_column.items() if v}
        lines.append(f"  concept_to_column: {mapped}")
        missing = [k for k, v in ir.concept_to_column.items() if not v]
        if missing:
            lines.append(f"  unresolved_concepts: {missing}")
    if ir.ambiguous_concepts:
        lines.append("  AMBIGUITY (do not silently guess):")
        for a in ir.ambiguous_concepts:
            lines.append(f"    - {a}")
    if ir.unsupported_notes:
        lines.append("  UNSUPPORTED:")
        for u in ir.unsupported_notes:
            lines.append(f"    - {u}")
    if ir.requirement_ids:
        lines.append("  requirement_ids: " + ", ".join(ir.requirement_ids))
    if ir.contract_text:
        lines.append("")
        lines.append(ir.contract_text)
    text = "\n".join(lines)
    return text[:max_chars]
