"""kline_service 集成测试: spider/refresh 入口走 hybrid pipeline.

通过 monkeypatch 替换 MongoRepository + KLinePipeline, 不发真实网络/DB.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.clients.kline.types import KLineRow
from app.models.entities import KLineDataEntity, KLineEntity
from app.services.kline_pipeline import HybridFetchResult
from app.services.kline_service import KLineService


def _row(date: str) -> KLineRow:
    return KLineRow(date=date, open=1.0, close=1.0, high=1.0, low=1.0,
                    volume=100, amount=1000.0)


def _make_service(monkeypatch, existing=None, pipeline_result=None):
    """构造 KLineService, mock MongoRepository + Pipeline + 跳过反爬延时."""
    fake_repo = MagicMock()
    fake_repo.find_by_id = AsyncMock(return_value=existing)
    fake_repo.delete_by_id = AsyncMock(return_value=True)
    fake_repo.save = AsyncMock(return_value=None)

    poly_result = pipeline_result or HybridFetchResult(
        rows=[_row(date.today().strftime("%Y-%m-%d"))],
        sources_used=["tdx"],
        tdx_rows_count=1,
    )
    fake_pipeline = MagicMock()
    fake_pipeline.fetch_hybrid = AsyncMock(return_value=poly_result)
    fake_pipeline.fetch_pure_network = AsyncMock(return_value=poly_result)
    fake_pipeline.aclose = AsyncMock()

    monkeypatch.setattr(
        "app.services.kline_service.MongoRepository",
        lambda *a, **kw: fake_repo,
    )
    monkeypatch.setattr(
        "app.services.kline_service.KLinePipeline",
        lambda *a, **kw: fake_pipeline,
    )
    monkeypatch.setattr("app.services.kline_service.asyncio.sleep", AsyncMock())

    service = KLineService()
    service.client = MagicMock()
    return service, fake_repo, fake_pipeline


# ------------------- spider_kline_data hybrid path -------------------


def test_spider_kline_data_uses_pipeline_when_db_empty(monkeypatch):
    """DB 无历史 → pipeline.fetch_hybrid(DEFAULT_LIMIT)."""
    service, fake_repo, fake_pipeline = _make_service(monkeypatch, existing=None)

    async def _run():
        return await service.spider_kline_data(code="510500", market=1, name="测试 ETF")

    result = asyncio.run(_run())
    assert fake_pipeline.fetch_hybrid.called
    call_kwargs = fake_pipeline.fetch_hybrid.call_args.kwargs
    assert call_kwargs["code"] == "510500"
    assert call_kwargs["market"] == 1
    assert call_kwargs["symbol"] == "sh510500"
    assert call_kwargs["limit"] == KLineService.DEFAULT_LIMIT
    assert isinstance(result, KLineEntity)
    assert len(result.klines) == 1


def test_spider_kline_data_incremental_limit(monkeypatch):
    """DB 有历史 → limit = 今天 - last_date 天数 (增量窗口)."""
    last_db_date = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    existing = KLineEntity(
        code="510500",
        name="old",
        klines=[KLineDataEntity(date=last_db_date, open="1", close="1",
                                higher="1", lower="1", vol="100", amount="1000",
                                amountOfAverage="10.000")],
    )
    service, fake_repo, fake_pipeline = _make_service(monkeypatch, existing=existing)

    async def _run():
        return await service.spider_kline_data(code="510500", market=1)

    asyncio.run(_run())
    call_kwargs = fake_pipeline.fetch_hybrid.call_args.kwargs
    assert call_kwargs["limit"] == 5


def test_spider_kline_data_keeps_hk_special_path(monkeypatch):
    """market=116 走 HK 直连, 不进 pipeline."""
    service, fake_repo, fake_pipeline = _make_service(monkeypatch)
    service._fetch_eastmoney_direct = AsyncMock(return_value=None)

    async def _run():
        return await service.spider_kline_data(code="00700", market=116, name="HK")

    asyncio.run(_run())
    assert not fake_pipeline.fetch_hybrid.called
    assert service._fetch_eastmoney_direct.called


# ------------------- refresh_kline_data hybrid path -------------------


def test_refresh_kline_data_uses_pipeline(monkeypatch):
    """refresh 入口: 删旧 doc → pipeline.fetch_hybrid → save."""
    service, fake_repo, fake_pipeline = _make_service(
        monkeypatch,
        existing=KLineEntity(code="510500", name="old", klines=[]),
    )

    async def _run():
        return await service.refresh_kline_data(
            code="510500", market=1, name="ETF", data_source="online",
        )

    result = asyncio.run(_run())
    assert fake_repo.delete_by_id.called
    assert fake_pipeline.fetch_hybrid.called
    assert fake_repo.save.called
    assert isinstance(result, KLineEntity)
