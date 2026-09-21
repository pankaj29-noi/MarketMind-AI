"""Tests for the per-provider LLM circuit breaker.

Measured problem this addresses: with Groq's daily budget exhausted, a single
question still made 7-8 provider attempts at ~1.4s each (~10s wasted per question)
before falling back to deterministic SQL.
"""
from unittest.mock import patch

import pytest

import backend.config as cfg
from backend.services import llm_cache, llm_circuit

RATE_LIMIT_MSG = (
    "Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` ... "
    "tokens per day (TPD): Limit 200000, Used 199777. Please try again in 2m54.96s."
)


@pytest.fixture(autouse=True)
def _reset():
    llm_circuit.clear()
    llm_cache.clear()
    yield
    llm_circuit.clear()
    llm_cache.clear()


def _always_rate_limited(calls):
    def build(temperature, model=None):
        class _C:
            def invoke(self, messages):
                calls.append(model)
                raise RuntimeError(RATE_LIMIT_MSG)

        return _C()

    return build


def test_retry_after_is_parsed_from_groq_message():
    assert llm_circuit.parse_retry_after(RATE_LIMIT_MSG) == pytest.approx(174.96, abs=0.1)


def test_retry_after_is_parsed_from_gemini_message():
    assert llm_circuit.parse_retry_after('{"retryDelay": "31s"}') == 31.0


def test_missing_retry_hint_falls_back_to_default_cooldown():
    assert llm_circuit.parse_retry_after("429 too many requests") is None
    waited = llm_circuit.trip("Groq", "429 too many requests")
    assert waited == llm_circuit.LLM_COOLDOWN_SECONDS


def test_cooldown_is_capped():
    waited = llm_circuit.trip("Groq", "Please try again in 600m0s")
    assert waited <= llm_circuit.LLM_COOLDOWN_MAX_SECONDS


def test_second_request_skips_a_cooling_provider():
    calls = []
    build = _always_rate_limited(calls)

    with patch.object(cfg, "_build_groq", build), patch.object(
        cfg, "has_valid_groq_key", lambda: True
    ), patch.object(cfg, "has_valid_gemini_key", lambda: False):
        with pytest.raises(RuntimeError):
            cfg.invoke_llm([{"role": "user", "content": "q1"}])
        first_round = len(calls)

        with pytest.raises(RuntimeError):
            cfg.invoke_llm([{"role": "user", "content": "q2"}])
        second_round = len(calls) - first_round

    assert first_round == len(cfg.GROQ_MODEL_CANDIDATES)
    assert second_round == 0, "a cooling provider must not be retried"
    assert llm_circuit.is_open("Groq")


def test_a_success_closes_the_breaker():
    llm_circuit.trip("Groq", RATE_LIMIT_MSG)
    assert llm_circuit.is_open("Groq")

    class _Resp:
        content = "ok"

    def build(temperature, model=None):
        class _C:
            def invoke(self, messages):
                return _Resp()

        return _C()

    with patch.object(cfg, "_build_groq", build), patch.object(
        cfg, "has_valid_groq_key", lambda: True
    ), patch.object(llm_circuit, "is_open", lambda provider: False):
        cfg.invoke_llm([{"role": "user", "content": "q"}])

    assert not llm_circuit.is_open("Groq")


def test_expired_cooldown_reopens_the_provider():
    with patch.object(llm_circuit, "LLM_COOLDOWN_SECONDS", 0.05), patch.object(
        llm_circuit, "LLM_COOLDOWN_MIN_SECONDS", 0.01
    ):
        llm_circuit.trip("Groq", "429 rate limit")
    assert llm_circuit.is_open("Groq")
    import time

    time.sleep(0.06)
    assert not llm_circuit.is_open("Groq")


def test_breaker_is_per_provider():
    llm_circuit.trip("Groq", RATE_LIMIT_MSG)
    assert llm_circuit.is_open("Groq")
    assert not llm_circuit.is_open("Gemini"), "Gemini must stay usable when Groq is limited"


def test_non_rate_limit_failures_do_not_trip_the_breaker():
    calls = []

    def build(temperature, model=None):
        class _C:
            def invoke(self, messages):
                calls.append(model)
                raise RuntimeError("Error code: 404 - model_not_found")

        return _C()

    with patch.object(cfg, "_build_groq", build), patch.object(
        cfg, "has_valid_groq_key", lambda: True
    ), patch.object(cfg, "has_valid_gemini_key", lambda: False):
        with pytest.raises(RuntimeError):
            cfg.invoke_llm([{"role": "user", "content": "q"}])

    assert not llm_circuit.is_open("Groq")
