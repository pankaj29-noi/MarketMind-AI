"""
Pydantic schemas for MarketMind Lead Intelligence (buyer requirement → supplier match).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ExtractedRequirement(BaseModel):
    """Structured buyer requirement extracted from free-text."""

    product_name: Optional[str] = Field(None, description="Product or item the buyer wants")
    product_category: Optional[str] = Field(None, description="Marketplace category guess")
    quantity: Optional[float] = Field(None, description="Requested quantity")
    unit: Optional[str] = Field(None, description="Unit of measure, e.g. units, kg, boxes")
    city: Optional[str] = Field(None, description="Delivery / buyer city")
    state: Optional[str] = Field(None, description="Indian state if known")
    delivery_time: Optional[str] = Field(None, description="Delivery timeline as stated")
    buyer_intent: Optional[str] = Field(
        None, description="purchase | quote | enquiry | bulk_purchase | unknown"
    )
    confidence_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Extraction confidence 0–1"
    )
    extraction_source: Optional[str] = Field(
        None,
        description="llm | demo_deterministic — how the requirement was extracted",
    )

    @field_validator("product_name", "product_category", "unit", "city", "state", "delivery_time", "buyer_intent", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("quantity", mode="before")
    @classmethod
    def coerce_quantity(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


class ValidationResult(BaseModel):
    is_valid: bool = True
    missing_fields: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    message: str = ""


class MatchedProduct(BaseModel):
    product_id: int
    name: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    supplier_id: int
    price: Optional[float] = None
    moq: Optional[int] = None
    stock: Optional[int] = None
    match_score: float = 0.0
    match_reason: str = ""


class RankedSupplier(BaseModel):
    rank: int
    supplier_id: int
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    rating: Optional[float] = None
    verified: bool = False
    response_time_hours: Optional[float] = None
    matching_products: List[str] = Field(default_factory=list)
    matching_product_ids: List[int] = Field(default_factory=list)
    product_match_score: float = 0.0
    rating_score: float = 0.0
    verified_score: float = 0.0
    response_time_score: float = 0.0
    order_performance_score: float = 0.0
    location_score: float = 0.0
    final_score: float = 0.0
    explanation: str = ""


class LeadAnalyzeResponse(BaseModel):
    workflow_status: str
    extracted_requirement: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None
    matched_products: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_suppliers: List[Dict[str, Any]] = Field(default_factory=list)
    session_id: Optional[str] = None
    error: Optional[str] = None
    ranking_formula: Optional[str] = None
