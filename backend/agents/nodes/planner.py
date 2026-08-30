import json
import logging
from typing import Dict, Any, List, Optional
from backend.agents.state import AgentState, get_effective_question
from backend.config import use_analytics_demo_fallback, invoke_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Lead Data Analyst Planner for MarketMind AI — an Agentic B2B Marketplace Intelligence Platform.
Your job is to analyze the user's natural language question, the dataset schema, and the SEMANTIC REQUIREMENTS contract, and produce a structured, step-by-step analysis plan.

The SEMANTIC REQUIREMENTS contract is AUTHORITATIVE. Every plan step set must satisfy it.

SEMANTIC PLANNING RULES:
1. DIMENSIONS: If the contract lists city/category/region/segment/product/channel, explicitly plan grouping/comparing ACROSS that dimension. Never drop it.
2. DERIVED METRICS: If profit_margin is required, explicitly plan: calculate profit margin using profit relative to sales. Raw profit is NOT equivalent to profit margin.
3. RELATIONSHIPS: Preserve any requested dimension. Category-level discount vs profitability → plan per-category metrics, not a single global correlation. Global correlation is allowed ONLY if no grouping dimension is requested.
4. COMPARISONS: For highest/lowest/versus/relatively low/mismatch/prioritize, plan comparative evidence (multiple groups + ranking/comparison). Do not plan a single-metric query.
5. RANKING INTERSECTIONS: For top-N by sales AND bottom-N by profit margin, explicitly plan: (a) calculate metrics, (b) independently rank sales, (c) independently rank profit margin, (d) intersect the two ranked sets. Do not say only "find top and bottom categories."
6. BUSINESS CONCLUSIONS: For insight/prioritization questions, plan evidence first (aggregations, comparisons). Do NOT invent scoring systems or arbitrary weights. SQL/report layers derive the narrative.
7. Execution success does not mean semantic success — the plan must enable full requirement coverage.

CRITICAL RULES:
1. PREFER SQL OVER PYTHON:
   - For all data retrieval, filtering, aggregations, groupings, averages, trends, stats, and visualization (Plotly charts), choose the "sql" approach.
   - Do NOT write Python code to filter, join, or aggregate data. DuckDB SQL is highly optimized and runs in-memory.
   - For chart generation requests, set approach="sql" and expected_output_type="chart". The system will execute the SQL query first and then automatically run a dedicated Python script to plot the resulting data.
   - CRITICAL: If the question asks for a relationship/correlation "across categories" (or segments/regions/cities) involving discount, sales, and/or profit margin, you MUST use approach="sql" with GROUP BY that dimension. Never plan a single global correlation that drops the dimension.
2. CONSTRAIN EXECUTION:
   - If the schema is MULTI-TABLE (marketplace), plan JOINs across the listed tables using the provided relationships. Do NOT invent a single table named "{table_name}" when multiple tables exist.
   - If the schema is a single table, all SQL queries will run against the active table name: "{table_name}"
   - Keep the steps clear and minimal, but complete against the SEMANTIC REQUIREMENTS contract.
3. MARKETPLACE DOMAIN HINTS (when multi-table):
   - GMV / order value → use orders.amount (optionally join buyers/suppliers/products/categories).
   - Lead conversion → compare leads (e.g. status='won') to leads volume, often joined to products/categories.
   - Supplier response time → suppliers.response_time_hours.
   - Demand → leads.quantity or lead counts by product/category.
4. DATE & TIMESTAMP HANDLING IN DUCKDB:
   - Carefully inspect column types and sample values in the schema context.
   - If a VARCHAR column contains dates or timestamps (e.g., "2/24/2003 0:00"), plan to parse it using `strptime(column_name, 'format_string')` inside the SQL query before applying any date operators (like `date_trunc` or `strftime`).
   - Determine the correct `format_string` based on the provided sample values (e.g. '%m/%d/%Y %H:%M' for '2/24/2003 0:00', or '%Y-%m-%d' for '2003-02-24').
   - For marketplace orders.order_date (YYYY-MM-DD) and leads.created_at, cast/parse appropriately before date_trunc.

You must return a JSON object with the following fields:
{{
  "steps": ["Step 1 explanation...", "Step 2..."],
  "approach": "sql",
  "expected_output_type": "dataframe" or "scalar" or "chart"
}}

Ensure your response is valid JSON only. Do not wrap in markdown blocks other than standard json output.
"""


def _parse_plan_json(content: str) -> Dict[str, Any]:
    content = (content or "").strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    return json.loads(content, strict=False)


def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Analyzes the schema and question, and returns an execution plan.
    Injects the canonical semantic requirement contract and self-checks plan steps.
    """
    import time
    node_name = "planner"
    start_time = time.time()
    retry_count = state.get("retry_count", 0)

    logger.info(f"Node started: {node_name} (Retry count: {retry_count})")

    question = get_effective_question(state)
    schema_profile = state.get("schema_profile")
    table_name = state.get("duckdb_table") or state.get("dataset_id")
    retry_history = state.get("retry_history", [])

    status = "success"
    error_msg = None
    updates: Dict[str, Any] = {}

    from backend.marketplace.demo_data import format_schema_context_for_llm
    from backend.services.requirement_coverage import (
        build_requirement_aware_plan_steps,
        check_plan_requirement_coverage,
        extract_question_requirements,
        format_semantic_requirement_contract,
        plan_precheck_feedback,
        schema_column_names,
    )

    req = extract_question_requirements(question)
    schema_cols = schema_column_names(schema_profile or {})
    requirement_contract = format_semantic_requirement_contract(
        req, schema_columns=schema_cols
    )
    schema_context = format_schema_context_for_llm(
        schema_profile or {}, fallback_table=table_name
    )

    def _attach_artifacts(
        base: Optional[Dict[str, Any]] = None,
        *,
        precheck_ok: Optional[bool] = None,
        precheck_missing: Optional[List[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        artifacts = dict(base or state.get("analysis_artifacts") or {})
        artifacts["question_requirements"] = req.to_dict()
        artifacts["requirement_contract"] = requirement_contract
        if precheck_ok is not None:
            artifacts["planning_precheck_ok"] = precheck_ok
        if precheck_missing is not None:
            artifacts["planning_precheck_missing"] = list(precheck_missing)
        if provider:
            artifacts["planning_provider"] = provider
        if model:
            artifacts["planning_model"] = model
        return artifacts

    def _demo_sql_plan() -> Dict[str, Any]:
        # Requirement-aware steps when practical; execution path unchanged (still SQL).
        steps = build_requirement_aware_plan_steps(req)
        # Keep a generic inspect step first for demo clarity
        if not any("schema" in s.lower() or "inspect" in s.lower() for s in steps):
            steps = ["Inspect available DuckDB schema and columns"] + steps
        return {
            "steps": steps,
            "approach": "sql",
            "expected_output_type": "dataframe",
            "planning_source": "deterministic_fallback",
        }

    def _self_check(plan_data: Dict[str, Any]):
        steps = plan_data.get("steps") or []
        if isinstance(steps, str):
            steps = [steps]
        return check_plan_requirement_coverage(question, steps, req)

    def _ensure_plan_semantically_complete(
        plan_data: Dict[str, Any],
        *,
        allow_repair: bool = True,
    ) -> tuple[Dict[str, Any], bool, List[str], Optional[Dict[str, Any]]]:
        """
        Returns (plan, ok, missing, failure_or_none).
        On hard failure after optional repair: failure uses semantic_incomplete.
        """
        ok, missing = _self_check(plan_data)
        if ok:
            return plan_data, True, [], None

        if not allow_repair:
            feedback = plan_precheck_feedback(question, missing, req)
            return (
                plan_data,
                False,
                missing,
                {
                    "failure_type": "semantic_incomplete",
                    "error_message": feedback,
                    "code_context": json.dumps(plan_data.get("steps") or []),
                    "expected_vs_actual": (
                        "semantic_incomplete. "
                        f"Plan missing: {missing}. "
                        "Suggested Retry Target: planner. "
                        "Suggested Retry Strategy: Satisfy the SEMANTIC REQUIREMENTS contract."
                    ),
                },
            )

        # Last-resort deterministic repair so code_generator receives a usable plan
        repaired = {
            "steps": build_requirement_aware_plan_steps(req),
            "approach": plan_data.get("approach") or "sql",
            "expected_output_type": plan_data.get("expected_output_type") or "dataframe",
            "planning_source": plan_data.get("planning_source") or "requirement_repair",
        }
        ok2, missing2 = _self_check(repaired)
        if ok2:
            logger.warning(
                "Planner self-check failed; applied requirement-aware plan repair. Was missing: %s",
                missing,
            )
            return repaired, True, [], None

        feedback = plan_precheck_feedback(question, missing2 or missing, req)
        return (
            repaired,
            False,
            missing2 or missing,
            {
                "failure_type": "semantic_incomplete",
                "error_message": feedback,
                "code_context": json.dumps(repaired.get("steps") or []),
                "expected_vs_actual": (
                    "semantic_incomplete. "
                    f"Plan missing: {missing2 or missing}."
                ),
            },
        )

    # DEMO MODE: skip planner LLM so analytics can run without a valid API key.
    if use_analytics_demo_fallback():
        logger.warning(
            "Analytics DEMO MODE — using deterministic SQL plan (skipping planner LLM)."
        )
        plan_data = _demo_sql_plan()
        plan_data, ok_pc, miss_pc, failure = _ensure_plan_semantically_complete(
            plan_data, allow_repair=True
        )
        updates = {
            "plan": plan_data,
            "expected_output_type": plan_data.get("expected_output_type"),
            "generated_code": None,
            "execution_success": False,
            "failure_summary": failure,
            "analysis_artifacts": _attach_artifacts(
                precheck_ok=ok_pc, precheck_missing=miss_pc
            ),
        }
    else:
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT.format(table_name=table_name)),
            HumanMessage(
                content=(
                    f"Dataset Schema:\n{schema_context}\n\n"
                    f"User Question:\n{question}\n\n"
                    f"{requirement_contract}\n\n"
                    "Produce a plan that satisfies BOTH the user question and the "
                    "SEMANTIC REQUIREMENTS contract."
                )
            ),
        ]

        # If we are retrying due to semantic failure
        if retry_history:
            semantic_failures = [
                f
                for f in retry_history
                if f["failure_type"] in ("semantic", "semantic_incomplete")
            ]
            if semantic_failures:
                logger.info("Injecting semantic failure history into Planner context.")
                failures_context = "\n---\n".join([
                    f"Attempt {i+1} Failure:\n"
                    f"- Failure Type: {f['failure_type']}\n"
                    f"- Error Message: {f['error_message']}\n"
                    f"- Code/SQL Executed: {f['code_context']}\n"
                    f"- Mismatch details: {f['expected_vs_actual']}"
                    for i, f in enumerate(semantic_failures)
                ])
                messages.append(HumanMessage(
                    content=(
                        "ATTENTION: Previous attempts failed validation due to semantic "
                        "mismatch. Here is the compressed history of failures:\n"
                        f"{failures_context}\n\n"
                        "Please adapt your plan to correct these issues against the "
                        "SEMANTIC REQUIREMENTS contract."
                    )
                ))

        try:
            inv = invoke_llm(messages, temperature=0.1)
            plan_data = _parse_plan_json(inv.get("content") or "")
            logger.info(
                "Generated plan via %s. Approach: %s, Expected Output: %s",
                inv.get("provider"),
                plan_data.get("approach"),
                plan_data.get("expected_output_type"),
            )

            ok_pc, miss_pc = _self_check(plan_data)
            if not ok_pc:
                logger.warning(
                    "Planner self-check failed (semantic_incomplete). Missing=%s. Regenerating once.",
                    miss_pc,
                )
                feedback = plan_precheck_feedback(question, miss_pc, req)
                regen_messages = list(messages) + [
                    HumanMessage(
                        content=(
                            f"{feedback}\n\n"
                            f"Previous incomplete plan steps:\n"
                            f"{json.dumps(plan_data.get('steps') or [], indent=2)}\n\n"
                            "Return corrected JSON plan only."
                        )
                    )
                ]
                try:
                    inv2 = invoke_llm(regen_messages, temperature=0.1)
                    plan_data = _parse_plan_json(inv2.get("content") or "")
                    inv = inv2
                except Exception as regen_err:
                    logger.warning("Planner regenerate call failed: %s", regen_err)

            plan_data, ok_pc, miss_pc, failure = _ensure_plan_semantically_complete(
                plan_data, allow_repair=True
            )

            updates = {
                "plan": plan_data,
                "expected_output_type": plan_data.get("expected_output_type"),
                "generated_code": None,
                "execution_success": False,
                "failure_summary": failure,
                "analysis_artifacts": _attach_artifacts(
                    precheck_ok=ok_pc,
                    precheck_missing=miss_pc,
                    provider=inv.get("provider"),
                    model=inv.get("model"),
                ),
            }
            if failure:
                status = "failed"
                error_msg = failure.get("error_message")
        except Exception as e:
            logger.error(f"Error in Planner Node: {e}")
            status = "failed"
            error_msg = str(e)
            fallback_plan = {
                "steps": ["Retrieve data using SELECT *"],
                "approach": "sql",
                "expected_output_type": "dataframe",
            }
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

            # Provider/auth failure → continue with SQL plan so code_generator
            # can apply the deterministic analytics fallback for any dataset.
            if is_provider:
                logger.warning(
                    "Planner LLM unavailable — continuing with deterministic SQL plan."
                )
                status = "success"
                error_msg = None
                plan_data = _demo_sql_plan()
                plan_data, ok_pc, miss_pc, failure = _ensure_plan_semantically_complete(
                    plan_data, allow_repair=True
                )
                updates = {
                    "plan": plan_data,
                    "expected_output_type": plan_data.get("expected_output_type"),
                    "generated_code": None,
                    "execution_success": False,
                    "failure_summary": failure,
                    "analysis_artifacts": _attach_artifacts(
                        precheck_ok=ok_pc, precheck_missing=miss_pc
                    ),
                }
            else:
                # Non-provider error: still try requirement-aware repair for continuity
                plan_data, ok_pc, miss_pc, failure = _ensure_plan_semantically_complete(
                    fallback_plan, allow_repair=True
                )
                updates = {
                    "plan": plan_data,
                    "expected_output_type": plan_data.get("expected_output_type", "dataframe"),
                    "generated_code": None,
                    "execution_success": False,
                    "failure_summary": failure,
                    "analysis_artifacts": _attach_artifacts(
                        precheck_ok=ok_pc, precheck_missing=miss_pc
                    ),
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
        "error_message": error_msg,
    }

    execution_metadata = list(state.get("execution_metadata") or [])
    execution_metadata.append(node_metadata)
    updates["execution_metadata"] = execution_metadata

    return updates
