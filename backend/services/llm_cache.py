"""Content-addressed cache for LLM responses.

At temperature 0 the prompt fully determines the response, so repeating a prompt
only burns latency and provider quota. Measured baseline: ~2.3k tokens per call at
5.6 calls/question exhausts a 200k/day budget in roughly 15 questions.

The key is a hash of the prompt content, so nothing dataset- or session-specific
leaks across entries: a different dataset produces a different prompt, hence a
different key.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

LLM_CACHE_TTL_SECONDS = float(os.getenv("LLM_CACHE_TTL_SECONDS", "1800"))
LLM_CACHE_MAX_ENTRIES = int(os.getenv("LLM_CACHE_MAX_ENTRIES", "256"))
# Above this temperature the model is expected to vary, so caching would be wrong.
LLM_CACHE_MAX_TEMPERATURE = float(os.getenv("LLM_CACHE_MAX_TEMPERATURE", "0.1"))

_CACHE: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()
_LOCK = threading.Lock()
_STATS = {"hits": 0, "misses": 0}


def _message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    role = getattr(message, "type", None)
    if role is None and isinstance(message, dict):
        role = message.get("role")
    return f"{role or ''}:{content or ''}"


def is_cacheable(temperature: float) -> bool:
    return temperature <= LLM_CACHE_MAX_TEMPERATURE


def make_key(messages, temperature: float) -> str:
    blob = "\n".join(_message_text(m) for m in messages)
    digest = hashlib.sha256(blob.encode("utf-8", errors="ignore")).hexdigest()
    return f"{digest}|t={temperature:.2f}"


def get(key: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    with _LOCK:
        item = _CACHE.get(key)
        if not item:
            _STATS["misses"] += 1
            return None
        stored_at, payload = item
        if now - stored_at > LLM_CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            _STATS["misses"] += 1
            return None
        _CACHE.move_to_end(key)
        _STATS["hits"] += 1
        return dict(payload)


def set(key: str, payload: Dict[str, Any]) -> None:
    with _LOCK:
        _CACHE[key] = (time.time(), dict(payload))
        _CACHE.move_to_end(key)
        while len(_CACHE) > LLM_CACHE_MAX_ENTRIES:
            _CACHE.popitem(last=False)


def stats() -> Dict[str, Any]:
    with _LOCK:
        total = _STATS["hits"] + _STATS["misses"]
        return {
            "hits": _STATS["hits"],
            "misses": _STATS["misses"],
            "entries": len(_CACHE),
            "hit_rate": round(_STATS["hits"] / total, 4) if total else 0.0,
        }


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
        _STATS["hits"] = 0
        _STATS["misses"] = 0
