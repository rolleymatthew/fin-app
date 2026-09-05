from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_double(d: float) -> float:
    try:
        return float(f"{d:.2f}")
    except Exception:
        return 0.0


def string_to_double(num: str | None) -> float:
    try:
        return float(num) if num is not None else 0.0
    except Exception:
        return 0.0


def add(*params: Decimal) -> Decimal:
    total = Decimal(0)
    for p in params:
        total += p if p is not None else Decimal(0)
    return total


def double_compare_zero(value: float) -> bool:
    return value > 0


def devide(amount: str, vol: str) -> Decimal:
    try:
        if amount and vol:
            v = Decimal(vol)
            if v != 0:
                return (Decimal(amount) / v).quantize(Decimal("0.000"), rounding=ROUND_HALF_UP)
    except Exception:
        pass
    return Decimal(0)
