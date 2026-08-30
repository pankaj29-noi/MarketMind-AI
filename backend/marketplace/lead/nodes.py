"""Lead Intelligence graph nodes."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.marketplace.lead.matching import (
    CITY_STATE_MAP,
    fetch_supplier_candidates,
    search_products,
)
from backend.marketplace.lead.ranking import (
    RANKING_FORMULA_DOC,
    build_explanation,
    score_supplier,
)
from backend.marketplace.lead.schemas import ExtractedRequirement, ValidationResult
from backend.marketplace.lead.state import LeadAgentState

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["product_name"]
IMPORTANT_OPTIONAL = ["quantity", "city", "state", "delivery_time"]

PARSER_SYSTEM = """You are a B2B buyer-requirement extractor for MarketMind AI (Indian marketplace).
Extract structured fields from the buyer's free-text requirement.

Return ONLY valid JSON with these keys:
{
  "product_name": string or null,
  "product_category": string or null,
  "quantity": number or null,
  "unit": string or null,
  "city": string or null,
  "state": string or null,
  "delivery_time": string or null,
  "buyer_intent": "purchase" | "quote" | "enquiry" | "bulk_purchase" | "unknown",
  "confidence_score": number between 0 and 1
}

Rules:
- Do NOT invent product names, cities, quantities, or categories that are not implied by the text.
- If a field is not present or unclear, set it to null (and lower confidence_score).
- Map obvious Indian cities to their state when the city is explicit (e.g. Jaipur → Rajasthan).
- product_category should be a marketplace-style category when inferable (e.g. Solar Products, Packaging Materials, Agricultural Equipment, Industrial Equipment).
- buyer_intent: prefer purchase / bulk_purchase when quantity or "need/require" is clear.
- confidence_score reflects how complete and clear the requirement is.
"""


def _parse_json_content(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text, strict=False)


def requirement_parser_node(state: LeadAgentState) -> Dict[str, Any]:
    text = (state.get("requirement_text") or "").strip()
    if not text:
        return {
            "extracted_requirement": None,
            "workflow_status": "needs_info",
            "error": "Requirement text is empty.",
            "stop_reason": "empty_input",
        }

    from backend.config import has_valid_llm_api_key, use_lead_demo_extraction
    from backend.marketplace.lead.demo_extractor import extract_requirement_demo

    # DEMO MODE: deterministic extractor when no valid Groq key (NOT an LLM).
    if use_lead_demo_extraction():
        logger.warning(
            "Lead Intelligence using DEMO MODE deterministic extractor "
            "(no valid GROQ_API_KEY). This is not a live LLM."
        )
        demo = extract_requirement_demo(text)
        if not demo:
            return {
                "extracted_requirement": None,
                "workflow_status": "needs_info",
                "error": (
                    "Could not extract a product from the requirement "
                    "(DEMO MODE deterministic parser). Provide a clearer product name."
                ),
                "stop_reason": "extraction_missing",
            }
        extracted = ExtractedRequirement.model_validate(demo)
        if extracted.city and not extracted.state:
            mapped = CITY_STATE_MAP.get(extracted.city.strip().lower())
            if mapped:
                extracted.state = mapped
        return {
            "extracted_requirement": extracted.model_dump(),
            "workflow_status": "running",
            "error": None,
            "stop_reason": None,
        }

    if not has_valid_llm_api_key():
        return {
            "extracted_requirement": None,
            "workflow_status": "failed",
            "error": (
                "GROQ_API_KEY is missing or still a placeholder, and DEMO_MODE is disabled. "
                "Set a real GROQ_API_KEY in DataAgent-Pro/.env, or set DEMO_MODE=true/auto."
            ),
            "stop_reason": "extraction_failed",
        }

    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke(
            [
                SystemMessage(content=PARSER_SYSTEM),
                HumanMessage(content=f"Buyer requirement:\n{text}"),
            ]
        )
        raw = _parse_json_content(response.content if hasattr(response, "content") else str(response))
        extracted = ExtractedRequirement.model_validate(raw)
        # Mark real LLM extraction source
        data = extracted.model_dump()
        data["extraction_source"] = "llm"

        # Deterministic city→state enrichment only when city known and state missing
        if data.get("city") and not data.get("state"):
            mapped = CITY_STATE_MAP.get(str(data["city"]).strip().lower())
            if mapped:
                data["state"] = mapped

        return {
            "extracted_requirement": data,
            "workflow_status": "running",
            "error": None,
            "stop_reason": None,
        }
    except Exception as e:
        logger.error("Requirement parser failed: %s", e)
        return {
            "extracted_requirement": None,
            "workflow_status": "failed",
            "error": f"Failed to extract requirement: {e}",
            "stop_reason": "extraction_failed",
        }


def validation_node(state: LeadAgentState) -> Dict[str, Any]:
    extracted = state.get("extracted_requirement")
    if not extracted:
        return {
            "validation_result": ValidationResult(
                is_valid=False,
                missing_fields=["product_name"],
                warnings=[],
                message="No structured requirement was extracted.",
            ).model_dump(),
            "workflow_status": "needs_info",
            "stop_reason": "extraction_missing",
        }

    missing: List[str] = []
    warnings: List[str] = []

    for field in REQUIRED_FIELDS:
        val = extracted.get(field)
        if val is None or (isinstance(val, str) and not str(val).strip()):
            missing.append(field)

    for field in IMPORTANT_OPTIONAL:
        val = extracted.get(field)
        if val is None or (isinstance(val, str) and not str(val).strip()):
            warnings.append(f"Optional field missing: {field}")

    confidence = float(extracted.get("confidence_score") or 0)
    if confidence < 0.4 and not missing:
        warnings.append("Low extraction confidence — results may be imprecise.")

    is_valid = len(missing) == 0
    if not is_valid:
        message = (
            "Missing required information: "
            + ", ".join(missing)
            + ". Please provide a clearer product or category."
        )
        status = "needs_info"
        stop = "missing_required_fields"
    else:
        message = "Requirement validated."
        if warnings:
            message += " Some optional details are missing."
        status = "running"
        stop = None

    return {
        "validation_result": ValidationResult(
            is_valid=is_valid,
            missing_fields=missing,
            warnings=warnings,
            message=message,
        ).model_dump(),
        "workflow_status": status,
        "stop_reason": stop,
        "error": None if is_valid else message,
    }


def product_matcher_node(state: LeadAgentState) -> Dict[str, Any]:
    extracted = state.get("extracted_requirement") or {}
    session_id = state["session_id"]
    products = search_products(
        session_id,
        extracted.get("product_name"),
        extracted.get("product_category"),
        limit=12,
    )
    if not products:
        return {
            "matched_products": [],
            "workflow_status": "no_products",
            "stop_reason": "no_product_match",
            "error": "No matching products found in the marketplace catalog.",
        }
    return {
        "matched_products": products,
        "workflow_status": "running",
        "stop_reason": None,
        "error": None,
    }


def supplier_matcher_node(state: LeadAgentState) -> Dict[str, Any]:
    session_id = state["session_id"]
    products = state.get("matched_products") or []
    candidates = fetch_supplier_candidates(session_id, products)
    if not candidates:
        return {
            "candidate_suppliers": [],
            "workflow_status": "no_suppliers",
            "stop_reason": "no_supplier_match",
            "error": "No suppliers found for the matched products.",
        }
    return {
        "candidate_suppliers": candidates,
        "workflow_status": "running",
        "stop_reason": None,
        "error": None,
    }


def supplier_ranker_node(state: LeadAgentState) -> Dict[str, Any]:
    extracted = state.get("extracted_requirement") or {}
    candidates = state.get("candidate_suppliers") or []
    req_city = extracted.get("city")
    req_state = extracted.get("state")

    ranked: List[Dict[str, Any]] = []
    for c in candidates:
        scores = score_supplier(
            product_match=float(c.get("best_product_match_score") or 0),
            rating=c.get("rating"),
            verified=c.get("verified"),
            response_time_hours=c.get("response_time_hours"),
            total_orders=int(c.get("total_orders") or 0),
            good_orders=int(c.get("good_orders") or 0),
            supplier_city=c.get("city"),
            supplier_state=c.get("state"),
            req_city=req_city,
            req_state=req_state,
        )
        explanation = build_explanation(
            scores,
            c.get("verified"),
            c.get("rating"),
            c.get("response_time_hours"),
        )
        ranked.append(
            {
                "rank": 0,
                "supplier_id": c["supplier_id"],
                "name": c.get("name"),
                "city": c.get("city"),
                "state": c.get("state"),
                "rating": c.get("rating"),
                "verified": bool(c.get("verified")),
                "response_time_hours": c.get("response_time_hours"),
                "matching_products": c.get("matching_products") or [],
                "matching_product_ids": c.get("matching_product_ids") or [],
                **scores,
                "explanation": explanation,
            }
        )

    ranked.sort(key=lambda x: (-x["final_score"], -(x.get("rating") or 0), x.get("name") or ""))
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i

    return {
        "recommended_suppliers": ranked[:10],
        "workflow_status": "running",
        "stop_reason": None,
        "error": None,
    }


def response_formatter_node(state: LeadAgentState) -> Dict[str, Any]:
    status = state.get("workflow_status") or "complete"
    if status == "running":
        status = "complete"
    # Preserve terminal statuses
    if state.get("stop_reason") in (
        "empty_input",
        "extraction_failed",
        "extraction_missing",
        "missing_required_fields",
        "no_product_match",
        "no_supplier_match",
    ):
        status = state.get("workflow_status") or status

    return {
        "workflow_status": status,
        "recommended_suppliers": state.get("recommended_suppliers") or [],
        "matched_products": state.get("matched_products") or [],
        # Attach formula documentation for API consumers
        "error": state.get("error"),
    }


# Expose formula for API layer
RANKING_FORMULA = RANKING_FORMULA_DOC
