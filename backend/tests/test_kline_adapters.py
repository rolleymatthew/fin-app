"""Tests for unified kline adapter."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.factory import build_aggregator
from app.clients.kline.sina_adapter import SinaAdapter
from app.clients.kline.tencent_adapter import TencentAdapter
from app.clients.kline.types import (
    FQT,
    PERIOD,
    SOURCE,
    FetchResult,
    KLineRow,
)


def _row(date, o, c, h, lo, v, amt=None, turnover=None):
    return KLineRow(
        date=date, open=o, close=c, high=h, low=lo,
        volume=v, amount=amt, turnover=turnover,
    )


# ------------------- KLineRow -------------------


def test_klinerow_defaults_optional_fields():
    r = KLineRow(date="20260105", open=1.0, close=1.0, high=1.0, low=1.0, volume=100)
    assert r.amount is None
    assert r.turnover is None


# ------------------- THS Adapter removed (2026-09-02) -------------------
# THS 适配器已下线, 增量场景改用腾讯主源 (existing 优先保留 11 字段).
# THS 专项测试随 ths_adapter.py 一起删除.


# ------------------- KLineRow -------------------


def test_klinerow_defaults_optional_fields():
    r = KLineRow(date="20260105", open=1.0, close=1.0, high=1.0, low=1.0, volume=100)
    assert r.amount is None
    assert r.turnover is None


# ------------------- Tencent Adapter -------------------


def _fake_tencent_response(date="2026-07-28", o="7.608", c="7.463",
                          h="7.647", lo="7.429", v="7990759.000"):
    return {
        "code": 0,
        "msg": "",
        "data": {
            "sh510500": {
                "qfqday": [
                    [date, o, c, h, lo, v],
                ]
            }
        },
    }


async def test_tencent_parses_qfq_row():
    adapter = TencentAdapter()
    fake_response = MagicMock()
    fake_response.json = MagicMock(return_value=_fake_tencent_response())
    fake_response.raise_for_status = MagicMock()
    with patch.object(adapter, "_get", AsyncMock(return_value=fake_response)):
        rows = await adapter.fetch(
            symbol="sh510500", period=PERIOD.DAY, fqt=FQT.QFQ, limit=5
        )
    assert len(rows) == 1
    r = rows[0]
    assert r.date == "2026-07-28"
    assert r.open == 7.608
    assert r.close == 7.463
    assert r.high == 7.647
    assert r.low == 7.429
    assert r.volume == 7990759 * 100  # 手 -> 股
    assert r.amount is None
    assert r.turnover is None


async def test_tencent_returns_empty_when_data_missing():
    adapter = TencentAdapter()
    fake_response = MagicMock()
    fake_response.json = MagicMock(return_value={"code": 0, "data": {"sh510500": {}}})
    fake_response.raise_for_status = MagicMock()
    with patch.object(adapter, "_get", AsyncMock(return_value=fake_response)):
        rows = await adapter.fetch(
            symbol="sh510500", period=PERIOD.DAY, fqt=FQT.QFQ, limit=5
        )
    assert rows == []


# ------------------- Sina Adapter -------------------


def _fake_sina_response():
    return json.dumps([
        {"day": "2026-07-28", "open": "7.608", "close": "7.463",
         "high": "7.647", "low": "7.429", "volume": "799075944"},
        {"day": "2026-07-29", "open": "7.460", "close": "7.540",
         "high": "7.593", "low": "7.342", "volume": "701473321"},
    ])


async def test_sina_parses_daily_row():
    adapter = SinaAdapter()
    fake_response = MagicMock()
    fake_response.json = MagicMock(return_value=json.loads(_fake_sina_response()))
    fake_response.raise_for_status = MagicMock()
    with patch.object(adapter, "_get", AsyncMock(return_value=fake_response)):
        rows = await adapter.fetch(
            symbol="sh510500", period=PERIOD.DAY, fqt=FQT.NONE, limit=5
        )
    assert len(rows) == 2
    assert rows[0].date == "2026-07-28"
    assert rows[0].volume == 799075944
    assert rows[0].amount is None


async def test_sina_handles_null_response():
    adapter = SinaAdapter()
    fake_response = MagicMock()
    fake_response.json = MagicMock(return_value=None)
    fake_response.raise_for_status = MagicMock()
    with patch.object(adapter, "_get", AsyncMock(return_value=fake_response)):
        rows = await adapter.fetch(
            symbol="sh510500", period=PERIOD.DAY, fqt=FQT.NONE, limit=5
        )
    assert rows == []


# ------------------- Aggregator (primary + fallback chain) -------------------


class _StubAdapter:
    def __init__(self, source, rows, raise_exc=None):
        self.source = source
        self._rows = rows
        self._raise = raise_exc
        self.calls = []

    async def fetch(self, symbol, period, fqt, limit):
        self.calls.append((symbol, period, fqt, limit))
        if self._raise is not None:
            raise self._raise
        return self._rows


async def test_aggregator_returns_primary_when_ok():
    primary = _StubAdapter(SOURCE.TENCENT, [_row("20260105", 1, 1, 1, 1, 100)])
    fallback = _StubAdapter(SOURCE.SINA, [_row("20260105", 2, 2, 2, 2, 200)])
    agg = KLineAggregator(primary=primary, fallbacks=[fallback])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert isinstance(result, FetchResult)
    assert result.source == SOURCE.TENCENT
    assert result.fell_back is False
    assert len(result.rows) == 1
    assert result.rows[0].open == 1
    assert len(primary.calls) == 1
    assert fallback.calls == []


async def test_aggregator_falls_back_when_primary_empty():
    primary = _StubAdapter(SOURCE.TENCENT, [])
    fallback = _StubAdapter(SOURCE.SINA, [_row("20260105", 2, 2, 2, 2, 200)])
    agg = KLineAggregator(primary=primary, fallbacks=[fallback])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert result.source == SOURCE.SINA
    assert result.fell_back is True
    assert len(result.rows) == 1


async def test_aggregator_falls_back_when_primary_raises():
    primary = _StubAdapter(SOURCE.TENCENT, [], raise_exc=RuntimeError("primary down"))
    fallback = _StubAdapter(SOURCE.SINA, [_row("20260105", 2, 2, 2, 2, 200)])
    agg = KLineAggregator(primary=primary, fallbacks=[fallback])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert result.source == SOURCE.SINA
    assert result.fell_back is True


async def test_aggregator_returns_empty_when_all_fail():
    primary = _StubAdapter(SOURCE.TENCENT, [])
    fallback = _StubAdapter(SOURCE.SINA, [], raise_exc=RuntimeError("down"))
    agg = KLineAggregator(primary=primary, fallbacks=[fallback])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert result.source is None
    assert result.rows == []
    assert result.error is not None


# ------------------- Factory -------------------


def test_factory_builds_aggregator_from_config(monkeypatch):
    from app.clients.kline import factory
    monkeypatch.setattr(factory, "_build_adapter", lambda source: _StubAdapter(source, []))
    agg = build_aggregator(primary="tencent", fallbacks=["eastmoney", "sina"])
    assert isinstance(agg, KLineAggregator)
    assert agg.primary_source == SOURCE.TENCENT
    assert agg.fallback_sources == [SOURCE.EASTMONEY, SOURCE.SINA]


def test_factory_rejects_unknown_source():
    try:
        build_aggregator(primary="bogus", fallbacks=[])
    except ValueError as e:
        assert "bogus" in str(e)
    else:
        pytest.fail("expected ValueError")


# ------------------- Eastmoney Adapter -------------------


def _em_kline_text(rows: list[str], name: str = "中证500ETF") -> str:
    import json
    return json.dumps({
        "rc": 0, "rt": 17, "data": {
            "code": "510500", "market": 1, "name": name,
            "decimal": 3, "klines": rows,
        }
    })


async def test_eastmoney_parses_full_11_fields():
    from app.clients.kline.eastmoney_adapter import EastmoneyAdapter
    adapter = EastmoneyAdapter()
    # f51..f61 顺序: date, open, close, high, low, vol, amount, amplitude,
    #               amountOfIncrease, upDownAmount, turnOver
    raw = ["2026-07-31,7.600,7.579,7.679,7.521,7460143,5673106900.000,2.15,3.19,0.234,12.16"]
    fake_client = MagicMock()

    async def fake_kline(**kw):
        return _em_kline_text(raw, name="中证500ETF南方")

    fake_client.kline = fake_kline
    adapter._client = fake_client
    rows = await adapter.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=10)
    assert len(rows) == 1
    r = rows[0]
    assert r.date == "2026-07-31"
    assert r.open == 7.6
    assert r.close == 7.579
    assert r.high == 7.679
    assert r.low == 7.521
    # f56 vol 单位是"手", 应换算为"股"
    assert r.volume == 7460143 * 100
    assert r.amount == 5673106900.0
    assert r.amplitude == 2.15
    assert r.amount_of_increase == 3.19
    assert r.up_down_amount == 0.234
    assert r.turnover == 12.16


async def test_eastmoney_rejects_non_sh_sz_bj():
    from app.clients.kline.eastmoney_adapter import EastmoneyAdapter
    adapter = EastmoneyAdapter()
    fake_client = MagicMock()
    fake_client.kline = AsyncMock()
    adapter._client = fake_client
    rows = await adapter.fetch("hk00700", PERIOD.DAY, FQT.QFQ, limit=5)
    assert rows == []
    fake_client.kline.assert_not_called()


async def test_eastmoney_returns_empty_on_http_error():
    from app.clients.kline.eastmoney_adapter import EastmoneyAdapter
    adapter = EastmoneyAdapter()
    fake_client = MagicMock()

    async def fake_kline(**kw):
        return ""

    fake_client.kline = fake_kline
    adapter._client = fake_client
    rows = await adapter.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert rows == []


# ------------------- KLineService chain integration -------------------


async def test_klineservice_uses_chain_for_sh_market(monkeypatch):
    """无历史 → 全量抓取走 eastmoney→sina→tencent 链."""
    from app.services.kline_service import KLineService

    # 强制构造 (避开真实 Mongo); repo.find_by_id 返回 None (无历史)
    service = KLineService.__new__(KLineService)
    service.repo = MagicMock()
    service.repo.find_by_id = AsyncMock(return_value=None)
    service.client = MagicMock()

    # stub full aggregator: 返回行 (volume 单位: 股)
    stub_rows = [_row("2026-07-31", 7.6, 7.579, 7.679, 7.521, 746014340)]
    stub_result = MagicMock(rows=stub_rows, source=SOURCE.EASTMONEY, fell_back=False, error=None)
    stub_full_agg = MagicMock()
    stub_full_agg.fetch = AsyncMock(return_value=stub_result)
    service._full_aggregator = stub_full_agg
    # 增量 aggregator 不应被调用
    service._aggregator = MagicMock()

    entity = await service.spider_kline_data("510500", 1)
    assert entity is not None
    assert entity.code == "510500"
    assert len(entity.klines) == 1
    assert entity.klines[0].date == "2026-07-31"
    # 746014340 股 -> 7460143 手 (与东财路径 _convert_kline 输出一致)
    assert entity.klines[0].vol == "7460143"
    # 验证 full aggregator 被调用, 参数正确
    args, kwargs = stub_full_agg.fetch.call_args
    assert kwargs["symbol"] == "sh510500"
    assert kwargs["limit"] == 99999
    # 增量 aggregator 未被调用
    service._aggregator.fetch.assert_not_called()


async def test_klineservice_falls_back_to_eastmoney_when_chain_empty(monkeypatch):
    """全量链上所有源都空 → 返回 None"""
    from app.services.kline_service import KLineService

    service = KLineService.__new__(KLineService)
    service.repo = MagicMock()
    service.repo.find_by_id = AsyncMock(return_value=None)
    service.client = MagicMock()
    stub_agg = MagicMock()
    stub_agg.fetch = AsyncMock(
        return_value=MagicMock(rows=[], source=None, fell_back=True, error="all empty")
    )
    service._full_aggregator = stub_agg
    service._aggregator = MagicMock()

    entity = await service.spider_kline_data("510500", 1)
    assert entity is None


async def test_klineservice_incremental_when_db_has_history():
    """DB 有历史 → 增量拉取 (腾讯主源), 只取 last_date 之后的行, 合并返回."""
    from app.models.entities import KLineDataEntity
    from app.services.kline_service import KLineService

    service = KLineService.__new__(KLineService)
    service.client = MagicMock()

    # DB 已有 2 行: 2026-07-29, 2026-07-30
    old_k = KLineDataEntity(
        date="2026-07-29", open="7.4", close="7.5", higher="7.6", lower="7.3", vol="70147"
    )
    old_k2 = KLineDataEntity(
        date="2026-07-30", open="7.4", close="7.3", higher="7.5", lower="7.2", vol="90160"
    )
    existing_entity = MagicMock()
    existing_entity.klines = [old_k, old_k2]
    existing_entity.name = "中证500ETF"
    service.repo = MagicMock()
    service.repo.find_by_id = AsyncMock(return_value=existing_entity)

    # 增量 aggregator 返回 07-30 + 07-31 (07-30 应被去重覆盖)
    inc_rows = [
        _row("2026-07-30", 7.4, 7.3, 7.5, 7.2, 9016071 * 100),
        _row("2026-07-31", 7.6, 7.5, 7.6, 7.4, 9936368 * 100),
    ]
    inc_result = MagicMock(rows=inc_rows, source=SOURCE.TENCENT, fell_back=False, error=None)
    stub_inc_agg = MagicMock()
    stub_inc_agg.fetch = AsyncMock(return_value=inc_result)
    service._aggregator = stub_inc_agg
    service._full_aggregator = MagicMock()

    entity = await service.spider_kline_data("510500", 1)
    assert entity is not None
    assert entity.name == "中证500ETF"
    dates = [k.date for k in entity.klines]
    assert dates == ["2026-07-31", "2026-07-30", "2026-07-29"]  # 降序
    assert len(entity.klines) == 3
    # 增量 limit 按 last_date 到今天的日历天数计算
    args, _ = stub_inc_agg.fetch.call_args
    assert args[3] >= 1  # 至少 1 天
    # full aggregator 未被调用
    service._full_aggregator.fetch.assert_not_called()


async def test_klineservice_incremental_uptodate_returns_existing():
    """DB 最新日期已经是最后一天 → 增量无新数据 → 返回 existing."""
    from app.models.entities import KLineDataEntity
    from app.services.kline_service import KLineService

    service = KLineService.__new__(KLineService)
    service.client = MagicMock()

    old_k = KLineDataEntity(
        date="2026-07-30", open="7.4", close="7.3", higher="7.5", lower="7.2", vol="90160"
    )
    existing_entity = MagicMock()
    existing_entity.klines = [old_k]
    existing_entity.name = "中证500ETF"
    service.repo = MagicMock()
    service.repo.find_by_id = AsyncMock(return_value=existing_entity)

    # 增量返回的都是 <= last_date 的数据
    inc_rows = [
        _row("2026-07-30", 7.4, 7.3, 7.5, 7.2, 9016071 * 100),
    ]
    inc_result = MagicMock(rows=inc_rows, source=SOURCE.TENCENT, fell_back=False, error=None)
    stub_inc_agg = MagicMock()
    stub_inc_agg.fetch = AsyncMock(return_value=inc_result)
    service._aggregator = stub_inc_agg
    service._full_aggregator = MagicMock()

    entity = await service.spider_kline_data("510500", 1)
    # 返回的是原 existing_entity (无新增)
    assert entity is existing_entity
    service._full_aggregator.fetch.assert_not_called()


async def test_klineservice_hk_market_skips_chain(monkeypatch):
    """market=116 (HK) 直接走东财, 不走聚合链."""
    import json

    from app.services.kline_service import KLineService

    service = KLineService.__new__(KLineService)
    service.repo = MagicMock()
    fake_em = MagicMock()

    async def fake_kline(fields1, fields2, beg, end, secid, klt, fqt):
        return json.dumps({
            "rc": 0, "data": {
                "code": "00700", "name": "腾讯控股",
                "klines": ["2026-07-31,400,401,405,402,10000000,4000000000.000,1.5,0.5,2,0.5"],
            }
        })

    fake_em.kline = fake_kline
    service.client = fake_em
    stub_agg = MagicMock()
    stub_agg.fetch = AsyncMock()
    service._aggregator = stub_agg

    entity = await service.spider_kline_data("00700", 116)
    assert entity is not None
    assert entity.name == "腾讯控股"
    stub_agg.fetch.assert_not_called()


def test_klineservice_rows_to_entities_computes_amountOfAverage():
    """验证 amountOfAverage = amount / vol / 100, 四舍五入 3 位."""
    from app.services.kline_service import KLineService

    service = KLineService.__new__(KLineService)
    rows = [
        KLineRow(date="2026-07-31", open=1.0, close=1.0, high=1.0, low=1.0,
                 volume=1000, amount=10000.0, turnover=5.0,
                 amplitude=1.5, amount_of_increase=0.5, up_down_amount=0.05),
    ]
    entities = service._rows_to_entities(rows)
    assert len(entities) == 1
    e = entities[0]
    assert e.amount == "10000"
    assert e.amplitude == "1.5"
    assert e.amountOfIncrease == "0.5"
    assert e.UpDownAmount == "0.05"
    assert e.turnOver == "5"
    # vol: 1000 股 -> 10 手 (KLineRow.volume 统一股, entity.vol 存手)
    assert e.vol == "10"
    # amountOfAverage = 10000 / 10 / 100 = 10.0
    assert e.amountOfAverage == "10.000"