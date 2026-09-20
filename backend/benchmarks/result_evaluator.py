"""Compare expected DuckDB result sets vs actual (evaluation only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def _norm_val(v: Any, tol: float = 1e-2) -> Any:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            pass
    if isinstance(v, float):
        return round(v, 6)
    if hasattr(v, "item"):
        try:
            return _norm_val(v.item(), tol)
        except Exception:
            pass
    return v


def normalize_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        out.append({str(k): _norm_val(v) for k, v in r.items()})
    return out


def compare_results(
    expected: Sequence[Dict[str, Any]],
    actual: Sequence[Dict[str, Any]],
    *,
    check_order: bool = True,
    numeric_tol: float = 0.05,
) -> Tuple[bool, List[str]]:
    """
    Return (ok, issues). Column names compared case-insensitively after str().
    Numeric values compared with absolute tolerance.
    """
    issues: List[str] = []
    exp = normalize_rows(expected)
    act = normalize_rows(actual)

    if len(exp) != len(act):
        issues.append(f"row_count expected={len(exp)} actual={len(act)}")

    if not exp and not act:
        return True, []

    if exp:
        exp_cols = set(exp[0].keys())
        act_cols = set(act[0].keys()) if act else set()
        if exp_cols != act_cols:
            # allow same cols different order / casing
            if {c.lower() for c in exp_cols} != {c.lower() for c in act_cols}:
                issues.append(f"columns expected={sorted(exp_cols)} actual={sorted(act_cols)}")

    n = min(len(exp), len(act))
    for i in range(n):
        er, ar = exp[i], act[i]
        # map actual keys lower
        amap = {k.lower(): v for k, v in ar.items()}
        for k, ev in er.items():
            av = ar.get(k, amap.get(k.lower()))
            if isinstance(ev, (int, float)) and isinstance(av, (int, float)):
                if abs(float(ev) - float(av)) > numeric_tol and abs(float(ev) - float(av)) > numeric_tol * max(1.0, abs(float(ev))):
                    issues.append(f"row[{i}].{k} expected={ev} actual={av}")
            elif ev != av:
                issues.append(f"row[{i}].{k} expected={ev!r} actual={av!r}")
        if not check_order:
            break

    return (len(issues) == 0), issues


def evaluate_answer_text(
    question: str,
    answer: str,
    result_rows: Sequence[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Lightweight groundedness heuristics for narrative answers."""
    issues: List[str] = []
    text = (answer or "").lower()
    if not text.strip():
        return True, []  # table-only answers OK
    # flag invented huge numbers not present in results
    import re

    nums = re.findall(r"\d[\d,]*\.?\d*", answer or "")
    flat_vals = []
    for r in result_rows[:50]:
        for v in r.values():
            if isinstance(v, (int, float)):
                flat_vals.append(float(v))
            elif v is not None:
                flat_vals.append(str(v).lower())
    for n in nums[:20]:
        raw = n.replace(",", "")
        try:
            f = float(raw)
        except ValueError:
            continue
        if f > 1000 and flat_vals:
            # must be close to some result number or appear as string
            if not any(
                (isinstance(v, float) and abs(v - f) <= max(1.0, 0.05 * abs(f)))
                or (isinstance(v, str) and raw in v)
                for v in flat_vals
            ):
                # soft warning only for very large unmatched numbers
                if f > 1e6:
                    issues.append(f"possible_ungrounded_number:{n}")
    q = (question or "").lower()
    if "employee satisfaction" in q and "cannot" not in text and "not" not in text and "unavailable" not in text:
        issues.append("should_abstain_missing_field")
    return (len(issues) == 0), issues
