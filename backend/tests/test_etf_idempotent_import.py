"""EtfService._import_szse_json 幂等性专项测试

实测：同一份 JSON 重复导入应等价于"覆盖"而不是"复制多份"。
- 第一次：无数据 → insert N 条
- 第二次（bytes 完全相同）：replace_one 命中 → DB 文档数仍为 N，totVol 不变
- 第三次（bytes scale 改了）：replace_one 替换 → DB 文档数仍为 N，totVol 更新为新值

不在 mock save 层（那只能验证 mapper 设 id），而是给 MongoRepository.collection
塞一个支持 replace_one/insert_one/count_documents 的 FakeCollection，验证 DB 层的 upsert 行为。
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128


class FakeUpsertCollection:
    """最小子集：replace_one(upsert=True) / insert_one / count_documents"""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    async def replace_one(self, query: dict, doc: dict, upsert: bool = False):
        _id = query.get("_id") or doc.get("_id")
        if _id in self._docs:
            self._docs[_id] = dict(doc)
            return ("updated", 1)
        if upsert:
            self._docs[_id] = dict(doc)
            return ("inserted", 1)
        return ("noop", 0)

    async def insert_one(self, doc: dict):
        _id = doc.get("_id")
        if _id in self._docs:
            raise RuntimeError(f"duplicate _id: {_id}")
        self._docs[_id] = dict(doc)

    async def count_documents(self, query: dict) -> int:
        if not query:
            return len(self._docs)
        n = 0
        for d in self._docs.values():
            if all(d.get(k) == v for k, v in query.items()):
                n += 1
        return n

    def get(self, _id: str) -> dict | None:
        return deepcopy(self._docs.get(_id))


def _to_bson(value):
    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, dict):
        return {k: _to_bson(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_bson(v) for v in value]
    if isinstance(value, tuple):
        return [_to_bson(v) for v in value]
    return value


def _make_save_many(collection: FakeUpsertCollection):
    """复制 MongoRepository.save 的最小实现：replace_one({"_id": _id}, doc, upsert=True)。"""

    async def _save(self, entity):
        doc = entity.model_dump(by_alias=True, exclude_none=True)
        doc = _to_bson(doc)
        _id = doc.get("_id") or doc.get("id")
        if _id is not None:
            doc["_id"] = _id
            await collection.replace_one({"_id": _id}, doc, upsert=True)

    async def _save_many(self, entities):
        for e in entities:
            await _save(self, e)

    return _save, _save_many


def _bytes_for(rows: list[dict]) -> bytes:
    return json.dumps(rows, ensure_ascii=False).encode("utf-8")


SAMPLE_ROWS = [
    {"code": "159001", "name": "货币ETF易方达", "scale": "0.32", "mgr": "易方达"},
    {"code": "159002", "name": "债券ETF", "scale": "1.50", "mgr": "管理人B"},
    {"code": "159792", "name": "港股通互联网ETF富国", "scale": "635.36", "mgr": "富国"},
]


def _make_service():
    """构造一个 EtfService，把 repo 替换成 FakeCollection 支撑的版本。"""
    from app.services.etf_service import EtfService

    collection = FakeUpsertCollection()
    _save, _save_many = _make_save_many(collection)

    svc = EtfService.__new__(EtfService)
    svc.repo = type(
        "Repo",
        (),
        {
            "collection": collection,
            "save": _save,
            "save_many": _save_many,
        },
    )()
    svc.kline_repo = type("KR", (), {"collection": FakeUpsertCollection(), "save": None})()
    svc.kline_service = type("KS", (), {})()
    svc.quarter_repo = type("QR", (), {"collection": FakeUpsertCollection(), "save": None})()
    svc.sse = type("SSE", (), {})()
    svc.szse = type("SZSE", (), {})()
    svc.gmbd = type("GMBD", (), {})()
    return svc, collection


@pytest.mark.asyncio
async def test_same_day_repeated_import_keeps_single_document():
    """同日重复导入：DB 文档数仍为 3，totVol 不变（幂等 no-op）。"""
    svc, collection = _make_service()

    content = _bytes_for(SAMPLE_ROWS)
    r1 = await svc._import_szse_json(content, date(2026, 9, 10))
    assert r1["imported"] == 3
    assert r1["skipped"] == 0
    assert await collection.count_documents({}) == 3

    # 完全相同的 bytes 再跑一次
    r2 = await svc._import_szse_json(content, date(2026, 9, 10))
    assert r2["imported"] == 3
    assert r2["skipped"] == 0
    assert await collection.count_documents({}) == 3  # 没有复制多份

    # totVol 还是原值
    doc = collection.get("1590012026-09-10")
    assert doc["totVol"].to_decimal() == Decimal("32000000")  # 0.32 * 10^8


@pytest.mark.asyncio
async def test_same_day_updated_scale_overwrites_existing():
    """同日 scale 变化：DB 文档数仍为 3，totVol 被覆盖到新值。"""
    svc, collection = _make_service()

    await svc._import_szse_json(_bytes_for(SAMPLE_ROWS), date(2026, 9, 10))
    assert await collection.count_documents({}) == 3
    assert collection.get("1590012026-09-10")["totVol"].to_decimal() == Decimal("32000000")

    # 同日 scale 改了
    updated_rows = [
        {"code": "159001", "name": "货币ETF易方达", "scale": "9.99", "mgr": "易方达"},
        {"code": "159002", "name": "债券ETF", "scale": "2.50", "mgr": "管理人B"},
        {"code": "159792", "name": "港股通互联网ETF富国", "scale": "700.00", "mgr": "富国"},
    ]
    r = await svc._import_szse_json(_bytes_for(updated_rows), date(2026, 9, 10))
    assert r["imported"] == 3
    assert await collection.count_documents({}) == 3  # 仍是 3 份

    assert collection.get("1590012026-09-10")["totVol"].to_decimal() == Decimal("999000000")
    assert collection.get("1590022026-09-10")["totVol"].to_decimal() == Decimal("250000000")
    assert collection.get("1597922026-09-10")["totVol"].to_decimal() == Decimal("70000000000")


@pytest.mark.asyncio
async def test_different_dates_create_distinct_documents():
    """不同日期：secCode 相同也不冲突（_id 含 statDate）。"""
    svc, collection = _make_service()

    await svc._import_szse_json(_bytes_for(SAMPLE_ROWS), date(2026, 9, 10))
    await svc._import_szse_json(_bytes_for(SAMPLE_ROWS), date(2026, 9, 11))
    await svc._import_szse_json(_bytes_for(SAMPLE_ROWS), date(2026, 9, 12))

    assert await collection.count_documents({}) == 9  # 3 days * 3 codes
    assert await collection.count_documents({"statDate": "2026-09-10"}) == 3
    assert await collection.count_documents({"statDate": "2026-09-11"}) == 3
    assert await collection.count_documents({"secCode": 159001}) == 3


@pytest.mark.asyncio
async def test_id_format_is_seccode_concat_statdate():
    """_id 格式 = secCode + statDate（无分隔符）。这是 upsert 幂等键。"""
    svc, collection = _make_service()

    await svc._import_szse_json(_bytes_for(SAMPLE_ROWS), date(2026, 9, 10))

    assert collection.get("1590012026-09-10") is not None
    assert collection.get("1590022026-09-10") is not None
    assert collection.get("1597922026-09-10") is not None
    assert collection.get("159001") is None  # 没有 statDate 不会是 _id

