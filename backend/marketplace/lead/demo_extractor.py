"""
Deterministic DEMO MODE requirement extractor for Lead Intelligence.

This is NOT an LLM. It uses keyword / regex rules so recruiter demos work
when GROQ_API_KEY is missing or still a placeholder.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from backend.marketplace.lead.matching import CITY_STATE_MAP

logger = logging.getLogger(__name__)

EXTRACTION_SOURCE_DEMO = "demo_deterministic"

# Ordered patterns: first match wins for product identity
_PRODUCT_PATTERNS = [
    {
        "keywords": ["solar panel", "solar panels", "pv panel", "photovoltaic"],
        "product_name": "solar panels",
        "product_category": "Solar Products",
        "unit": "units",
    },
    {
        "keywords": ["water pump", "water pumps", "industrial pump", "industrial pumps"],
        "product_name": "industrial water pumps",
        "product_category": "Industrial Equipment",
        "unit": "units",
    },
    {
        "keywords": [
            "packaging box",
            "packaging boxes",
            "carton box",
            "carton boxes",
            "corrugated",
            "packaging",
        ],
        "product_name": "packaging boxes",
        "product_category": "Packaging Materials",
        "unit": "boxes",
    },
    {
        "keywords": [
            "agricultural equipment",
            "agriculture equipment",
            "farm equipment",
            "agricultural machine",
            "agricultural machines",
        ],
        "product_name": "agricultural equipment",
        "product_category": "Agricultural Equipment",
        "unit": "units",
    },
    {
        "keywords": ["solar"],
        "product_name": "solar panels",
        "product_category": "Solar Products",
        "unit": "units",
    },
    {
        "keywords": ["pump"],
        "product_name": "industrial water pumps",
        "product_category": "Industrial Equipment",
        "unit": "units",
    },
]


def _find_city(text: str) -> Optional[str]:
    lower = text.lower()
    # Prefer longer city names first
    cities = sorted(CITY_STATE_MAP.keys(), key=len, reverse=True)
    for city in cities:
        if re.search(rf"\b{re.escape(city)}\b", lower):
            return city.title() if city != "new delhi" else "New Delhi"
    return None


def _find_quantity(text: str) -> Optional[float]:
    m = re.search(r"\b(\d+(?:\.\d+)?)\b", text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _find_delivery_time(text: str) -> Optional[str]:
    lower = text.lower()
    patterns = [
        r"within\s+two\s+weeks?",
        r"within\s+\d+\s+weeks?",
        r"within\s+\d+\s+days?",
        r"in\s+\d+\s+weeks?",
        r"in\s+\d+\s+days?",
        r"asap",
        r"immediate(?:ly)?",
    ]
    for pat in patterns:
        m = re.search(pat, lower)
        if m:
            return m.group(0)
    return None


def _find_product(text: str) -> Optional[Dict[str, str]]:
    lower = text.lower()
    for rule in _PRODUCT_PATTERNS:
        for kw in rule["keywords"]:
            if kw in lower:
                return {
                    "product_name": rule["product_name"],
                    "product_category": rule["product_category"],
                    "unit": rule["unit"],
                }
    return None


def _buyer_intent(text: str, quantity: Optional[float]) -> str:
    lower = text.lower()
    if "bulk" in lower or (quantity is not None and quantity >= 100):
        return "bulk_purchase"
    if any(w in lower for w in ("need", "require", "looking for", "want", "buy", "purchase")):
        return "purchase"
    if "quote" in lower:
        return "quote"
    if "enquir" in lower or "inquiry" in lower:
        return "enquiry"
    return "unknown"


def extract_requirement_demo(text: str) -> Optional[Dict[str, Any]]:
    """
    Deterministically parse a buyer requirement for DEMO MODE.

    Returns None when the input is too unclear to extract a product_name
    (caller should treat that as needs_info).
    """
    raw = (text or "").strip()
    if not raw:
        return None

    # Gibberish / too short without product keywords
    if len(raw) < 4 or re.fullmatch(r"[a-z]{1,6}", raw.lower()):
        logger.info("Demo extractor: unclear input rejected (%r)", raw)
        return None

    product = _find_product(raw)
    if not product:
        # Unknown product phrase like "xyz unknown widget" — still extract a name
        # so validation can pass and product matching can return no_products.
        unknown = re.search(
            r"(?:need|looking for|require|want)\s+(.+?)(?:\s+in\s+|\s+for\s+|\s+within\s+|$)",
            raw,
            flags=re.IGNORECASE,
        )
        if unknown:
            name = unknown.group(1).strip(" .,!")
            # Strip leading quantity words
            name = re.sub(r"^\d+\s+", "", name).strip()
            if name and len(name) > 2 and name.lower() not in {"a", "an", "the", "some"}:
                product = {
                    "product_name": name,
                    "product_category": None,
                    "unit": "units",
                }
            else:
                return None
        else:
            return None

    quantity = _find_quantity(raw)
    city = _find_city(raw)
    state = CITY_STATE_MAP.get(city.lower()) if city else None
    delivery_time = _find_delivery_time(raw)
    intent = _buyer_intent(raw, quantity)

    confidence = 0.55
    if product.get("product_category"):
        confidence += 0.15
    if quantity is not None:
        confidence += 0.1
    if city:
        confidence += 0.1
    if delivery_time:
        confidence += 0.05
    confidence = min(confidence, 0.95)

    result = {
        "product_name": product["product_name"],
        "product_category": product.get("product_category"),
        "quantity": quantity,
        "unit": product.get("unit") or "units",
        "city": city,
        "state": state,
        "delivery_time": delivery_time,
        "buyer_intent": intent,
        "confidence_score": round(confidence, 2),
        "extraction_source": EXTRACTION_SOURCE_DEMO,
    }
    logger.info(
        "Demo extractor (deterministic, NOT LLM) parsed product=%r city=%r qty=%s",
        result["product_name"],
        city,
        quantity,
    )
    return result
