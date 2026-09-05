"""Tests for KLineService.detect_gap_in_window + GapInfo dataclass.

(2026-08-26 新增: ROE sheet K 线断层自动补抓)
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from datetime import date as _date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.kline import SOURCE, FetchResult
from app.clients.kline.types import KLineRow
from app.models.entities import KLineDataEntity, KLineEntity
from app.services.kline_service import KLineService


def _row(d: str) -> KLineDataEntity:
    return KLineDataEntity(
        date=d, open="1.0", close="1.0", higher="1.0", lower="1.0",
        vol="100", amount="100.0", amountOfAverage="0.0",
    )


def test_gap_info_is_frozen():
    """GapInfo 是 frozen dataclass, 构造后字段不可变."""
    from app.services.kline_service import KLineService as KS
    info = KS.GapInfo(start=date(2024, 12, 31), end=date(2025, 12, 31), span_days=365)
    assert info.start == date(2024, 12, 31)
    assert info.end == date(2025, 12, 31)
    assert info.span_days == 365
    with pytest.raises(FrozenInstanceError):
        info.span_days = 100  # type: ignore[misc]


def test_detect_returns_none_when_window_has_enough_klines():
    """窗口内 >= 5 条 K 线 → 不算断层, 返 None."""
    # 2025-12-31 窗口是 [2024-12-31, 2025-12-31], 放 60 条均匀分布的 K 线
    klines = [_row(f"2025-{m:02d}-{d:02d}") for m in range(1, 13) for d in (10, 20)]
    result = KLineService.detect_gap_in_window(klines, date(2025, 12, 31))
    assert result is None


def test_detect_returns_gap_when_window_empty():
    """窗口内 0 条 K 线 → 视为断层, 返 GapInfo."""
    klines = [_row("2025-09-30"), _row("2026-01-05")]  # 都不在 [2024-12-31, 2025-12-31]
    result = KLineService.detect_gap_in_window(klines, date(2025, 12, 31))
    assert result is not None
    assert result.start == date(2024, 12, 31)
    assert result.end == date(2025, 12, 31)
    assert result.span_days == 365


def test_detect_returns_gap_when_window_under_threshold():
    """窗口内 4 条 K 线 (低于阈值 5) → 视为断层."""
    klines = [_row(f"2025-{m:02d}-15") for m in range(1, 5)]  # 4 条
    result = KLineService.detect_gap_in_window(klines, date(2025, 12, 31))
    assert result is not None
    assert result.span_days == 365


def test_detect_window_end_alignment():
    """mapper_window_end 不同 → 窗口起点不同 (previous_years 反推)."""
    klines: list = []
    # mapper_window_end=2026-03-31 → 窗口 [2025-03-31, 2026-03-31]
    result_2026 = KLineService.detect_gap_in_window(klines, date(2026, 3, 31))
    assert result_2026 is not None
    assert result_2026.start == date(2025, 3, 31)
    assert result_2026.end == date(2026, 3, 31)
    assert result_2026.span_days == 365

    # mapper_window_end=2025-12-31 → 窗口 [2024-12-31, 2025-12-31]
    result_2025 = KLineService.detect_gap_in_window(klines, date(2025, 12, 31))
    assert result_2025.start == date(2024, 12, 31)
    assert result_2025.end == date(2025, 12, 31)


def _make_service_with_mocks():
    """构造 KLineService, repo + _aggregator 全部 mock."""
    svc = KLineService()
    svc.repo = MagicMock()
    svc.repo.find_by_id = AsyncMock(return_value=None)
    svc.repo.save = AsyncMock()
    svc._aggregator = MagicMock()
    svc._aggregator.fetch = AsyncMock()
    return svc


def _tencent_row(date_str: str) -> KLineRow:
    """构造腾讯格式的 KLineRow (6 字段, 其余 None)."""
    return KLineRow(
        date=date_str,
        open=10.0, close=10.0, high=10.0, low=10.0,
        volume=1000, amount=None, turnover=None,
        amplitude=None, amount_of_increase=None, up_down_amount=None,
    )


async def test_backfill_window_returns_none_when_market_none():
    """market=None → 立即返 None, 不发请求."""
    svc = _make_service_with_mocks()
    result = await svc.backfill_kline_window(
        "300122", market=None,
        start_date=_date(2025, 10, 1), end_date=_date(2025, 12, 31),
    )
    assert result is None
    svc._aggregator.fetch.assert_not_awaited()
    svc.repo.save.assert_not_awaited()


async def test_backfill_window_returns_none_when_end_before_start():
    """end_date < start_date → 立即返 None (防御)."""
    svc = _make_service_with_mocks()
    result = await svc.backfill_kline_window(
        "300122", market=0,
        start_date=_date(2025, 12, 31), end_date=_date(2025, 10, 1),
    )
    assert result is None
    svc._aggregator.fetch.assert_not_awaited()


async def test_backfill_window_returns_none_when_aggregator_empty():
    """_aggregator.fetch 返回 0 行 → 返 None, 不落库."""
    svc = _make_service_with_mocks()
    svc._aggregator.fetch.return_value = FetchResult(rows=[], source=None, fell_back=True)
    result = await svc.backfill_kline_window(
        "300122", market=0,
        start_date=_date(2025, 10, 1), end_date=_date(2025, 12, 31),
    )
    assert result is None
    svc.repo.save.assert_not_awaited()


async def test_backfill_window_returns_none_when_sliced_empty():
    """_aggregator 返回的行不在 [start, end] 区间 → 切片 0 条, 返 None."""
    svc = _make_service_with_mocks()
    svc._aggregator.fetch.return_value = FetchResult(
        rows=[_tencent_row("2026-01-15"), _tencent_row("2026-02-20")],
        source=SOURCE.TENCENT, fell_back=False,
    )
    result = await svc.backfill_kline_window(
        "300122", market=0,
        start_date=_date(2025, 10, 1), end_date=_date(2025, 12, 31),
    )
    assert result is None
    svc.repo.save.assert_not_awaited()


async def test_backfill_window_slices_window_and_saves():
    """正常路径: 切片 [start, end] → 与现有 klines 合并 → 落库."""
    svc = _make_service_with_mocks()
    svc._aggregator.fetch.return_value = FetchResult(
        rows=[
            _tencent_row("2025-09-30"),
            _tencent_row("2025-10-15"),
            _tencent_row("2025-11-20"),
            _tencent_row("2025-12-15"),
            _tencent_row("2026-01-15"),
        ],
        source=SOURCE.TENCENT, fell_back=False,
    )
    svc.repo.find_by_id.return_value = KLineEntity(
        code="300122", name="智飞生物",
        klines=[_row("2025-09-30")],
    )

    result = await svc.backfill_kline_window(
        "300122", market=0,
        start_date=_date(2025, 10, 1), end_date=_date(2025, 12, 31),
        name="智飞生物",
    )

    call_args = svc._aggregator.fetch.await_args
    assert call_args is not None
    symbol_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("symbol")
    assert symbol_arg == "sz300122"

    assert svc.repo.save.await_count == 1
    saved = svc.repo.save.await_args.args[0]
    assert saved.code == "300122"
    assert len(saved.klines) == 4
    dates = sorted(k.date for k in saved.klines)
    assert dates == ["2025-09-30", "2025-10-15", "2025-11-20", "2025-12-15"]

    assert result is saved
