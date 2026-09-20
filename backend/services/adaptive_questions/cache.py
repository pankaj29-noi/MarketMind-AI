"""In-memory suggestion cache keyed by session + dataset + fingerprint."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_TTL_SECONDS = 1800


def _key(session_id: str, dataset_id: str, fingerprint: str) -> str:
    return f"{session_id}|{dataset_id}|{fingerprint}"


def get_cached(session_id: str, dataset_id: str, fingerprint: str) -> Optional[Dict[str, Any]]:
    k = _key(session_id, dataset_id, fingerprint)
    item = _CACHE.get(k)
    if not item:
        return None
    ts, payload = item
    if time.time() - ts > _TTL_SECONDS:
        _CACHE.pop(k, None)
        return None
    return payload


def set_cached(session_id: str, dataset_id: str, fingerprint: str, payload: Dict[str, Any]) -> None:
    _CACHE[_key(session_id, dataset_id, fingerprint)] = (time.time(), payload)


def invalidate_session(session_id: str) -> None:
    dead = [k for k in _CACHE if k.startswith(f"{session_id}|")]
    for k in dead:
        _CACHE.pop(k, None)
