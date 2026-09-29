"""KLinePipeline 单测: 4 阶段 + 边界 + 配置驱动顺序.

通过 monkeypatch 替换 TdxAdapter / KLineAggregator, 不发真实网络, 不读真实 .day.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.types import FetchResult, KLineRow
from app.services.kline_pipeline import HybridFetchResult, KLinePipeline


def _row(date: str, source_tag: str = "any", price: float = 1.0) -> KLineRow:
    return KLineRow(date=date, open=price, close=price, high=price,
                    low=price, volume=100, amount=None)


def _make_pipeline_with_mocks(
    monkeypatch=None,
    tdx_rows: list[KLineRow] | None = None,
    tdx_available: bool = True,
    tdx_side_effect: Exception | None = None,
    network_rows_by_source: dict[str, list[KLineRow]] | None = None,
) -> KLinePipeline:
    """构造 Pipeline: mock TdxAdapter, mock KLineAggregator 行为.

    network_rows_by_source 形如 {"sina": [...], "tencent": [...]} — 提供哪个 key 就让
    该源返行; 缺省源返空 (模拟失败).

    TdxAdapter mock 行为:
    - tdx_side_effect 给定 → 抛该异常 (覆盖其他两种)
    - tdx_available=False → 抛 FileNotFoundError("no .day") (模拟本地缺失)
    - 否则 → 返 tdx_rows 或 []
    """
    # 1) mock TdxAdapter
    fake_tdx_adapter = MagicMock()
    fake_tdx_adapter.source = MagicMock(value="tdx")
    if tdx_side_effect is not None:
        fake_tdx_adapter.fetch = AsyncMock(side_effect=tdx_side_effect)
    elif not tdx_available:
        fake_tdx_adapter.fetch = AsyncMock(side_effect=FileNotFoundError("no .day"))
    else:
        fake_tdx_adapter.fetch = AsyncMock(return_value=tdx_rows or [])
    fake_tdx_adapter.aclose = AsyncMock()

    # 2) mock KLineAggregator — 用真实 build_aggregator 但替换内部 adapters
    network_rows_by_source = network_rows_by_source or {}

    def _adapter_factory(source_name: str):
        adapter = MagicMock()
        adapter.source = MagicMock(value=source_name)
        adapter.fetch = AsyncMock(return_value=network_rows_by_source.get(source_name, []))
        adapter.aclose = AsyncMock()
        return adapter

    if monkeypatch is not None:
        monkeypatch.setattr(
            "app.services.kline_pipeline.build_aggregator",
            lambda primary, fallbacks: _FakeAggregator(primary, fallbacks, _adapter_factory),
        )

    pipeline = KLinePipeline(
        network_chain_cfg=["sina", "tencent", "eastmoney"],
        fallback_chain_cfg=["tencent", "eastmoney", "sina"],
    )
    # 替换 _gap_chain / _pure_chain 为 mock
    pipeline._gap_chain = _FakeAggregator(
        "sina", ["tencent", "eastmoney"], _adapter_factory,
    )
    pipeline._pure_chain = _FakeAggregator(
        "tencent", ["eastmoney", "sina"], _adapter_factory,
    )
    pipeline._tdx_adapter = fake_tdx_adapter
    return pipeline


class _FakeAggregator(KLineAggregator):
    """用 _adapter_factory 替换内部 adapter 的 fake aggregator."""

    def __init__(self, primary: str, fallbacks: list[str], adapter_factory):
        self._primary = adapter_factory(primary)
        self._fallbacks = [adapter_factory(f) for f in fallbacks]

    @property
    def primary(self):
        return self._primary

    @property
    def fallbacks(self):
        return self._fallbacks

    async def fetch(self, symbol, period, fqt, limit):
        chain = [self._primary, *self._fallbacks]
        for idx, ad in enumerate(chain):
            rows = await ad.fetch(symbol, period, fqt, limit)
            if rows:
                return FetchResult(
                    rows=rows,
                    source=ad.source,
                    fell_back=idx > 0,
                )
        return FetchResult(rows=[], source=None, fell_back=True,
                           error="all sources empty")

    async def aclose(self):
        await self._primary.aclose()
        for f in self._fallbacks:
            await f.aclose()


# ------------------- Phase 1 + Phase 2 -------------------


def test_phase1_gap_zero_skips_network():
    """TDX 有数据且 max_date == today → 不调网络链."""
    today_str = date.today().strftime("%Y-%m-%d")
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(today_str)],
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert isinstance(result, HybridFetchResult)
    assert result.tdx_available is True
    assert result.network_attempted is False
    assert result.gap_days == 0
    assert len(result.rows) == 1
    assert result.sources_used == ["tdx"]


def test_phase2_gap_positive_fills_via_sina():
    """TDX max_date = today - 4 → gap=4 → 网络链补 5 行 (sina)."""
    from datetime import timedelta
    tdx_max_obj = date.today() - timedelta(days=4)
    tdx_max = tdx_max_obj.strftime("%Y-%m-%d")
    sina_rows = [
        _row((date.today() - timedelta(days=i)).strftime("%Y-%m-%d"))
        for i in range(6)
        if (date.today() - timedelta(days=i)) != tdx_max_obj
    ][:5]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(tdx_max)],
        network_rows_by_source={"sina": sina_rows},
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is True
    assert result.gap_days == 4
    assert result.network_attempted is True
    assert "sina" in result.sources_used
    assert "tdx" in result.sources_used
    # 合并: tdx 1 行 + sina 5 行 = 6 行 (同日期去重不重, 因为 tdx_max 是 4 天前)
    assert len(result.rows) == 6
    # 按日期降序
    dates = [r.date for r in result.rows]
    assert dates == sorted(dates, reverse=True)


def test_phase1_empty_falls_to_pure_network():
    """TDX 不可用 → Phase 3 纯网络 (fallback_chain_cfg)."""
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[],
        tdx_available=False,
        network_rows_by_source={"tencent": [_row("2026-09-29")]},
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is False
    assert result.gap_days is None
    assert result.network_attempted is True  # phase3 也算 attempt
    assert "tencent" in result.sources_used
    assert "tdx" not in result.sources_used
    assert len(result.rows) == 1


def test_phase1_generic_exception_falls_to_pure_network():
    """TDX 抛非 FileNotFoundError → Phase 3 纯网络, tdx_available=False."""
    pipeline = _make_pipeline_with_mocks(
        tdx_side_effect=ValueError("gbbq parse failed"),
        network_rows_by_source={"tencent": [_row("2026-09-29")]},
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is False
    assert result.gap_days is None
    assert result.network_attempted is True
    assert "tencent" in result.sources_used
    assert "tdx" not in result.sources_used
    assert len(result.rows) == 1


def test_phase2_all_empty_falls_back_to_tdx():
    """TDX 有数据, 网络链全空 → 仍返 TDX rows, network_error 记录."""
    tdx_max = "2026-09-25"
    tdx_rows = [_row(tdx_max)]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=tdx_rows,
        network_rows_by_source={},  # 所有网络源都返空
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is True
    assert result.network_attempted is True
    assert result.network_error is not None
    assert len(result.rows) == 1
    assert result.sources_used == ["tdx"]


def test_phase2_falls_back_to_tencent_when_sina_empty():
    """Phase 2 网络链 sina 空, tencent 返行 → fell_back 到 tencent."""
    from datetime import timedelta
    tdx_max = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
    tencent_rows = [_row(date.today().strftime("%Y-%m-%d"))]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(tdx_max)],
        network_rows_by_source={"tencent": tencent_rows},  # sina 缺省 = 空
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert "tencent" in result.sources_used
    assert "sina" not in result.sources_used
    assert result.gap_days == 3


def test_network_chain_order_respects_config():
    """spec: 默认 sina,tencent,eastmoney 顺序, 即使 sina 返空也按顺序试."""
    from datetime import timedelta
    tdx_max = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    eastmoney_rows = [_row(date.today().strftime("%Y-%m-%d"))]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(tdx_max)],
        network_rows_by_source={"eastmoney": eastmoney_rows},
        # sina/tencent 都没返, 验证确实跳到 eastmoney
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert "eastmoney" in result.sources_used
    # sources_used 顺序反映实际触发顺序
    assert result.sources_used.index("eastmoney") > result.sources_used.index("tdx")