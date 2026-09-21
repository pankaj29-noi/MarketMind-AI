"""Generic SQL analytical pattern library (schema-adaptive, not dataset-overfit).

Provides:
  - pattern detection from NL questions
  - deterministic SQL templates when schema evidence is sufficient
  - validation hints for result checkers

Never invents column names — callers must pass resolved physical columns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class PatternMatch:
    pattern_id: str
    confidence: float
    sql: Optional[str] = None
    validation_rules: Optional[List[str]] = None
    reason: str = ""


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _limit(q: str, default: int = 10) -> int:
    m = re.search(r"\btop\s+(\d+)\b", q, re.I)
    if m:
        return max(1, min(100, int(m.group(1))))
    m = re.search(r"\bbottom\s+(\d+)\b", q, re.I)
    if m:
        return max(1, min(100, int(m.group(1))))
    return default


def _singular(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ses") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _question_tokens(question: str) -> set[str]:
    tokens = set()
    for raw in re.findall(r"[a-z0-9_]+", (question or "").lower()):
        tokens.add(raw)
        tokens.add(_singular(raw))
        for part in raw.split("_"):
            if part:
                tokens.add(part)
                tokens.add(_singular(part))
    return tokens


def resolve_column(question: str, candidates: Sequence[str]) -> Optional[str]:
    """Pick the column a question refers to, or None when the evidence is weak.

    Matching is name-evidence only: full name, name with separators as spaces, or
    the distinctive tokens of the name (product_name -> "product"/"products").
    Returns None rather than guessing when two candidates tie.
    """
    q = (question or "").lower()
    tokens = _question_tokens(q)
    scored: List[Tuple[int, str]] = []
    for name in candidates:
        if not name:
            continue
        lower = name.lower()
        spaced = lower.replace("_", " ")
        score = 0
        if lower in q or spaced in q:
            score = 100 + len(lower)
        else:
            parts = [p for p in lower.split("_") if p]
            matched = [p for p in parts if p in tokens or _singular(p) in tokens]
            leftover = {p for p in parts if p not in matched}
            if matched and not leftover:
                score = 80
            elif matched and leftover == {"name"}:
                # "top 10 products" means the product label column, not a product attribute.
                score = 70
            elif matched and leftover == {"id"}:
                score = 45
            elif matched:
                # Partial name match ("product" for product_category) is weaker but usable.
                score = 40 + 10 * len(matched)
        if score:
            scored.append((score, name))
    if not scored:
        return None
    scored.sort(key=lambda s: (-s[0], len(s[1])))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None  # ambiguous — let the caller decide rather than guess
    return scored[0][1]


def detect_patterns(question: str) -> List[str]:
    q = (question or "").lower()
    hits: List[str] = []
    rules = [
        ("COUNT", r"\b(how many|count|number of rows|row count)\b"),
        ("SUM", r"\b(sum|total)\b"),
        ("AVG", r"\b(average|avg|mean)\b"),
        ("MIN", r"\b(minimum|min|lowest)\b"),
        ("MAX", r"\b(maximum|max|highest)\b"),
        ("DISTINCT_COUNT", r"\b(distinct|unique)\b"),
        ("TOP_N", r"\btop\s+\d+\b"),
        ("BOTTOM_N", r"\bbottom\s+\d+\b"),
        ("PERCENT_OF_TOTAL", r"\b(share of|percent(age)? of total|% of total|contribution)\b"),
        ("RANK", r"\b(rank|ranking)\b"),
        ("YEAR_OVER_YEAR", r"\b(year[- ]over[- ]year|yoy|previous year)\b"),
        ("ABOVE_AVERAGE", r"\babove\s+(the\s+)?(overall\s+)?average\b"),
        ("BELOW_AVERAGE", r"\bbelow\s+(the\s+)?(overall\s+)?average\b"),
        ("MINIMUM_SAMPLE", r"\b(at least|fewer than|minimum)\s+\d+\b"),
        ("GROUP_BY", r"\b(by |per |each |group)\b"),
        ("HAVING", r"\b(having|with more than|with at least)\b"),
    ]
    for pid, pat in rules:
        if re.search(pat, q):
            hits.append(pid)
    return hits


def try_simple_deterministic_sql(
    question: str,
    table: str,
    columns: Sequence[Dict[str, Any]],
) -> Optional[PatternMatch]:
    """
    Fast-path SQL for obvious SIMPLE questions when columns are known.

    Returns None when the question is too complex / ambiguous for templates.
    """
    q = (question or "").strip().lower()
    if not q or not table or not columns:
        return None

    col_by_lower = {(c.get("name") or "").lower(): c.get("name") for c in columns if c.get("name")}
    names = [c.get("name") for c in columns if c.get("name")]
    numeric = [
        c.get("name")
        for c in columns
        if c.get("name")
        and str(c.get("dtype") or c.get("analytical_role") or "").lower()
        in ("number", "measure", "derived_measure", "int", "double", "float", "decimal")
    ]
    # also treat analytical_role measure
    for c in columns:
        if c.get("analytical_role") in ("measure", "derived_measure") and c.get("name"):
            if c["name"] not in numeric:
                numeric.append(c["name"])

    tbl = _ident(table)

    # Row count
    if re.search(r"\b(how many rows|row count|number of rows|count rows)\b", q) or q in (
        "count(*)",
        "count all",
    ):
        return PatternMatch(
            "COUNT",
            0.99,
            sql=f"SELECT COUNT(*) AS row_count FROM {tbl}",
            validation_rules=["exactly_one_row", "column:row_count"],
        )

    # Distinct values list for a named column
    m = re.search(r"\blist distinct\s+([a-z0-9_]+)", q)
    if m and m.group(1) in col_by_lower:
        col = col_by_lower[m.group(1)]
        return PatternMatch(
            "DISTINCT",
            0.95,
            sql=f"SELECT DISTINCT {_ident(col)} AS value FROM {tbl} ORDER BY 1",
            validation_rules=["non_empty"],
        )

    cats = [
        c.get("name")
        for c in columns
        if c.get("name")
        and c.get("analytical_role") in ("categorical", "temporal", None)
        and c.get("name") not in numeric
    ]

    # Percent of total contributed by a top-N subset.
    # Denominator must be the overall total, not the top-N subtotal.
    if (
        re.search(r"\b(percent(age)?|share|%|contribution)\b", q)
        and re.search(r"\btop\s+\d+\b", q)
        and numeric
    ):
        measure = resolve_column(q, numeric) or (numeric[0] if len(numeric) == 1 else None)
        dim = resolve_column(q, [c for c in cats if c])
        if measure and dim:
            lim = _limit(q)
            m_id, d_id = _ident(measure), _ident(dim)
            return PatternMatch(
                "PERCENT_OF_TOTAL_TOP_N",
                0.88,
                sql=(
                    f"WITH grouped AS (\n"
                    f"  SELECT {d_id} AS dim, SUM({m_id}) AS group_total\n"
                    f"  FROM {tbl}\n"
                    f"  WHERE {m_id} IS NOT NULL\n"
                    f"  GROUP BY 1\n"
                    f"), ranked AS (\n"
                    f"  SELECT dim, group_total,\n"
                    f"         ROW_NUMBER() OVER (ORDER BY group_total DESC) AS rn\n"
                    f"  FROM grouped\n"
                    f")\n"
                    f"SELECT\n"
                    f"  SUM(CASE WHEN rn <= {lim} THEN group_total ELSE 0 END) AS top_{lim}_total,\n"
                    f"  SUM(group_total) AS overall_total,\n"
                    f"  ROUND(100.0 * SUM(CASE WHEN rn <= {lim} THEN group_total ELSE 0 END)\n"
                    f"        / NULLIF(SUM(group_total), 0), 2) AS pct_of_total\n"
                    f"FROM ranked"
                ),
                validation_rules=[
                    "exactly_one_row",
                    "percent_bounds_0_100",
                    "column:pct_of_total",
                    "denominator:overall_total",
                ],
                reason=f"percent of total {measure} from top {lim} {dim}",
            )

    # Sum / avg / min / max of a named column
    for agg, words in (
        ("SUM", r"\b(sum|total)\s+(?:of\s+)?([a-z0-9_]+)"),
        ("AVG", r"\b(average|avg|mean)\s+(?:of\s+)?([a-z0-9_]+)"),
        ("MIN", r"\b(minimum|min)\s+(?:of\s+)?([a-z0-9_]+)"),
        ("MAX", r"\b(maximum|max)\s+(?:of\s+)?([a-z0-9_]+)"),
        ("COUNT_DISTINCT", r"\b(how many distinct|count distinct|unique)\s+([a-z0-9_]+)"),
    ):
        mm = re.search(words, q)
        if not mm:
            continue
        raw = mm.group(2).lower()
        col = col_by_lower.get(raw)
        if not col:
            # fuzzy: column mentioned somewhere
            for cname in names:
                if cname.lower() in q and (
                    agg.startswith("COUNT")
                    or cname in numeric
                    or any(
                        str(c.get("dtype")) == "number"
                        for c in columns
                        if c.get("name") == cname
                    )
                ):
                    # prefer exact token match later
                    pass
            # try token equality only
            continue
        if agg == "SUM":
            return PatternMatch(
                "SUM",
                0.93,
                sql=f"SELECT SUM({_ident(col)}) AS total_{col} FROM {tbl}",
                validation_rules=["exactly_one_row"],
            )
        if agg == "AVG":
            return PatternMatch(
                "AVG",
                0.93,
                sql=f"SELECT AVG({_ident(col)}) AS avg_{col} FROM {tbl}",
                validation_rules=["exactly_one_row"],
            )
        if agg == "MIN":
            return PatternMatch(
                "MIN",
                0.93,
                sql=f"SELECT MIN({_ident(col)}) AS min_{col} FROM {tbl}",
                validation_rules=["exactly_one_row"],
            )
        if agg == "MAX":
            return PatternMatch(
                "MAX",
                0.93,
                sql=f"SELECT MAX({_ident(col)}) AS max_{col} FROM {tbl}",
                validation_rules=["exactly_one_row"],
            )
        if agg == "COUNT_DISTINCT":
            return PatternMatch(
                "DISTINCT_COUNT",
                0.93,
                sql=f"SELECT COUNT(DISTINCT {_ident(col)}) AS n FROM {tbl}",
                validation_rules=["exactly_one_row"],
            )

    # Top-N by numeric measure grouped by a categorical column mentioned in question
    if re.search(r"\btop\s+\d+\b", q) and numeric:
        lim = _limit(q)
        measure = None
        for n in numeric:
            if n.lower() in q:
                measure = n
                break
        if measure is None and len(numeric) == 1:
            measure = numeric[0]
        if measure is None:
            measure = resolve_column(q, numeric)
        dim = None
        for cname in cats:
            if cname and cname.lower() in q:
                dim = cname
                break
        if dim is None:
            dim = resolve_column(q, [c for c in cats if c])
        if measure and dim:
            return PatternMatch(
                "TOP_N",
                0.85,
                sql=(
                    f"SELECT {_ident(dim)} AS dim, SUM({_ident(measure)}) AS total "
                    f"FROM {tbl} GROUP BY 1 ORDER BY total DESC LIMIT {lim}"
                ),
                validation_rules=[f"max_rows:{lim}", "ordered_desc:total"],
            )

    return None


def validation_hints_for_question(question: str) -> List[str]:
    """Result-level validation hints derived from question text."""
    q = (question or "").lower()
    hints: List[str] = []
    m = re.search(r"\btop\s+(\d+)\b", q)
    if m:
        hints.append(f"max_rows:{m.group(1)}")
    m = re.search(r"\bbottom\s+(\d+)\b", q)
    if m:
        hints.append(f"max_rows:{m.group(1)}")
    if re.search(r"\b(share|percent|%)\b", q):
        hints.append("percent_bounds_0_100")
    if re.search(r"\b(at least|fewer than|minimum)\s+(\d+)\b", q):
        hints.append("min_sample_filter_required")
    return hints
