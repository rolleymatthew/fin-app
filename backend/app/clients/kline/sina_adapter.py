"""Sina KLine adapter (vip.stock.finance.sina.com.cn).

Returns 6 fields per row: day, open, high, low, close, volume(股).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.clients.kline.types import FQT, PERIOD, SOURCE, KLineRow

_PERIOD_MAP = {
    PERIOD.DAY: "240",
    PERIOD.WEEK: "1440",
    PERIOD.MONTH: "4320",
    PERIOD.M5: "5",
    PERIOD.M15: "15",
    PERIOD.M30: "30",
    PERIOD.M60: "60",
}


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    f = _to_float(v)
    if f is None:
        return None
    return int(f)


class SinaAdapter:
    source = SOURCE.SINA
    base_url = "https://vip.stock.finance.sina.com.cn"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Referer": "https://finance.sina.com.cn/",
            },
        )

    async def _get(self, url: str, params: dict[str, Any]) -> Any:
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp

    async def fetch(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> list[KLineRow]:
        if limit <= 0:
            return []
        scale = _PERIOD_MAP.get(period, "240")
        # 新浪日线 datalen 上限约 3248, 自动饱和; 分钟线需控小一些
        actual_datalen = limit
        url = (
            f"{self.base_url}/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData"
        )
        params = {
            "symbol": symbol,
            "scale": scale,
            "ma": "no",
            "datalen": actual_datalen,
        }
        resp = await self._get(url, params)
        raw_rows = resp.json() or []
        rows: list[KLineRow] = []
        for r in raw_rows[:limit]:
            # r = {day, open, high, low, close, volume}
            rows.append(KLineRow(
                date=str(r["day"]).split(" ")[0],  # 'YYYY-MM-DD HH:MM:SS' -> date
                open=_to_float(r.get("open")) or 0.0,
                close=_to_float(r.get("close")) or 0.0,
                high=_to_float(r.get("high")) or 0.0,
                low=_to_float(r.get("low")) or 0.0,
                volume=_to_int(r.get("volume")) or 0,
                amount=None,
                turnover=None,
            ))
        return rows

    async def aclose(self) -> None:
        await self._client.aclose()