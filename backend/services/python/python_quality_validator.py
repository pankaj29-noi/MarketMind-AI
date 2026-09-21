import ast
import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# Strict allowlist of modules genuinely needed for analytical transformations
ALLOWED_MODULES = {
    "pandas", "numpy", "math", "statistics", "re", "json", "datetime", "collections"
}

# Dangerous calls to reject
DANGEROUS_CALLS = {
    "eval", "exec", "__import__", "globals", "locals", "compile", "breakpoint", "input",
}

# I/O helpers — only relative scratch filenames are allowed (sandbox wrapper uses these)
_SAFE_SCRATCH_FILE = re.compile(r"^[\w.-]+\.(csv|json)$")
_FORBIDDEN_IO_ATTRS = {
    "read_csv",
    "read_excel",
    "read_parquet",
    "read_json",
    "read_html",
    "read_pickle",
    "read_fwf",
    "read_table",
    "to_pickle",
    "to_excel",
}


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_safe_scratch_path(path: str) -> bool:
    if not path or ".." in path or "/" in path or "\\" in path:
        return False
    return bool(_SAFE_SCRATCH_FILE.match(path))


def validate_python_code(code: str) -> Tuple[bool, str]:
    """
    Deterministically validates Python code using AST parsing.
    Checks:
    - Syntax correctness
    - Forbidden imports (anything not in ALLOWED_MODULES)
    - Dangerous builtins (eval, exec, open to arbitrary paths, etc.)
    - Pandas/path I/O limited to relative scratch filenames
    Returns (is_valid, error_message)
    """
    try:
        root = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax Error: {e.msg} at line {e.lineno}, col {e.offset}"
    except Exception as e:
        return False, f"AST parsing failed: {e}"

    for node in ast.walk(root):
        # 1. Check imports (Import and ImportFrom)
        if isinstance(node, ast.Import):
            for name in node.names:
                base_module = name.name.split('.')[0]
                if base_module not in ALLOWED_MODULES:
                    return False, f"Import Violation: Module '{base_module}' is not in the whitelist of permitted libraries."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base_module = node.module.split('.')[0]
                if base_module not in ALLOWED_MODULES:
                    return False, f"Import Violation: Module '{base_module}' is not in the whitelist of permitted libraries."

        # 2. Check call arguments and attributes for dangerous dynamic imports or builtins
        elif isinstance(node, ast.Call):
            # Checking direct builtin calls (e.g. exec(), eval(), open())
            if isinstance(node.func, ast.Name):
                fname = node.func.id
                if fname in DANGEROUS_CALLS:
                    return False, f"Security Violation: Use of forbidden function '{fname}' is prohibited."
                if fname == "open":
                    path = _const_str(node.args[0]) if node.args else None
                    # Sandbox wrapper writes result.json; nothing else may open files.
                    if path != "result.json":
                        return False, "Security Violation: open() is restricted to result.json inside the sandbox."

            # Checking getattr/dynamic attributes like getattr(..., '__import__')
            elif isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if attr in DANGEROUS_CALLS:
                    return False, f"Security Violation: Accessing forbidden attribute '{attr}' is prohibited."
                if attr in _FORBIDDEN_IO_ATTRS or attr == "to_csv":
                    path = _const_str(node.args[0]) if node.args else None
                    # Allow only relative scratch CSV/JSON used by the sandbox envelope.
                    if attr.startswith("read_") and path and _is_safe_scratch_path(path):
                        pass
                    elif attr == "to_csv" and path and _is_safe_scratch_path(path):
                        pass
                    else:
                        return False, (
                            f"Security Violation: '{attr}()' may only use a relative scratch "
                            "filename (e.g. dataset.csv), never absolute or parent paths."
                        )

        # 3. Check name nodes (just in case exec/eval/globals are referenced or passed around)
        elif isinstance(node, ast.Name):
            if node.id in DANGEROUS_CALLS and not isinstance(node.ctx, ast.Store):
                return False, f"Security Violation: Reference to forbidden identifier '{node.id}' is prohibited."

    return True, ""
