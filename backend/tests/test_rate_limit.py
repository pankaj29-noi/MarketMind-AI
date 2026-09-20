"""Rate limiter dependency regressions."""
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from backend.utils.rate_limit import SlidingWindowRateLimiter, limit_expensive_endpoint


def test_sliding_window_blocks_after_max():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True


def test_expensive_endpoint_dependency_returns_429(monkeypatch):
    from backend.utils import rate_limit as rl

    monkeypatch.setattr(rl, "_expensive", SlidingWindowRateLimiter(max_requests=1, window_seconds=60))

    app = FastAPI()

    @app.get("/x")
    async def x(_: None = Depends(limit_expensive_endpoint)):
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 429
