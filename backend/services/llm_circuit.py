"""Per-provider circuit breaker for LLM calls.

Measured problem: when Groq's daily token budget is exhausted, every node in a
request still attempts the provider. At ~1.4s per failed attempt and 7-8 calls per
question that is ~10s of pure waiting before the deterministic fallback runs.

Once a provider reports a rate limit, it will keep reporting it for a while, so the
breaker skips that provider until the cooldown expires. Any success closes it.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Dict, Optional

LLM_COOLDOWN_SECONDS = float(os.getenv("LLM_COOLDOWN_SECONDS", "60"))
LLM_COOLDOWN_MIN_SECONDS = float(os.getenv("LLM_COOLDOWN_MIN_SECONDS", "1"))
LLM_COOLDOWN_MAX_SECONDS = float(os.getenv("LLM_COOLDOWN_MAX_SECONDS", "900"))

_OPEN_UNTIL: Dict[str, float] = {}
_LOCK = threading.Lock()

# Groq reports "Please try again in 2m54.96s"; Gemini uses "retryDelay": "31s".
_RETRY_AFTER_PATTERNS = (
    re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.I),
    re.compile(r"retry\w*delay\W+(\d+)s", re.I),
)


def parse_retry_after(error_message: str) -> Optional[float]:
    """Seconds the provider asked us to wait, when it says so."""
    text = error_message or ""
    match = _RETRY_AFTER_PATTERNS[0].search(text)
    if match:
        minutes = float(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return minutes * 60 + seconds
    match = _RETRY_AFTER_PATTERNS[1].search(text)
    if match:
        return float(match.group(1))
    return None


def is_open(provider: str) -> bool:
    """True when the provider should be skipped entirely."""
    with _LOCK:
        until = _OPEN_UNTIL.get(provider)
        if until is None:
            return False
        if time.monotonic() >= until:
            _OPEN_UNTIL.pop(provider, None)
            return False
        return True


def cooldown_remaining(provider: str) -> float:
    with _LOCK:
        until = _OPEN_UNTIL.get(provider)
        return max(0.0, until - time.monotonic()) if until else 0.0


def trip(provider: str, error_message: str = "") -> float:
    """Open the breaker, honouring the provider's own retry hint when present."""
    wait = parse_retry_after(error_message) or LLM_COOLDOWN_SECONDS
    wait = min(max(wait, LLM_COOLDOWN_MIN_SECONDS), LLM_COOLDOWN_MAX_SECONDS)
    with _LOCK:
        _OPEN_UNTIL[provider] = time.monotonic() + wait
    return wait


def reset(provider: str) -> None:
    with _LOCK:
        _OPEN_UNTIL.pop(provider, None)


def clear() -> None:
    with _LOCK:
        _OPEN_UNTIL.clear()


def state() -> Dict[str, float]:
    with _LOCK:
        now = time.monotonic()
        return {p: round(max(0.0, until - now), 1) for p, until in _OPEN_UNTIL.items()}
