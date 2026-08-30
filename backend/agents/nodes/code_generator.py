import logging
from typing import Dict, Any, List, Optional
from backend.agents.state import AgentState, get_effective_question
from backend.config import use_analytics_demo_fallback, invoke_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

SQL_GENERATOR_PROMPT = """You are the SQL Code Generator for MarketMind AI — Agentic B2B Marketplace Intelligence.
Your job is to generate a single, highly optimized SELECT query to run against DuckDB.

SEMANTIC CORRECTNESS (critical):
- Execution success does not mean semantic success.
- The SQL must answer every explicit analytical requirement in the SEMANTIC REQUIREMENTS contract.
- Never collapse a dimension-level question into a global aggregate.
- Never substitute profit for profit_margin when margin is explicitly requested.
- Never answer a top/bottom intersection question with only one ranking.
- Return enough rows and metrics to support the requested comparison and business conclusion.
- SQL returns evidence only; do not write narrative business insights in SQL.

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
6. REQUIRED DIMENSIONS: If the contract lists city/category/region/segment/product/channel, include that dimension in SELECT and GROUP BY when analysis is across/by that dimension.
7. DERIVED METRICS: If profit_margin is required, compute SUM(profit)/NULLIF(SUM(sales_amount),0) AS profit_margin (use schema column names). Raw profit alone is not enough.
8. RELATIONSHIPS: Across a dimension → aggregate per dimension with the relevant metrics. A single global CORR() is not enough.
9. COMPARISONS: Prefer multiple relevant rows/rankings. Avoid LIMIT 1 unless comparison context is still present.
10. RANKINGS / INTERSECTION: For top-N by sales AND bottom-N by profit margin, use separate DENSE_RANK()/RANK() expressions and return the INTERSECTION (sales_rank <= N AND margin_rank <= N).
11. When asked for total sales, total profit, and profit margin per group, return ALL three for every group.

Schema:
{schema_context}

Original Question:
{question}

Plan Steps:
{plan_steps}

{requirement_contract}
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
7. SEMANTIC: Satisfy the SEMANTIC REQUIREMENTS contract (dimensions, metrics, derived metrics). Execution success ≠ semantic success.

Schema:
{schema_context}

Original Question:
{question}

Plan Steps:
{plan_steps}

{requirement_contract}
"""


def _strip_code_fences(code: str) -> str:
    code = (code or "").strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        code = "\n".join(lines).strip()
    return code


def code_generator_node(state: AgentState) -> Dict[str, Any]:
    """
    Generates SQL or Python code based on the plan and schema.
    Injects a canonical semantic requirement contract and pre-checks SQL coverage.
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
    from backend.services.analytics_fallback import (
        resolve_analytics_fallback,
        unsupported_analytics_message,
        ANALYSIS_SOURCE_FALLBACK,
        ANALYSIS_SOURCE_LLM,
    )
    from backend.services.requirement_coverage import (
        check_requirement_coverage,
        extract_question_requirements,
        format_semantic_requirement_contract,
        generation_precheck_feedback,
        schema_column_names,
    )

    req = extract_question_requirements(question)
    schema_cols = schema_column_names(schema_profile or {})
    requirement_contract = format_semantic_requirement_contract(
        req, schema_columns=schema_cols
    )

    def _finish(
        code: str,
        *,
        source: str,
        failed: bool = False,
        failure: dict | None = None,
        provider: str | None = None,
        model: str | None = None,
        precheck_ok: bool | None = None,
        precheck_missing: Optional[List[str]] = None,
    ):
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        node_metadata = {
            "node_name": node_name,
            "start_time": start_time,
            "end_time": end_time,
            "duration_ms": duration_ms,
            "status": "failed" if failed else "success",
            "retry_count": retry_count,
            "error_message": None if not failed else (failure or {}).get("error_message"),
        }
        execution_metadata = list(state.get("execution_metadata") or [])
        execution_metadata.append(node_metadata)
        artifacts = dict(state.get("analysis_artifacts") or {})
        artifacts["analysis_source"] = source
        artifacts["question_requirements"] = req.to_dict()
        artifacts["requirement_contract"] = requirement_contract
        if precheck_ok is not None:
            artifacts["generation_precheck_ok"] = precheck_ok
        if precheck_missing is not None:
            artifacts["generation_precheck_missing"] = list(precheck_missing)
        if provider:
            artifacts["provider"] = provider
        elif source == ANALYSIS_SOURCE_FALLBACK:
            artifacts["provider"] = "Deterministic Fallback"
        if model:
            artifacts["model"] = model
        elif source == ANALYSIS_SOURCE_FALLBACK:
            artifacts["model"] = "schema-aware-sql"
        return {
            "generated_code": code,
            "execution_metadata": execution_metadata,
            "analysis_artifacts": artifacts,
            "failure_summary": failure,
        }

    schema_context = format_schema_context_for_llm(schema_profile or {}, fallback_table=table_name)

    # DEMO MODE: try deterministic schema-aware SQL before calling the LLM.
    if approach == "sql" and use_analytics_demo_fallback():
        fallback = resolve_analytics_fallback(question, schema_profile or {}, dataset_id)
        if fallback.sql:
            logger.warning(
                "Analytics DEMO MODE — using deterministic SQL fallback (skipping LLM)."
            )
            ok_fb, miss_fb = check_requirement_coverage(question, fallback.sql, columns=None)
            return _finish(
                fallback.sql,
                source=ANALYSIS_SOURCE_FALLBACK,
                precheck_ok=ok_fb,
                precheck_missing=miss_fb,
            )
        logger.warning(
            "Analytics DEMO MODE — no deterministic SQL for question (reason=%s).",
            fallback.reason,
        )
        return _finish(
            "",
            source=ANALYSIS_SOURCE_FALLBACK,
            failed=True,
            failure={
                "failure_type": "unsupported_question",
                "error_message": unsupported_analytics_message(
                    fallback.reason, schema_profile or {}, dataset_id
                ),
                "code_context": "",
                "expected_vs_actual": fallback.reason,
            },
        )

    if approach == "sql":
        system_prompt = SQL_GENERATOR_PROMPT.format(
            table_name=table_name,
            schema_context=schema_context,
            question=question,
            plan_steps=plan_steps,
            requirement_contract=requirement_contract,
        )
    else:
        system_prompt = PYTHON_GENERATOR_PROMPT.format(
            dataset_id=dataset_id,
            schema_context=schema_context,
            question=question,
            plan_steps=plan_steps,
            requirement_contract=requirement_contract,
        )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Generate the code to answer: '{question}' using the plan above.\n\n"
                "You MUST satisfy BOTH the original question AND the SEMANTIC REQUIREMENTS contract."
            )
        ),
    ]

    # Inject failure history if we are retrying code generation
    if retry_history:
        code_failures = [
            f for f in retry_history
            if f["failure_type"] in [
                "runtime", "structural", "visualization", "timeout", "semantic",
                "semantic_incomplete",
            ]
        ]
        if code_failures:
            logger.info("Injecting code/semantic failure history into Code Generator context.")
            failures_context = "\n---\n".join([
                f"Attempt {i+1} Failure Details:\n"
                f"- Failure Type: {f['failure_type']}\n"
                f"- Error Message: {f['error_message']}\n"
                f"- Code Executed:\n{f['code_context']}\n"
                f"- Mismatch details: {f['expected_vs_actual']}"
                for i, f in enumerate(code_failures)
            ])
            messages.append(HumanMessage(
                content=(
                    "ATTENTION: Previous attempts failed (including semantic coverage). "
                    "History:\n"
                    f"{failures_context}\n\n"
                    "Regenerate SQL so EVERY required metric/dimension/derived metric is present. "
                    "Do NOT repeat the same incomplete query."
                )
            ))

    def _semantic_precheck(code: str):
        # Pre-check inspects generated SQL only — do not pass schema columns
        # (that would falsely mark metrics as covered merely because they exist in the dataset).
        return check_requirement_coverage(question, code, columns=None)

    try:
        inv = invoke_llm(messages, temperature=0.0)
        code = _strip_code_fences(inv.get("content") or "")
        provider = inv.get("provider")
        model = inv.get("model")
        source = inv.get("analysis_source") or ANALYSIS_SOURCE_LLM

        # Lightweight deterministic pre-check (SQL only; do not execute)
        if approach == "sql" and code:
            ok_cov, missing = _semantic_precheck(code)
            if not ok_cov:
                logger.warning(
                    "SQL generation pre-check failed (semantic_incomplete). Missing=%s. Regenerating once.",
                    missing,
                )
                feedback = generation_precheck_feedback(question, missing, req)
                regen_messages = list(messages) + [
                    HumanMessage(
                        content=(
                            f"{feedback}\n\n"
                            f"Previous incomplete SQL:\n{code}\n\n"
                            "Output ONLY corrected raw SQL."
                        )
                    )
                ]
                try:
                    inv2 = invoke_llm(regen_messages, temperature=0.0)
                    code2 = _strip_code_fences(inv2.get("content") or "")
                    if code2:
                        code = code2
                        provider = inv2.get("provider") or provider
                        model = inv2.get("model") or model
                        source = inv2.get("analysis_source") or source
                except Exception as regen_err:
                    logger.warning("Pre-check regeneration call failed: %s", regen_err)

                ok_cov, missing = _semantic_precheck(code)
                if not ok_cov:
                    feedback = generation_precheck_feedback(question, missing, req)
                    logger.warning(
                        "SQL still fails semantic pre-check after regenerate. Missing=%s",
                        missing,
                    )
                    # Do not pass incomplete SQL downstream as success — use existing retry path
                    return _finish(
                        "",
                        source=source,
                        failed=True,
                        failure={
                            "failure_type": "semantic_incomplete",
                            "error_message": feedback,
                            "code_context": code,
                            "expected_vs_actual": (
                                "semantic_incomplete. "
                                f"Missing requirements: {list(missing)}. "
                                "Suggested Retry Target: code_generator. "
                                "Suggested Retry Strategy: Satisfy the SEMANTIC REQUIREMENTS "
                                "contract (dimensions, metrics, derived metrics, rankings)."
                            ),
                        },
                        provider=provider,
                        model=model,
                        precheck_ok=False,
                        precheck_missing=list(missing),
                    )

            logger.info(
                "Generated SQL passed semantic pre-check via %s (%s).",
                provider,
                model,
            )
            return _finish(
                code,
                source=source,
                provider=provider,
                model=model,
                precheck_ok=True,
                precheck_missing=[],
            )

        generated_code = code
        logger.info(
            "Generated %s code successfully via %s (%s).",
            approach.upper(),
            provider,
            model,
        )
        return _finish(
            generated_code,
            source=source,
            provider=provider,
            model=model,
        )
    except Exception as e:
        logger.error(f"Error in Code Generator Node: {e}")
        status = "failed"
        error_msg = str(e)
        from backend.utils.provider_errors import (
            is_provider_auth_or_config_error,
            provider_error_user_message,
        )

        error_str = error_msg.lower()
        is_rate_limited = (
            "429" in error_str
            or "resource_exhausted" in error_str
            or "rate limit" in error_str
        )
        is_provider = (
            is_rate_limited
            or is_provider_auth_or_config_error(error_msg)
            or "all llm providers failed" in error_str
        )

        # Provider/auth failure → deterministic fallback for any loaded dataset
        if is_provider and approach == "sql":
            fallback = resolve_analytics_fallback(question, schema_profile or {}, dataset_id)
            if fallback.sql:
                logger.warning(
                    "LLM provider unavailable — using deterministic analytics fallback."
                )
                ok_fb, miss_fb = check_requirement_coverage(
                    question, fallback.sql, columns=None
                )
                return _finish(
                    fallback.sql,
                    source=ANALYSIS_SOURCE_FALLBACK,
                    precheck_ok=ok_fb,
                    precheck_missing=miss_fb,
                )
            return _finish(
                "",
                source=ANALYSIS_SOURCE_FALLBACK,
                failed=True,
                failure={
                    "failure_type": "unsupported_question",
                    "error_message": unsupported_analytics_message(
                        fallback.reason, schema_profile or {}, dataset_id
                    ),
                    "code_context": "",
                    "expected_vs_actual": fallback.reason,
                },
            )

        if is_provider:
            logger.error("Provider chain exhausted. Skipping agent retry loop.")
            return _finish(
                generated_code,
                source=ANALYSIS_SOURCE_FALLBACK,
                failed=True,
                failure={
                    "failure_type": "provider_error",
                    "error_message": provider_error_user_message(error_msg),
                    "code_context": "",
                    "expected_vs_actual": error_msg,
                },
            )

    # Record metrics (non-provider unexpected path with empty code)
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
        "execution_metadata": execution_metadata,
        "analysis_artifacts": {
            **(state.get("analysis_artifacts") or {}),
            "question_requirements": req.to_dict(),
            "requirement_contract": requirement_contract,
        },
    }
