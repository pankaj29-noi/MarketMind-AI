"""Regression tests for CORS allowlist configuration."""
from fastapi.testclient import TestClient

from backend.config import get_cors_allowed_origins
from backend.main import app


def test_default_cors_includes_local_and_production():
    origins = get_cors_allowed_origins()
    assert "http://localhost:5173" in origins
    assert "https://marketmind-ai-pankaj.vercel.app" in origins
    assert "*" not in origins


def test_cors_preflight_allows_known_origin(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,https://marketmind-ai-pankaj.vercel.app",
    )
    # Re-read would require reimport; exercise middleware with current app defaults.
    client = TestClient(app)
    origin = "https://marketmind-ai-pankaj.vercel.app"
    res = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code in (200, 204)
    assert res.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_rejects_unknown_origin():
    client = TestClient(app)
    res = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette/FastAPI omit ACAO for disallowed origins
    assert res.headers.get("access-control-allow-origin") != "https://evil.example.com"
    assert res.headers.get("access-control-allow-origin") != "*"
