from __future__ import annotations

from typing import List

from app.models.entities import HKItemRow


def parse_hk_amount(text: str | None) -> float | None:
    if text is None or str(text).strip() in ("--", ""):
        return None
    try:
        return float(str(text).strip())
    except (ValueError, TypeError):
        return None


def parse_hk_amount_to_yi(text: str | None) -> float | None:
    val = parse_hk_amount(text)
    if val is None:
        return None
    return round(val / 1e8, 2)


def get_item_amount(items: List[HKItemRow] | None, item_code: str) -> float | None:
    if not items:
        return None
    for item in items:
        if item.itemCode == item_code:
            return parse_hk_amount(item.amount)
    return None


def get_item_amount_to_yi(items: List[HKItemRow] | None, item_code: str) -> float | None:
    if not items:
        return None
    for item in items:
        if item.itemCode == item_code:
            return parse_hk_amount_to_yi(item.amount)
    return None


def get_item_amount_str(items: List[HKItemRow] | None, item_code: str) -> str | None:
    if not items:
        return None
    for item in items:
        if item.itemCode == item_code:
            return item.amount
    return None
