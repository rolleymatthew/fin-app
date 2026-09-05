from __future__ import annotations

import json
from typing import Any, TypeVar

T = TypeVar("T")


def to_json(obj: Any) -> str | None:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return None


def to_object(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def to_list(text: str) -> list[Any]:
    if not text:
        return []
    try:
        return json.loads(text)
    except Exception:
        return []


def get_seg_from_json(json_str: str, key: str) -> str | None:
    try:
        data = json.loads(json_str)
        if key not in data:
            return None
        return json.dumps(data[key], ensure_ascii=False)
    except Exception:
        raise
