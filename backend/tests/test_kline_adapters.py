"""Tests for unified kline adapter."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.factory import build_aggregator
from app.clients.kline.sina_adapter import SinaAdapter
from app.clients.kline.tencent_adapter import TencentAdapter
from app.clients.kline.ths_adapter import ThsAdapter
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


# ------------------- THS v4 per-year decode -------------------


def _fake_v4_payload(year_data: dict[int, list[str]]):
    """year_data: {2026: [line1, line2, ...], 2025: [...]}"""
    parts = []
    for year in sorted(year_data.keys()):
        ds = ";".join(year_data[year])
        parts.append(f'{{"total":{len(year_data[year])},"data":"{ds}"}}')
    return "quotebridge_v4_line_hs_510500_01_0000(" + ",".join(parts) + ")"


def test_ths_decode_v4_row_basic():
    from app.clients.kline.ths_adapter import _decode_v4_row
    line = "20260727,7.544,7.739,7.484,7.726,590866130,4519820200.000,9.629,,0"
    row = _decode_v4_row(line)
    assert row is not None
    assert row.date == "2026-07-27"
    assert row.open == 7.544
    assert row.high == 7.739
    assert row.low == 7.484
    assert row.close == 7.726
    assert row.volume == 590866130
    assert row.amount == 4519820200.000
    assert row.turnover == 9.629


def test_ths_decode_v4_row_short_line_returns_none():
    from app.clients.kline.ths_adapter import _decode_v4_row
    assert _decode_v4_row("20260105,7.4,7.5") is None


async def test_ths_fetch_returns_merged_history():
    """v4 多年份合并 + 并发请求 + amount/turnover 都在."""
    adapter = ThsAdapter()

    years_payload = {
        2026: [
            "20260105,7.431,7.583,7.429,7.581,276371420,2138958700.000,1.422,,0",
            "20260727,7.544,7.739,7.484,7.726,590866130,4519820200.000,9.629,,0",
        ],
        2025: ["20251231,7.386,7.400,7.340,7.377,446353440,3386684000.000,2.5,,0"],
        2024: ["20241231,5.000,5.100,4.900,5.050,200000000,1000000000.000,1.5,,0"],
    }

    async def fake_get(url):
        # 从 URL 提取年份
        import re as _re
        m = _re.search(r"/(\d{4})\.js$", url)
        if not m:
            return None
        year = int(m.group(1))
        rows_for_year = years_payload.get(year, [])
        data_str = ";".join(rows_for_year)
        payload = '{"total":%d,"data":"%s"}' % (len(rows_for_year), data_str)
        text = "quotebridge_v4_line_hs_510500_01_%d(%s)" % (year, payload)
        fake = MagicMock()
        fake.text = text
        fake.raise_for_status = MagicMock()
        return fake

    with patch.object(adapter, "_get", fake_get):
        rows = await adapter.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=10)
    assert len(rows) == 4
    # 按日期升序
    assert rows[0].date == "2024-12-31"
    assert rows[-1].date == "2026-07-27"
    # 所有行都有 amount 和 turnover (THS v4 给完整 11 字段)
    for r in rows:
        assert r.amount is not None
        assert r.turnover is not None


async def test_ths_fetch_skips_failed_years():
    """个别年份失败不应影响其他年份."""
    adapter = ThsAdapter()

    async def fake_get(url):
        import re as _re
        m = _re.search(r"/(\d{4})\.js$", url)
        if not m:
            return None
        year = int(m.group(1))
        if year == 2025:
            raise RuntimeError("simulated failure")
        # 2026 成功, 2024 成功, 其它年份返回空 data
        if year == 2026:
            text = ('quotebridge_v4_line_hs_510500_01_2026('
                    '{"total":1,"data":"20260727,7.5,7.7,7.4,7.6,100,200,1,,0"})')
        elif year == 2024:
            text = ('quotebridge_v4_line_hs_510500_01_2024('
                    '{"total":1,"data":"20241231,5.0,5.1,4.9,5.05,200,1000,1.5,,0"})')
        else:
            text = 'quotebridge_v4_line_hs_510500_01_%d({"total":0,"data":""})' % year
        fake = MagicMock()
        fake.text = text
        fake.raise_for_status = MagicMock()
        return fake

    with patch.object(adapter, "_get", fake_get):
        rows = await adapter.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=10)
    assert len(rows) == 2
    dates = [r.date for r in rows]
    assert "2024-12-31" in dates
    assert "2026-07-27" in dates
    assert "2025" not in str(dates)  # 2025 失败被跳过


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


# ------------------- THS Adapter -------------------


def _fake_ths_csv_line(date="20260727", o="7.544", h="7.739",
                       lo="7.484", c="7.726", v="590866130",
                       amt="4519820200.000", turnover="9.629"):
    return f"{date},{o},{h},{lo},{c},{v},{amt},{turnover},,0"


def _fake_ths_payload(year_data: dict[int, list[str]]):
    """year_data: {2026: [line1, line2, ...], 2025: [...]}"""
    parts = []
    for year in sorted(year_data.keys()):
        rows = year_data[year]
        ds = ";".join(rows)
        sort_year_entry = f'[{year},{len(rows)}]'
        parts.append(
            f'{{"total":{sum(len(v) for v in year_data.values())},'
            f'"sortYear":[{sort_year_entry}],'
            f'"data":"{ds}"}}'
        )
    return "quotebridge_v4_line_hs_510500_01_all(" + ",".join(parts) + ")"


async def test_ths_normalizes_strips_market_prefix():
    adapter = ThsAdapter()

    async def fake_get(url):
        fake = MagicMock()
        fake.text = ('quotebridge_v4_line_hs_510500_01_2026('
                     '{"total":1,"data":"20260727,7.5,7.7,7.4,7.6,100,200,1,,0"})')
        fake.raise_for_status = MagicMock()
        return fake

    visited_urls = []

    async def tracker(url):
        visited_urls.append(url)
        return await fake_get(url)

    with patch.object(adapter, "_get", tracker):
        await adapter.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=1)
    assert visited_urls, "expected at least one HTTP call"
    sample_url = next(u for u in visited_urls if "/hs_" in u)
    assert "/hs_510500/" in sample_url
    assert "sh510500" not in sample_url.split("/hs_")[-1].split("/")[0]


async def test_ths_supports_qfq_and_raw_codes():
    adapter = ThsAdapter()

    urls_visited = []

    async def fake_get(url):
        urls_visited.append(url)
        fake = MagicMock()
        # 返回空 data 即可, 测的是 URL 模式
        fake.text = 'quotebridge_v4_line_hs_510500_01_2026({"total":0,"data":""})'
        fake.raise_for_status = MagicMock()
        return fake

    with patch.object(adapter, "_get", fake_get):
        await adapter.fetch("510500", PERIOD.DAY, FQT.QFQ, limit=1)
        await adapter.fetch("510500", PERIOD.DAY, FQT.NONE, limit=1)
    qfq_urls = [u for u in urls_visited if "/01/" in u]
    raw_urls = [u for u in urls_visited if "/02/" in u]
    assert len(qfq_urls) > 0
    assert len(raw_urls) > 0


async def test_ths_does_not_call_when_limit_is_zero():
    adapter = ThsAdapter()
    with patch.object(adapter, "_get", AsyncMock()) as m_get:
        rows = await adapter.fetch("510500", PERIOD.DAY, FQT.QFQ, limit=0)
    assert rows == []
    m_get.assert_not_called()


async def test_ths_falls_back_to_v4_when_v6_failed():
    """当前实现只用 v4; 保留此测试以验证 v6 不可达也不影响数据."""
    adapter = ThsAdapter()

    async def fake_get(url):
        fake = MagicMock()
        # 模拟任何年份都有 1 条 CSV
        import re as _re
        m = _re.search(r"/(\d{4})\.js$", url)
        year = m.group(1) if m else "?"
        payload = '{"total":1,"data":"2026%s-01-01,7,7,7,7,100,200,1,,0"}' % year[2:]
        fake.text = "quotebridge_v4_line_hs_510500_01_%s(%s)" % (year, payload)
        fake.raise_for_status = MagicMock()
        return fake

    with patch.object(adapter, "_get", fake_get):
        rows = await adapter.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=50)
    # 每个年份至少有 1 条, 至少有 13 条 (15 - 一些未来年)
    assert len(rows) >= 13
    # 所有行都应该有 amount/turnover (v4 提供)
    for r in rows:
        assert r.amount is not None
        assert r.turnover is not None


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
    agg = build_aggregator(primary="ths", fallbacks=["tencent", "sina"])
    assert isinstance(agg, KLineAggregator)
    assert agg.primary_source == SOURCE.THS
    assert agg.fallback_sources == [SOURCE.TENCENT, SOURCE.SINA]


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
    """无历史 → 全量抓取走 eastmoney→ths→sina→tencent 链."""
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
    """DB 有历史 → 增量拉取 (THS 主源), 只取 last_date 之后的行, 合并返回."""
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
    inc_result = MagicMock(rows=inc_rows, source=SOURCE.THS, fell_back=False, error=None)
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
    _, kwargs = stub_inc_agg.fetch.call_args
    assert kwargs["limit"] >= 1  # 至少 1 天
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
    inc_result = MagicMock(rows=inc_rows, source=SOURCE.THS, fell_back=False, error=None)
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