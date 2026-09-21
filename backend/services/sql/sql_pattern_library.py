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
    Synonyms (sales→revenue, vendors→supplier) expand evidence without inventing columns.
    Returns None rather than guessing when two candidates tie.
    """
    q = (question or "").lower()
    # Expand common business synonyms so paraphrases resolve to real columns.
    _SYNONYMS = {
        "sales": ("revenue", "net_sales", "sales_amount", "gmv"),
        "vendors": ("supplier", "vendor"),
        "vendor": ("supplier", "vendor"),
        "sellers": ("supplier", "vendor"),
        "seller": ("supplier", "vendor"),
        "buyers": ("customer", "buyer"),
        "buyer": ("customer", "buyer"),
        "teams": ("department",),
        "team": ("department",),
        "stores": ("store",),
        "brands": ("brand",),
        "plans": ("plan",),
        "recurring revenue": ("mrr",),
        "mrr": ("mrr",),
    }
    expanded_q = q
    for syn, targets in _SYNONYMS.items():
        if re.search(rf"\b{re.escape(syn)}\b", q):
            expanded_q += " " + " ".join(targets)
    tokens = _question_tokens(expanded_q)
    scored: List[Tuple[int, str]] = []
    for name in candidates:
        if not name:
            continue
        lower = name.lower()
        spaced = lower.replace("_", " ")
        score = 0
        if lower in q or spaced in q or lower in expanded_q:
            score = 100 + len(lower)
        else:
            parts = [p for p in lower.split("_") if p]
            matched = [p for p in parts if p in tokens or _singular(p) in tokens]
            leftover = {p for p in parts if p not in matched}
            if matched and not leftover:
                score = 80
            elif matched and leftover == {"name"}:
                score = 70
            elif matched and leftover == {"id"}:
                score = 45
            elif matched:
                score = 40 + 10 * len(matched)
            # Synonym hit: question says "sales", candidate is "revenue"
            for syn, targets in _SYNONYMS.items():
                if re.search(rf"\b{re.escape(syn)}\b", q) and any(
                    t in lower or t == lower for t in targets
                ):
                    score = max(score, 75)
        if score:
            scored.append((score, name))
    if not scored:
        return None
    scored.sort(key=lambda s: (-s[0], len(s[1])))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        # Tie-break: prefer primary customer_* dims over supplier_* / secondary.
        top = scored[0][0]
        tied = [name for score, name in scored if score == top]
        preferred = [n for n in tied if n.lower().startswith("customer_")]
        if len(preferred) == 1:
            return preferred[0]
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
    raw_q = (question or "").strip().lower()
    # Strip chart/plot phrasing so "bar chart of X by Y" still hits GROUP_BY / TOP_N.
    q = re.sub(
        r"\b(show|create|make|plot|draw)\s+(a\s+)?(bar|line|pie|area)?\s*charts?\s*(of\s+)?",
        "show ",
        raw_q,
    )
    q = re.sub(r"\bas\s+a\s+(bar|line|pie|area)\s+chart\b", "", q)
    q = re.sub(r"\b(line|bar|pie|area)\s+charts?\s*(of\s+)?", "", q)
    q = re.sub(r"\b(visualize|visualise|graph|plot)\b", "show", q)
    q = re.sub(r"\s+", " ", q).strip()
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

    # Row count / entity count ("how many orders are there?")
    # Do not swallow "how many distinct suppliers" — that needs COUNT(DISTINCT …).
    # Do not swallow "how many records in each region" — that needs COUNT_BY.
    if (
        not re.search(r"\b(distinct|unique)\b", q)
        and not re.search(r"\b(each|per|by|across|grouped)\b", q)
        and (
            re.search(r"\b(how many rows|row count|number of rows|count rows)\b", q)
            or re.search(r"\bhow many\b.+\bare there\b", q)
            or re.search(
                r"\bhow many (orders|transactions|employees|products|records|accounts|subscriptions)\b",
                q,
            )
            or q in ("count(*)", "count all")
        )
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

    # Sum / avg / min / max of a named column.
    # Skip when the question clearly asks for a breakdown, ranking, filter, or trend —
    # those shapes are handled by the more specific patterns below. Matching a bare
    # SUM here used to silently answer "total revenue by region" as a global total.
    _needs_structure = bool(
        re.search(
            r"\b(by|per|each|within|across|for the|for\s+[a-z]|which\s+\w+|highest|lowest|"
            r"top\s+\d+|bottom\s+\d+|trend|over time|monthly|yearly|month[- ]by[- ]month|"
            r"month|year|share|percent|%|"
            r"above|below|at least|fewer than|compare|versus|vs\b|growth|decline)\b",
            q,
        )
    )
    if not _needs_structure:
        for agg, words in (
            ("SUM", r"\b(sum|total)\s+(?:of\s+)?([a-z0-9_]+)"),
            ("AVG", r"\b(average|avg|mean)\s+(?:of\s+)?([a-z0-9_]+)"),
            ("MIN", r"\b(minimum|min)\s+(?:of\s+)?([a-z0-9_]+)"),
            ("MAX", r"\b(maximum|max)\s+(?:of\s+)?([a-z0-9_]+)"),
        ):
            mm = re.search(words, q)
            if not mm:
                continue
            raw = mm.group(2).lower()
            col = col_by_lower.get(raw)
            if not col:
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

    # Distinct count: "how many distinct suppliers"
    mm = re.search(r"\b(?:how many\s+)?(?:distinct|unique)\s+([a-z0-9_ ]+?)(?:\s+are there)?\??\s*$", q)
    if mm:
        phrase = mm.group(1).strip()
        col = col_by_lower.get(phrase.replace(" ", "_")) or resolve_column(phrase, names)
        if col:
            return PatternMatch(
                "DISTINCT_COUNT",
                0.93,
                sql=f"SELECT COUNT(DISTINCT {_ident(col)}) AS n FROM {tbl}",
                validation_rules=["exactly_one_row"],
            )

    # Count by dimension: "how many orders in each order status" /
    # "how many records belong to each region"
    count_by = (
        re.search(
            r"\bhow many\b.+\b(?:in\s+|belong(?:ing)?\s+to\s+)?each\s+([a-z0-9_ ]+)\??\s*$",
            q,
        )
        or re.search(r"\bcount\b.+\bby\s+([a-z0-9_ ]+)\??\s*$", q)
        or re.search(r"\brecords?\s+(?:per|by|for each)\s+([a-z0-9_ ]+)\??\s*$", q)
    )
    if count_by and cats:
        dim = resolve_column(count_by.group(1).strip(), [c for c in cats if c])
        if dim:
            return PatternMatch(
                "COUNT_BY",
                0.88,
                sql=(
                    f"SELECT {_ident(dim)} AS dim, COUNT(*) AS n "
                    f"FROM {tbl} GROUP BY 1 ORDER BY n DESC"
                ),
                validation_rules=["non_empty"],
                reason=f"count by {dim}",
            )

    # Boolean / categorical filter count: "how many transactions were returned"
    filter_count = re.search(
        r"\bhow many\b.+\b(were|are|is)\s+([a-z0-9_ ]+)\??\s*$",
        q,
    )
    if filter_count:
        token = filter_count.group(2).strip().lower().replace(" ", "_")
        for c in columns:
            name = c.get("name")
            if not name:
                continue
            lower = name.lower()
            if token == lower or token in lower or _singular(token) in lower.split("_"):
                return PatternMatch(
                    "FILTERED_COUNT",
                    0.82,
                    sql=(
                        f"SELECT COUNT(*) AS n FROM {tbl} "
                        f"WHERE LOWER(CAST({_ident(name)} AS VARCHAR)) IN "
                        f"('yes', 'true', '1', '{token.replace(chr(39), '')}')"
                    ),
                    validation_rules=["exactly_one_row"],
                    reason=f"count where {name}",
                )

    # Top-N by numeric measure. "most/biggest" paraphrases count, but "which X has the
    # highest Y" is a single-group ranking handled below — do not steal it here.
    _is_which_highest = bool(
        re.search(r"\bwhich\s+.+\s+has\s+the\s+(highest|lowest|most|least)\b", q)
    )
    if (
        not _is_which_highest
        and (re.search(r"\btop\s+\d+\b", q) or re.search(r"\b(most|biggest|largest)\b", q))
        and numeric
    ):
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

    # Dual metric by dimension: "total X and total Y by Z" (before single GROUP_BY)
    dual_matched = False
    dual = re.search(
        r"\btotal\s+([a-z0-9_ ]+?)\s+and\s+(?:total\s+)?([a-z0-9_ ]+?)\s+by\s+"
        r"([a-z0-9_ ]+?)\s*\??\.?\s*$",
        q,
    )
    if dual and numeric and cats:
        m1_phrase, m2_phrase, dim_phrase = dual.groups()
        m1 = resolve_column(m1_phrase, numeric)
        m2 = resolve_column(m2_phrase, numeric)
        dim = resolve_column(dim_phrase, [c for c in cats if c])
        if m1 and m2 and dim and m1 != m2:
            return PatternMatch(
                "MULTI_METRIC_GROUP",
                0.87,
                sql=(
                    f"SELECT {_ident(dim)} AS {_ident(dim)}, "
                    f"SUM({_ident(m1)}) AS total_{m1}, "
                    f"SUM({_ident(m2)}) AS total_{m2} "
                    f"FROM {tbl} WHERE {_ident(dim)} IS NOT NULL "
                    f"GROUP BY {_ident(dim)} "
                    f"ORDER BY total_{m1} DESC LIMIT 25"
                ),
                validation_rules=["non_empty"],
                reason=f"{m1} and {m2} by {dim}",
            )
        dual_matched = True  # dual phrasing present — do not collapse to single GROUP_BY

    # Aggregate by dimension: "total revenue by customer region"
    by_match = re.search(
        r"\b(total|sum|average|avg|mean)\s+([a-z0-9_ ]+?)\s+by\s+([a-z0-9_ ]+?)\s*$",
        q,
    ) or re.search(
        r"\b([a-z0-9_ ]+)\s+by\s+([a-z0-9_ ]+)\b",
        q,
    )
    if by_match and numeric and cats and not dual_matched:
        groups = by_match.groups()
        if len(groups) == 3:
            agg_word, measure_phrase, dim_phrase = groups
            agg = "AVG" if any(w in agg_word for w in ("average", "avg", "mean")) else "SUM"
            measure = resolve_column(measure_phrase, numeric) or resolve_column(q, numeric)
            dim = resolve_column(dim_phrase, [c for c in cats if c])
        else:
            measure = resolve_column(groups[0], numeric) or resolve_column(q, numeric)
            dim = resolve_column(groups[1], [c for c in cats if c])
            agg = "AVG" if re.search(r"\b(average|avg|mean)\b", q) else "SUM"
        if measure and dim and not re.search(r"\btop\s+\d+\b", q):
            alias = "avg_value" if agg == "AVG" else "total"
            return PatternMatch(
                "GROUP_BY",
                0.84,
                sql=(
                    f"SELECT {_ident(dim)} AS dim, {agg}({_ident(measure)}) AS {alias} "
                    f"FROM {tbl} GROUP BY 1 ORDER BY {alias} DESC"
                ),
                validation_rules=["non_empty", f"ordered_desc:{alias}"],
                reason=f"{agg.lower()} {measure} by {dim}",
            )

    # Highest / lowest group: "which customer region has the highest total revenue"
    which_match = re.search(
        r"\bwhich\s+([a-z0-9_ ]+?)\s+has\s+the\s+(highest|lowest|most|least)\s+(?:total\s+|average\s+)?([a-z0-9_ ]+)\??\s*$",
        q,
    )
    if which_match and numeric and cats:
        dim_phrase, direction, measure_phrase = which_match.groups()
        dim = resolve_column(dim_phrase, [c for c in cats if c])
        measure = resolve_column(measure_phrase, numeric) or resolve_column(q, numeric)
        if measure and dim:
            order = "ASC" if direction in ("lowest", "least") else "DESC"
            return PatternMatch(
                "TOP_1_GROUP",
                0.86,
                sql=(
                    f"SELECT {_ident(dim)} AS dim, SUM({_ident(measure)}) AS total "
                    f"FROM {tbl} GROUP BY 1 ORDER BY total {order} LIMIT 1"
                ),
                validation_rules=["exactly_one_row"],
                reason=f"{direction} {measure} by {dim}",
            )

    # Filtered scalar: "total revenue for the North customer region"
    for_match = re.search(
        r"\b(total|sum|average|avg)\s+([a-z0-9_]+)\s+for\s+(?:the\s+)?([a-z0-9_ -]+?)(?:\s+[a-z0-9_]+)*\??\s*$",
        q,
    )
    if for_match and numeric and cats:
        agg_word, measure_token, filter_token = for_match.groups()
        measure = resolve_column(measure_token, numeric) or col_by_lower.get(measure_token)
        # Find a categorical column whose sample values or name fit the filter token.
        dim = None
        filter_value = None
        token = filter_token.strip().lower().replace("-", " ")
        for c in columns:
            name = c.get("name")
            if not name or name in numeric:
                continue
            samples = [str(s).lower() for s in (c.get("sample_values") or c.get("examples") or [])]
            if token in samples or any(token == s for s in samples):
                dim, filter_value = name, next(
                    (str(s) for s in (c.get("sample_values") or c.get("examples") or []) if str(s).lower() == token),
                    filter_token.strip(),
                )
                break
            # Fall back: "north customer region" -> customer_region with value North
            if name.lower() in q and token.split()[0] in q:
                dim = name
                filter_value = token.split()[0].title()
                break
        if measure and dim and filter_value:
            agg = "AVG" if any(w in agg_word for w in ("average", "avg")) else "SUM"
            alias = "avg_value" if agg == "AVG" else f"total_{measure}"
            return PatternMatch(
                "FILTERED_AGG",
                0.82,
                sql=(
                    f"SELECT {agg}({_ident(measure)}) AS {alias} FROM {tbl} "
                    f"WHERE LOWER(CAST({_ident(dim)} AS VARCHAR)) = LOWER('{filter_value.replace(chr(39), chr(39)+chr(39))}')"
                ),
                validation_rules=["exactly_one_row"],
                reason=f"{agg.lower()} {measure} where {dim}={filter_value}",
            )

    # Above / below average groups
    dim_phrase = side = measure_phrase = None
    ab_match = re.search(
        r"\bwhich\s+([a-z0-9_ ]+?)\s+have\s+(above|below)[- ]average\s+([a-z0-9_ ]+?)\??\s*$",
        q,
    )
    if ab_match:
        dim_phrase, side, measure_phrase = ab_match.groups()
    else:
        ab_match2 = re.search(
            r"\bwhich\s+([a-z0-9_ ]+?)\s+have\s+total\s+([a-z0-9_ ]+?)\s+"
            r"(above|below)\s+the\s+overall\s+average\b",
            q,
        )
        if ab_match2:
            dim_phrase, measure_phrase, side = ab_match2.groups()
    if dim_phrase and side and measure_phrase and numeric and cats:
        dim = resolve_column(dim_phrase, [c for c in cats if c])
        measure = resolve_column(measure_phrase, numeric) or resolve_column(q, numeric)
        if measure and dim:
            op = ">" if side == "above" else "<"
            order = "DESC" if side == "above" else "ASC"
            return PatternMatch(
                "ABOVE_BELOW_AVERAGE",
                0.85,
                sql=(
                    f"WITH g AS (\n"
                    f"  SELECT {_ident(dim)} AS dim, SUM({_ident(measure)}) AS total\n"
                    f"  FROM {tbl} GROUP BY 1\n"
                    f")\n"
                    f"SELECT dim, total FROM g\n"
                    f"WHERE total {op} (SELECT AVG(total) FROM g)\n"
                    f"ORDER BY total {order}"
                ),
                validation_rules=["non_empty"],
                reason=f"{side} average {measure} by {dim}",
            )

    # Among dim with at least N records, top M by measure
    min_top = re.search(
        r"among\s+([a-z0-9_ ]+?)\s+values?\s+with\s+at\s+least\s+(\d+)\s+records?,\s*"
        r"(?:what are\s+)?the\s+top\s+(\d+)\s+by\s+(?:total\s+)?([a-z0-9_ ]+?)\??\s*$",
        q,
    )
    if min_top and numeric and cats:
        dim_phrase, min_n, top_n, measure_phrase = min_top.groups()
        dim = resolve_column(dim_phrase, [c for c in cats if c])
        measure = resolve_column(measure_phrase, numeric) or resolve_column(q, numeric)
        if dim and measure:
            mn = max(1, min(50, int(min_n)))
            tn = max(1, min(50, int(top_n)))
            return PatternMatch(
                "TOP_N_MIN_SAMPLE",
                0.86,
                sql=(
                    f"SELECT {_ident(dim)} AS dim_val, "
                    f"SUM({_ident(measure)}) AS total_m, COUNT(*) AS n "
                    f"FROM {tbl} WHERE {_ident(dim)} IS NOT NULL "
                    f"GROUP BY 1 HAVING COUNT(*) >= {mn} "
                    f"ORDER BY total_m DESC, dim_val LIMIT {tn}"
                ),
                validation_rules=["non_empty", f"max_rows:{tn}"],
                reason=f"top {tn} {dim} by {measure} with n>={mn}",
            )

    # Monthly / yearly trend
    if re.search(r"\b(monthly|month[- ]by[- ]month|by month|over time)\b", q) and numeric:
        measure = resolve_column(q, numeric)
        time_cols = [
            c.get("name")
            for c in columns
            if c.get("name")
            and (
                str(c.get("analytical_role") or "").lower() == "temporal"
                or "date" in str(c.get("dtype") or "").lower()
                or "date" in (c.get("name") or "").lower()
                or (c.get("name") or "").lower() in ("month", "period")
            )
        ]
        time_col = time_cols[0] if time_cols else None
        if measure and time_col:
            return PatternMatch(
                "MONTHLY_TREND",
                0.84,
                sql=(
                    f"SELECT strftime(TRY_CAST({_ident(time_col)} AS DATE), '%Y-%m') AS period, "
                    f"SUM({_ident(measure)}) AS total "
                    f"FROM {tbl} "
                    f"WHERE TRY_CAST({_ident(time_col)} AS DATE) IS NOT NULL "
                    f"GROUP BY 1 ORDER BY 1"
                ),
                validation_rules=["non_empty"],
                reason=f"monthly {measure} trend",
            )

    if re.search(r"\b(by year|yearly|each year)\b", q) and numeric:
        measure = resolve_column(q, numeric)
        time_cols = [
            c.get("name")
            for c in columns
            if c.get("name")
            and (
                str(c.get("analytical_role") or "").lower() == "temporal"
                or "date" in str(c.get("dtype") or "").lower()
                or "date" in (c.get("name") or "").lower()
                or (c.get("name") or "").lower() in ("month", "period", "hire_date", "launch_date")
            )
        ]
        time_col = time_cols[0] if time_cols else None
        if measure and time_col:
            return PatternMatch(
                "YEARLY_TREND",
                0.84,
                sql=(
                    f"SELECT CAST(strftime(TRY_CAST({_ident(time_col)} AS DATE), '%Y') AS INTEGER) AS year, "
                    f"SUM({_ident(measure)}) AS total "
                    f"FROM {tbl} "
                    f"WHERE TRY_CAST({_ident(time_col)} AS DATE) IS NOT NULL "
                    f"GROUP BY 1 ORDER BY 1"
                ),
                validation_rules=["non_empty"],
                reason=f"yearly {measure}",
            )

    # Contribution / share of total by dimension
    if re.search(r"\b(share of total|percentage of total|% of total|contribution)\b", q) and numeric and cats:
        measure = resolve_column(q, numeric)
        dim = resolve_column(q, [c for c in cats if c])
        if measure and dim and not re.search(r"\btop\s+\d+\b", q):
            return PatternMatch(
                "CONTRIBUTION",
                0.86,
                sql=(
                    f"SELECT {_ident(dim)} AS dim, "
                    f"ROUND(100.0 * SUM({_ident(measure)}) / NULLIF((SELECT SUM({_ident(measure)}) FROM {tbl}), 0), 2) AS pct "
                    f"FROM {tbl} GROUP BY 1 ORDER BY pct DESC"
                ),
                validation_rules=["percent_bounds_0_100", "non_empty"],
                reason=f"share of total {measure} by {dim}",
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
