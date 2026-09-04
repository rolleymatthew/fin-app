"""Tencent KLine adapter (web.ifzq.gtimg.cn).

Returns 6 fields per row: date, open, close, high, low, volume(手).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.clients.kline.types import FQT, PERIOD, SOURCE, KLineRow

_PERIOD_MAP = {
    PERIOD.DAY: "day",
    PERIOD.WEEK: "week",
    PERIOD.MONTH: "month",
    PERIOD.M5: "m5",
    PERIOD.M15: "m15",
    PERIOD.M30: "m30",
    PERIOD.M60: "m60",
}


_FQT_MAP = {
    FQT.NONE: "",
    FQT.QFQ: "qfq",
    FQT.HFQ: "hfq",
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


class TencentAdapter:
    source = SOURCE.TENCENT
    base_url = "https://web.ifzq.gtimg.cn"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )},
        )

    async def _get(self, url: str) -> Any:
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp

    async def fetch(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> list[KLineRow]:
        if limit <= 0:
            return []
        period_code = _PERIOD_MAP.get(period, "day")
        fqt_code = _FQT_MAP[fqt]
        url = (
            f"{self.base_url}/appstock/app/fqkline/get"
            f"?param={symbol},{period_code},,,{limit},{fqt_code}"
        )
        resp = await self._get(url)
        data = resp.json()
        sym_data = (data.get("data") or {}).get(symbol) or {}
        key = f"{fqt_code}{period_code}" if fqt_code else period_code
        raw_rows = sym_data.get(key) or sym_data.get(period_code) or []
        rows: list[KLineRow] = []
        for r in raw_rows[:limit]:
            # r = [date, open, close, high, low, volume]
            # 腾讯 volume 单位是 "手", 1 手 = 100 股
            volume = (_to_int(r[5]) or 0) * 100
            rows.append(KLineRow(
                date=str(r[0]),
                open=_to_float(r[1]) or 0.0,
                close=_to_float(r[2]) or 0.0,
                high=_to_float(r[3]) or 0.0,
                low=_to_float(r[4]) or 0.0,
                volume=volume,
                amount=None,
                turnover=None,
            ))
        return rows

    async def aclose(self) -> None:
        await self._client.aclose()