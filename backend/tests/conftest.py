"""Pytest defaults — keep unit tests offline unless SQLCODER_TEST_LIVE=1."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _sqlcoder_offline_by_default(monkeypatch):
    """
    Disable local SQLCoder for the suite so existing mocks of invoke_llm still apply.

    Live GGUF tests set SQLCODER_TEST_LIVE=1 and opt in explicitly.
    """
    if os.getenv("SQLCODER_TEST_LIVE", "").strip() == "1":
        return
    monkeypatch.setenv("SQLCODER_ENABLED", "false")


@pytest.fixture(autouse=True)
def _isolate_expensive_rate_limiter(monkeypatch):
    """
    Prevent the shared sliding-window limiter from leaking 429s across the suite.

    Production still uses the real limiter; test_rate_limit.py constructs its own
    FastAPI app + limiter instance and is unaffected.
    """
    from backend.utils import rate_limit as rl

    monkeypatch.setattr(
        rl,
        "_expensive",
        rl.SlidingWindowRateLimiter(max_requests=50_000, window_seconds=60),
    )
