"""Dataset fingerprinting for suggestion cache isolation."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Sequence


def compute_fingerprint(
    *,
    columns: Sequence[Dict[str, Any]],
    row_count: int,
    sample_digest: str = "",
) -> str:
    payload = {
        "row_count": int(row_count),
        "columns": [
            {"name": c.get("name"), "dtype": str(c.get("dtype") or c.get("type") or "")}
            for c in columns
        ],
        "sample_digest": sample_digest or "",
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def sample_digest_from_values(samples: Dict[str, List[Any]], limit: int = 8) -> str:
    parts: List[str] = []
    for col in sorted(samples.keys()):
        vals = samples[col][:limit]
        parts.append(f"{col}=" + ",".join(str(v) for v in vals))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
