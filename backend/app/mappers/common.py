from __future__ import annotations

from datetime import datetime
from typing import Type, TypeVar

from app.utils.transform import normalize_keys

T = TypeVar("T")


def dto_to_entity(dto: dict, entity_cls: Type[T], id_field: str = "id") -> T:
    data = normalize_keys(dto)
    entity = entity_cls.model_validate(data)
    if hasattr(entity, "reportDate") and hasattr(entity, "securityCode"):
        report_date = getattr(entity, "reportDate") or ""
        report_date = report_date.replace(" 00:00:00", "")
        entity_id = f"{getattr(entity, 'securityCode', '')}{report_date}"
        setattr(entity, id_field, entity_id)
    if hasattr(entity, "updatedAt"):
        setattr(entity, "updatedAt", datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    return entity


def dto_to_entity_with_id(dto: dict, entity_cls: Type[T], id_value: str) -> T:
    data = normalize_keys(dto)
    entity = entity_cls.model_validate(data)
    if hasattr(entity, "updatedAt"):
        setattr(entity, "updatedAt", datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    setattr(entity, "id", id_value)
    return entity
