"""Tests for KLineService.refresh_kline_data (force full re-fetch)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.models.entities import KLineDataEntity, KLineEntity
from app.services.kline_service import KLineService


def _row(date, o, c, h, lo, v, amt=None):
    return KLineDataEntity(
        date=date, open=o, close=c, higher=h, lower=lo,
        vol=str(v) if v else "0", amount=str(amt) if amt else "0",
        amountOfAverage="0.000",
    )


def _make_service():
    svc = KLineService()
    svc.repo = MagicMock()
    svc.repo.delete_by_id = AsyncMock()
    svc.repo.save = AsyncMock()
    svc.repo.find_by_id = AsyncMock(return_value=None)
    return svc


async def test_refresh_deletes_existing_then_full_fetch(monkeypatch):
    svc = _make_service()

    full_rows = [_row("2026-08-04", "4.816", "4.860", "4.873", "4.816", 2025299, 981798355.030),
                _row("2026-08-05", "4.816", "4.920", "4.942", "4.815", 2787830, 1367741702.271),
                _row("2026-08-06", "4.883", "4.910", "4.938", "4.870", 1615030, 792128715.769)]

    captured = {}

    async def fake_spider(code, market, name=None):
        captured["spider_called"] = (code, market, name)
        # spider_kline_data 走全量分支（repo.find_by_id 返回 None）
        return KLineEntity(code=code, name=name or "测试", klines=full_rows)

    monkeypatch.setattr(svc, "spider_kline_data", fake_spider)

    result = await svc.refresh_kline_data("159919", market=0, name=None)

    # 1) 旧 doc 被删除
    svc.repo.delete_by_id.assert_awaited_once_with("159919")
    # 2) spider_kline_data 被以 None existing 触发（走全量）
    assert captured["spider_called"] == ("159919", 0, None)
    # 3) 新数据落库
    assert svc.repo.save.await_count == 1
    saved_entity = svc.repo.save.await_args.args[0]
    assert saved_entity.code == "159919"
    assert len(saved_entity.klines) == 3
    assert saved_entity.klines[0].date == "2026-08-04"
    # 4) 返回值
    assert result is not None
    assert len(result.klines) == 3


async def test_refresh_returns_none_when_full_fetch_empty(monkeypatch):
    svc = _make_service()

    async def fake_spider(code, market, name=None):
        return KLineEntity(code=code, name=name, klines=[])

    monkeypatch.setattr(svc, "spider_kline_data", fake_spider)

    result = await svc.refresh_kline_data("159919", market=0)
    assert result is None
    svc.repo.save.assert_not_awaited()


async def test_refresh_returns_none_when_market_none(monkeypatch):
    svc = _make_service()
    called = False

    async def fake_spider(code, market, name=None):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(svc, "spider_kline_data", fake_spider)
    result = await svc.refresh_kline_data("159919", market=None)
    assert result is None
    assert called is False
    svc.repo.delete_by_id.assert_not_awaited()


async def test_refresh_swallows_delete_error(monkeypatch):
    svc = _make_service()
    svc.repo.delete_by_id.side_effect = Exception("doc not found")

    async def fake_spider(code, market, name=None):
        return KLineEntity(
            code=code,
            name=name,
            klines=[_row("2026-08-06", "1", "1", "1", "1", 1, 1)],
        )

    monkeypatch.setattr(svc, "spider_kline_data", fake_spider)
    # 即使 delete 抛错也应继续 full fetch + save
    result = await svc.refresh_kline_data("159919", market=0)
    assert result is not None
    svc.repo.save.assert_awaited_once()