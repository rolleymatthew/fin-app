from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Type

from app.utils.date_utils import parse_date


class ClassConvertErrException(Exception):
    def __init__(self, obj: Any, target: Type[Any]):
        super().__init__(f"Cannot cast {type(obj)} to {target}")


def set_field_value_by_field_name(obj: Any, field_name: str, value: Any) -> None:
    if value is None:
        return
    if not hasattr(obj, field_name):
        setattr(obj, field_name, value)
        return
    current = getattr(obj, field_name)
    try:
        if isinstance(current, str) or current is None:
            setattr(obj, field_name, str(value))
        elif isinstance(current, int):
            setattr(obj, field_name, int(value))
        elif isinstance(current, float):
            setattr(obj, field_name, float(value))
        elif isinstance(current, bool):
            setattr(obj, field_name, bool(value))
        elif isinstance(current, Decimal):
            setattr(obj, field_name, Decimal(str(value)))
        elif isinstance(current, datetime):
            setattr(obj, field_name, parse_date(str(value)))
        else:
            setattr(obj, field_name, value)
    except Exception:
        setattr(obj, field_name, value)


def get_field_value_by_name(field_name: str, obj: Any) -> Any:
    return getattr(obj, field_name, None)


def cast(obj: Any, target: Type[Any]) -> Any:
    if isinstance(obj, target):
        return obj
    raise ClassConvertErrException(obj, target)
