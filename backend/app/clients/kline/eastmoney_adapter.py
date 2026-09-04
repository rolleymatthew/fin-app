"""Eastmoney KLine adapter wrapping EastmoneyClient.

通过 push2his.eastmoney.com/api/qt/stock/kline/get 取 K 线,
字段最全 (11 个), 需要 cookie (从 EastmoneyClient 内部 cookie_dir 加载).
"""
from __future__ import annotations

from typing import Any

from app.clients.eastmoney import EastmoneyClient, get_eastmoney_client
from app.clients.kline.types import FQT, PERIOD, SOURCE, KLineRow

# 字段位置 (fields2 拼接顺序):
# f51 date, f52 open, f53 close, f54 high, f55 low, f56 vol, f57 amount,
# f58 amplitude%, f59 amountOfIncrease%, f60 UpDownAmount, f61 turnOver%
# 项目里 fqt=1 是 qfq (前复权)
_EM_FQT_MAP = {
    FQT.NONE: "0",
    FQT.QFQ: "1",
    FQT.HFQ: "2",
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


class EastmoneyAdapter:
    source = SOURCE.EASTMONEY

    def __init__(self, client: EastmoneyClient | None = None):
        # 接受外部注入的 client; 默认用全局单例 (含 cookie)
        self._client = client or get_eastmoney_client()

    async def _to_market_secid(self, symbol: str) -> tuple[int | None, str]:
        """'sh510500' -> (1, '510500'), 'sz159915' -> (0, '159915')."""
        s = symbol.lower()
        for prefix, market in (("sh", 1), ("sz", 0), ("bj", 2)):
            if s.startswith(prefix):
                return market, s[len(prefix):]
        return None, s

    async def fetch(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> list[KLineRow]:
        if limit <= 0:
            return []
        if period not in (PERIOD.DAY,):
            return []
        market, code = await self._to_market_secid(symbol)
        if market is None:
            return []
        secid = f"{market}.{code}"
        fqt_code = _EM_FQT_MAP[fqt]
        try:
            text = await self._client.kline(
                fields1="f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                fields2="f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                beg=0,
                end=20500101,
                secid=secid,
                klt=101,  # 日线
                fqt=int(fqt_code),
            )
        except Exception:
            return []
        if not text:
            return []
        import json
        try:
            payload = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            return []
        data = payload.get("data") or {}
        klines = data.get("klines") or []
        rows: list[KLineRow] = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            try:
                rows.append(KLineRow(
                    date=parts[0],
                    open=_to_float(parts[1]) or 0.0,
                    close=_to_float(parts[2]) or 0.0,
                    high=_to_float(parts[3]) or 0.0,
                    low=_to_float(parts[4]) or 0.0,
                    # A股 f56 vol 单位是"手"(1手=100股), 统一换算为"股"
                    volume=(_to_int(parts[5]) or 0) * 100,
                    amount=_to_float(parts[6]),
                    amplitude=_to_float(parts[7]),
                    amount_of_increase=_to_float(parts[8]),
                    up_down_amount=_to_float(parts[9]),
                    turnover=_to_float(parts[10]),
                ))
            except Exception:
                continue
        rows.sort(key=lambda r: r.date, reverse=True)
        result = rows[:limit]
        result.sort(key=lambda r: r.date)
        return result

    async def aclose(self) -> None:
        # 不关闭全局 client, 留作 singleton
        pass