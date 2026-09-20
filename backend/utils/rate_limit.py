"""Simple in-memory sliding-window rate limiter for public demo endpoints."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1, int(window_seconds))
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True


# Conservative defaults for a public portfolio API on free-tier hosts
_expensive = SlidingWindowRateLimiter(max_requests=20, window_seconds=60)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def limit_expensive_endpoint(request: Request) -> None:
    """FastAPI dependency: 429 when the client exceeds the sliding window."""
    key = _client_key(request)
    if not _expensive.allow(key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a minute before retrying.",
        )
