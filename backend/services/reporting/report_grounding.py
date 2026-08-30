"""
Deterministic report grounding checks and lightweight repairs (STEP 5).

The executed result is the source of truth. These helpers catch common
ungrounded claims without a second LLM pipeline.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence, Tuple


_MISSING_CLAIM_PATTERNS = [
    r"\b(no|not|cannot|can't|unable).{0,40}(categor|city|segment|region).{0,20}(data|level|breakdown|available)",
    r"\b(categor|city|segment).{0,40}(unavailable|absent|missing|not available|not present)",
    r"\b(data|results?|metrics?|columns?).{0,30}(unavailable|not available|missing)",
    r"\b(unavailable|missing|not available).{0,40}(sales|profit|margin|discount|categor|city|segment|metrics?)",
    r"\bcannot\s+(identify|determine|compare)",
    r"\bsales\s+comparison.{0,30}(impossible|not\s+possible|cannot)",
    r"\bfurther\s+data\s+collection",
    r"\bcould\s+not\s+be\s+performed",
    r"\banalysis\s+could\s+not",
]

_CAUSATION_PATTERNS = [
    r"\bcaused?\b",
    r"\bcaus(?:es|ing)\b",
    r"\bdrives?\b",
    r"\bdriven\s+by\b",
    r"\bleads?\s+to\b",
    r"\bresults?\s+in\b",
]

_EXAGGERATION_PATTERNS = [
    r"\bdramatic(?:ally)?\b",
    r"\bsevere\b",
    r"\bmajor\s+(profitability\s+)?problem\b",
    r"\bcollaps(?:e|ing)\b",
    r"\bcrisis\b",
    r"\bhuge\s+(gap|difference|drop)\b",
    r"\bvast(?:ly)?\b",
]


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _result_has_evidence(columns: Sequence[str], tokens: Sequence[str]) -> bool:
    cols = " ".join(str(c).lower() for c in (columns or []))
    return any(t.lower() in cols for t in tokens)


def extract_numeric_column(
    columns: Sequence[str],
    rows: Sequence[Any],
    *name_hints: str,
) -> List[float]:
    """Return numeric values for the first matching column hint."""
    cols = [str(c) for c in (columns or [])]
    col_idx = None
    col_name = None
    lower_cols = [c.lower() for c in cols]
    for hint in name_hints:
        for i, c in enumerate(lower_cols):
            if hint.lower() in c:
                col_idx = i
                col_name = cols[i]
                break
        if col_idx is not None:
            break
    if col_idx is None:
        return []

    values: List[float] = []
    for row in rows or []:
        raw = None
        if isinstance(row, dict):
            raw = row.get(col_name)
            if raw is None:
                for k, v in row.items():
                    if str(k).lower() == col_name.lower():
                        raw = v
                        break
        elif isinstance(row, (list, tuple)) and col_idx < len(row):
            raw = row[col_idx]
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    return values


def margin_spread_points(columns: Sequence[str], rows: Sequence[Any]) -> Optional[float]:
    """Absolute spread across profit_margin values, in percentage points."""
    vals = extract_numeric_column(columns, rows, "profit_margin", "margin")
    if len(vals) < 2:
        return None
    mn, mx = min(vals), max(vals)
    if mx <= 1.5:
        return abs(mx - mn) * 100.0
    return abs(mx - mn)


def check_report_grounding(
    *,
    report_text: str,
    result_columns: Sequence[str],
    result_rows: Sequence[Any],
    coverage_ok: bool,
    question: str = "",
) -> Tuple[bool, List[str]]:
    """Return (ok, issues). Issues are human-readable grounding violations."""
    blob = _norm_text(report_text)
    issues: List[str] = []
    cols = list(result_columns or [])

    has_category = _result_has_evidence(cols, ("category", "product_category"))
    has_city = _result_has_evidence(cols, ("city",))
    has_segment = _result_has_evidence(cols, ("segment", "customer_segment"))
    has_sales = _result_has_evidence(cols, ("sales", "revenue", "sales_amount"))
    has_margin = _result_has_evidence(cols, ("margin", "profit_margin"))
    has_discount = _result_has_evidence(cols, ("discount",))

    for pat in _MISSING_CLAIM_PATTERNS:
        if re.search(pat, blob):
            if has_category or has_city or has_segment or has_sales or has_margin:
                issues.append(
                    "report claims data unavailable despite result columns containing evidence"
                )
                break

    if coverage_ok and re.search(
        r"\b(could not|cannot|unable to)\s+(perform|complete|run)\s+(the\s+)?analysis\b",
        blob,
    ):
        issues.append(
            "report claims analysis could not be performed despite semantic coverage pass"
        )

    q = _norm_text(question)
    if re.search(r"\b(relationship|associated|correlat|across)\b", q) or has_discount:
        if any(re.search(p, blob) for p in _CAUSATION_PATTERNS):
            if not re.search(r"\bcausal\s+evidence\b|\bcausality\s+tested\b", blob):
                issues.append(
                    "report implies causation; prefer association language for relationship findings"
                )

    spread = margin_spread_points(cols, result_rows)
    if spread is not None and spread < 0.5:
        if any(re.search(p, blob) for p in _EXAGGERATION_PATTERNS):
            issues.append(
                f"report exaggerates profitability gap; margin spread is only ~{spread:.4f} pp"
            )

    seen = set()
    uniq: List[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return (len(uniq) == 0, uniq)


def build_evidence_summary(
    question: str,
    columns: Sequence[str],
    rows: Sequence[Any],
    *,
    max_rows: int = 8,
) -> str:
    """Deterministic evidence-first narrative from returned rows."""
    cols = [str(c) for c in (columns or [])]
    preview = list(rows or [])[:max_rows]
    if not cols:
        return (
            "The query executed but returned no columns. "
            "Review the results table and execution details."
        )

    lines = [
        "Executed results are the source of truth for this answer.",
        f"Returned columns: {', '.join(cols)}.",
        f"Returned {len(rows or [])} row(s).",
    ]

    samples: List[str] = []
    for row in preview[:5]:
        if isinstance(row, dict):
            samples.append(", ".join(f"{c}={row.get(c)}" for c in cols[:6]))
        elif isinstance(row, (list, tuple)):
            samples.append(
                ", ".join(
                    f"{cols[i]}={row[i]}" for i in range(min(len(cols), len(row), 6))
                )
            )
    if samples:
        lines.append("Evidence preview: " + " | ".join(samples) + ".")

    spread = margin_spread_points(cols, rows)
    if spread is not None:
        lines.append(
            f"Observed profit_margin spread across groups is approximately {spread:.4f} "
            "percentage points."
        )
        if spread < 0.5:
            lines.append(
                "Although ranks may differ, the practical margin difference appears negligible; "
                "statistical significance testing is not required for this business interpretation."
            )

    q = _norm_text(question)
    if "discount" in q and "categor" in q:
        lines.append(
            "Interpret discount vs profitability as an association across categories, "
            "not as proven causation."
        )
    if "insight" in q or "priorit" in q:
        lines.append(
            "Business interpretation should follow the comparison evidence above; "
            "avoid recommendations that are not supported by returned metrics."
        )

    return " ".join(lines)


def soften_causation_language(text: str) -> str:
    """Replace common causal phrasing with association language."""
    if not text:
        return text
    replacements = [
        (r"\bcaused\s+by\b", "associated with"),
        (r"\bcaused\b", "were associated with"),
        (r"\bcauses\b", "is associated with"),
        (r"\bcausing\b", "associating with"),
        (r"\bcause\b", "association with"),
        (r"\bdrives\b", "is associated with"),
        (r"\bdriven\s+by\b", "associated with"),
        (r"\bleads\s+to\b", "is associated with"),
        (r"\bresulting\s+in\b", "associated with"),
        (r"\bresults\s+in\b", "is associated with"),
    ]
    out = text
    for pat, repl in replacements:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def repair_report_text_for_grounding(
    *,
    summary: str,
    headline: str,
    question: str,
    columns: Sequence[str],
    rows: Sequence[Any],
    issues: Sequence[str],
) -> Tuple[str, str]:
    """Lightweight deterministic repair when grounding fails."""
    evidence = build_evidence_summary(question, columns, rows)
    new_summary = evidence
    if any("exaggerat" in i.lower() for i in issues):
        spread = margin_spread_points(columns, rows)
        if spread is not None:
            new_summary += (
                f" Ranking differences exist, but the margin spread (~{spread:.4f} pp) "
                "does not indicate a large practical profitability problem."
            )
    new_headline = headline or "Analysis grounded in executed results."
    if any("unavailable" in i.lower() or "could not be performed" in i.lower() for i in issues):
        new_headline = "Results contain the requested evidence; see grounded summary."
    return soften_causation_language(new_headline), soften_causation_language(new_summary)
