"""Shared state for the Lead Intelligence LangGraph workflow."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class LeadAgentState(TypedDict, total=False):
    # Inputs
    session_id: str
    requirement_text: str
    run_id: Optional[str]

    # Pipeline artifacts
    extracted_requirement: Optional[Dict[str, Any]]
    validation_result: Optional[Dict[str, Any]]
    matched_products: List[Dict[str, Any]]
    candidate_suppliers: List[Dict[str, Any]]
    recommended_suppliers: List[Dict[str, Any]]

    # Observability
    node_executions: List[Dict[str, Any]]

    # Control
    workflow_status: str  # running | needs_info | no_products | no_suppliers | complete | failed
    error: Optional[str]
    stop_reason: Optional[str]
