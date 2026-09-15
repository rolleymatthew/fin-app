"""EtfService._import_szse_json 单元测试（mock repo，纯逻辑）

复测：与 CSV 路径同构，只是数据源从 csv bytes 换成 json bytes。
- happy path: 2 行有效 + 1 行 code 非法 → imported=2 skipped=0 (mapper 已剔除)
- 空文件 / 全部非法 → imported=0 skipped=0
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.etf_service import EtfService


def _json_bytes(items: list[dict]) -> bytes:
    return json.dumps(items, ensure_ascii=False).encode("utf-8")


@pytest.mark.asyncio
async def test_import_szse_json_happy_path():
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    valid = _json_bytes([
        {"code": "159792", "name": "港股通互联网ETF富国", "scale": "635.36", "mgr": "富国基金"},
        {"code": "ABC", "name": "BAD_CODE", "scale": "1.0", "mgr": "X"},
        {"code": "159516", "name": "半导体设备ETF国泰", "scale": "618.59", "mgr": "国泰基金"},
    ])

    report = await service._import_szse_json(valid, date(2026, 9, 9))

    assert report["imported"] == 2
    assert report["skipped"] == 0
    assert report["stat_date"] == "2026-09-09"

    service.repo.save_many.assert_awaited_once()
    saved_entities = service.repo.save_many.await_args.args[0]
    assert len(saved_entities) == 2
    assert saved_entities[0].secCode == 159792
    assert saved_entities[0].totVol == Decimal("635.36") * Decimal(100000000)
    assert saved_entities[0].id == "1597922026-09-09"
    assert saved_entities[1].id == "1595162026-09-09"


@pytest.mark.asyncio
async def test_import_szse_json_empty_returns_zero():
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_json(b"", date(2026, 9, 9))
    assert report == {"imported": 0, "skipped": 0, "stat_date": "2026-09-09"}
    service.repo.save_many.assert_awaited_once_with([])


@pytest.mark.asyncio
async def test_import_szse_json_all_invalid_returns_zero():
    bad = _json_bytes([
        {"code": "ABC", "name": "B", "scale": "bad", "mgr": "X"},
    ])
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_json(bad, date(2026, 9, 9))
    assert report["imported"] == 0
    assert report["skipped"] == 0
