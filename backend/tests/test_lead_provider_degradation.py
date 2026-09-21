"""Hermetic tests for Lead Intelligence behaviour when the LLM provider is degraded.

Baseline bug (measured 2026-09-21): a Groq 429 made requirement_parser_node return
workflow_status='failed' even though a deterministic extractor could read the same
requirement. These tests mock the provider so they never depend on live quota.
"""
from unittest.mock import patch

import pytest

import backend.marketplace.lead.nodes as lead_nodes
from backend.marketplace.lead.demo_extractor import EXTRACTION_SOURCE_DEMO

RATE_LIMIT = RuntimeError(
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` ... tokens per day (TPD): Limit 200000, Used 199777'}}"
)

CLEAR_REQUIREMENT = "Need 500 solar panels in Jaipur within two weeks"


def _parse(text, error):
    """Run the parser node with a provider that always raises `error`."""

    def boom(temperature=0.0):
        raise error

    with patch.object(lead_nodes, "get_llm", boom), patch(
        "backend.config.use_lead_demo_extraction", lambda: False
    ), patch("backend.config.has_valid_llm_api_key", lambda: True):
        return lead_nodes.requirement_parser_node({"requirement_text": text})


def test_rate_limited_provider_degrades_to_deterministic_extractor():
    out = _parse(CLEAR_REQUIREMENT, RATE_LIMIT)

    assert out["workflow_status"] == "running", "a 429 must not sink a parseable requirement"
    assert out["error"] is None
    extracted = out["extracted_requirement"]
    assert extracted is not None
    assert extracted["extraction_source"] == EXTRACTION_SOURCE_DEMO
    assert extracted["degraded_from_llm"] is True
    assert extracted["quantity"] == 500
    assert "solar" in (extracted["product_name"] or "").lower()


def test_degraded_extraction_still_enriches_city_to_state():
    out = _parse(CLEAR_REQUIREMENT, RATE_LIMIT)
    extracted = out["extracted_requirement"]
    assert (extracted.get("city") or "").lower() == "jaipur"
    assert extracted.get("state"), "city→state enrichment must survive the degraded path"


@pytest.mark.parametrize(
    "error",
    [
        RATE_LIMIT,
        RuntimeError("Error code: 404 - model_not_found"),
        RuntimeError("All LLM providers failed: groq[...]:timeout"),
    ],
)
def test_any_provider_failure_degrades_rather_than_fails(error):
    out = _parse(CLEAR_REQUIREMENT, error)
    assert out["workflow_status"] == "running"


def test_unparseable_requirement_still_fails_honestly():
    """Degradation must not turn an unreadable requirement into a fake success."""
    out = _parse("zzzz", RATE_LIMIT)
    assert out["workflow_status"] == "failed"
    assert out["stop_reason"] == "extraction_failed"
    assert "rate limit" in (out["error"] or "").lower()


def test_error_message_never_leaks_provider_internals():
    out = _parse("zzzz", RATE_LIMIT)
    message = out["error"] or ""
    for secret in ("org_01m19yk998e7rvpnxxmy1vezf5", "console.groq.com/settings/billing"):
        assert secret not in message
