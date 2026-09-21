"""Regression tests for the LLM provider fallback chain.

Baseline failure these lock in (measured 2026-09-21): the chain walked retired
models (qwen/qwen3.6-27b, gemini-2.0-flash, gemini-1.5-flash all 404) and let the
client retry internally on 429, costing up to ~120s for one logical LLM call.
"""
import time
from unittest.mock import patch

import pytest

import backend.config as cfg
from backend.utils.provider_errors import (
    is_model_unavailable_error,
    is_rate_limit_error,
)


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    """Stands in for ChatGroq / ChatGoogleGenerativeAI."""

    def __init__(self, behaviour, model, calls, delay=0.0):
        self.behaviour = behaviour
        self.model = model
        self.calls = calls
        self.delay = delay

    def invoke(self, messages):
        self.calls.append(self.model)
        if self.delay:
            time.sleep(self.delay)
        outcome = self.behaviour.get(self.model, "ok")
        if outcome == "ok":
            return _Resp(f"answer from {self.model}")
        raise RuntimeError(outcome)


def _chain(behaviour, delay=0.0):
    """Run invoke_llm against a fake provider chain; return (result, models_tried)."""
    calls: list[str] = []

    def build(temperature, model=None):
        return _FakeClient(behaviour, model, calls, delay)

    with patch.object(cfg, "_build_groq", build), patch.object(cfg, "_build_gemini", build), patch.object(
        cfg, "has_valid_groq_key", lambda: True
    ), patch.object(cfg, "has_valid_gemini_key", lambda: True):
        try:
            result = cfg.invoke_llm([{"role": "user", "content": "hi"}])
        except RuntimeError as exc:
            result = exc
    return result, calls


def test_retired_models_are_never_attempted():
    """Models known to answer 404 must not cost a round-trip."""
    _, calls = _chain({})
    for retired in ("qwen/qwen3.6-27b", "gemini-2.0-flash", "gemini-1.5-flash"):
        assert retired not in calls, f"retired model {retired} was attempted"


def test_gemini_default_is_a_reachable_model():
    """gemini-2.0-flash returns 404 upstream; the resolved default must not be it."""
    assert cfg.DEFAULT_GEMINI_MODEL not in cfg._RETIRED_GEMINI_MODELS
    assert cfg.GEMINI_FALLBACK_MODEL not in cfg._RETIRED_GEMINI_MODELS
    for model in cfg.GEMINI_MODEL_CANDIDATES:
        assert model not in cfg._RETIRED_GEMINI_MODELS
    for model in cfg.GROQ_MODEL_CANDIDATES:
        assert model not in cfg._RETIRED_GROQ_MODELS


def test_env_configured_retired_model_is_replaced():
    """A stale GEMINI_FALLBACK_MODEL in render.yaml must resolve to a live model."""
    with patch.object(cfg, "_RAW_GEMINI_MODEL", "gemini-2.0-flash"):
        assert cfg.resolve_gemini_model_name() == cfg.DEFAULT_GEMINI_MODEL


def test_rate_limited_primary_falls_through_to_next_model():
    result, calls = _chain({"openai/gpt-oss-120b": "Error code: 429 - rate_limit_exceeded"})
    assert isinstance(result, dict)
    assert result["model"] == "openai/gpt-oss-20b"
    assert calls[0] == "openai/gpt-oss-120b"


def test_chain_stops_at_deadline_instead_of_walking_every_candidate():
    """A degraded provider must not consume the request budget."""
    behaviour = {m: "Error code: 429 - rate limit" for m in cfg.GROQ_MODEL_CANDIDATES}
    behaviour.update({m: "Error code: 429 - RESOURCE_EXHAUSTED" for m in cfg.GEMINI_MODEL_CANDIDATES})

    with patch.object(cfg, "LLM_CHAIN_DEADLINE_SECONDS", 0.25):
        started = time.monotonic()
        result, calls = _chain(behaviour, delay=0.2)
        elapsed = time.monotonic() - started

    assert isinstance(result, RuntimeError)
    assert "All LLM providers failed" in str(result)
    # Without a deadline every candidate would be tried; the budget must cut it short.
    assert len(calls) < len(cfg.GROQ_MODEL_CANDIDATES) + len(cfg.GEMINI_MODEL_CANDIDATES)
    assert elapsed < 1.0, f"chain took {elapsed:.2f}s despite a 0.25s deadline"


def test_clients_are_built_with_timeout_and_no_internal_retries():
    """langchain clients retry with backoff by default; that caused 45s single calls."""
    assert cfg.LLM_MAX_RETRIES == 0
    assert 0 < cfg.LLM_REQUEST_TIMEOUT_SECONDS <= 60
    assert 0 < cfg.LLM_CHAIN_DEADLINE_SECONDS <= 120

    captured = {}

    class _Probe:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with patch.dict("sys.modules"):
        import langchain_groq

        with patch.object(langchain_groq, "ChatGroq", _Probe):
            cfg._build_groq(0.0, model="openai/gpt-oss-120b")

    assert captured["timeout"] == cfg.LLM_REQUEST_TIMEOUT_SECONDS
    assert captured["max_retries"] == cfg.LLM_MAX_RETRIES


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 429 - rate_limit_exceeded",
        "429 RESOURCE_EXHAUSTED",
        "Rate limit reached for model ... tokens per day (TPD)",
    ],
)
def test_rate_limit_detection(message):
    assert is_rate_limit_error(message)
    assert not is_model_unavailable_error(message)


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 404 - model_not_found",
        "The model `qwen/qwen3.6-27b` does not exist or you do not have access to it.",
        "This model models/gemini-2.0-flash is no longer available.",
    ],
)
def test_model_unavailable_detection(message):
    assert is_model_unavailable_error(message)
