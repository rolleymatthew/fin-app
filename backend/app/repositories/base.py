from __future__ import annotations

from decimal import Decimal
from typing import Any, Generic, Iterable, List, Type, TypeVar

from bson.decimal128 import Decimal128

from app.db import get_db


T = TypeVar("T")


def _collection_name(model: Type[Any], override: str | None) -> str:
    if override:
        return override
    if hasattr(model, "__collection__") and model.__collection__:
        return model.__collection__
    raise ValueError("Collection name is required")


class MongoRepository(Generic[T]):
    def __init__(self, model: Type[T], collection: str | None = None):
        self.model = model
        self.collection_name = _collection_name(model, collection)
        self._collection = get_db()[self.collection_name]

    @property
    def collection(self):
        return self._collection

    def _to_bson(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return Decimal128(value)
        if isinstance(value, dict):
            return {k: self._to_bson(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._to_bson(v) for v in value]
        if isinstance(value, tuple):
            return [self._to_bson(v) for v in value]
        return value

    def _from_bson(self, value: Any) -> Any:
        if isinstance(value, Decimal128):
            return value.to_decimal()
        if isinstance(value, dict):
            return {k: self._from_bson(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._from_bson(v) for v in value]
        if isinstance(value, tuple):
            return [self._from_bson(v) for v in value]
        return value

    async def save(self, entity: T) -> T:
        if hasattr(entity, "model_dump"):
            doc = entity.model_dump(by_alias=True, exclude_none=True)
        else:
            doc = entity
        doc = self._to_bson(doc)
        _id = doc.get("_id") or doc.get("id")
        if _id is not None:
            doc["_id"] = _id
            await self.collection.replace_one({"_id": _id}, doc, upsert=True)
        else:
            await self.collection.insert_one(doc)
        return entity

    async def save_many(self, entities: Iterable[T]) -> None:
        for e in entities:
            await self.save(e)

    async def find_by_id(self, _id: str) -> T | None:
        doc = await self.collection.find_one({"_id": _id})
        if not doc:
            return None
        return self.model.model_validate(self._from_bson(doc))

    async def delete_by_id(self, _id: str) -> None:
        await self.collection.delete_one({"_id": _id})

    async def find_all(self) -> List[T]:
        ret = []
        async for doc in self.collection.find({}):
            ret.append(self.model.model_validate(self._from_bson(doc)))
        return ret

    async def find_all_by_security_code_order_by_report_date_desc(self, security_code: str) -> List[T]:
        cursor = self.collection.find({"securityCode": security_code}).sort("reportDate", -1)
        ret = []
        async for doc in cursor:
            ret.append(self.model.model_validate(self._from_bson(doc)))
        return ret

    async def find_all_by_sec_code(self, sec_code: int) -> List[T]:
        cursor = self.collection.find({"secCode": sec_code})
        ret = []
        async for doc in cursor:
            ret.append(self.model.model_validate(self._from_bson(doc)))
        return ret
