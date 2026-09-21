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


def _strip_code_fences(code) -> str:
    # Some providers (esp. Gemini) return content as a list of parts.
    if isinstance(code, list):
        parts: List[str] = []
        for part in code:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(getattr(part, "text", None) or part))
        code = "\n".join(p for p in parts if p)
    code = (code or "").strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        code = "\n".join(lines).strip()
    # If the model emitted multiple statements, keep the first read-only query only.
    if ";" in code:
        first = code.split(";", 1)[0].strip()
        upper = first.upper()
        if upper.startswith("SELECT") or upper.startswith("WITH"):
            code = first
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
        ANALYSIS_SOURCE_SQLCODER,
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

    # Structured IR for prompts + artifacts
    from backend.services.question_ir import build_question_ir, format_ir_for_llm
    from backend.services.analytics_perf import classify_question_complexity
    from backend.services.sql.sql_pattern_library import try_simple_deterministic_sql

    ir = build_question_ir(question, schema_profile or {})
    complexity = ir.complexity or classify_question_complexity(question)
    ir_block = format_ir_for_llm(ir)
    if ir_block:
        requirement_contract = requirement_contract + "\n\n" + ir_block

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
        artifacts["question_ir"] = ir.to_dict()
        artifacts["question_complexity"] = complexity
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

    # A question that cannot be pinned to one reading must be clarified, not guessed at.
    if approach == "sql" and retry_count == 0:
        from backend.services.ambiguity import detect_ambiguity

        ambiguity = detect_ambiguity(question, schema_profile or {})
        if ambiguity:
            logger.info("Question is %s (%s); asking for clarification.", ambiguity.kind, ambiguity.term)
            outcome = _finish(
                "",
                source=ANALYSIS_SOURCE_FALLBACK,
                failed=True,
                failure={
                    "failure_type": "ambiguous_question",
                    "error_message": ambiguity.message(),
                    "code_context": "",
                    "expected_vs_actual": f"{ambiguity.kind}: {ambiguity.term}",
                },
            )
            outcome["analysis_artifacts"]["ambiguity"] = ambiguity.to_dict()
            return outcome

    # FAST PATH: schema-adaptive pattern SQL for SIMPLE questions (0 LLM).
    # Also allow high-precision percent-of-total templates on COMPLEX questions —
    # those patterns are exact and prevent ranking-instead-of-proportion regressions.
    if approach == "sql" and retry_count == 0:
        cols = (schema_profile or {}).get("columns") or []
        if isinstance(cols, list) and cols:
            hit = try_simple_deterministic_sql(question, table_name, cols)
            if hit and hit.sql:
                allow_pattern = (
                    complexity == "SIMPLE"
                    or (hit.pattern_id or "").startswith("PERCENT_OF_TOTAL")
                )
                if allow_pattern:
                    ok_pat, miss_pat = check_requirement_coverage(question, hit.sql, columns=None)
                    schema_for_pat = dict(schema_profile or {})
                    if table_name and not schema_for_pat.get("dataset_id"):
                        schema_for_pat["dataset_id"] = table_name
                    from backend.services.sql.sql_quality_validator import validate_sql as _vs

                    _v = _vs(hit.sql, schema_for_pat, question)
                    schema_ok_pat = bool(_v.get("is_valid"))
                    schema_diag_pat = _v.get("diagnostics") or ""
                    if ok_pat and schema_ok_pat:
                        logger.info(
                            "Fast-path pattern SQL (%s, conf=%.2f) for %s question.",
                            hit.pattern_id,
                            hit.confidence,
                            complexity,
                        )
                        result = _finish(
                            hit.sql,
                            source=ANALYSIS_SOURCE_FALLBACK,
                            precheck_ok=ok_pat,
                            precheck_missing=miss_pat,
                        )
                        result["analysis_artifacts"]["sql_pattern_id"] = hit.pattern_id
                        return result
                    if not schema_ok_pat:
                        logger.warning("Pattern SQL failed schema validation: %s", schema_diag_pat)

    # Outside DEMO MODE: still try deterministic marketplace/CSV templates for SIMPLE.
    if approach == "sql" and complexity == "SIMPLE" and retry_count == 0 and not use_analytics_demo_fallback():
        fallback = resolve_analytics_fallback(question, schema_profile or {}, dataset_id)
        if fallback.sql:
            ok_fb, miss_fb = check_requirement_coverage(question, fallback.sql, columns=None)
            from backend.services.sql.sql_quality_validator import validate_sql as _vs2

            schema_for_fb = dict(schema_profile or {})
            if table_name and not schema_for_fb.get("dataset_id"):
                schema_for_fb["dataset_id"] = table_name
            _vf = _vs2(fallback.sql, schema_for_fb, question)
            if ok_fb and _vf.get("is_valid"):
                logger.info("Fast-path deterministic fallback SQL for SIMPLE question.")
                return _finish(
                    fallback.sql,
                    source=ANALYSIS_SOURCE_FALLBACK,
                    precheck_ok=ok_fb,
                    precheck_missing=miss_fb,
                )

    def _semantic_precheck(code: str):
        # Pre-check inspects generated SQL only — do not pass schema columns
        # (that would falsely mark metrics as covered merely because they exist in the dataset).
        return check_requirement_coverage(question, code, columns=None)

    def _schema_validate(code: str) -> tuple[bool, str]:
        """Validate generated SQL against the real DuckDB schema before execution."""
        from backend.services.sql.sql_quality_validator import validate_sql

        schema_for_val = dict(schema_profile or {})
        if table_name and not schema_for_val.get("dataset_id"):
            schema_for_val["dataset_id"] = table_name
        validation = validate_sql(code, schema_for_val, question)
        if not validation.get("is_valid"):
            return False, validation.get("diagnostics") or "SQL failed schema validation."
        return True, ""

    def _accept_sqlcoder(code: str, *, model: str, provider: str = "sqlcoder"):
        ok_cov, missing = _semantic_precheck(code)
        schema_ok, schema_diag = _schema_validate(code)
        if not schema_ok:
            logger.warning("SQLCoder SQL failed schema validation: %s", schema_diag)
            return None, list(missing) if missing else [schema_diag], schema_diag
        if not ok_cov:
            return None, list(missing), "semantic_incomplete"
        return _finish(
            code,
            source=ANALYSIS_SOURCE_SQLCODER,
            provider=provider,
            model=model,
            precheck_ok=True,
            precheck_missing=[],
        ), [], ""

    # PRIMARY local NL→SQL: Defog SQLCoder (schema + requirements only; no CSV dump).
    sqlcoder_attempted = False
    sqlcoder_last_sql = ""
    sqlcoder_last_error = ""

    def _run_sqlcoder_attempt() -> Optional[Dict[str, Any]]:
        nonlocal sqlcoder_attempted, sqlcoder_last_sql, sqlcoder_last_error
        from backend.services.sql.sqlcoder_service import generate_sql_with_sqlcoder

        sqlcoder_attempted = True
        sc = generate_sql_with_sqlcoder(
            question,
            schema_profile or {},
            table_name=table_name or "",
            requirement_contract=requirement_contract,
        )
        if sc.ok and sc.sql:
            sqlcoder_last_sql = sc.sql
            accepted, miss_sc, reason = _accept_sqlcoder(sc.sql, model=sc.model)
            if accepted is not None:
                logger.info(
                    "Generated SQL via local SQLCoder (%s); schema+semantic checks passed.",
                    sc.model,
                )
                return accepted
            # One local regenerate on semantic OR schema rejection.
            if reason and (miss_sc or reason != "semantic_incomplete"):
                if reason == "semantic_incomplete":
                    feedback = generation_precheck_feedback(question, miss_sc, req)
                else:
                    feedback = f"Schema/quality validation failed:\n{reason}"
                regen_contract = (
                    f"{requirement_contract}\n\nPREVIOUS SQL REJECTED:\n{sc.sql}\n"
                    f"FIX REQUIRED:\n{feedback}\n"
                    "Use ONLY columns that exist in the schema DDL."
                )
                sc2 = generate_sql_with_sqlcoder(
                    question,
                    schema_profile or {},
                    table_name=table_name or "",
                    requirement_contract=regen_contract,
                )
                if sc2.ok and sc2.sql:
                    sqlcoder_last_sql = sc2.sql
                    accepted2, _, _ = _accept_sqlcoder(sc2.sql, model=sc2.model)
                    if accepted2 is not None:
                        logger.info("SQLCoder regenerate passed schema+semantic checks.")
                        return accepted2
            sqlcoder_last_error = reason or "validation_failed"
            logger.warning(
                "SQLCoder SQL rejected (%s); falling through.",
                sqlcoder_last_error,
            )
        else:
            sqlcoder_last_error = sc.error or "empty_sql"
            logger.warning(
                "SQLCoder unavailable or empty (%s).",
                sqlcoder_last_error,
            )
        return None

    if approach == "sql":
        from backend.services.sql.sqlcoder_service import should_try_sqlcoder_first

        if should_try_sqlcoder_first():
            hit = _run_sqlcoder_attempt()
            if hit is not None:
                return hit

    # DEMO MODE: try deterministic schema-aware SQL when no generative path remains.
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
                "code_context": sqlcoder_last_sql,
                "expected_vs_actual": fallback.reason,
            },
        )

    # API LLM fallback — only when SQLCoder did not produce validated SQL (or is off).
    # Skip the round-trip when no provider key is configured.
    from backend.config import has_valid_llm_api_key

    if approach == "sql" and sqlcoder_attempted and not has_valid_llm_api_key():
        fallback = resolve_analytics_fallback(question, schema_profile or {}, dataset_id)
        if fallback.sql:
            logger.warning(
                "SQLCoder did not yield validated SQL and no API LLM key is set — "
                "using deterministic fallback."
            )
            ok_fb, miss_fb = check_requirement_coverage(question, fallback.sql, columns=None)
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
                "code_context": sqlcoder_last_sql,
                "expected_vs_actual": (
                    f"sqlcoder:{sqlcoder_last_error or 'failed'}; fallback:{fallback.reason}"
                ),
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

    if approach == "sql" and sqlcoder_attempted and sqlcoder_last_sql:
        messages.append(
            HumanMessage(
                content=(
                    "A local SQLCoder draft failed validation. Do not repeat its mistakes.\n"
                    f"Draft SQL:\n{sqlcoder_last_sql}\n"
                    f"Rejection: {sqlcoder_last_error or 'validation_failed'}"
                )
            )
        )

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

    try:
        inv = invoke_llm(messages, temperature=0.0)
        code = _strip_code_fences(inv.get("content") or "")
        provider = inv.get("provider")
        model = inv.get("model")
        source = inv.get("analysis_source") or ANALYSIS_SOURCE_LLM

        # Lightweight deterministic pre-check (SQL only; do not execute)
        if approach == "sql" and code:
            ok_cov, missing = _semantic_precheck(code)
            schema_ok, schema_diag = _schema_validate(code)
            if not ok_cov or not schema_ok:
                logger.warning(
                    "API SQL pre-check failed (semantic_ok=%s schema_ok=%s). Regenerating once.",
                    ok_cov,
                    schema_ok,
                )
                if not ok_cov:
                    feedback = generation_precheck_feedback(question, missing, req)
                else:
                    feedback = f"Schema/quality validation failed:\n{schema_diag}"
                regen_messages = list(messages) + [
                    HumanMessage(
                        content=(
                            f"{feedback}\n\n"
                            f"Previous incomplete/invalid SQL:\n{code}\n\n"
                            "Output ONLY corrected raw SQL using real schema columns."
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
                schema_ok, schema_diag = _schema_validate(code)
                if not ok_cov or not schema_ok:
                    # Optional: local SQLCoder rescue when API-first mode is configured
                    from backend.services.sql.sqlcoder_service import should_try_sqlcoder_as_fallback

                    if should_try_sqlcoder_as_fallback() and not sqlcoder_attempted:
                        rescue = _run_sqlcoder_attempt()
                        if rescue is not None:
                            return rescue

                    feedback = (
                        generation_precheck_feedback(question, missing, req)
                        if not ok_cov
                        else schema_diag
                    )
                    logger.warning(
                        "SQL still fails pre-check after regenerate. semantic_missing=%s schema=%s",
                        missing,
                        schema_diag,
                    )
                    return _finish(
                        "",
                        source=source,
                        failed=True,
                        failure={
                            "failure_type": (
                                "semantic_incomplete" if not ok_cov else "structural"
                            ),
                            "error_message": feedback,
                            "code_context": code,
                            "expected_vs_actual": (
                                "precheck_failed. "
                                f"Missing requirements: {list(missing)}. "
                                f"Schema: {schema_diag}. "
                                "Suggested Retry Target: code_generator."
                            ),
                        },
                        provider=provider,
                        model=model,
                        precheck_ok=False,
                        precheck_missing=list(missing),
                    )

            logger.info(
                "Generated SQL passed schema+semantic pre-check via %s (%s).",
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

        # Provider/auth failure → try SQLCoder (API-first mode) then deterministic
        if is_provider and approach == "sql":
            from backend.services.sql.sqlcoder_service import should_try_sqlcoder_as_fallback

            if should_try_sqlcoder_as_fallback() and not sqlcoder_attempted:
                rescue = _run_sqlcoder_attempt()
                if rescue is not None:
                    return rescue

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
