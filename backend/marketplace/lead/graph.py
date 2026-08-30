"""
Lead Intelligence LangGraph workflow (independent from analytics agent graph).

Flow:
  requirement_parser → validation → product_matcher → supplier_matcher
  → supplier_ranker → response_formatter → END

Early-exit paths:
  validation failure / no products / no suppliers → response_formatter → END

Node executions are timed via lightweight wrappers for observability.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Dict

from langgraph.graph import END, StateGraph

from backend.marketplace.lead.nodes import (
    product_matcher_node,
    requirement_parser_node,
    response_formatter_node,
    supplier_matcher_node,
    supplier_ranker_node,
    validation_node,
)
from backend.marketplace.lead.state import LeadAgentState
from backend.marketplace.observability import (
    complete_workflow_run,
    create_workflow_run,
    sanitize_error_message,
)

logger = logging.getLogger(__name__)

_lead_graph = None

WORKFLOW_NAME = "lead_intelligence"


def _timed_node(node_name: str, fn: Callable[[LeadAgentState], Dict[str, Any]]):
    """Wrap a node to record duration/status into state.node_executions."""

    def wrapped(state: LeadAgentState) -> Dict[str, Any]:
        start = time.time()
        order = len(state.get("node_executions") or []) + 1
        status = "success"
        err_msg = None
        try:
            updates = fn(state) or {}
        except Exception as e:
            logger.exception("Lead node %s raised: %s", node_name, e)
            err_msg = sanitize_error_message(str(e))
            status = "failed"
            updates = {
                "workflow_status": "failed",
                "error": err_msg or "Node execution failed.",
                "stop_reason": f"{node_name}_exception",
            }

        # Infer soft-failure statuses from node outcomes
        wf_status = updates.get("workflow_status")
        if wf_status == "failed" or updates.get("stop_reason") == "extraction_failed":
            status = "failed"
            err_msg = sanitize_error_message(updates.get("error")) or err_msg
        elif wf_status in ("needs_info", "no_products", "no_suppliers"):
            status = wf_status

        duration_ms = round((time.time() - start) * 1000, 2)
        executions = list(state.get("node_executions") or [])
        executions.append(
            {
                "node_name": node_name,
                "execution_order": order,
                "duration_ms": duration_ms,
                "status": status,
                "error_message": err_msg,
            }
        )
        updates["node_executions"] = executions
        if updates.get("error"):
            updates["error"] = sanitize_error_message(updates.get("error"))
        return updates

    return wrapped


def _route_after_validation(state: LeadAgentState) -> str:
    if state.get("workflow_status") in ("needs_info", "failed"):
        return "response_formatter"
    return "product_matcher"


def _route_after_products(state: LeadAgentState) -> str:
    if state.get("workflow_status") == "no_products":
        return "response_formatter"
    return "supplier_matcher"


def _route_after_suppliers(state: LeadAgentState) -> str:
    if state.get("workflow_status") == "no_suppliers":
        return "response_formatter"
    return "supplier_ranker"


def create_lead_graph():
    """Compile the Lead Intelligence StateGraph (no Postgres checkpointer needed)."""
    workflow = StateGraph(LeadAgentState)

    workflow.add_node("requirement_parser", _timed_node("requirement_parser", requirement_parser_node))
    workflow.add_node("validation", _timed_node("validation", validation_node))
    workflow.add_node("product_matcher", _timed_node("product_matcher", product_matcher_node))
    workflow.add_node("supplier_matcher", _timed_node("supplier_matcher", supplier_matcher_node))
    workflow.add_node("supplier_ranker", _timed_node("supplier_ranker", supplier_ranker_node))
    workflow.add_node("response_formatter", _timed_node("response_formatter", response_formatter_node))

    workflow.set_entry_point("requirement_parser")
    workflow.add_edge("requirement_parser", "validation")
    workflow.add_conditional_edges(
        "validation",
        _route_after_validation,
        {
            "product_matcher": "product_matcher",
            "response_formatter": "response_formatter",
        },
    )
    workflow.add_conditional_edges(
        "product_matcher",
        _route_after_products,
        {
            "supplier_matcher": "supplier_matcher",
            "response_formatter": "response_formatter",
        },
    )
    workflow.add_conditional_edges(
        "supplier_matcher",
        _route_after_suppliers,
        {
            "supplier_ranker": "supplier_ranker",
            "response_formatter": "response_formatter",
        },
    )
    workflow.add_edge("supplier_ranker", "response_formatter")
    workflow.add_edge("response_formatter", END)

    compiled = workflow.compile()
    logger.info("Lead Intelligence LangGraph compiled successfully.")
    return compiled


def get_lead_graph():
    global _lead_graph
    if _lead_graph is None:
        _lead_graph = create_lead_graph()
    return _lead_graph


def run_lead_analysis(session_id: str, requirement: str) -> Dict[str, Any]:
    """Invoke the lead workflow, record observability, and return a serializable response."""
    from backend.marketplace.lead.ranking import RANKING_FORMULA_DOC

    run_id = str(uuid.uuid4())
    create_workflow_run(
        workflow_name=WORKFLOW_NAME,
        session_id=session_id,
        input_summary=requirement,
        run_id=run_id,
    )

    graph = get_lead_graph()
    initial: LeadAgentState = {
        "session_id": session_id,
        "requirement_text": requirement,
        "run_id": run_id,
        "extracted_requirement": None,
        "validation_result": None,
        "matched_products": [],
        "candidate_suppliers": [],
        "recommended_suppliers": [],
        "node_executions": [],
        "workflow_status": "running",
        "error": None,
        "stop_reason": None,
    }

    started = time.time()
    try:
        final = graph.invoke(initial)
    except Exception as e:
        latency_ms = round((time.time() - started) * 1000, 2)
        safe_err = sanitize_error_message(str(e)) or "Lead workflow failed."
        complete_workflow_run(
            run_id,
            final_status="failed",
            latency_ms=latency_ms,
            product_matches_count=0,
            supplier_matches_count=0,
            error_message=safe_err,
            node_executions=[],
        )
        return {
            "run_id": run_id,
            "workflow_status": "failed",
            "extracted_requirement": None,
            "validation_result": None,
            "matched_products": [],
            "recommended_suppliers": [],
            "session_id": session_id,
            "error": safe_err,
            "ranking_formula": RANKING_FORMULA_DOC,
            "stop_reason": "graph_exception",
            "latency_ms": latency_ms,
            "node_executions": [],
        }

    latency_ms = round((time.time() - started) * 1000, 2)
    status = final.get("workflow_status") or "complete"
    products = final.get("matched_products") or []
    suppliers = final.get("recommended_suppliers") or []
    nodes = final.get("node_executions") or []
    safe_err = sanitize_error_message(final.get("error"))

    complete_workflow_run(
        run_id,
        final_status=status,
        latency_ms=latency_ms,
        product_matches_count=len(products),
        supplier_matches_count=len(suppliers),
        error_message=safe_err,
        node_executions=nodes,
    )

    return {
        "run_id": run_id,
        "workflow_status": status,
        "extracted_requirement": final.get("extracted_requirement"),
        "validation_result": final.get("validation_result"),
        "matched_products": products,
        "recommended_suppliers": suppliers,
        "session_id": session_id,
        "error": safe_err,
        "ranking_formula": RANKING_FORMULA_DOC,
        "stop_reason": final.get("stop_reason"),
        "latency_ms": latency_ms,
        "node_executions": nodes,
    }
