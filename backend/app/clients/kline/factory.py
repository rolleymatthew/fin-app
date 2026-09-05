"""Build KLineAggregator from a config dict or source-name list.

Usage:
    from app.clients.kline.factory import build_aggregator
    agg = build_aggregator(primary="tencent", fallbacks=["eastmoney", "sina"])
"""
from __future__ import annotations

from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.eastmoney_adapter import EastmoneyAdapter
from app.clients.kline.sina_adapter import SinaAdapter
from app.clients.kline.tencent_adapter import TencentAdapter
from app.clients.kline.types import SOURCE


def _build_adapter(source: SOURCE):
    if source == SOURCE.TENCENT:
        return TencentAdapter()
    if source == SOURCE.SINA:
        return SinaAdapter()
    if source == SOURCE.EASTMONEY:
        return EastmoneyAdapter()
    raise ValueError(f"unknown kline source: {source}")


def build_aggregator(
    primary: str | SOURCE,
    fallbacks: list[str | SOURCE] | None = None,
) -> KLineAggregator:
    primary_source = SOURCE(primary)
    primary_adapter = _build_adapter(primary_source)
    fallback_adapters = []
    for s in (fallbacks or []):
        src = SOURCE(s)
        if src == primary_source:
            continue
        fallback_adapters.append(_build_adapter(src))
    return KLineAggregator(
        primary=primary_adapter,
        fallbacks=fallback_adapters,
    )