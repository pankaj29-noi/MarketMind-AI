"""Tests for the content-addressed LLM response cache."""
from unittest.mock import patch

import pytest

import backend.config as cfg
from backend.services import llm_cache


class _Resp:
    def __init__(self, content):
        self.content = content


@pytest.fixture(autouse=True)
def _clear_cache():
    llm_cache.clear()
    yield
    llm_cache.clear()


def _chain(counter, content="SELECT 1"):
    def build(temperature, model=None):
        class _C:
            def invoke(self, messages):
                counter.append(model)
                return _Resp(content)

        return _C()

    return patch.object(cfg, "_build_groq", build), patch.object(cfg, "has_valid_groq_key", lambda: True)


def test_identical_prompt_is_served_from_cache():
    calls = []
    build_patch, key_patch = _chain(calls)
    messages = [{"role": "user", "content": "total revenue by region"}]

    with build_patch, key_patch:
        first = cfg.invoke_llm(messages, temperature=0.0)
        second = cfg.invoke_llm(messages, temperature=0.0)

    assert len(calls) == 1, "second identical prompt must not hit the provider"
    assert first["content"] == second["content"]
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


def test_different_prompt_is_not_served_from_cache():
    calls = []
    build_patch, key_patch = _chain(calls)

    with build_patch, key_patch:
        cfg.invoke_llm([{"role": "user", "content": "dataset A question"}], temperature=0.0)
        cfg.invoke_llm([{"role": "user", "content": "dataset B question"}], temperature=0.0)

    assert len(calls) == 2


def test_high_temperature_is_never_cached():
    calls = []
    build_patch, key_patch = _chain(calls)
    messages = [{"role": "user", "content": "suggest a chart"}]

    with build_patch, key_patch:
        cfg.invoke_llm(messages, temperature=0.7)
        cfg.invoke_llm(messages, temperature=0.7)

    assert len(calls) == 2, "non-deterministic sampling must not be cached"


def test_temperature_is_part_of_the_key():
    calls = []
    build_patch, key_patch = _chain(calls)
    messages = [{"role": "user", "content": "same prompt"}]

    with build_patch, key_patch:
        cfg.invoke_llm(messages, temperature=0.0)
        cfg.invoke_llm(messages, temperature=0.1)

    assert len(calls) == 2


def test_cache_evicts_beyond_max_entries():
    with patch.object(llm_cache, "LLM_CACHE_MAX_ENTRIES", 3):
        for i in range(5):
            llm_cache.set(f"k{i}", {"content": str(i)})
    assert llm_cache.stats()["entries"] <= 3
    assert llm_cache.get("k0") is None
    assert llm_cache.get("k4") is not None


def test_expired_entries_are_dropped():
    with patch.object(llm_cache, "LLM_CACHE_TTL_SECONDS", -1):
        llm_cache.set("stale", {"content": "old"})
        assert llm_cache.get("stale") is None


def test_stats_report_hit_rate():
    llm_cache.set("k", {"content": "v"})
    llm_cache.get("k")
    llm_cache.get("missing")
    stats = llm_cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
