"""
MarketMind Lead Intelligence & marketplace smoke tests.

All tests are deterministic and run in DEMO MODE (no live LLM required).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.marketplace.demo_data import load_marketplace_demo
from backend.marketplace.lead.demo_extractor import (
    EXTRACTION_SOURCE_DEMO,
    extract_requirement_demo,
)
from backend.marketplace.lead.graph import run_lead_analysis
from backend.marketplace.lead.matching import search_products
from backend.marketplace.lead.ranking import (
    WEIGHTS,
    rating_score,
    response_time_score,
    score_supplier,
    verified_score,
)


# ── A. Supplier Ranking ─────────────────────────────────────────────────────


class TestSupplierRanking:
    def test_higher_rating_scores_higher(self):
        assert rating_score(5.0) > rating_score(3.0)
        assert rating_score(5.0) == pytest.approx(1.0)
        assert rating_score(None) == 0.0

    def test_verified_suppliers_score_correctly(self):
        assert verified_score(True) == 1.0
        assert verified_score(False) == 0.0
        assert verified_score("yes") == 1.0

    def test_faster_response_improves_score(self):
        assert response_time_score(2.0) > response_time_score(48.0)
        assert response_time_score(72.0) == pytest.approx(0.0)
        assert response_time_score(0.0) == pytest.approx(1.0)

    def test_weights_sum_to_one(self):
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)

    def test_final_ranking_order_is_deterministic(self):
        strong = score_supplier(
            product_match=0.95,
            rating=4.8,
            verified=True,
            response_time_hours=4.0,
            total_orders=15,
            good_orders=14,
            supplier_city="Jaipur",
            supplier_state="Rajasthan",
            req_city="Jaipur",
            req_state="Rajasthan",
        )
        weak = score_supplier(
            product_match=0.4,
            rating=2.5,
            verified=False,
            response_time_hours=60.0,
            total_orders=1,
            good_orders=0,
            supplier_city="Chennai",
            supplier_state="Tamil Nadu",
            req_city="Jaipur",
            req_state="Rajasthan",
        )
        assert strong["final_score"] > weak["final_score"]

        # Stable across repeats
        again = score_supplier(
            product_match=0.95,
            rating=4.8,
            verified=True,
            response_time_hours=4.0,
            total_orders=15,
            good_orders=14,
            supplier_city="Jaipur",
            supplier_state="Rajasthan",
            req_city="Jaipur",
            req_state="Rajasthan",
        )
        assert again == strong


# ── B. Demo Requirement Extractor ───────────────────────────────────────────


class TestDemoExtractor:
    def test_solar_panels_jaipur(self):
        out = extract_requirement_demo(
            "Need 500 solar panels in Jaipur within two weeks"
        )
        assert out is not None
        assert "solar" in out["product_name"].lower()
        assert out["quantity"] == 500.0
        assert out["city"] == "Jaipur"
        assert out["state"] == "Rajasthan"
        assert out["extraction_source"] == EXTRACTION_SOURCE_DEMO
        assert out["product_category"] == "Solar Products"
        assert "two weeks" in (out.get("delivery_time") or "")

    def test_water_pumps_delhi(self):
        out = extract_requirement_demo(
            "Looking for industrial water pumps for my factory in Delhi"
        )
        assert out is not None
        assert "pump" in out["product_name"].lower()
        assert out["city"] == "Delhi"
        assert out["state"] == "Delhi"
        assert out["extraction_source"] == EXTRACTION_SOURCE_DEMO

    def test_packaging_boxes_mumbai(self):
        out = extract_requirement_demo("Need bulk packaging boxes in Mumbai")
        assert out is not None
        assert "packaging" in out["product_name"].lower() or "box" in out["product_name"].lower()
        assert out["city"] == "Mumbai"
        assert out["state"] == "Maharashtra"
        assert out["extraction_source"] == EXTRACTION_SOURCE_DEMO
        assert out["buyer_intent"] in ("bulk_purchase", "purchase")

    def test_unclear_input_returns_none(self):
        assert extract_requirement_demo("asdf") is None
        assert extract_requirement_demo("") is None


# ── C. Product Matching ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def marketplace_session_id() -> str:
    sid = f"test-{uuid.uuid4()}"
    load_marketplace_demo(sid)
    return sid


class TestProductMatching:
    def test_solar_panels_match(self, marketplace_session_id):
        rows = search_products(marketplace_session_id, "solar panels", "Solar Products")
        assert len(rows) > 0
        blob = " ".join(r["name"].lower() for r in rows)
        assert "solar" in blob or "panel" in blob or "pv" in blob

    def test_water_pumps_match(self, marketplace_session_id):
        rows = search_products(
            marketplace_session_id, "industrial water pumps", "Industrial Equipment"
        )
        assert len(rows) > 0
        blob = " ".join(r["name"].lower() for r in rows)
        assert "pump" in blob

    def test_packaging_boxes_match(self, marketplace_session_id):
        rows = search_products(
            marketplace_session_id, "packaging boxes", "Packaging Materials"
        )
        assert len(rows) > 0
        blob = " ".join(r["name"].lower() for r in rows)
        assert "box" in blob or "carton" in blob or "packaging" in blob

    def test_unknown_widget_no_matches(self, marketplace_session_id):
        rows = search_products(marketplace_session_id, "xyz unknown widget", None)
        assert rows == []


# ── D. Lead Workflow statuses ────────────────────────────────────────────────


class TestLeadWorkflow:
    def test_clear_requirement_complete(self, marketplace_session_id):
        out = run_lead_analysis(
            marketplace_session_id,
            "Need 500 solar panels in Jaipur within two weeks",
        )
        assert out["workflow_status"] == "complete"
        assert out["extracted_requirement"]["extraction_source"] == EXTRACTION_SOURCE_DEMO
        assert out["matched_products"]
        assert out["recommended_suppliers"]
        assert out["node_executions"]
        assert out["run_id"]

    def test_unknown_product_no_products(self, marketplace_session_id):
        out = run_lead_analysis(marketplace_session_id, "Need xyz unknown widget")
        assert out["workflow_status"] == "no_products"
        assert out.get("matched_products") == []

    def test_unclear_requirement_needs_info(self, marketplace_session_id):
        out = run_lead_analysis(marketplace_session_id, "asdf")
        assert out["workflow_status"] == "needs_info"


# ── E. API smoke tests ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


class TestMarketplaceAPI:
    def test_demo_load(self, client):
        res = client.post("/marketplace/demo")
        assert res.status_code == 200
        body = res.json()
        assert body.get("session_id")
        assert set(body.get("tables") or []) >= {
            "categories",
            "suppliers",
            "buyers",
            "products",
            "leads",
            "orders",
        }

    def test_lead_analyze(self, client):
        demo = client.post("/marketplace/demo").json()
        res = client.post(
            "/marketplace/lead/analyze",
            json={
                "session_id": demo["session_id"],
                "requirement": "Need 500 solar panels in Jaipur within two weeks",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["workflow_status"] == "complete"
        assert body["extracted_requirement"]["extraction_source"] == EXTRACTION_SOURCE_DEMO
        assert body["matched_products"]
        assert body["recommended_suppliers"]

    def test_observability_summary(self, client):
        res = client.get("/marketplace/observability/summary")
        assert res.status_code == 200
        body = res.json()
        summary = body.get("summary") or body
        assert "total_runs" in summary
