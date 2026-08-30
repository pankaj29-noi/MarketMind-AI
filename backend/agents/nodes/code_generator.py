import json
import logging
from typing import Dict, Any
from backend.agents.state import AgentState, get_effective_question
from backend.config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

SQL_GENERATOR_PROMPT = """You are the SQL Code Generator for MarketMind AI — Agentic B2B Marketplace Intelligence.
Your job is to generate a single, highly optimized SELECT query to run against DuckDB.

CRITICAL RULES:
1. ONLY write a SELECT statement. Do NOT write INSERT, UPDATE, DELETE, CREATE, or DROP statements.
2. TABLE NAMES:
   - If the schema is MULTI-TABLE, use the real table names (categories, suppliers, buyers, products, leads, orders) and JOIN using the documented relationships. Do NOT query a fictional table named "{table_name}".
   - If the schema is a single uploaded CSV, the active table name must be "{table_name}".
3. Keep the column names exactly as they appear in the schema.
4. Output ONLY the raw SQL query. Do not wrap it in explanation text or backticks, just output the plain SQL.
5. DATE & TIMESTAMP OPERATIONS (DUCKDB SQL-COMPATIBLE):
   - Review the schema and sample values for columns representing dates/timestamps.
   - If a column is a VARCHAR resembling a date (e.g., '2/24/2003 0:00'), you MUST parse it using the `strptime()` function with the correct format string (e.g. `strptime(OrderDate, '%m/%d/%Y %H:%M')`) before applying date functions like `date_trunc()` or `strftime()`.
   - For marketplace `orders.order_date` (YYYY-MM-DD), you may use CAST(order_date AS DATE) or strptime as appropriate.
   - Never apply `date_trunc` or date aggregations directly on unparsed VARCHAR columns.

Schema:
{schema_context}

Original Question:
{question}

Plan Steps:
{plan_steps}
"""

PYTHON_GENERATOR_PROMPT = """You are the Python Code Generator for the Autonomous Data Analyst Agent.
Your job is to generate a self-contained Python script to solve the analysis plan (typically for visualization or report generation).

CRITICAL RULES:
1. DATA LOADING:
   - The dataset is stored as a CSV file in the current working directory as "{dataset_id}.csv".
   - Load it using pandas: `df = pd.read_csv("{dataset_id}.csv")`
2. VISUALIZATION (IF APPLICABLE):
   - If the expected output is a chart, generate a Plotly chart.
   - You MUST write the Plotly Figure object to a file named "chart.json" in the current directory using fig.write_json("chart.json"):
     ```python
     # Create figure 'fig'
     fig.write_json("chart.json")
     ```
3. PDF GENERATION (IF APPLICABLE):
   - If generating a PDF report, use ReportLab and save the output file to "report.pdf" in the current directory.
4. SANDBOX LIMITS:
   - Do NOT attempt to access the network.
   - Do NOT import unauthorized libraries (standard libraries like pandas, numpy, plotly, reportlab, json, and math are allowed).
5. Output ONLY the raw Python code. Do not wrap it in markdown backticks or explanation text.
6. Handle exceptions gracefully within your script and print clean outputs.

Schema:
{schema_context}

Original Question:
{question}

Plan Steps:
{plan_steps}
"""

def code_generator_node(state: AgentState) -> Dict[str, Any]:
    """
    Generates SQL or Python code based on the plan and schema.
    """
    import time
    node_name = "code_generator"
    start_time = time.time()
    retry_count = state.get("retry_count", 0)
    
    logger.info(f"Node started: {node_name} (Retry count: {retry_count})")
    
    question = get_effective_question(state)
    schema_profile = state.get("schema_profile")
    plan = state.get("plan") or {}
    dataset_id = state.get("dataset_id")
    table_name = state.get("duckdb_table") or dataset_id
    retry_history = state.get("retry_history", [])
    
    approach = plan.get("approach", "sql")
    plan_steps = "\n".join([f"- {s}" for s in plan.get("steps", [])])

    status = "success"
    error_msg = None
    generated_code = ""

    from backend.marketplace.demo_data import format_schema_context_for_llm

    schema_context = format_schema_context_for_llm(schema_profile or {}, fallback_table=table_name)

    if approach == "sql":
        system_prompt = SQL_GENERATOR_PROMPT.format(table_name=table_name, schema_context=schema_context, question=question, plan_steps=plan_steps)
    else:
        system_prompt = PYTHON_GENERATOR_PROMPT.format(dataset_id=dataset_id, schema_context=schema_context, question=question, plan_steps=plan_steps)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Generate the code to answer: '{question}' using the plan above.")
    ]

    # Inject failure history if we are retrying code generation
    if retry_history:
        # Get failures related to code execution (runtime, structural, visualization, timeout)
        code_failures = [f for f in retry_history if f["failure_type"] in ["runtime", "structural", "visualization", "timeout"]]
        if code_failures:
            logger.info("Injecting code execution failure history into Code Generator context.")
            failures_context = "\n---\n".join([
                f"Attempt {i+1} Failure Details:\n"
                f"- Failure Type: {f['failure_type']}\n"
                f"- Error Message: {f['error_message']}\n"
                f"- Code Executed:\n{f['code_context']}\n"
                f"- Mismatch details: {f['expected_vs_actual']}"
                for i, f in enumerate(code_failures)
            ])
            messages.append(HumanMessage(
                content=f"ATTENTION: Previous code execution attempts failed. Here is the compressed history of failures:\n{failures_context}\n\nPlease analyze these failures and rewrite the code to fix the root cause. Do NOT repeat the same mistakes."
            ))

    try:
        llm = get_llm(temperature=0.0) # 0.0 temperature for deterministic code generation
        response = llm.invoke(messages)
        code = response.content.strip()

        # Clean markdown code blocks (e.g. ```sql or ```python)
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines).strip()

        generated_code = code
        logger.info(f"Generated {approach.upper()} code successfully.")
    except Exception as e:
        logger.error(f"Error in Code Generator Node: {e}")
        status = "failed"
        error_msg = str(e)
        from backend.utils.provider_errors import (
            is_provider_auth_or_config_error,
            provider_error_user_message,
        )
        from backend.marketplace.demo_data import MARKETPLACE_DATASET_ID
        from backend.marketplace.sql_fallback import resolve_marketplace_fallback

        error_str = error_msg.lower()
        is_rate_limited = (
            "429" in error_str
            or "resource_exhausted" in error_str
            or "rate limit" in error_str
        )
        is_provider = is_rate_limited or is_provider_auth_or_config_error(error_msg)

        # Marketplace demo offline path: deterministic SQL when LLM keys are invalid.
        if (
            is_provider
            and approach == "sql"
            and dataset_id == MARKETPLACE_DATASET_ID
        ):
            from backend.marketplace.sql_fallback import (
                resolve_marketplace_fallback,
                unsupported_user_message,
            )
            fallback = resolve_marketplace_fallback(question)
            if fallback.sql:
                logger.warning(
                    "Using marketplace SQL fallback after LLM provider failure "
                    "(source=%s).",
                    fallback.analysis_source,
                )
                status = "success"
                error_msg = None
                generated_code = fallback.sql
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                node_metadata = {
                    "node_name": node_name,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_ms": duration_ms,
                    "status": status,
                    "retry_count": retry_count,
                    "error_message": None,
                }
                execution_metadata = list(state.get("execution_metadata") or [])
                execution_metadata.append(node_metadata)
                return {
                    "generated_code": generated_code,
                    "execution_metadata": execution_metadata,
                    "failure_summary": None,
                    "analysis_artifacts": {
                        "analysis_source": fallback.analysis_source,
                    },
                }

            # No safe SQL template — graceful unsupported response (not System Failure)
            logger.warning(
                "Marketplace question not answerable via deterministic fallback "
                "(reason=%s).",
                fallback.reason,
            )
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            node_metadata = {
                "node_name": node_name,
                "start_time": start_time,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "status": "failed",
                "retry_count": retry_count,
                "error_message": fallback.reason,
            }
            execution_metadata = list(state.get("execution_metadata") or [])
            execution_metadata.append(node_metadata)
            return {
                "generated_code": "",
                "execution_metadata": execution_metadata,
                "failure_summary": {
                    "failure_type": "unsupported_question",
                    "error_message": unsupported_user_message(fallback.reason),
                    "code_context": "",
                    "expected_vs_actual": fallback.reason,
                },
                "analysis_artifacts": {
                    "analysis_source": "deterministic_fallback",
                },
            }

        if is_provider:
            logger.error("Provider chain exhausted. Skipping agent retry loop.")
            # Record metrics here since we are returning early
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            node_metadata = {
                "node_name": node_name,
                "start_time": start_time,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "status": status,
                "retry_count": retry_count,
                "error_message": error_msg
            }
            execution_metadata = list(state.get("execution_metadata") or [])
            execution_metadata.append(node_metadata)
            return {
                "generated_code": generated_code,
                "execution_metadata": execution_metadata,
                "failure_summary": {
                    "failure_type": "provider_error",
                    "error_message": provider_error_user_message(error_msg),
                    "code_context": "",
                    "expected_vs_actual": error_msg
                }
            }

    # Record metrics
    end_time = time.time()
    duration_ms = (end_time - start_time) * 1000
    logger.info(f"Node completed: {node_name} in {duration_ms:.2f}ms | Status: {status}")
    
    node_metadata = {
        "node_name": node_name,
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "status": status,
        "retry_count": retry_count,
        "error_message": error_msg
    }
    
    execution_metadata = list(state.get("execution_metadata") or [])
    execution_metadata.append(node_metadata)
    
    return {
        "generated_code": generated_code,
        "execution_metadata": execution_metadata
    }
