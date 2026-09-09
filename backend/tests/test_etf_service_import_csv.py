"""EtfService._import_szse_csv 单元测试（mock repo，纯逻辑）"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mappers.custom import etf_szse_dto_to_entity
from app.services.etf_service import EtfService


CSV_TEXT = (
    "排名,代码,简称,规模 (亿),管理人\n"
    "1,159792,港股通互联网 ETF 富国,635.36,富国基金\n"
    "2,ABC,BAD_CODE,1.0,X\n"
    "3,159516,半导体设备 ETF 国泰,618.59,国泰基金\n"
).encode("utf-8-sig")


@pytest.mark.asyncio
async def test_import_szse_csv_happy_path():
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_csv(CSV_TEXT, date(2026, 9, 8))

    assert report["imported"] == 2
    assert report["skipped"] == 0
    assert report["stat_date"] == "2026-09-08"

    service.repo.save_many.assert_awaited_once()
    saved_entities = service.repo.save_many.await_args.args[0]
    assert len(saved_entities) == 2
    assert saved_entities[0].secCode == 159792
    assert saved_entities[0].totVol == Decimal("635.36") * Decimal(100000000)
    # 验证 id 唯一键
    assert saved_entities[0].id == "1597922026-09-08"
    assert saved_entities[1].id == "1595162026-09-08"


@pytest.mark.asyncio
async def test_import_szse_csv_empty_returns_zero():
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_csv(b"", date(2026, 9, 8))
    assert report == {"imported": 0, "skipped": 0, "stat_date": "2026-09-08"}
    service.repo.save_many.assert_awaited_once_with([])


@pytest.mark.asyncio
async def test_import_szse_csv_all_invalid_returns_zero():
    bad = "排名,代码,简称,规模 (亿),管理人\n1,ABC,B,bad,X\n".encode("utf-8-sig")
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_csv(bad, date(2026, 9, 8))
    assert report["imported"] == 0
    assert report["skipped"] == 0
