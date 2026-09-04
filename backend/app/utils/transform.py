from __future__ import annotations

import re
from typing import Any


def _to_camel(s: str) -> str:
    if s.isupper():
        s = s.lower()
    if "_" not in s:
        return s[0].lower() + s[1:] if s and s[0].isupper() else s
    parts = s.lower().split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def normalize_keys(data: Any) -> Any:
    if isinstance(data, list):
        return [normalize_keys(x) for x in data]
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            key = _to_camel(k) if isinstance(k, str) else k
            out[key] = normalize_keys(v)
        return out
    return data
