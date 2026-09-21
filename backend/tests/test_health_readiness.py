"""/health must be a readiness signal, not just proof the process is alive.

Baseline: /health returned 200 {"status":"ok"} while reporting agent_ready=False.
Render gates deploys on this path, so a broken deploy looked healthy.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app
from backend.services import llm_circuit


def test_ready_service_reports_ok():
    llm_circuit.clear()
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["agent_ready"] is True
    assert "providers" in body


def test_missing_agent_graph_is_not_reported_as_healthy():
    with TestClient(app) as client:
        with patch.object(main, "agent_graph", None):
            response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["agent_ready"] is False


def test_cooling_provider_is_reported_as_degraded_not_broken():
    """Analytics still answers via deterministic SQL, so this is degraded, not down."""
    with TestClient(app) as client:
        llm_circuit.trip("Groq", "429 rate limit")
        try:
            response = client.get("/health")
        finally:
            llm_circuit.clear()

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "degraded"
    assert "Groq" in body["providers_cooling_down_seconds"]
    assert body["deterministic_fallback_available"] is True


def test_health_never_exposes_credentials():
    llm_circuit.clear()
    with TestClient(app) as client:
        raw = client.get("/health").text
    for secret in ("gsk_", "AIza", "GROQ_API_KEY", "GOOGLE_API_KEY"):
        assert secret not in raw
