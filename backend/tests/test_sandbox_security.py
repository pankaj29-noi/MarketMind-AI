"""Adversarial sandbox / AST gate regressions."""
from backend.agents.sandbox import run_python_in_sandbox
from backend.services.python.python_quality_validator import validate_python_code


def test_ast_rejects_os_and_subprocess():
    for code in (
        "import os\nos.system('id')\n",
        "import subprocess\nsubprocess.run(['id'])\n",
        "import socket\n",
        "eval('1+1')\n",
        "exec('x=1')\n",
        "__import__('os')\n",
    ):
        ok, msg = validate_python_code(code)
        assert ok is False, code
        assert msg


def test_sandbox_rejects_before_spawn(tmp_path, monkeypatch):
    # Avoid needing a real DuckDB session: rejection happens before prepare_scratch
    ok, err, outputs = run_python_in_sandbox("sess", "t", "import os\nprint(os.getcwd())\n")
    assert ok is False
    assert "Sandbox rejected code" in err
    assert outputs == {}


def test_ast_allows_pandas_numpy():
    code = "import pandas as pd\nimport numpy as np\nresult = int(np.array([1,2,3]).sum())\n"
    ok, msg = validate_python_code(code)
    assert ok is True, msg
