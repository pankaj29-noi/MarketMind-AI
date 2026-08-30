import os
import sys
import subprocess
import shutil
import logging
import json
import duckdb
from typing import Dict, Any, Tuple
from backend.services.session_manager import session_manager
from backend.config import SANDBOX_TIMEOUT_SECONDS, get_scratch_root

logger = logging.getLogger(__name__)

# Base scratch directory (Vercel → /tmp/marketmind/scratch)
SCRATCH_DIR = str(get_scratch_root())

def prepare_scratch_directory(session_id: str, dataset_id: str) -> str:
    """
    Prepares a clean scratch directory for the session and exports active table(s) to CSV.

    For the MarketMind multi-table demo, ``dataset_id`` is the logical id ``marketplace``
    (not a DuckDB table). Export each real table instead.
    """
    session_dir = os.path.join(SCRATCH_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    from backend.marketplace.demo_data import MARKETPLACE_DATASET_ID, MARKETPLACE_TABLES

    tables_to_export = (
        list(MARKETPLACE_TABLES)
        if dataset_id == MARKETPLACE_DATASET_ID
        else [dataset_id]
    )

    try:
        conn = session_manager.get_session_connection(session_id)
        for table_name in tables_to_export:
            csv_path = os.path.join(session_dir, f"{table_name}.csv")
            if os.path.exists(csv_path):
                continue
            logger.info(
                f"Exporting in-memory DuckDB table {table_name} to {csv_path} for Python execution..."
            )
            conn.execute(
                f"COPY {table_name} TO '{csv_path.replace(os.sep, '/')}' "
                f"(HEADER, DELIMITER ',');"
            )
    except Exception as e:
        logger.error(f"Failed to export table(s) to CSV for sandbox: {e}")
        raise

    return session_dir

def run_python_in_sandbox(session_id: str, dataset_id: str, code: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Runs Python code inside a restricted subprocess sandbox.
    Returns: (success, error_message, outputs_dict)
    """
    try:
        session_dir = prepare_scratch_directory(session_id, dataset_id)
    except Exception as e:
        return False, f"Failed to initialize sandbox directory: {e}", {}

    script_path = os.path.join(session_dir, "sandbox_run.py")
    
    # Write the generated code to a file
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)

    logger.info(f"Executing Python script in sandbox process. Timeout: {SANDBOX_TIMEOUT_SECONDS}s")
    
    # Determine the python executable to use (matching our virtualenv if active)
    python_exe = sys.executable
    
    try:
        # Harden sandbox by constructing a whitelisted environment (drop all API/secrets/DB credentials)
        whitelist_keys = {
            "PATH", "PYTHONPATH", "TEMP", "TMP", 
            "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEM32"
        }
        whitelist_env = {
            k: v for k, v in os.environ.items()
            if k.upper() in whitelist_keys or k.upper().startswith("LC_") or k.upper().startswith("LANG")
        }

        # Run subprocess with timeout
        result = subprocess.run(
            [python_exe, "sandbox_run.py"],
            cwd=session_dir,
            capture_output=True,
            text=True,
            env=whitelist_env,
            timeout=SANDBOX_TIMEOUT_SECONDS
        )
        
        # Check execution status
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"Process exited with code {result.returncode}"
            logger.warning(f"Sandbox execution failed: {error_msg}")
            return False, error_msg, {}

        # Success - check for generated files (chart.json, report.pdf)
        outputs = {}
        
        chart_path = os.path.join(session_dir, "chart.json")
        if os.path.exists(chart_path):
            try:
                with open(chart_path, "r") as f:
                    outputs["chart_json"] = json.load(f)
                logger.info("Found generated chart.json in sandbox.")
            except Exception as e:
                logger.error(f"Failed to read chart.json from sandbox: {e}")
                return False, f"Generated chart.json was malformed: {e}", {}
                
        pdf_path = os.path.join(session_dir, "report.pdf")
        if os.path.exists(pdf_path):
            # Move PDF to a more permanent location or keep in scratch and return path
            # We will keep in scratch for download
            outputs["pdf_path"] = pdf_path
            logger.info("Found generated report.pdf in sandbox.")

        result_path = os.path.join(session_dir, "result.json")
        if os.path.exists(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    outputs["result_data"] = json.load(f).get("result")
                logger.info("Found generated result.json in sandbox.")
            except Exception as e:
                logger.error(f"Failed to read result.json from sandbox: {e}")
                return False, f"Generated result.json was malformed: {e}", {}

        return True, "", outputs

    except subprocess.TimeoutExpired:
        logger.warning(f"Sandbox execution timed out after {SANDBOX_TIMEOUT_SECONDS}s")
        return False, f"Execution Timeout: Code execution took longer than {SANDBOX_TIMEOUT_SECONDS} seconds.", {}
    except Exception as e:
        logger.error(f"Exception during sandbox execution: {e}")
        return False, str(e), {}
    finally:
        # Clean up code file, but keep output files for retrieval
        try:
            if os.path.exists(script_path):
                os.remove(script_path)
        except Exception:
            pass
