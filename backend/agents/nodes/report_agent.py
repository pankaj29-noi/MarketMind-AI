"""
report_agent.py — Generates a fully structured JSON report validated against
the AnalysisResponse Pydantic schema.

The LLM is asked to produce ONLY a JSON object matching LLMReportOutput.
The node then assembles the full AnalysisResponse by merging LLM output
with execution context (tables, charts, SQL, dataset info).

On Pydantic ValidationError the node retries ONCE with the error injected
into the prompt before falling back to a graceful failure report.
"""

import json
import logging
from typing import Any, Dict

from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents.state import AgentState, get_effective_question
from backend.agents.schemas import (
    AnalysisResponse,
    ChartSpec,
    ChartType,
    DebugInfo,
    ExecutiveSummary,
    FailureResponse,
    Insight,
    LLMReportOutput,
    Recommendation,
    ReportSection,
    TableResult,
)
from backend.config import get_llm
from backend.services.pdf_generator import generate_pdf_report
from backend.agents.sandbox import prepare_scratch_directory

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

from backend.services.reporting.report_mode import ReportMode, determine_report_mode
from backend.services.reporting.fact_generator import generate_facts
from backend.services.reporting.recommendation_engine import generate_recommendations

SEMANTIC_CONTRACTS = {
    "GROUPED_AGGREGATION": """\
FAMILY-SPECIFIC RULES: Grouped Aggregation
1. Use aggregation terminology ONLY.
2. Allowed terms: highest, lowest, ranks first, leads, contributes the most, accounts for, total, average, difference, gap, concentration, share (only if share was explicitly calculated).
3. Example: "Classic Cars records the highest total sales at $3.92M."
4. Do NOT use correlation terms (e.g., "correlation", "linear relationship"), statistical significance terms, or causality terms (e.g., "drives", "determines", "causal impact") unless these operations were separately computed and present in analysis_artifacts.
""",
    "RANKING": """\
FAMILY-SPECIFIC RULES: Ranking
1. Use ranking/ordering terminology ONLY.
2. Allowed terms: highest, lowest, ranks first, leads, contributes the most, accounts for, total, average, difference, gap, concentration, share (only if share was explicitly calculated).
3. Example: "Euro Shopping Channel leads the ranked customers by total sales."
4. Do NOT use correlation terms (e.g., "correlation", "linear relationship"), statistical significance terms, or causality terms (e.g., "drives", "determines", "causal impact") unless these operations were separately computed and present in analysis_artifacts.
""",
    "CONTRIBUTION": """\
FAMILY-SPECIFIC RULES: Percentage Contribution / Share
1. Use share/contribution terminology ONLY.
2. Allowed terms: contributes X%, accounts for X% of total, largest share, smallest share, combined share, percentage-point gap, concentration.
3. Example: "Medium deals account for 60.7% of total sales, the largest share among the three deal-size categories."
4. Do NOT call categorical share differences or groupings: positive correlation, negative correlation, or linear correlation.
5. Do NOT use correlation terms (e.g., "correlation", "linear relationship"), statistical significance/causality terms, or confidence levels.
""",
    "CORRELATION": """\
FAMILY-SPECIFIC RULES: Correlation Analysis
1. Use correlation terminology ONLY.
2. Describe coefficient magnitude (|r|) strictly according to these thresholds:
   - |r| < 0.20: "very weak linear correlation"
   - 0.20 <= |r| < 0.40: "weak linear correlation"
   - 0.40 <= |r| < 0.70: "moderate linear correlation"
   - 0.70 <= |r| < 0.90: "strong linear correlation"
   - |r| >= 0.90: "very strong linear correlation"
3. Always preserve the correlation direction (positive or negative).
4. Example: "Quantity ordered and sales show a moderate positive linear correlation (r = 0.5514)."
5. Do NOT translate correlation coefficient magnitude into "evidence level", "confidence level", "statistical significance", "reliability", or "generalizability".
6. Do NOT infer causality, feature importance, business impact, or use terms like "determines" or "drives".
7. Allowed relation terms: "associated with", "shows a linear relationship with", "correlation between".
""",
    "TREND": """\
FAMILY-SPECIFIC RULES: Time Series / Trend Analysis
1. Use temporal language ONLY.
2. Allowed terms: increased over the observed period, decreased, fluctuated, peaked in [period], reached its lowest value in [period], month-over-month variation, upward/downward direction, moving average, temporal pattern.
3. State the grain and aggregation accurately if known: e.g., "Monthly total sales, aggregated using SUM, show..."
4. Do NOT claim seasonality (unless seasonality was tested/computed), forecasting, statistical significance, causal explanation, or future growth.
5. Do NOT invent business or data-quality reasons for peaks, declines, or variations.
""",
    "OUTLIER": """\
FAMILY-SPECIFIC RULES: Outlier Analysis
1. Use outlier terminology ONLY.
2. Allowed terms: outliers detected, IQR-based outlier detection, observations outside calculated bounds, upper/lower bound, number or proportion of flagged observations.
3. Do NOT call outliers anomalies caused by fraud, errors, or suspicious transactions unless the computed facts/artifacts explicitly establish those causes.
""",
    "DISTRIBUTION": """\
FAMILY-SPECIFIC RULES: Distribution / Spread
1. Use distribution terminology ONLY.
2. Allowed terms: mean, median, skewness, kurtosis, spread, variation, shape of distribution.
3. Do NOT infer causality, business drivers, or correlation.
""",
    "DESCRIPTIVE": """\
FAMILY-SPECIFIC RULES: Descriptive Statistics
1. Use descriptive statistics terminology ONLY.
2. Allowed terms: mean, median, standard deviation, minimum, maximum, range, skewness (only if computed), variability.
3. Do NOT infer causality, correlation, trends, or business drivers.
""",
    "CROSS_TAB": """\
FAMILY-SPECIFIC RULES: Cross-Tab / Multi-Dimensional Grouping
1. Use comparison terminology ONLY.
2. Allowed terms: comparison across dimensions, highest combination, lowest combination, concentration across groups, differences between category combinations.
3. Do NOT call dimensional differences or multi-dimensional groupings "correlations" or "trends" unless those operations were separately computed.
""",
    "UNKNOWN": """\
FAMILY-SPECIFIC RULES: General Analysis
1. State only the facts directly computed and present in query_result or analysis_artifacts.
2. Do NOT use specialized analytical terms like correlation, trend, outlier, or statistical significance unless those operations are explicitly present in the data.
"""
}

def classify_result_family_strict(
    question: str,
    last_worker_result: dict,
    query_result: dict,
    analysis_artifacts: dict,
    state: dict
) -> str:
    """
    Deterministic result family classifier.
    Priority of evidence:
    1. structured analysis_artifacts
    2. structured result metadata and result schema
    3. query-result column names and result shape
    4. resolved capability / execution context in state
    5. raw or resolved user question as a final hint
    """
    # 1. Structured analysis_artifacts
    has_correlation_artifact = "correlation_matrix" in analysis_artifacts
    has_trend_artifact = "trend_analysis" in analysis_artifacts or "trend" in analysis_artifacts
    has_outlier_artifact = "outliers" in analysis_artifacts or "outlier_analysis" in analysis_artifacts
    has_distribution_artifact = "distributions" in analysis_artifacts or "distribution" in analysis_artifacts
    has_descriptive_artifact = "descriptive_stats" in analysis_artifacts or "descriptive" in analysis_artifacts

    # Check query_result schema & column names
    qr_cols = query_result.get("columns") or []
    dtypes = query_result.get("dtypes") or {}
    roles = query_result.get("analytical_roles") or {}
    rows = query_result.get("rows") or []
    
    # Infer roles if missing
    if qr_cols and not roles:
        from backend.utils.analytical_roles import infer_analytical_roles
        roles = infer_analytical_roles(qr_cols, dtypes)

    num_categorical = sum(1 for c in qr_cols if roles.get(c) == "categorical")
    num_measure = sum(1 for c in qr_cols if roles.get(c) in ("measure", "derived_measure"))
    num_temporal = sum(1 for c in qr_cols if roles.get(c) == "temporal")
    num_identifier = sum(1 for c in qr_cols if roles.get(c) == "identifier")

    # Check column name keywords for CONTRIBUTION
    has_pct_col = False
    for col in qr_cols:
        c_lower = col.lower()
        if any(pk in c_lower for pk in ["pct", "percent", "percentage", "share", "contribution", "proportion"]):
            has_pct_col = True
            break

    # Check state execution context (worker, approach, plan, etc.)
    last_worker = last_worker_result.get("worker_name", "")
    analysis_type = last_worker_result.get("analysis_type", "")
    
    # Check question hints
    q_lower = question.lower()
    
    # Precedence implementation:
    # CORRELATION
    if has_correlation_artifact or analysis_type == "correlation":
        return "CORRELATION"
    if qr_cols and len(qr_cols) >= 2 and all(roles.get(c) == "measure" for c in qr_cols):
        if "Variable" in qr_cols or len(rows) == len(qr_cols):
            is_corr_shape = True
            for r in rows:
                if isinstance(r, dict):
                    vals = [v for k, v in r.items() if k != "Variable" and isinstance(v, (int, float))]
                elif isinstance(r, (list, tuple)):
                    vals = [v for v in r if isinstance(v, (int, float))]
                else:
                    vals = []
                if vals and not all(-1.01 <= v <= 1.01 for v in vals):
                    is_corr_shape = False
                    break
            if is_corr_shape and ("correlation" in q_lower or "pearson" in q_lower):
                return "CORRELATION"

    # TREND
    if has_trend_artifact or analysis_type == "trend":
        return "TREND"
    if num_temporal >= 1 and num_measure >= 1:
        if any(tk in q_lower for tk in ["trend", "over time", "monthly", "yearly", "quarterly", "daily", "by year", "by month", "timeline", "history", "forecast"]):
            return "TREND"

    # OUTLIER
    if has_outlier_artifact or analysis_type == "outlier":
        return "OUTLIER"

    # CONTRIBUTION
    if has_pct_col:
        return "CONTRIBUTION"
    if any(ck in q_lower for ck in ["percentage contribution", "percent contribution", "contribution of total", "revenue share", "sales share", "market share", "proportion"]):
        return "CONTRIBUTION"

    # RANKING
    code_lower = (state.get("generated_code") or "").lower()
    has_limit = "limit " in code_lower
    has_orderby = "order by " in code_lower
    if (has_limit and has_orderby) or (any(rk in q_lower for rk in ["top ", "bottom ", "highest", "lowest", "best ", "worst ", "rank", "first ", "last "])):
        if (num_categorical >= 1 or num_temporal >= 1 or num_identifier >= 1) and num_measure >= 1:
            return "RANKING"

    # CROSS_TAB
    if (num_categorical + num_temporal) >= 2 and num_measure >= 1:
        return "CROSS_TAB"

    # DISTRIBUTION
    if has_distribution_artifact or analysis_type == "distribution":
        return "DISTRIBUTION"

    # DESCRIPTIVE
    if has_descriptive_artifact or analysis_type == "descriptive":
        return "DESCRIPTIVE"

    # GROUPED_AGGREGATION
    if (num_categorical >= 1 or num_temporal >= 1 or num_identifier >= 1) and num_measure >= 1:
        return "GROUPED_AGGREGATION"

    # Final disambiguation hints
    if "correlation" in q_lower or "pearson" in q_lower:
        return "CORRELATION"
    if "trend" in q_lower or "over time" in q_lower:
        return "TREND"
    if "outlier" in q_lower or "anomaly" in q_lower:
        return "OUTLIER"
    if "contribution" in q_lower or "share" in q_lower or "percent" in q_lower:
        return "CONTRIBUTION"
    if "distribution" in q_lower or "spread" in q_lower:
        return "DISTRIBUTION"
    if "descriptive" in q_lower or "summary stats" in q_lower:
        return "DESCRIPTIVE"

    return "GROUPED_AGGREGATION" if num_measure >= 1 else "UNKNOWN"

def _get_dynamic_system_prompt(mode: ReportMode, result_family: str) -> str:
    # Scale requirements based on mode
    if mode == ReportMode.QUICK:
        insight_req = "Write 0 insights. Do not include an insights array."
        summary_req = "The 'summary' must be a single concise sentence."
    elif mode == ReportMode.STANDARD:
        insight_req = "Write exactly 1-2 insights."
        summary_req = "The 'summary' must be 1 short paragraph."
    else: # ANALYTICAL or RESEARCH
        insight_req = "Write 3-4 detailed insights."
        summary_req = "The 'summary' must be 2-3 paragraphs of professional business narrative."
        
    family_rules = SEMANTIC_CONTRACTS.get(result_family, SEMANTIC_CONTRACTS["UNKNOWN"])
    
    return f"""\
You are the Lead Report Analyst for MarketMind AI — an Agentic B2B Marketplace Intelligence Platform.
Your ONLY job is to produce a single, valid JSON object that matches the schema below.

OUTPUT RULES:
1. Respond with RAW JSON only — no markdown, no ```json fences, no explanation text.
2. Every field listed as required MUST be present and non-empty.
3. The "headline" must directly answer the user's question in one sentence.
4. {summary_req}
5. {insight_req}
6. Do NOT invent recommendations. Leave the recommendations array empty (the system handles them).
7. Do NOT include SQL, table data, or chart specifications.
8. GROUNDING (critical):
   - The executed analysis result is authoritative.
   - Do not claim missing data if returned columns contain the requested evidence.
   - Do not invent metrics, rankings, relationships, percentages, or conclusions.
   - Distinguish association from causation (prefer "associated with").
   - Distinguish lowest rank from a meaningful practical difference (check value spread).
   - Do not require statistical significance / ANOVA unless the user asked for it.
   - Business insights must show evidence first, then a cautious interpretation.
   - Confidence must reflect semantic coverage and evidence quality — not execution success alone.
9. INSIGHT QUALITY RULES:
   - Key Insights must add value beyond repeating the Executive Summary.
   - Start from an actual computed fact.
   - Name the correct analytical relationship.
   - Include a concrete number when useful.
   - Compare values only when the compared values exist.
   - Do not invent business explanations.
   - Do not invent recommendations (leave recommendations empty).
   - Do not invent data-quality problems.
   - Do not infer causality.
   - Do not use generic filler (e.g., "further analysis is required", "complex and multifaceted", "may not be generalizable", "improved data collection is needed") unless computed facts explicitly support the statement.
   - Prefer concise analytical findings over verbose generic commentary.
10. {family_rules}

REQUIRED JSON SCHEMA:
{{
  "title": "<4-8 word descriptive report title>",
  "executive_summary": {{
    "headline": "<one sentence that directly answers the question>",
    "summary": "<narrative complying with the summary rule, grounding rules, and result family rules>",
    "confidence": "High" | "Medium" | "Low"
  }},
  "insights": [
    {{ "title": "<4-6 word title>", "body": "<insight paragraph presenting the analytical findings concisely without generic filler or misusing evidence levels>" }}
  ],
  "recommendations": [],
  "llm_reasoning": "<optional: brief explanation of your analytical approach>"
}}
"""

REPORT_FAILURE_SYSTEM_PROMPT = """\
You are the Lead Failure Diagnostics Analyst for an Autonomous Data Analyst Agent.
The system attempted to answer the user's question but failed within the retry budget.

OUTPUT RULES:
1. Respond with RAW JSON only — no markdown, no fences, no explanation text.
2. Produce a JSON object matching exactly this schema:
{
  "title": "<descriptive failure title>",
  "executive_summary": {
    "headline": "<one sentence describing what was attempted and why it failed>",
    "summary": "<2-3 paragraphs: what was tried, root cause, suggestions to fix>",
    "confidence": "Low"
  },
  "insights": [
    { "title": "<failure insight title>", "body": "<what the agent found before failing>" }
  ],
  "recommendations": [
    { "title": "<action the user should take>", "body": "<how to reformulate the question or fix the data>" }
  ],
  "llm_reasoning": null
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Strip accidental markdown fences that some models still emit."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Drop first line (```json or ```) and last line (```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


def _call_llm_for_report(
    system_prompt: str,
    user_content: str,
    validation_error: str | None = None,
) -> LLMReportOutput:
    """
    Calls the LLM, parses JSON, validates against LLMReportOutput.
    Raises ValueError or ValidationError on failure.
    """
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    if validation_error:
        messages.append(HumanMessage(
            content=(
                f"Your previous response failed Pydantic validation with this error:\n"
                f"{validation_error}\n\n"
                "Please fix the JSON and return ONLY a valid JSON object."
            )
        ))

    from backend.config import invoke_llm

    inv = invoke_llm(messages, temperature=0.3)
    raw = _clean_json(inv.get("content") or "")
    data = json.loads(raw, strict=False)
    return LLMReportOutput.model_validate(data)


def _build_user_prompt(
    question: str,
    code: str,
    facts: dict,
    plan_steps: str | None,
    result_family: str,
    schema_columns: list | None = None,
    *,
    result_columns: list | None = None,
    result_preview: list | None = None,
    requirement_contract: str | None = None,
    coverage_ok: bool | None = None,
    coverage_missing: list | None = None,
    analysis_source: str | None = None,
) -> str:
    result_cols = ", ".join(map(str, result_columns or [])) or "(none)"
    schema_cols = ", ".join(schema_columns or []) or "(see schema in facts)"
    preview = json.dumps(result_preview or [], indent=2, default=str)
    cov = (
        "PASS"
        if coverage_ok is True
        else ("FAIL" if coverage_ok is False else "unknown")
    )
    missing = ", ".join(coverage_missing or []) or "(none)"
    contract = requirement_contract or "(not provided)"
    return (
        f"User Question: {question}\n\n"
        f"Classified Result Family: {result_family}\n\n"
        f"Analysis source: {analysis_source or 'unknown'}\n"
        f"Semantic coverage: {cov}\n"
        f"Coverage gaps: {missing}\n\n"
        f"SEMANTIC REQUIREMENTS (authoritative intent):\n{contract}\n\n"
        f"EXECUTED RESULT COLUMNS (primary evidence — do NOT claim these are missing):\n"
        f"{result_cols}\n\n"
        f"EXECUTED RESULT PREVIEW (authoritative):\n{preview}\n\n"
        f"Dataset schema columns (context only):\n{schema_cols}\n\n"
        f"Execution Plan:\n{plan_steps or 'N/A'}\n\n"
        f"Executed SQL/Code:\n{code or 'N/A'}\n\n"
        f"Computed Facts:\n{json.dumps(facts, indent=2, default=str)}\n\n"
        "CRITICAL: Answer from the EXECUTED RESULT. "
        "If a required dimension/metric appears in EXECUTED RESULT COLUMNS, "
        "never say that category/city/segment/discount analysis is unavailable. "
        "Prefer association over causation. "
        "If margin values are nearly identical, say the practical difference is negligible "
        "even if ranks differ — do not require statistical tests unless asked."
    )


def _build_failure_prompt(question: str, code: str, failures: list) -> str:
    failures_desc = "\n".join(
        f"- Attempt {i + 1} ({f['failure_type']}): {f['error_message']}\n"
        f"  Context: {f.get('expected_vs_actual', '')}"
        for i, f in enumerate(failures)
    )
    return (
        f"User Question: {question}\n\n"
        f"Last Attempted Code:\n{code or 'N/A'}\n\n"
        f"Failure History:\n{failures_desc}"
    )


def _plan_steps_str(plan: dict) -> str | None:
    steps = plan.get("steps", [])
    if not steps:
        return None
    return "\n".join(f"- {s}" for s in steps)


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

def report_agent_node(state: AgentState) -> Dict[str, Any]:
    """
    Generates the final AnalysisResponse-shaped dict stored in state.final_report.

    Success path:
      1. Build user prompt from question + SQL + data preview.
      2. Call LLM → validate LLMReportOutput.
      3. On ValidationError: retry ONCE with error context.
      4. Merge with tables (from query_result), charts (from output_summary),
         SQL (from generated_code), plan steps → AnalysisResponse.
      5. Serialize to dict → store as final_report.

    Failure path (graceful_failure=True):
      Same as above but uses REPORT_FAILURE_SYSTEM_PROMPT and omits tables/charts.
    """
    import time
    node_name = "report_agent"
    start_time = time.time()
    retry_count = state.get("retry_count", 0)
    
    logger.info(f"Node started: {node_name} (Retry count: {retry_count})")
    session_id     = state.get("session_id", "")
    question       = get_effective_question(state)
    code           = state.get("generated_code") or ""
    output_summary = state.get("output_summary") or {}
    query_result   = state.get("query_result") or {}
    plan           = state.get("plan") or {}
    retry_history  = state.get("retry_history", [])
    graceful_failure = state.get("graceful_failure", False)
    schema_profile = state.get("schema_profile") or {}

    logger.info(f"Report Agent Node — graceful_failure={graceful_failure}")

    # ── Scratch dir for PDF ──────────────────────────────────────────────────
    dataset_id = state.get("dataset_id", "unknown")
    try:
        scratch_dir = prepare_scratch_directory(session_id, dataset_id)
    except Exception as e:
        logger.warning(f"Could not prepare scratch dir: {e}")
        import os
        scratch_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "scratch", session_id)
        )
        os.makedirs(scratch_dir, exist_ok=True)

    # ── Dataset context ──────────────────────────────────────────────────────
    columns_list = schema_profile.get("columns", [])
    dataset_info = {
        "name":    dataset_id,
        "rows":    schema_profile.get("row_count", 0),
        "columns": len(columns_list),
    }

    # ── Plan steps string ────────────────────────────────────────────────────
    plan_steps = _plan_steps_str(plan)

    # ═════════════════════════════════════════════════════════════════════════
    # GRACEFUL FAILURE PATH
    # ═════════════════════════════════════════════════════════════════════════
    last_worker_result = state.get("last_worker_result") or {}
    is_failure = graceful_failure or last_worker_result.get("status") == "failed"
    
    # Treat visualization failures/skips as non-critical: override is_failure to False
    if is_failure and last_worker_result.get("worker_name") == "VISUALIZATION":
        logger.info("Non-critical visualization failure detected. Overriding workflow status to success.")
        is_failure = False
    
    if is_failure:
        from backend.services.reporting.failure_formatter import generate_failure_report
        final_report = generate_failure_report(state)
        
        # PDF
        pdf_path: str | None = None
        try:
            pdf_path = generate_pdf_report(
                session_id=session_id,
                question=question,
                report_data={
                    "executive_summary": final_report["report"]["executive_summary"],
                    "insights": final_report["report"]["insights"],
                    "recommendations": final_report["report"]["recommendations"],
                },
                tables=[],
                scratch_dir=scratch_dir,
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            
        final_report["pdf_path"] = pdf_path

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        logger.info(f"Node completed: {node_name} (deterministic failure path) in {duration_ms:.2f}ms")
        
        node_metadata = {
            "node_name": node_name,
            "start_time": start_time,
            "end_time": end_time,
            "duration_ms": duration_ms,
            "status": "failed",
            "retry_count": retry_count,
            "error_message": "Exhausted retries or received failure status, returned deterministic failure report."
        }
        execution_metadata = list(state.get("execution_metadata") or [])
        execution_metadata.append(node_metadata)
        
        worker_result = {
            "worker_name": "REPORT",
            "status": "success",
            "confidence": 1.0,
            "summary": "Deterministic failure report generated.",
            "routing_hint": "TERMINATE",
            "duration_ms": duration_ms
        }
        
        return {
            "final_report": final_report,
            "execution_metadata": execution_metadata,
            "last_worker_result": worker_result
        }

    # SUCCESS PATH
    # ═════════════════════════════════════════════════════════════════════════
    
    # 1. Determine Report Mode
    report_mode = determine_report_mode(
        question=question,
        last_worker_result=state.get("last_worker_result") or {},
        query_result=query_result,
        analysis_artifacts=state.get("analysis_artifacts") or {}
    )
    logger.info(f"Report Agent operating in mode: {report_mode}")
    
    # 2. Compute Deterministic Facts
    facts = generate_facts(question, query_result)
    if state.get("analysis_artifacts"):
        facts["analysis_artifacts"] = state.get("analysis_artifacts")
        
    # 2b. Classify Result Family
    result_family = classify_result_family_strict(
        question=question,
        last_worker_result=state.get("last_worker_result") or {},
        query_result=query_result,
        analysis_artifacts=state.get("analysis_artifacts") or {},
        state=state
    )
    logger.info(f"Classified result family: {result_family}")
    facts["classified_result_family"] = result_family

    # 3. Compute Deterministic Recommendations
    python_recommendations = generate_recommendations(question, schema_profile)

    analysis_source = (state.get("analysis_artifacts") or {}).get("analysis_source")
    artifacts = dict(state.get("analysis_artifacts") or {})
    from backend.services.analytics_fallback import ANALYSIS_SOURCE_FALLBACK
    from backend.services.requirement_coverage import (
        check_requirement_coverage,
        confidence_from_coverage,
        extract_question_requirements,
        format_semantic_requirement_contract,
        schema_column_names,
    )
    from backend.services.reporting.report_grounding import (
        build_evidence_summary,
        check_report_grounding,
        repair_report_text_for_grounding,
        soften_causation_language,
        margin_spread_points,
    )

    result_columns = list(query_result.get("columns") or [])
    result_rows = list(query_result.get("rows") or [])
    req = extract_question_requirements(question)
    requirement_contract = (
        artifacts.get("requirement_contract")
        or format_semantic_requirement_contract(
            req, schema_columns=schema_column_names(schema_profile)
        )
    )
    cov_ok, cov_missing = check_requirement_coverage(
        question,
        code or "",
        result_columns,
        row_count=query_result.get("row_count") or len(result_rows),
    )
    artifacts["question_requirements"] = req.to_dict()
    artifacts["requirement_contract"] = requirement_contract
    artifacts["coverage_ok"] = cov_ok
    artifacts["coverage_missing"] = list(cov_missing)

    # Deterministic narrative only when analysis itself was deterministic — never
    # because DEMO_MODE is on while an LLM provider is available.
    use_deterministic_report = analysis_source == ANALYSIS_SOURCE_FALLBACK

    llm_output = None
    validation_err = None

    if use_deterministic_report:
        logger.warning(
            "Analytics DEMO MODE — building deterministic success report (skipping report LLM)."
        )
        evidence = build_evidence_summary(question, result_columns, result_rows)
        spread = margin_spread_points(result_columns, result_rows)
        insights = [
            Insight(
                title="Analysis source",
                body=(
                    "deterministic_fallback — schema inspection + safe DuckDB SQL templates. "
                    "Conclusions are grounded in executed result columns, not a live LLM narrative."
                ),
            )
        ]
        if spread is not None and spread < 0.5:
            insights.append(
                Insight(
                    title="Practical margin spread",
                    body=(
                        f"Profit margin spread across groups is ~{spread:.4f} percentage points, "
                        "so ranking differences may not indicate a large practical profitability gap."
                    ),
                )
            )
        llm_output = LLMReportOutput(
            title="Demo Analysis Results",
            executive_summary=ExecutiveSummary(
                headline="Analysis completed using executed results as the source of truth.",
                summary=evidence,
                confidence="Medium",
            ),
            insights=insights,
            recommendations=[],
        )
    else:
        user_prompt = _build_user_prompt(
            question,
            code,
            facts,
            plan_steps,
            result_family,
            schema_columns=schema_column_names(schema_profile),
            result_columns=result_columns,
            result_preview=result_rows[:8],
            requirement_contract=requirement_contract,
            coverage_ok=cov_ok,
            coverage_missing=list(cov_missing),
            analysis_source=analysis_source,
        )
        system_prompt = _get_dynamic_system_prompt(report_mode, result_family)

        for attempt in range(2):  # try → retry once on validation failure
            try:
                llm_output = _call_llm_for_report(
                    system_prompt,
                    user_prompt,
                    validation_error=validation_err,
                )
                break
            except ValidationError as exc:
                validation_err = str(exc)
                logger.warning(f"Report Agent LLM attempt {attempt + 1} — ValidationError: {exc}")
            except json.JSONDecodeError as exc:
                validation_err = f"JSON decode error: {exc}"
                logger.warning(f"Report Agent LLM attempt {attempt + 1} — JSONDecodeError: {exc}")
            except Exception as exc:
                validation_err = str(exc)
                logger.error(f"Report Agent LLM attempt {attempt + 1} — unexpected error: {exc}")

    if llm_output is None:
        # Hard fallback — still evidence-first
        llm_output = LLMReportOutput(
            title="Analysis Complete",
            executive_summary=ExecutiveSummary(
                headline="Analysis executed successfully.",
                summary=build_evidence_summary(question, result_columns, result_rows),
                confidence="Medium",
            ),
            insights=[],
            recommendations=[],
        )

    # Deterministic grounding guard (no second LLM pipeline)
    report_blob = " ".join(
        [
            llm_output.title or "",
            llm_output.executive_summary.headline or "",
            llm_output.executive_summary.summary or "",
        ]
        + [f"{i.title} {i.body}" for i in (llm_output.insights or [])]
    )
    ground_ok, ground_issues = check_report_grounding(
        report_text=report_blob,
        result_columns=result_columns,
        result_rows=result_rows,
        coverage_ok=cov_ok,
        question=question,
    )
    if not ground_ok:
        logger.warning("Report grounding check failed: %s", ground_issues)
        new_headline, new_summary = repair_report_text_for_grounding(
            summary=llm_output.executive_summary.summary or "",
            headline=llm_output.executive_summary.headline or "",
            question=question,
            columns=result_columns,
            rows=result_rows,
            issues=ground_issues,
        )
        llm_output.executive_summary.headline = new_headline
        llm_output.executive_summary.summary = new_summary
        # Soften causation in insights in-place
        for ins in llm_output.insights or []:
            ins.body = soften_causation_language(ins.body or "")
            ins.title = soften_causation_language(ins.title or "")
        artifacts["report_grounding_ok"] = False
        artifacts["report_grounding_issues"] = list(ground_issues)
    else:
        artifacts["report_grounding_ok"] = True
        artifacts["report_grounding_issues"] = []

    # Confidence from semantic coverage + evidence (execution ≠ High by itself)
    conf = confidence_from_coverage(
        coverage_ok=cov_ok,
        missing=cov_missing,
        analysis_source=analysis_source,
        execution_success=True,
        evidence_limited=(not result_columns or len(result_rows) == 0),
    )
    llm_output.executive_summary.confidence = conf
    if not cov_ok and llm_output.executive_summary.summary:
        llm_output.executive_summary.summary = (
            llm_output.executive_summary.summary
            + f"\n\nNote: some question requirements may be only partially covered ({', '.join(cov_missing)})."
        )

    # ── Build tables from query_result ───────────────────────────────────────
    tables: list[dict] = []
    qr_cols = query_result.get("columns", [])
    qr_rows = query_result.get("rows", [])
    if qr_cols and qr_rows:
        # rows from mcp/data_access come as list-of-dicts; normalise to list-of-lists
        normalised_rows: list[list] = []
        for row in qr_rows:
            if isinstance(row, dict):
                normalised_rows.append([row.get(c) for c in qr_cols])
            elif isinstance(row, (list, tuple)):
                normalised_rows.append(list(row))
            else:
                normalised_rows.append([row])
        tables.append({
            "title": "Query Results",
            "columns": qr_cols,
            "rows": normalised_rows,
        })

    # ── Build tables from analysis_artifacts ─────────────────────────────────
    analysis_artifacts = artifacts
    if "correlation_matrix" in analysis_artifacts:
        corr = analysis_artifacts["correlation_matrix"]
        if isinstance(corr, dict) and corr:
            variables = list(corr.keys())
            cols = ["Variable"] + variables
            rows = []
            for var in variables:
                row = [var]
                for col_var in variables:
                    val = corr[var].get(col_var)
                    row.append(val)
                rows.append(row)
            tables.append({
                "title": "Correlation Matrix",
                "columns": cols,
                "rows": rows,
            })

    # ── Build charts from output_summary.chart_json ──────────────────────────
    charts: list[dict] = []
    raw_chart = output_summary.get("chart_json")
    if raw_chart and isinstance(raw_chart, dict):
        # Infer chart type from Plotly trace type
        trace_type = "other"
        data_traces = raw_chart.get("data", [])
        if data_traces and isinstance(data_traces, list):
            trace_type = data_traces[0].get("type", "other")

        try:
            chart_type_enum = ChartType(trace_type)
        except ValueError:
            chart_type_enum = ChartType.OTHER

        layout_title = raw_chart.get("layout", {}).get("title", {})
        chart_title  = (
            layout_title.get("text") if isinstance(layout_title, dict) else layout_title
        ) or llm_output.title

        charts.append({
            "title":       chart_title,
            "type":        chart_type_enum.value,
            "plotly_json": raw_chart,
        })

    # ── Generate PDF ─────────────────────────────────────────────────────────
    pdf_path = None
    try:
        pdf_path = generate_pdf_report(
            session_id=session_id,
            question=question,
            report_data={
                "executive_summary": llm_output.executive_summary.model_dump(mode="json"),
                "insights": [i.model_dump(mode="json") for i in llm_output.insights],
                "recommendations": python_recommendations,
            },
            tables=tables,
            scratch_dir=scratch_dir,
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")

    # Accurate provider/model metadata — never invent; never leave Unknown when known
    provider_meta = artifacts.get("provider")
    model_meta = artifacts.get("model")
    if not provider_meta:
        if analysis_source == ANALYSIS_SOURCE_FALLBACK or use_deterministic_report:
            provider_meta = "Deterministic Fallback"
        elif analysis_source == "gemini":
            provider_meta = "Gemini"
        elif analysis_source == "groq":
            provider_meta = "Groq"
    if not model_meta and (
        analysis_source == ANALYSIS_SOURCE_FALLBACK or use_deterministic_report
    ):
        model_meta = "schema-aware-sql"

    # ── Assemble final_report dict ────────────────────────────────────────────
    final_report = {
        "success": True,
        "dataset": dataset_info,
        "report": {
            "title": llm_output.title,
            "report_type": "SUCCESS",
            "executive_summary": llm_output.executive_summary.model_dump(mode="json"),
            "tables": tables,
            "charts": charts,
            "insights": [i.model_dump(mode="json") for i in llm_output.insights],
            "recommendations": python_recommendations,
        },
        "debug": {
            "generated_code": code or None,
            "execution_mode": state.get("plan", {}).get("approach", "DETERMINISTIC").upper(),
            "execution_plan": plan_steps,
            "llm_reasoning": (
                "Deterministic DEMO MODE report. LLM bypassed."
                if use_deterministic_report
                else llm_output.llm_reasoning
            ),
            "analysis_source": analysis_source or (
                ANALYSIS_SOURCE_FALLBACK if use_deterministic_report else None
            ),
            "provider": provider_meta,
            "model": model_meta,
            "coverage_ok": cov_ok,
            "report_grounding_ok": artifacts.get("report_grounding_ok"),
        },
        "pdf_path": pdf_path,
    }

    end_time = time.time()
    duration_ms = (end_time - start_time) * 1000
    logger.info(f"Node completed: {node_name} (success path) in {duration_ms:.2f}ms")
    
    node_metadata = {
        "node_name": node_name,
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "status": "success",
        "retry_count": retry_count,
        "error_message": None
    }
    execution_metadata = list(state.get("execution_metadata") or [])
    execution_metadata.append(node_metadata)
    
    worker_result = {
        "worker_name": "REPORT",
        "status": "success",
        "confidence": 1.0,
        "summary": "Report generated successfully.",
        "routing_hint": "TERMINATE",
        "duration_ms": duration_ms
    }
    
    updates = {
        "final_report": final_report,
        "execution_metadata": execution_metadata,
        "last_worker_result": worker_result,
        "analysis_artifacts": artifacts,
    }
    
    if not graceful_failure:
        updates["conversational_context"] = {
            "previous_question": state.get("question", ""),
            "previous_resolved_question": get_effective_question(state),
            "previous_capability": state.get("plan", {}).get("approach", "UNKNOWN").upper(),
            "previous_result_columns": query_result.get("columns", []),
            "previous_result_summary": output_summary.get("summary", "") if isinstance(output_summary, dict) else ""
        }
        
    return updates
