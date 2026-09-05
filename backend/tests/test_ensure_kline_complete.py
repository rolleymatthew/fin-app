"""Tests for FinanceService._ensure_kline_complete.

(2026-08-26 新增: ROE sheet K 线断层自动补抓协调逻辑)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.models.entities import KLineDataEntity, KLineEntity, SecCodeEntity
from app.services.finance_service import FinanceService
from app.services.kline_service import KLineService


def _kline(d: str) -> KLineDataEntity:
    return KLineDataEntity(
        date=d, open="1.0", close="1.0", higher="1.0", lower="1.0",
        vol="100", amount="100.0", amountOfAverage="0.0",
    )


def _make_finance_service():
    fs = FinanceService()
    fs.kline_service = MagicMock()
    fs.kline_service.detect_gap_in_window = MagicMock(return_value=None)
    fs.kline_service.market_code = MagicMock(return_value=0)
    fs.kline_service.refresh_kline_data = AsyncMock()
    fs.kline_service.backfill_kline_window = AsyncMock()
    fs._get_profit_list_by_org_type = AsyncMock()
    return fs


def _sec_code_entity() -> SecCodeEntity:
    entity = SecCodeEntity(
        id="300122",
        securityCode="300122",
        securityNameAbbr="智飞生物",
        secucode="300122.SZ",
        orgTypeCode="4",
    )
    return entity


async def test_returns_original_when_no_profit():
    """无 profit 数据 → 不检测, 直接返原 entity."""
    fs = _make_finance_service()
    fs._get_profit_list_by_org_type.return_value = []
    kline_entity = KLineEntity(code="300122", name="智飞生物", klines=[_kline("2026-03-31")])

    result = await fs._ensure_kline_complete(kline_entity, _sec_code_entity())

    assert result is kline_entity
    fs.kline_service.detect_gap_in_window.assert_not_called()
    fs.kline_service.refresh_kline_data.assert_not_awaited()
    fs.kline_service.backfill_kline_window.assert_not_awaited()


async def test_returns_original_when_all_windows_intact():
    """所有季度窗口 K 线齐 → 不补抓, 返原 entity."""
    fs = _make_finance_service()
    fs._get_profit_list_by_org_type.return_value = [MagicMock(reportDate="2026-03-31 00:00:00")]
    # 所有窗口 detect 都返 None
    fs.kline_service.detect_gap_in_window.return_value = None
    kline_entity = KLineEntity(code="300122", name="智飞生物", klines=[])

    result = await fs._ensure_kline_complete(kline_entity, _sec_code_entity())

    assert result is kline_entity
    # 4 个窗口都调过 detect
    assert fs.kline_service.detect_gap_in_window.call_count == 4
    fs.kline_service.refresh_kline_data.assert_not_awaited()
    fs.kline_service.backfill_kline_window.assert_not_awaited()


async def test_em_path_when_biggest_gap_exceeds_120():
    """最大缺口 > 120 日 → 走 EM 全量重抓 (refresh_kline_data)."""
    fs = _make_finance_service()
    fs._get_profit_list_by_org_type.return_value = [MagicMock(reportDate="2026-03-31 00:00:00")]

    # 第 2 个窗口 (week[1]=2025-12-31) 返回 GapInfo(365 天), 其他窗口 None
    big_gap = KLineService.GapInfo(
        start=date(2024, 12, 31), end=date(2025, 12, 31), span_days=365,
    )
    fs.kline_service.detect_gap_in_window.side_effect = [
        None,        # week[0]=2026-03-31 齐
        big_gap,     # week[1]=2025-12-31 断层 365 天
        None,        # week[2]=2025-09-30 齐
        None,        # week[3]=2025-06-30 齐
    ]
    refreshed = KLineEntity(code="300122", name="智飞生物", klines=[_kline("2025-12-15")])
    fs.kline_service.refresh_kline_data.return_value = refreshed

    kline_entity = KLineEntity(code="300122", name="智飞生物", klines=[])
    result = await fs._ensure_kline_complete(kline_entity, _sec_code_entity())

    # 走 EM 全量重抓
    fs.kline_service.refresh_kline_data.assert_awaited_once()
    fs.kline_service.backfill_kline_window.assert_not_awaited()
    assert result is refreshed


async def test_backfill_path_when_biggest_gap_under_120():
    """最大缺口 ≤ 120 日 → 走定向补抓 (backfill_kline_window)."""
    fs = _make_finance_service()
    fs._get_profit_list_by_org_type.return_value = [MagicMock(reportDate="2026-03-31 00:00:00")]

    # 第 3 个窗口 (week[3]=2025-06-30) 返回 GapInfo(90 天)
    small_gap = KLineService.GapInfo(
        start=date(2024, 6, 30), end=date(2025, 6, 30), span_days=90,
    )
    fs.kline_service.detect_gap_in_window.side_effect = [
        None, None, None, small_gap,
    ]
    backed = KLineEntity(code="300122", name="智飞生物", klines=[_kline("2025-06-15")])
    fs.kline_service.backfill_kline_window.return_value = backed

    kline_entity = KLineEntity(code="300122", name="智飞生物", klines=[])
    result = await fs._ensure_kline_complete(kline_entity, _sec_code_entity())

    fs.kline_service.backfill_kline_window.assert_awaited_once()
    fs.kline_service.refresh_kline_data.assert_not_awaited()
    assert result is backed
    # 验证传给 backfill 的参数 (start, end)
    call_args = fs.kline_service.backfill_kline_window.await_args
    assert call_args.kwargs["start_date"] == date(2024, 6, 30)
    assert call_args.kwargs["end_date"] == date(2025, 6, 30)


async def test_only_one_backfill_triggered_per_call():
    """多个窗口断层时, 单次调用最多触发 1 次补抓 (取最大缺口)."""
    fs = _make_finance_service()
    fs._get_profit_list_by_org_type.return_value = [MagicMock(reportDate="2026-03-31 00:00:00")]

    gap_a = KLineService.GapInfo(
        start=date(2024, 12, 31), end=date(2025, 12, 31), span_days=365,
    )
    gap_b = KLineService.GapInfo(
        start=date(2024, 6, 30), end=date(2025, 6, 30), span_days=90,
    )
    fs.kline_service.detect_gap_in_window.side_effect = [gap_a, None, None, gap_b]
    fs.kline_service.refresh_kline_data.return_value = KLineEntity(
        code="300122", name="智飞生物", klines=[],
    )

    await fs._ensure_kline_complete(
        KLineEntity(code="300122", name="智飞生物", klines=[]),
        _sec_code_entity(),
    )

    # 只补最大的 (365 天), 不补小的 (90 天)
    fs.kline_service.refresh_kline_data.assert_awaited_once()
    fs.kline_service.backfill_kline_window.assert_not_awaited()


async def test_propagates_none_when_backfill_fails():
    """补抓返 None → _ensure_kline_complete 透传 None."""
    fs = _make_finance_service()
    fs._get_profit_list_by_org_type.return_value = [MagicMock(reportDate="2026-03-31 00:00:00")]
    fs.kline_service.detect_gap_in_window.side_effect = [
        KLineService.GapInfo(
            start=date(2024, 12, 31), end=date(2025, 12, 31), span_days=365,
        ),
        None, None, None,
    ]
    fs.kline_service.refresh_kline_data.return_value = None

    result = await fs._ensure_kline_complete(
        KLineEntity(code="300122", name="智飞生物", klines=[]),
        _sec_code_entity(),
    )

    assert result is None
