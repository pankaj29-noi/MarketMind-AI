"""
Lightweight question-requirement extraction and SQL coverage checks.

STEP 1 focus: formalize analytical requirements from natural-language questions
into a stable structured representation (no LLM, no new framework).

Coverage checking remains available for downstream validators; this module does
not change LangGraph topology or execution routing.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _uniq(items: Sequence[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _blob(sql: str, columns: Sequence[str]) -> str:
    cols = " ".join(str(c).lower() for c in (columns or []))
    return f"{(sql or '').lower()} {cols}"


# Logical requirement tokens → common CSV / marketplace column aliases
_SCHEMA_ALIASES: Dict[str, Tuple[str, ...]] = {
    "city": ("city", "town"),
    "category": ("category", "product_category", "category_name"),
    "region": ("region", "state", "province"),
    "segment": ("customer_segment", "segment", "buyer_segment"),
    "product": ("product", "product_name", "item"),
    "channel": ("sales_channel", "channel"),
    "sales": ("sales_amount", "sales", "revenue", "gmv", "amount", "order_value"),
    "profit": ("profit", "net_profit"),
    "quantity": ("quantity", "qty", "units"),
    "discount": ("discount_rate", "discount", "discount_pct"),
    "profit_margin": ("profit_margin", "margin"),
}


@dataclass
class QuestionRequirements:
    """
    Structured analytical requirements inferred from a user question.

    Canonical fields (preferred API):
      dimensions, metrics, derived_metrics, comparisons, rankings,
      relationships, filters, requested_conclusions

    Legacy aliases kept for existing callers:
      derived (== derived_metrics), operations, needs_top_n, needs_bottom_n
    """

    dimensions: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    derived_metrics: List[str] = field(default_factory=list)
    comparisons: List[str] = field(default_factory=list)
    rankings: List[str] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    requested_conclusions: List[str] = field(default_factory=list)

    # Legacy / convenience
    needs_top_n: Optional[int] = None
    needs_bottom_n: Optional[int] = None

    @property
    def derived(self) -> List[str]:
        """Back-compat alias used by existing coverage / prompt code."""
        return self.derived_metrics

    @derived.setter
    def derived(self, value: List[str]) -> None:
        self.derived_metrics = list(value or [])

    @property
    def operations(self) -> List[str]:
        """Flattened operation tags derived from richer fields (legacy)."""
        ops: List[str] = []
        if self.relationships:
            ops.append("correlation_or_relationship")
        if self.dimensions and (
            self.relationships
            or any("each" in c or "per_" in c for c in self.comparisons)
            or "group_by_dimension" in self.comparisons
        ):
            ops.append("group_by_dimension")
        if self.comparisons:
            ops.append("compare")
        if self.rankings or self.needs_top_n is not None or self.needs_bottom_n is not None:
            ops.append("rank")
        if self.needs_top_n is not None:
            ops.append("top_n")
        if self.needs_bottom_n is not None:
            ops.append("bottom_n")
        if self.needs_top_n is not None and self.needs_bottom_n is not None:
            ops.append("rank_intersection")
        if any("aggregat" in c or c.startswith("total_") for c in self.comparisons):
            ops.append("aggregate")
        if any("trend" in c for c in self.comparisons + self.requested_conclusions):
            ops.append("trend")
        return _uniq(ops)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "dimensions": list(self.dimensions),
            "metrics": list(self.metrics),
            "derived_metrics": list(self.derived_metrics),
            "comparisons": list(self.comparisons),
            "rankings": list(self.rankings),
            "relationships": list(self.relationships),
            "filters": list(self.filters),
            "requested_conclusions": list(self.requested_conclusions),
            "needs_top_n": self.needs_top_n,
            "needs_bottom_n": self.needs_bottom_n,
            # legacy mirrors for existing artifact consumers
            "derived": list(self.derived_metrics),
            "operations": self.operations,
        }
        return data

    def summary_lines(self) -> List[str]:
        lines: List[str] = []
        if self.dimensions:
            lines.append("dimensions: " + ", ".join(self.dimensions))
        if self.metrics:
            lines.append("metrics: " + ", ".join(self.metrics))
        if self.derived_metrics:
            lines.append("derived_metrics: " + ", ".join(self.derived_metrics))
        if self.comparisons:
            lines.append("comparisons: " + ", ".join(self.comparisons))
        if self.rankings:
            lines.append("rankings: " + ", ".join(self.rankings))
        if self.relationships:
            lines.append("relationships: " + ", ".join(self.relationships))
        if self.filters:
            lines.append("filters: " + ", ".join(self.filters))
        if self.requested_conclusions:
            lines.append("requested_conclusions: " + ", ".join(self.requested_conclusions))
        if self.needs_top_n is not None:
            lines.append(f"top_n: {self.needs_top_n}")
        if self.needs_bottom_n is not None:
            lines.append(f"bottom_n: {self.needs_bottom_n}")
        return lines


def extract_question_requirements(question: str) -> QuestionRequirements:
    """
    Deterministically extract structured analytical requirements from a question.

    profit and profit_margin are distinct:
      - "profit" / "profitability" → metric profit
      - "profit margin" / "margins" → derived_metrics profit_margin
    """
    q = _norm(question)
    req = QuestionRequirements()

    # ── Dimensions / grouping entities ──────────────────────────────────────
    # Filters first so "in Delhi" / "through Online channel" do not force grouping dims
    city_filter = re.search(
        r"\bin\s+(delhi|mumbai|jaipur|pune|chennai|bangalore|bengaluru|hyderabad|kolkata)\b",
        q,
    )
    if city_filter:
        req.filters.append(f"city={city_filter.group(1).title()}")

    segment_filter = re.search(
        r"\bamong\s+(corporate|consumer|home\s+office|small\s+business)\b"
        r"|\b(corporate|consumer|home\s+office)\s+customers?\b",
        q,
    )
    if segment_filter:
        seg = (segment_filter.group(1) or segment_filter.group(2) or "").strip()
        if seg:
            req.filters.append(f"segment={seg.title()}")

    channel_filter = re.search(
        r"\b(?:through|via|on|using)\s+(?:the\s+)?(online|retail|partner)\s+channel\b",
        q,
    )
    if channel_filter:
        req.filters.append(f"channel={channel_filter.group(1).title()}")

    if re.search(r"\bcit(y|ies)\b", q) and not any(f.startswith("city=") for f in req.filters):
        req.dimensions.append("city")
    if re.search(r"\bcategor", q):
        req.dimensions.append("category")
    if re.search(r"\b(customer\s+)?segments?\b", q) and not any(
        f.startswith("segment=") for f in req.filters
    ):
        req.dimensions.append("segment")
    if re.search(r"\bregions?\b", q):
        req.dimensions.append("region")
    if re.search(r"\bchannel", q) and not any(f.startswith("channel=") for f in req.filters):
        req.dimensions.append("channel")
    if re.search(
        r"\b(which\s+products?|product\s+has|products?\s+with|by product|per product|"
        r"each product|top\s+\d+\s+products?|products?\s+by)\b",
        q,
    ):
        req.dimensions.append("product")
    elif re.search(r"\bproducts?\b", q) and not re.search(r"\bcategor", q):
        if re.search(r"\b(across|by|per|each)\s+products?\b", q):
            req.dimensions.append("product")

    # Time-series / period grouping intent
    if re.search(r"\b(months?|monthly|quarters?|quarterly|over time|by month|by quarter)\b", q):
        req.comparisons.append("time_series")
    if re.search(r"\b(decline|drop|fell|largest decrease)\b", q):
        req.comparisons.append("period_over_period_change")

    # Unsupported predictive / causal asks (pipeline is descriptive analytics)
    if re.search(
        r"\b(predict|forecast|will become|next year|next month|what caused)\b"
        r"|\bcaus(?:e|ed|es)\b",
        q,
    ):
        req.requested_conclusions.append("unsupported_predictive_or_causal")

    # ── Metrics (base measures — not derived) ───────────────────────────────
    if re.search(r"\b(sales_amount|sales volume|order value|revenue|gmv)\b", q) or re.search(
        r"\bsales\b", q
    ):
        req.metrics.append("sales")
    if re.search(r"\b(quantity|units?\s+sold|unit count)\b", q):
        req.metrics.append("quantity")
    if re.search(r"\bdiscount(_rate|_pct|_percent)?\b", q):
        req.metrics.append("discount")

    # profit vs profit_margin: detect margin first so we can still add profit when needed
    has_explicit_margin = bool(re.search(r"\b(profit\s*margins?|margins?)\b", q))
    # "profitability" implies profit concept; "profit margin" is derived
    has_profit_word = bool(re.search(r"\bprofit", q))  # profit, profits, profitability
    if has_profit_word:
        req.metrics.append("profit")

    # ── Derived metrics ─────────────────────────────────────────────────────
    if has_explicit_margin:
        req.derived_metrics.append("profit_margin")
    if re.search(r"\bprofitability\b", q) and "profit_margin" not in req.derived_metrics:
        req.derived_metrics.append("profit_margin")

    # high sales + low/weak profit(/margin) ⇒ need margin (or sales+profit contrast)
    contrast_high_low = bool(
        re.search(r"\b(sales|revenue)\b", q)
        and re.search(r"\bprofit", q)
        and re.search(
            r"\b(high|highest|strong|strongest|low|lowest|weak|weakest|"
            r"relative|compar|but|versus|vs|mismatch)\b",
            q,
        )
    )
    if contrast_high_low and "profit_margin" not in req.derived_metrics:
        # Prefer capturing margin intent for profitability comparisons
        if has_explicit_margin or re.search(
            r"\b(relative|compar|mismatch|weak|weakest|but|strongest|strong)\b", q
        ):
            req.derived_metrics.append("profit_margin")

    if re.search(r"\b(average|avg|mean)\b", q) and re.search(r"\b(discount|sales|profit|quantity)\b", q):
        # average of a base metric is still the same metric; mark comparison tag
        req.comparisons.append("average_requested")
    if re.search(r"\b(growth|yoy|mom|increase|decrease)\b", q):
        req.derived_metrics.append("growth")

    # Ensure sales+profit present when margin is required
    if "profit_margin" in req.derived_metrics:
        if "sales" not in req.metrics:
            req.metrics.append("sales")
        if "profit" not in req.metrics:
            req.metrics.append("profit")

    # Explicit "calculate total sales, total profit, and profit margin"
    if re.search(r"\btotal\s+sales\b", q) and "sales" not in req.metrics:
        req.metrics.append("sales")
    if re.search(r"\btotal\s+profit\b", q) and "profit" not in req.metrics:
        req.metrics.append("profit")

    # ── Relationships ───────────────────────────────────────────────────────
    if re.search(r"\b(relationship|correlat|associated with|association)\b", q):
        # Capture subject pair when possible
        if re.search(r"\bdiscount", q) and re.search(r"\b(profit|margin|profitab)", q):
            req.relationships.append("discount_vs_profitability")
        elif re.search(r"\b(relationship|correlat)\b", q):
            req.relationships.append("metric_relationship")
        # Critical: "across/by <dimension>" must keep that dimension (already extracted)
        if req.dimensions and re.search(r"\b(across|by|per|among)\b", q):
            req.relationships.append("across_dimension")

    # ── Comparisons ─────────────────────────────────────────────────────────
    if re.search(
        r"\b(high|highest|strong|strongest).{0,40}\b(sales|revenue).{0,60}"
        r"\b(low|lowest|weak|weakest|relative).{0,40}\bprofit",
        q,
    ) or (
        re.search(r"\b(sales|revenue)\b", q)
        and re.search(r"\bprofit", q)
        and re.search(r"\b(but|versus|vs|mismatch|relative)\b", q)
    ):
        req.comparisons.append("high_sales_low_profit")

    if re.search(r"\b(compare|comparison|versus|vs\.?)\b", q):
        req.comparisons.append("compare_groups")
    if re.search(r"\b(each|for each|every|all segments|all categor)\b", q):
        req.comparisons.append("per_group_breakdown")
    if req.dimensions and re.search(r"\b(across|by|per)\b", q):
        req.comparisons.append("group_by_dimension")
    if re.search(r"\bmismatch\b", q):
        req.comparisons.append("identify_mismatch")

    # ── Rankings ────────────────────────────────────────────────────────────
    m = re.search(r"\btop\s+(\d+)\b", q)
    if m:
        req.needs_top_n = int(m.group(1))
        req.rankings.append(f"top_{m.group(1)}")
    m = re.search(r"\bbottom\s+(\d+)\b", q)
    if m:
        req.needs_bottom_n = int(m.group(1))
        req.rankings.append(f"bottom_{m.group(1)}")
    if re.search(r"\b(highest|most)\b", q) and re.search(r"\b(sales|revenue|profit|margin)\b", q):
        req.rankings.append("highest")
    if re.search(r"\b(lowest|least|weak)\b", q) and re.search(r"\b(sales|revenue|profit|margin)\b", q):
        req.rankings.append("lowest")
    if req.needs_top_n is not None and req.needs_bottom_n is not None:
        req.rankings.append("rank_intersection")

    # ── Filters already populated above (city / segment / channel literals) ──

    # ── Requested conclusions / narrative asks ──────────────────────────────
    if re.search(r"\b(business insight|insight|what (could|does) this (indicate|mean|imply)|derive)\b", q):
        req.requested_conclusions.append("business_insight")
    if re.search(r"\b(identify|which)\b", q) and req.dimensions:
        req.requested_conclusions.append("identify_entity")
    if re.search(r"\b(prioritize|should the company)\b", q):
        req.requested_conclusions.append("prioritization_recommendation")
    if re.search(r"\bmismatch\b", q):
        req.requested_conclusions.append("explain_mismatch")
    if re.search(r"\b(practically significant|meaningful|negligible)\b", q):
        req.requested_conclusions.append("practical_significance")

    req.dimensions = _uniq(req.dimensions)
    req.metrics = _uniq(req.metrics)
    req.derived_metrics = _uniq(req.derived_metrics)
    req.comparisons = _uniq(req.comparisons)
    req.rankings = _uniq(req.rankings)
    req.relationships = _uniq(req.relationships)
    req.filters = _uniq(req.filters)
    req.requested_conclusions = _uniq(req.requested_conclusions)
    return req


def match_requirements_to_schema(
    requirements: QuestionRequirements,
    columns: Sequence[str],
) -> Dict[str, Optional[str]]:
    """
    Schema-aware helper: map logical requirement tokens → best matching column.

    Returns dict like {"city": "city", "sales": "sales_amount", "profit_margin": None}.
    Does not invent columns; None means no confident match in the provided schema.
    """
    lower_map = {c.lower(): c for c in columns if c}
    matched: Dict[str, Optional[str]] = {}

    tokens = list(requirements.dimensions) + list(requirements.metrics) + list(
        requirements.derived_metrics
    )
    for token in _uniq(tokens):
        aliases = _SCHEMA_ALIASES.get(token, (token,))
        found: Optional[str] = None
        for alias in aliases:
            if alias.lower() in lower_map:
                found = lower_map[alias.lower()]
                break
        if found is None:
            # fuzzy contains
            for alias in aliases:
                for col_l, col in lower_map.items():
                    if alias.lower() in col_l or col_l in alias.lower():
                        found = col
                        break
                if found:
                    break
        matched[token] = found
    return matched


def format_semantic_requirement_contract(
    requirements: QuestionRequirements,
    *,
    schema_columns: Optional[Sequence[str]] = None,
) -> str:
    """
    Concise machine-readable contract for SQL/code generation prompts.

    Prefer this over relying on the natural-language question alone.
    """
    req = requirements
    lines: List[str] = ["SEMANTIC REQUIREMENTS"]

    def _section(title: str, items: Sequence[str]) -> None:
        lines.append(f"{title}:")
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- (none)")

    _section("Dimensions", req.dimensions)
    _section("Metrics", req.metrics)
    _section("Derived metrics", req.derived_metrics)
    _section("Comparisons", req.comparisons)
    _section("Rankings", req.rankings)
    _section("Relationships", req.relationships)
    if req.filters:
        _section("Filters", req.filters)
    if req.requested_conclusions:
        _section("Requested conclusions", req.requested_conclusions)

    expectations: List[str] = []
    if req.dimensions:
        expectations.append(
            "return "
            + "/".join(req.dimensions)
            + "-level rows (GROUP BY the dimension; never collapse to a global-only aggregate)"
        )
    if "discount" in req.metrics:
        expectations.append("include discount information (e.g. AVG(discount_rate))")
    if "sales" in req.metrics:
        expectations.append("include sales/sales_amount aggregate")
    if "profit" in req.metrics:
        expectations.append("include profit aggregate (distinct from profit_margin)")
    if "profit_margin" in req.derived_metrics:
        expectations.append(
            "compute profit_margin = SUM(profit)/NULLIF(SUM(sales_amount),0) — "
            "do not substitute raw profit for margin"
        )
    if req.relationships:
        expectations.append(
            "preserve relationship evaluation at the requested dimension "
            "(do not return only a global CORR()/correlation)"
        )
    if "compare_groups" in req.comparisons:
        expectations.append(
            "return multiple groups for comparison — avoid LIMIT 1 unless comparison context is included"
        )
    if "rank_intersection" in req.rankings or (
        req.needs_top_n is not None and req.needs_bottom_n is not None
    ):
        n_top = req.needs_top_n or "N"
        n_bot = req.needs_bottom_n or "N"
        expectations.append(
            f"use separate rankings for top {n_top} and bottom {n_bot}; "
            "return their INTERSECTION (sales_rank AND margin_rank)"
        )
    elif req.rankings:
        expectations.append("include ranking/ordering context for highest/lowest identification")
    if req.requested_conclusions:
        expectations.append(
            "return enough metric evidence for the report layer to derive the conclusion "
            "(SQL must not write the narrative)"
        )

    lines.append("Required output expectations:")
    if expectations:
        for e in expectations:
            lines.append(f"- {e}")
    else:
        lines.append("- answer the question with all explicitly requested fields")

    if schema_columns:
        matched = match_requirements_to_schema(req, schema_columns)
        mapped = [f"{k}→{v}" for k, v in matched.items() if v]
        if mapped:
            lines.append("Schema column hints:")
            for m in mapped:
                lines.append(f"- {m}")

    return "\n".join(lines)


def generation_precheck_feedback(
    question: str,
    missing: Sequence[str],
    requirements: Optional[QuestionRequirements] = None,
) -> str:
    """Concise retry feedback when generated SQL fails the semantic pre-check."""
    req = requirements or extract_question_requirements(question)
    contract_bits: List[str] = []
    if req.dimensions:
        contract_bits.append("dimensions=" + ",".join(req.dimensions))
    if req.metrics:
        contract_bits.append("metrics=" + ",".join(req.metrics))
    if req.derived_metrics:
        contract_bits.append("derived=" + ",".join(req.derived_metrics))
    if req.relationships:
        contract_bits.append("relationships=" + ",".join(req.relationships))
    if req.rankings:
        contract_bits.append("rankings=" + ",".join(req.rankings))

    miss = "; ".join(missing)
    return (
        "semantic_incomplete pre-check failed.\n"
        f"Question requires: {'; '.join(contract_bits) or 'full coverage'}.\n"
        f"Missing: {miss}.\n"
        "Regenerate SQL that satisfies the SEMANTIC REQUIREMENTS contract. "
        "Never collapse a dimension-level question into a global aggregate. "
        "Never substitute profit for profit_margin when margin is required. "
        "Never answer a top/bottom intersection with only one ranking."
    )


_DIM_PLAN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "city": ("city", "cities"),
    "category": ("categor", "product categor"),
    "segment": ("segment", "customer_segment", "customer segment"),
    "region": ("region",),
    "product": ("product",),
    "channel": ("channel", "sales_channel"),
}


def _plan_blob(steps: Sequence[str]) -> str:
    return _norm(" ".join(str(s) for s in (steps or [])))


def check_plan_requirement_coverage(
    question: str,
    steps: Sequence[str],
    requirements: Optional[QuestionRequirements] = None,
) -> Tuple[bool, List[str]]:
    """
    Lightweight deterministic check that a planner's steps address canonical requirements.

    Does not execute SQL. Used by the planner self-check before returning a plan.
    """
    req = requirements or extract_question_requirements(question)
    blob = _plan_blob(steps)
    missing: List[str] = []

    def has(*pats: str) -> bool:
        return any(re.search(p, blob) for p in pats)

    # Dimensions: must mention the dimension AND grouping/comparison intent
    for dim in req.dimensions:
        aliases = _DIM_PLAN_ALIASES.get(dim, (dim,))
        dim_mentioned = any(a in blob for a in aliases)
        grouped = has(
            r"\bgroup",
            r"\bacross\b",
            r"\bby\b",
            r"\beach\b",
            r"\bper\b",
            r"\bcompar",
            r"\brank",
            r"\bbreakdown\b",
        )
        if not dim_mentioned:
            missing.append(f"plan missing dimension: {dim}")
        elif not grouped and dim_mentioned:
            # soft: if dimension appears with relationship language still OK
            if not has(r"\brelationship\b", r"\bmismatch\b", r"\bversus\b", r"\bvs\b"):
                missing.append(
                    f"plan missing grouping/comparison across {dim}"
                )

    if "sales" in req.metrics and not has(r"\bsales", r"\brevenue", r"\bgmv"):
        missing.append("plan missing metric: sales")

    if "profit" in req.metrics:
        # profit_margin alone does not count as planning for base profit
        scrubbed = re.sub(r"profit\s*_?\s*margins?", " ", blob)
        if not re.search(r"\bprofit", scrubbed):
            missing.append("plan missing metric: profit")

    if "discount" in req.metrics and not has(r"\bdiscount"):
        missing.append("plan missing metric: discount")

    if "quantity" in req.metrics and not has(r"\bquantity", r"\bunits\b", r"\bvolume\b"):
        missing.append("plan missing metric: quantity")

    if "profit_margin" in req.derived_metrics:
        has_margin = has(
            r"\bmargin\b",
            r"profit\s*margin",
            r"profitability",
            r"profit\s+relative\s+to\s+sales",
            r"profit\s*/\s*sales",
        )
        if not has_margin:
            missing.append(
                "plan missing derived metric: profit_margin "
                "(raw profit is not equivalent)"
            )

    # Relationships must not be planned as global-only when a dimension is required
    if req.relationships and req.dimensions:
        dim_ok = all(
            any(a in blob for a in _DIM_PLAN_ALIASES.get(d, (d,)))
            for d in req.dimensions
        )
        avoids_global = has(
            r"not only a global correl",
            r"do not .{0,40}global correl",
            r"never .{0,40}global correl",
            r"not .{0,30}only .{0,30}correl",
            r"avoid .{0,30}global correl",
        )
        global_only = has(r"\bglobal\s+correl") and not avoids_global
        correl_without_dim = (
            has(r"\bcorrelat")
            and not dim_ok
            and not has(r"\bgroup", r"\bacross\b", r"\bper\b", r"\beach\b", r"-level")
        )
        if global_only or correl_without_dim:
            missing.append(
                "plan relationship incomplete: need dimension-level analysis "
                "(not only a global correlation)"
            )
        if "discount_vs_profitability" in req.relationships:
            if not (has(r"\bdiscount") and has(r"\bprofit", r"\bmargin", r"\bprofitab")):
                missing.append(
                    "plan relationship incomplete: need discount and profitability together"
                )

    # Comparisons / contrast
    if "high_sales_low_profit" in req.comparisons or "identify_mismatch" in req.comparisons:
        if not has(
            r"\bcompar",
            r"\brank",
            r"\bmismatch",
            r"\bversus",
            r"\bvs\b",
            r"\bhigh",
            r"\blow",
            r"\brelative",
        ):
            missing.append("plan missing comparative logic for sales vs profitability")

    # Ranking intersection
    needs_intersection = "rank_intersection" in req.rankings or (
        req.needs_top_n is not None and req.needs_bottom_n is not None
    )
    if needs_intersection:
        has_top = has(r"\btop\b", r"\bhighest\b")
        has_bottom = has(r"\bbottom\b", r"\blowest\b")
        has_intersect = has(
            r"\bintersect",
            r"sales_rank",
            r"margin_rank",
            r"independently\s+rank",
            r"separate\s+rank",
            r"both\s+rank",
        )
        has_sales_side = has(r"\bsales", r"\brevenue") and has_top
        has_margin_side = has(r"\bmargin", r"profit_margin") and has_bottom
        if not (has_top and has_bottom):
            missing.append(
                "plan ranking incomplete: need both top-N (sales) and bottom-N (margin)"
            )
        elif not (has_intersect or (has_sales_side and has_margin_side)):
            missing.append(
                "plan ranking incomplete: need intersection of top sales and bottom margin"
            )

    return (len(_uniq(missing)) == 0, _uniq(missing))


def plan_precheck_feedback(
    question: str,
    missing: Sequence[str],
    requirements: Optional[QuestionRequirements] = None,
) -> str:
    """Retry feedback when a plan fails the semantic self-check."""
    req = requirements or extract_question_requirements(question)
    return (
        "semantic_incomplete: planner self-check failed.\n"
        f"Missing from plan: {'; '.join(missing)}.\n"
        "Revise steps so they explicitly cover every item in the SEMANTIC REQUIREMENTS "
        "contract (dimensions with GROUP BY / across, metrics, profit_margin if required, "
        "dual rankings + intersection when required). "
        "Do not plan a global-only correlation when a dimension is required."
    )


def build_requirement_aware_plan_steps(requirements: QuestionRequirements) -> List[str]:
    """
    Deterministic plan steps derived from canonical requirements.
    Used for DEMO/fallback enrichment and as a last-resort plan repair.
    """
    req = requirements
    steps: List[str] = []

    if req.dimensions:
        dims = ", ".join(req.dimensions)
        steps.append(f"Group and compare records across {dims}")

    if "discount" in req.metrics:
        steps.append("Calculate discount metrics (e.g. average discount_rate) per group")
    if "sales" in req.metrics:
        steps.append("Aggregate total sales / sales_amount per group")
    if "profit" in req.metrics:
        steps.append("Aggregate total profit per group")
    if "quantity" in req.metrics:
        steps.append("Aggregate quantity / volume per group")

    if "profit_margin" in req.derived_metrics:
        steps.append(
            "Calculate profit margin using profit relative to sales "
            "(SUM(profit)/NULLIF(SUM(sales_amount),0)) — do not substitute raw profit"
        )
    elif "discount_vs_profitability" in req.relationships or any(
        "profitab" in r for r in req.relationships
    ):
        # Relationship asks for profitability even when extractor did not tag profit_margin
        steps.append(
            "Calculate profitability / profit margin using profit relative to sales per group"
        )
        if "sales" not in req.metrics:
            steps.append("Aggregate sales volume per group for comparison")

    if req.relationships:
        dim = req.dimensions[0] if req.dimensions else "the requested dimension"
        steps.append(
            f"Evaluate the relationship across {dim}-level metrics "
            "(do not use only a global correlation)"
        )

    if "high_sales_low_profit" in req.comparisons or "identify_mismatch" in req.comparisons:
        steps.append(
            "Compare groups to identify high sales with relatively low profit / margin mismatch"
        )
    elif "compare_groups" in req.comparisons:
        steps.append("Compare groups against each other using the calculated metrics")

    if "rank_intersection" in req.rankings or (
        req.needs_top_n is not None and req.needs_bottom_n is not None
    ):
        n_top = req.needs_top_n or "N"
        n_bot = req.needs_bottom_n or "N"
        steps.append(f"Independently rank groups by sales (top {n_top})")
        steps.append(f"Independently rank groups by profit margin (bottom {n_bot})")
        steps.append(
            "Intersect the two ranked sets (top sales AND bottom profit margin)"
        )
    else:
        if "highest" in req.rankings or "lowest" in req.rankings:
            steps.append("Rank or order groups to identify highest and/or lowest values")

    if req.requested_conclusions:
        steps.append(
            "Return enough metric evidence for the report layer to derive the business conclusion"
        )

    if not steps:
        steps.append("Map question intent to aggregation / ranking / grouping")

    steps.append("Generate and validate safe SELECT SQL")
    steps.append("Execute against DuckDB and summarize results")
    return steps



# Back-compat alias used by older imports/tests
def extract_analytics_requirements(question: str) -> Dict[str, Any]:
    r = extract_question_requirements(question)
    return {
        "needs_sales": "sales" in r.metrics,
        "needs_profit": "profit" in r.metrics,
        "needs_margin": "profit_margin" in r.derived_metrics,
        "needs_city": "city" in r.dimensions,
        "needs_category": "category" in r.dimensions,
        "needs_top_n": r.needs_top_n,
        "needs_bottom_n": r.needs_bottom_n,
        "needs_intersection": "rank_intersection" in r.rankings
        or (r.needs_top_n is not None and r.needs_bottom_n is not None),
        **r.to_dict(),
    }


def _blob_has(blob: str, *pats: str) -> bool:
    return any(re.search(p, blob) for p in pats)


def _has_dimension_coverage(
    dim: str, *, sql_l: str, cols_l: Sequence[str], blob: str
) -> bool:
    """True if result/SQL clearly includes the analytical dimension (not global-only)."""
    has = lambda *p: _blob_has(blob, *p)  # noqa: E731
    if dim == "segment":
        return has(r"\bcustomer_segment\b", r"\bsegment\b") and (
            "group by" in sql_l or any("segment" in c for c in cols_l)
        )
    if dim == "category":
        return has(r"\bcategor") and (
            "group by" in sql_l or any("categor" in c for c in cols_l)
        )
    if dim == "channel":
        # sales_channel: underscore means \bchannel\b alone does not match
        return has(r"\bsales_channel\b", r"\bchannel\b") and (
            "group by" in sql_l or any("channel" in c for c in cols_l)
        )
    return has(rf"\b{re.escape(dim)}\b") and (
        "group by" in sql_l or any(dim in c for c in cols_l)
    )


def _has_sales_metric(blob: str) -> bool:
    return _blob_has(
        blob, r"\bsales", r"\brevenue", r"\bgmv", r"\border_value\b", r"\bsales_amount\b"
    )


def _has_profit_metric(blob: str) -> bool:
    """Base profit metric. A lone profit_margin column does not count as profit."""
    scrubbed = re.sub(r"profit\s*_?\s*margins?", " ", blob)
    return bool(re.search(r"\bprofit\b", scrubbed))


def _has_margin_derived(blob: str) -> bool:
    """profit_margin must be present or clearly computed; profit-only is insufficient."""
    return _blob_has(
        blob,
        r"\bprofit_margin\b",
        r"\bmargin\b",
        r"profit\s*/\s*",
        r"/\s*nullif",
        r"sum\s*\(\s*profit\s*\)\s*/",
    )


def _has_rank_intersection_coverage(blob: str, sql_l: str) -> bool:
    """
    Top-N ∩ bottom-N requires evidence of BOTH ranking sides.
    A single RANK() on sales alone must fail.
    """
    sales_rank = _blob_has(
        blob,
        r"\bsales_rank\b",
        r"\brevenue_rank\b",
        r"rank\s*\([^)]*order\s+by[^)]*sales",
        r"row_number\s*\([^)]*order\s+by[^)]*sales",
        r"dense_rank\s*\([^)]*order\s+by[^)]*sales",
    )
    margin_rank = _blob_has(
        blob,
        r"\bmargin_rank\b",
        r"\bprofit_margin_rank\b",
        r"rank\s*\([^)]*order\s+by[^)]*(margin|profit_margin)",
        r"row_number\s*\([^)]*order\s+by[^)]*(margin|profit_margin)",
        r"dense_rank\s*\([^)]*order\s+by[^)]*(margin|profit_margin)",
    )
    if sales_rank and margin_rank:
        return True

    # Two window ranks + both sales and margin concepts in the query
    rank_calls = len(re.findall(r"\b(?:rank|row_number|dense_rank)\s*\(", sql_l))
    if rank_calls >= 2 and _has_sales_metric(blob) and _has_margin_derived(blob):
        return True

    # Explicit dual filter language
    if re.search(r"sales_rank\s*<=", sql_l) and re.search(
        r"(margin_rank|profit_margin_rank)\s*<=", sql_l
    ):
        return True

    return False


def _has_comparison_support(
    req: QuestionRequirements,
    *,
    sql_l: str,
    blob: str,
    row_count: Optional[int],
) -> Optional[str]:
    """
    Return a missing-label if compare-with-other-groups is required but unsupported.
    Narrative insight alone is not required; multi-group evidence is.
    """
    # Only explicit compare-with-others — not every GROUP BY / across-dimension query
    if "compare_groups" not in req.comparisons:
        return None

    # Hard single-row / single-group collapse
    if re.search(r"\blimit\s+1\b", sql_l) or re.search(r"\bfetch\s+first\s+1\b", sql_l):
        return (
            "comparison incomplete: result limited to a single row; "
            "need multiple groups for comparison"
        )
    if row_count is not None and row_count < 2:
        return (
            "comparison incomplete: fewer than 2 groups/rows; "
            "cannot compare with other categories/segments"
        )
    return None


def check_requirement_coverage(
    question: str,
    sql: Optional[str],
    columns: Optional[Sequence[str]] = None,
    row_count: Optional[int] = None,
) -> Tuple[bool, List[str]]:
    """
    Return (ok, missing_requirements).

    Deterministic semantic gate: executed SQL/columns/row_count must cover
    canonical requirements from extract_question_requirements().
    profit != profit_margin. Global aggregates fail when a dimension is required.
    """
    req = extract_question_requirements(question)
    sql_l = (sql or "").lower()
    cols_l = [str(c).lower() for c in (columns or [])]
    blob = _blob(sql or "", columns or [])
    missing: List[str] = []
    q = _norm(question)

    # 1. Metrics
    if "sales" in req.metrics and not _has_sales_metric(blob):
        missing.append("required metric missing: sales/revenue")

    if "profit" in req.metrics and not _has_profit_metric(blob):
        missing.append("required metric missing: profit")

    if "discount" in req.metrics and not _blob_has(blob, r"\bdiscount"):
        missing.append("required metric missing: discount")

    if "quantity" in req.metrics and not _blob_has(
        blob, r"\bquantity", r"\bqty\b", r"\bunits\b"
    ):
        missing.append("required metric missing: quantity")

    # 2. Derived metrics — profit_margin is NOT satisfied by profit alone
    if "profit_margin" in req.derived_metrics:
        explicit_margin = bool(re.search(r"\b(profit\s*margins?|margins?)\b", q))
        if explicit_margin:
            if not _has_margin_derived(blob):
                missing.append(
                    "derived metric missing: profit_margin "
                    "(profit alone is not sufficient; need margin or profit/sales)"
                )
        else:
            # Contrast questions may accept sales+profit as enough to judge low profitability
            if not (
                _has_margin_derived(blob)
                or (_has_sales_metric(blob) and _has_profit_metric(blob))
            ):
                missing.append(
                    "derived metric missing: sales vs profit comparison / profit_margin"
                )

    # 3. Dimensions — every explicit dimension must appear
    dim_labels = {
        "city": "required dimension missing: city",
        "category": "required dimension missing: category (GROUP BY category)",
        "segment": "required dimension missing: customer_segment",
        "region": "required dimension missing: region",
        "product": "required dimension missing: product",
        "channel": "required dimension missing: sales_channel",
    }
    for dim in req.dimensions:
        if not _has_dimension_coverage(dim, sql_l=sql_l, cols_l=cols_l, blob=blob):
            missing.append(dim_labels.get(dim, f"required dimension missing: {dim}"))

    # 4. Relationships — must be evaluable at the requested dimension level
    if req.relationships and req.dimensions:
        for dim in req.dimensions:
            if not _has_dimension_coverage(dim, sql_l=sql_l, cols_l=cols_l, blob=blob):
                missing.append(
                    f"relationship not evaluable: missing {dim}-level breakdown "
                    "(global correlation alone is not enough)"
                )
                break
        if "discount_vs_profitability" in req.relationships or (
            "discount" in req.metrics and ("profit" in req.metrics or "profit_margin" in req.derived_metrics)
        ):
            if not (
                _blob_has(blob, r"\bdiscount")
                and (_has_margin_derived(blob) or _has_profit_metric(blob))
            ):
                missing.append(
                    "relationship not evaluable: need discount and profitability "
                    "together at the dimension level"
                )
        # Global-only CORR()/correlation without GROUP BY
        if re.search(r"\b(corr|correlation)\b", sql_l) and "group by" not in sql_l:
            if req.dimensions:
                missing.append(
                    "relationship not evaluable: global correlation without "
                    "dimension-level metrics"
                )

    # 5. Ranking / intersection
    needs_intersection = "rank_intersection" in req.rankings or (
        req.needs_top_n is not None and req.needs_bottom_n is not None
    )
    if needs_intersection:
        if not _has_rank_intersection_coverage(blob, sql_l):
            missing.append(
                "ranking incomplete: need top-N by sales AND bottom-N by profit_margin "
                "with intersection (single-side ranking is not enough)"
            )

    # 6. Comparison with other groups
    cmp_miss = _has_comparison_support(
        req, sql_l=sql_l, blob=blob, row_count=row_count
    )
    if cmp_miss:
        missing.append(cmp_miss)

    # 7. High sales / low profit contrast still needs both base metrics
    if (
        "high_sales_low_profit" in req.comparisons
        or re.search(
            r"\b(high|highest|strong|strongest).{0,40}\b(sales|revenue).{0,60}"
            r"\b(low|lowest|weak|weakest).{0,40}\bprofit",
            q,
        )
        or (
            re.search(r"\bsales\b", q)
            and re.search(r"\bprofit", q)
            and re.search(r"\bbut\b", q)
        )
    ):
        if _has_profit_metric(blob) and not _has_sales_metric(blob):
            missing.append(
                "comparison incomplete: sales metric required alongside profit "
                "(high sales / low profit)"
            )

    # 8. Explicit filters must appear in SQL
    for filt in req.filters:
        key, _, val = filt.partition("=")
        val_l = val.lower()
        if not val_l:
            continue
        if key == "city" and val_l not in sql_l:
            missing.append(f"required filter missing: city={val}")
        elif key == "segment" and val_l not in sql_l and "corporate" not in sql_l:
            missing.append(f"required filter missing: segment={val}")
        elif key == "channel" and val_l not in sql_l:
            missing.append(f"required filter missing: channel={val}")

    # 9. Time grouping for month/quarter/over-time questions
    if "time_series" in req.comparisons or "period_over_period_change" in req.comparisons:
        if not _blob_has(
            blob,
            r"date_trunc",
            r"strftime",
            r"\bmonth\b",
            r"\bquarter\b",
            r"\bperiod\b",
            r"order_date",
        ):
            missing.append(
                "required time grouping missing (order_date month/quarter/period)"
            )

    # 10. Predictive / causal questions are outside descriptive analytics support
    if "unsupported_predictive_or_causal" in req.requested_conclusions:
        missing.append(
            "unsupported question: predictive/causal analysis is not available "
            "in the current descriptive analytics pipeline"
        )

    # De-dupe while preserving order
    missing = _uniq(missing)
    return (len(missing) == 0, missing)


def coverage_failure_message(
    missing: List[str],
    *,
    question: str = "",
    requirements: Optional[QuestionRequirements] = None,
) -> str:
    """
    Human-readable semantic_incomplete feedback for retries.
    Does not require a narrative insight sentence in the result set.
    """
    req = requirements or (
        extract_question_requirements(question) if question else None
    )
    joined = "; ".join(missing)

    if req:
        parts: List[str] = []
        if req.dimensions:
            parts.append(
                f"{'/'.join(req.dimensions)}-level analysis of "
                + ", ".join(
                    list(req.metrics)
                    + [f"derived:{d}" for d in req.derived_metrics]
                )
            )
        if req.relationships:
            parts.append("relationship evaluation (" + ", ".join(req.relationships) + ")")
        if any("compar" in m.lower() for m in missing) or "compare_groups" in req.comparisons:
            parts.append("group comparison")
        if any("rank" in m.lower() for m in missing) or "rank_intersection" in req.rankings:
            parts.append("dual ranking / intersection")
        need = "; ".join(parts) if parts else "full analytical coverage"
        return (
            f"semantic_incomplete: Question requires {need}. "
            f"Previous result was incomplete: {joined}."
        )

    return (
        f"semantic_incomplete: Generated SQL/results do not cover required "
        f"concepts from the question: {joined}."
    )


def confidence_from_coverage(
    *,
    coverage_ok: bool,
    missing: Sequence[str],
    analysis_source: Optional[str] = None,
    execution_success: bool = True,
    evidence_limited: bool = False,
) -> str:
    """
    Map coverage + evidence quality to High/Medium/Low.

    Execution success alone is never enough for High.
    Deterministic fallback is NOT downgraded solely due to source when coverage passes.
    """
    if not execution_success or not coverage_ok:
        return "Low"
    if missing or evidence_limited:
        return "Medium"
    return "High"


def schema_column_names(schema_profile: Optional[Dict[str, Any]]) -> List[str]:
    schema_profile = schema_profile or {}
    cols = schema_profile.get("columns") or []
    names: List[str] = []
    for c in cols:
        if isinstance(c, dict):
            names.append(str(c.get("name") or ""))
        else:
            names.append(str(c))
    if schema_profile.get("multi_table") and schema_profile.get("tables"):
        for t in schema_profile["tables"]:
            for c in t.get("columns") or []:
                if isinstance(c, dict):
                    names.append(str(c.get("name") or ""))
    return [n for n in names if n]
