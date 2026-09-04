"""KLine aggregator: try primary source first, fall back to next on empty/error."""
from __future__ import annotations

import asyncio

from app.clients.kline.types import (
    FQT,
    PERIOD,
    SOURCE,
    FetchResult,
    KLineAdapter,
)


class KLineAggregator:
    """Chain primary + fallback sources. First non-empty result wins.

    `primary_source` 是配置来源(用于日志和 FetchResult.source),
    `primary` 是实际适配器实例, 同理 fallbacks/fallback_sources.
    """

    def __init__(
        self,
        primary: KLineAdapter,
        fallbacks: list[KLineAdapter] | None = None,
    ):
        self.primary = primary
        self.fallbacks = list(fallbacks or [])
        self.primary_source: SOURCE = primary.source
        self.fallback_sources: list[SOURCE] = [a.source for a in self.fallbacks]

    async def fetch(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> FetchResult:
        chain: list[KLineAdapter] = [self.primary, *self.fallbacks]
        last_error: str | None = None
        chain_results: list[tuple[str, str, int, str | None]] = []
        for idx, adapter in enumerate(chain):
            is_primary = idx == 0
            try:
                rows = await adapter.fetch(symbol, period, fqt, limit)
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                last_error = err
                chain_results.append((adapter.source.value, "error", 0, err))
                continue
            if rows:
                chain_results.append((adapter.source.value, "ok", len(rows), None))
                return FetchResult(
                    rows=rows,
                    source=adapter.source,
                    fell_back=not is_primary,
                    chain_results=chain_results,
                )
            chain_results.append((adapter.source.value, "empty", 0, None))
        return FetchResult(
            rows=[],
            source=None,
            fell_back=True,
            error=last_error or "all sources returned empty",
            chain_results=chain_results,
        )

    async def aclose(self) -> None:
        await asyncio.gather(
            self.primary.aclose(),
            *(a.aclose() for a in self.fallbacks),
            return_exceptions=True,
        )