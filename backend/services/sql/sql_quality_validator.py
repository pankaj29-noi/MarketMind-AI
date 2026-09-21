import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Aggregate functions recognised when checking GROUP BY correctness
_AGG_FUNC_RE = (
    r"\b(MAX|MIN|AVG|SUM|COUNT|MEDIAN|MODE|STDDEV|STDDEV_SAMP|STDDEV_POP|"
    r"VAR_SAMP|VAR_POP|VARIANCE|CORR|COVAR_SAMP|COVAR_POP|QUANTILE|"
    r"QUANTILE_CONT|QUANTILE_DISC|ANY_VALUE|ARG_MAX|ARG_MIN|"
    r"STRING_AGG|LIST|FIRST|LAST)\s*\("
)

# SQL / DuckDB tokens that must never be treated as column names
_SQL_KEYWORDS: Set[str] = {
    "select", "from", "where", "group", "by", "order", "having", "limit", "offset",
    "as", "on", "join", "left", "right", "inner", "outer", "full", "cross", "with",
    "and", "or", "not", "in", "is", "null", "true", "false", "case", "when", "then",
    "else", "end", "distinct", "all", "union", "except", "intersect", "asc", "desc",
    "nulls", "first", "last", "between", "like", "ilike", "exists", "cast", "over",
    "partition", "rows", "range", "unbounded", "preceding", "following", "current",
    "row", "qualify", "filter", "window", "recursive", "values", "using", "natural",
    "lateral", "tablesample", "pivot", "unpivot", "exclude", "replace", "include",
    "if", "elseif", "elsif", "into", "set", "returning", "fetch", "only", "ties",
    "percent", "top", "bottom", "of", "at", "zone", "interval", "date", "time",
    "timestamp", "year", "month", "day", "hour", "minute", "second", "week",
    "quarter", "epoch", "timezone", "both", "leading", "trailing", "trim",
    "extract", "truncate", "trunc", "date_trunc", "date_part", "strptime",
    "strftime", "age", "now", "current_date", "current_timestamp", "localtime",
    "localtimestamp", "coalesce", "nullif", "greatest", "least", "abs", "round",
    "floor", "ceil", "ceiling", "power", "sqrt", "exp", "ln", "log", "log10",
    "mod", "div", "sign", "pi", "random", "lower", "upper", "length", "len",
    "substr", "substring", "replace", "concat", "concat_ws", "string_agg",
    "list_agg", "array_agg", "count", "sum", "avg", "min", "max", "median",
    "mode", "stddev", "variance", "corr", "rank", "dense_rank", "row_number",
    "ntile", "lag", "lead", "first_value", "last_value", "nth_value",
    "percentile_cont", "percentile_disc", "quantile", "any_value", "arg_max",
    "arg_min", "bool_and", "bool_or", "bit_and", "bit_or", "generate_series",
    "unnest", "json_extract", "struct", "map", "list", "array", "map_keys",
    "map_values", "typeof", "try_cast", "try", "pragma", "explain", "analyze",
    "describe", "show", "tables", "columns", "databases", "schemas", "views",
    "functions", "indexes", "settings", "macro", "create", "drop", "alter",
    "insert", "update", "delete", "copy", "attach", "detach", "use", "force",
    "integer", "bigint", "smallint", "tinyint", "hugeint", "ubigint", "uint",
    "double", "float", "real", "decimal", "numeric", "varchar", "char", "text",
    "string", "blob", "boolean", "bool", "uuid", "json", "hugeint",
}

_IDENT_RE = re.compile(r"\b([A-Za-z_][\w$]*)\b")
_QUALIFIED_RE = re.compile(
    r'(?:"([^"]+)"|([A-Za-z_][\w$]*))\s*\.\s*(?:"([^"]+)"|([A-Za-z_][\w$]*))'
)
_ALIAS_RE = re.compile(
    r"\bAS\s+(?:\"([^\"]+)\"|([A-Za-z_][\w$]*))",
    re.IGNORECASE,
)
_CTE_RE = re.compile(
    # Matches WITH cte AS (…), and subsequent CTEs: ), next_cte AS (
    r"(?:\"([^\"]+)\"|([A-Za-z_][\w$]*))\s+AS\s*\(",
    re.IGNORECASE,
)
_FROM_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:\"([^\"]+)\"|([A-Za-z_][\w$]*))"
    r"(?:\s+(?:AS\s+)?(?:\"([^\"]+)\"|([A-Za-z_][\w$]*)))?",
    re.IGNORECASE,
)


def _strip_sql_literals(sql: str) -> str:
    """Replace single-quoted string literals (keep double-quoted identifiers)."""
    out: List[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            out.append(" ")
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _schema_column_names(schema: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    if schema.get("multi_table") and schema.get("tables"):
        for table in schema["tables"]:
            tname = (table.get("name") or "").lower()
            if tname:
                names.add(tname)
            for col in table.get("columns") or []:
                cname = (col.get("name") or "").lower()
                if cname:
                    names.add(cname)
                    if tname:
                        names.add(f"{tname}.{cname}")
    else:
        for col in schema.get("columns") or []:
            cname = (col.get("name") or "").lower()
            if cname:
                names.add(cname)
        for key in ("dataset_id", "table_name", "duckdb_table"):
            name = schema.get(key)
            if isinstance(name, str) and name:
                names.add(name.lower())
    return names


def _collect_query_aliases(query: str) -> Set[str]:
    aliases: Set[str] = set()
    for m in _ALIAS_RE.finditer(query):
        alias = (m.group(1) or m.group(2) or "").lower()
        if alias:
            aliases.add(alias)
    for m in _CTE_RE.finditer(query):
        name = (m.group(1) or m.group(2) or "").lower()
        if name:
            aliases.add(name)
    for m in _FROM_ALIAS_RE.finditer(query):
        table = (m.group(1) or m.group(2) or "").lower()
        alias = (m.group(3) or m.group(4) or "").lower()
        if table:
            aliases.add(table)
        # Do not treat SQL keywords (GROUP, WHERE, ORDER, …) as table aliases
        if alias and alias not in _SQL_KEYWORDS:
            aliases.add(alias)
    return aliases


def find_unknown_column_references(query: str, schema: Dict[str, Any]) -> List[str]:
    """
    Return unknown column/table identifiers (quoted and unquoted) vs schema.

    Allows SELECT/FROM aliases and CTEs. Designed to catch hallucinated columns
    like `SELECT revenue FROM t` when only `sales_amount` exists.
    """
    if not schema or not (("columns" in schema) or schema.get("multi_table")):
        return []

    valid = _schema_column_names(schema)
    aliases = _collect_query_aliases(query)
    relations: Set[str] = set(aliases)

    # Relations named in FROM/JOIN are not column refs (even if outside schema list —
    # DuckDB will reject unknown tables at execute time).
    for m in _FROM_ALIAS_RE.finditer(query):
        table = (m.group(1) or m.group(2) or "").lower()
        alias = (m.group(3) or m.group(4) or "").lower()
        if table:
            relations.add(table)
        if alias:
            relations.add(alias)

    known_tables = {
        n for n in valid
        if "." not in n and (
            schema.get("multi_table")
            or n in {
                (schema.get("dataset_id") or "").lower(),
                (schema.get("table_name") or "").lower(),
                (schema.get("duckdb_table") or "").lower(),
            }
        )
    }
    if schema.get("multi_table") and schema.get("tables"):
        known_tables = {(t.get("name") or "").lower() for t in schema["tables"] if t.get("name")}
    else:
        # Single-table CSV uploads: only the registered dataset table is valid.
        for key in ("dataset_id", "table_name", "duckdb_table"):
            name = (schema.get(key) or "").strip().lower()
            if name:
                known_tables.add(name)

    issues: List[str] = []
    seen: Set[str] = set()

    cte_names = {
        (m.group(1) or m.group(2) or "").lower()
        for m in _CTE_RE.finditer(query)
        if (m.group(1) or m.group(2))
    }

    if known_tables:
        for m in _FROM_ALIAS_RE.finditer(query):
            table = (m.group(1) or m.group(2) or "").lower()
            # Compare against known tables / CTEs only — FROM table names are also
            # present in `aliases`, so do not use aliases to skip this check.
            if table and table not in known_tables and table not in cte_names:
                key = f"table:{table}"
                if key not in seen:
                    seen.add(key)
                    issues.append(f'Invalid table reference: "{table}"')

    # Double-quoted identifiers
    for col in re.findall(r'"([^"]+)"', query):
        low = col.lower()
        if low in valid or low in aliases or low in relations or low in _SQL_KEYWORDS:
            continue
        if low not in seen:
            seen.add(low)
            issues.append(f'Invalid column reference: "{col}"')

    # Qualified refs: alias.col or table.col
    for m in _QUALIFIED_RE.finditer(query):
        left = (m.group(1) or m.group(2) or "").lower()
        right = (m.group(3) or m.group(4) or "").lower()
        if not right or right in _SQL_KEYWORDS:
            continue
        base_ok = right in valid or f"{left}.{right}" in valid
        if left in relations or left in valid:
            if not base_ok and right not in aliases and right not in relations:
                key = f"{left}.{right}"
                if key not in seen:
                    seen.add(key)
                    issues.append(f'Invalid column reference: "{left}.{right}"')
        elif right not in valid and right not in aliases and right not in relations:
            key = f"{left}.{right}"
            if key not in seen:
                seen.add(key)
                issues.append(f'Invalid column reference: "{left}.{right}"')

    # Unquoted identifiers (string literals stripped). Aliases already collected.
    scrubbed = _strip_sql_literals(query)
    # Remove AS <alias> so alias names aren't re-scanned as bare identifiers.
    scrubbed_no_alias = _ALIAS_RE.sub(" ", scrubbed)

    for m in _IDENT_RE.finditer(scrubbed_no_alias):
        tok = m.group(1)
        low = tok.lower()
        if low in _SQL_KEYWORDS or low in aliases or low in valid or low in relations:
            continue
        if low.isdigit():
            continue
        end = m.end()
        rest = scrubbed_no_alias[end : end + 8].lstrip()
        if rest.startswith("("):
            continue
        if scrubbed_no_alias[end : end + 1] == ".":
            continue
        if low not in seen:
            seen.add(low)
            issues.append(f'Invalid column reference: "{tok}"')

    return issues

def split_top_level(text: str, sep: str = ',') -> List[str]:
    parts = []
    current = []
    depth = 0
    in_quote = False
    quote_char = None
    for char in text:
        if in_quote:
            if char == quote_char:
                in_quote = False
            current.append(char)
        elif char in ("'", '"'):
            in_quote = True
            quote_char = char
            current.append(char)
        elif char == '(':
            depth += 1
            current.append(char)
        elif char == ')':
            if depth > 0:
                depth -= 1
            current.append(char)
        elif char == sep and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append(''.join(current))
    return parts

def validate_sql(query: str, schema: Dict[str, Any] = None, question: str = "") -> Dict[str, Any]:
    """
    Validates SQL query quality deterministically.
    Returns a dict with:
    {
        "is_valid": bool,
        "diagnostics": str,
        "critical_issues": List[str],
        "warnings": List[str]
    }
    """
    critical_issues = []
    warnings = []
    
    stripped = query.strip()
    if not stripped:
        return {
            "is_valid": False,
            "diagnostics": "CRITICAL ISSUES:\n- Empty SQL query.",
            "critical_issues": ["Empty SQL query."],
            "warnings": [],
        }

    # Strip a single trailing semicolon for statement checks
    core = stripped.rstrip(";").strip()
    query_upper = core.upper()

    # Reject multi-statement payloads (second statement after ;)
    if ";" in core:
        return {
            "is_valid": False,
            "diagnostics": "CRITICAL ISSUES:\n- Multi-statement SQL is not allowed.",
            "critical_issues": ["Multi-statement SQL is not allowed."],
            "warnings": [],
        }

    # Read-only gate: only SELECT / WITH…SELECT are valid analytical queries
    if not (query_upper.startswith("SELECT") or query_upper.startswith("WITH")):
        msg = "Only read-only SELECT (or WITH…SELECT) statements are allowed."
        return {
            "is_valid": False,
            "diagnostics": f"CRITICAL ISSUES:\n- {msg}",
            "critical_issues": [msg],
            "warnings": [],
        }

    # Block obvious write / DuckDB filesystem primitives even inside SELECT wrappers
    forbidden = (
        "INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "TRUNCATE ",
        "COPY ", "ATTACH ", "EXPORT ", "IMPORT ", "INSTALL ", "LOAD ", "PRAGMA ",
        "CALL ", "EXECUTE ",
    )
    padded = f" {query_upper} "
    for kw in forbidden:
        if f" {kw}" in padded or query_upper.startswith(kw.strip()):
            # Allow PRAGMA table_info only if needed? Prefer deny-all for generated SQL.
            if kw == "PRAGMA ":
                msg = "PRAGMA statements are not allowed in generated analytical SQL."
            else:
                msg = f"Forbidden SQL keyword detected: {kw.strip()}"
            critical_issues.append(msg)

    # Block DuckDB file/table functions that can escape the session dataset
    file_fn = re.search(
        r"\b("
        r"READ_CSV(?:_AUTO)?|READ_PARQUET|PARQUET_SCAN|SCAN_PARQUET|"
        r"READ_JSON(?:_AUTO)?|READ_NDJSON|READ_BLOB|GLOB|EXCEL_SCAN|"
        r"ICU_LOAD|HTTPFS|READ_TEXT"
        r")\s*\(",
        query_upper,
    )
    if file_fn:
        critical_issues.append(
            f"Forbidden filesystem/table function detected: {file_fn.group(1)}"
        )

    if critical_issues:
        diagnostics = "CRITICAL ISSUES:\n- " + "\n- ".join(critical_issues)
        return {
            "is_valid": False,
            "diagnostics": diagnostics,
            "critical_issues": critical_issues,
            "warnings": [],
        }

    # Keep upper form for remaining quality checks (use original query for regex on mixed case)
    # Re-bind query_upper to the full original upper for SELECT * / GROUP BY heuristics
    query_upper = query.upper()
    # Window aggregates (SUM(...) OVER (...)) are not GROUP BY aggregates.
    query_upper_no_windows = re.sub(
        r"\b(SUM|AVG|COUNT|MIN|MAX)\s*\([^)]*\)\s+OVER\s*\([^)]*\)",
        " WINDOW_AGG ",
        query_upper,
        flags=re.IGNORECASE,
    )

    # 1. Misuse of SELECT *
    if re.search(r"SELECT\s+\*\s+FROM", query_upper) or re.search(r"SELECT\s+.*,\s*\*\s+FROM", query_upper):
        critical_issues.append("Misuse of SELECT * when only a subset of fields is required.")

    # 2. Missing GROUP BY when required
    has_aggregate = bool(re.search(_AGG_FUNC_RE, query_upper_no_windows))
    if has_aggregate and "GROUP BY" not in query_upper:
        select_clause_match = re.search(r"SELECT\s+(.*?)\s+FROM", query, re.IGNORECASE | re.DOTALL)
        if select_clause_match:
            select_clause = select_clause_match.group(1)
            select_clause_plain = re.sub(
                r"\b(SUM|AVG|COUNT|MIN|MAX)\s*\([^)]*\)\s+OVER\s*\([^)]*\)",
                " WINDOW_AGG ",
                select_clause,
                flags=re.IGNORECASE,
            )
            top_level_exprs = split_top_level(select_clause_plain, ',')
            
            has_non_agg = False
            for expr in top_level_exprs:
                if not re.search(_AGG_FUNC_RE, expr, flags=re.IGNORECASE):
                    # Clean the expression to see if it's just a literal
                    cleaned = re.sub(r"\bAS\s+(?:\"[^\"]*\"|'[^']*'|[\w]+)", "", expr, flags=re.IGNORECASE)
                    cleaned = re.sub(r"'[^']*'", "", cleaned)
                    cleaned = re.sub(r"\b\d+(\.\d+)?\b", "", cleaned)
                    cleaned = re.sub(r"\b(NULL|DISTINCT|WINDOW_AGG)\b", "", cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r"[\s,;+\-*/=<>]+", "", cleaned)
                    if cleaned:
                        has_non_agg = True
                        break
                        
            if has_non_agg:
                critical_issues.append("Missing GROUP BY when required: non-aggregated columns are selected alongside aggregates.")

    # 3. Missing LIMIT for Top/Bottom N queries
    # Accept LIMIT, or window-rank top-N (QUALIFY / ROW_NUMBER / RANK / DENSE_RANK).
    question_lower = question.lower()
    if re.search(r"\b(top|bottom|first|last)\s+\d+\b", question_lower) or re.search(r"\b(highest|lowest)\b", question_lower):
        has_limit = "LIMIT" in query_upper
        has_window_topn = bool(
            re.search(r"\bQUALIFY\b", query_upper)
            or re.search(r"\b(ROW_NUMBER|RANK|DENSE_RANK)\s*\(", query_upper)
        )
        if not has_limit and not has_window_topn:
            critical_issues.append("Missing LIMIT for Top/Bottom N queries.")

    # 4. Incorrect ORDER BY direction (first sort key only)
    if "ORDER BY" in query_upper:
        order_tail = query_upper.split("ORDER BY", 1)[1]
        order_primary = re.split(r"\bLIMIT\b|\bOFFSET\b|;", order_tail, maxsplit=1)[0]
        first_key = order_primary.split(",")[0].strip()
        is_desc = bool(re.search(r"\bDESC\b", first_key))
        if re.search(r"\b(highest|top|most|largest|max)\b", question_lower):
            if not is_desc:
                critical_issues.append("Incorrect ORDER BY direction: Expected DESC for 'highest'/'top' intent.")
        elif re.search(r"\b(lowest|bottom|least|smallest|min)\b", question_lower):
            if is_desc:
                critical_issues.append("Incorrect ORDER BY direction: Expected ASC for 'lowest'/'bottom' intent.")

    # 5. Invalid column references (quoted AND unquoted — catch hallucinations)
    if schema and ("columns" in schema or schema.get("multi_table")):
        for issue in find_unknown_column_references(query, schema):
            critical_issues.append(issue)

    # 6. Aggregate Alias (WARNING)
    select_clause_match = re.search(r"SELECT\s+(.*?)\s+FROM", query, re.IGNORECASE | re.DOTALL)
    if select_clause_match:
        select_clause = select_clause_match.group(1)
        top_level_exprs = split_top_level(select_clause, ',')
        for expr in top_level_exprs:
            if re.search(r"\b(MAX|MIN|AVG|SUM|COUNT)\s*\(", expr, flags=re.IGNORECASE):
                if not re.search(r"\bAS\s+", expr, flags=re.IGNORECASE):
                    warnings.append(f"Aggregate expression {expr.strip()} is missing a meaningful alias using AS.")

    # 7. Monetary Formatting (WARNING)
    monetary_keywords = ["amount", "price", "cost", "revenue", "salary", "balance", "billing"]
    for match in re.finditer(r"\b(MAX|MIN|AVG|SUM)\s*\(\s*(?:DISTINCT\s+)?([^)]+)\)", query_upper):
        col_name = match.group(2).lower()
        if any(kw in col_name for kw in monetary_keywords):
            if "ROUND" not in query_upper:
                warnings.append("When returning monetary values, automatically round to two decimal places where appropriate.")
                break

    is_valid = len(critical_issues) == 0
    diagnostics = ""
    if critical_issues:
        diagnostics += "CRITICAL ISSUES:\n- " + "\n- ".join(critical_issues) + "\n"
    if warnings:
        diagnostics += "WARNINGS:\n- " + "\n- ".join(warnings) + "\n"

    return {
        "is_valid": is_valid,
        "diagnostics": diagnostics.strip(),
        "critical_issues": critical_issues,
        "warnings": warnings
    }
