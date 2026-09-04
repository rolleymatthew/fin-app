"""THS (Tonghuashun / 10jqka) KLine adapter.

Full history via parallel v4 per-year requests, 11 fields per row:
[date, open, high, low, close, volume, amount, turnover, ?, ?, ?]

无需 cookie. fields [8]/[9]/[10] 在大多数日期为空, 含义不明.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date as _date
from typing import Any

import httpx

from app.clients.kline.types import FQT, PERIOD, SOURCE, KLineRow

_FQT_CODE_MAP = {
    FQT.QFQ: "01",
    FQT.NONE: "02",
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


def _strip_market_prefix(symbol: str) -> str:
    s = symbol.lower()
    for p in ("sh", "sz", "bj"):
        if s.startswith(p):
            return s[len(p):]
    return s


def _format_ths_date(s: str) -> str:
    """'20260105' -> '2026-01-05'."""
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _decode_v4_row(line: str) -> KLineRow | None:
    """单行 CSV: date,open,high,low,close,volume,amount,turnover,?,?,?"""
    parts = line.strip().split(",")
    if len(parts) < 7:
        return None
    return KLineRow(
        date=_format_ths_date(parts[0]),
        open=_to_float(parts[1]) or 0.0,
        high=_to_float(parts[2]) or 0.0,
        low=_to_float(parts[3]) or 0.0,
        close=_to_float(parts[4]) or 0.0,
        volume=_to_int(parts[5]) or 0,
        amount=_to_float(parts[6]),
        turnover=_to_float(parts[7]),
    )


def _decode_v4_payload(payload: dict) -> list[KLineRow]:
    data_str = payload.get("data") or ""
    if not data_str:
        return []
    rows: list[KLineRow] = []
    for line in data_str.split(";"):
        row = _decode_v4_row(line)
        if row is not None:
            rows.append(row)
    return rows


def _extract_year(url: str) -> int | None:
    m = re.search(r"/(\d{4})\.js$", url)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


class ThsAdapter:
    source = SOURCE.THS
    base_url = "https://d.10jqka.com.cn"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            timeout=30, follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                ),
                "Referer": "http://stockpage.10jqka.com.cn/",
            },
        )

    async def _get(self, url: str) -> Any:
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp

    def _year_urls(self, code: str, fqt_code: str, years: list[int]) -> list[str]:
        return [
            f"{self.base_url}/v4/line/hs_{code}/{fqt_code}/{y}.js"
            for y in years
        ]

    @staticmethod
    def _years_to_fetch(today: _date, max_years: int = 15) -> list[int]:
        """从今年往回推 max_years 年. THS 一般能覆盖到 ETF 上市日, 超出自动为空."""
        return [today.year - i for i in range(max_years)]

    async def _fetch_year(self, url: str) -> list[KLineRow]:
        try:
            resp = await self._get(url)
        except Exception:
            return []
        m = re.search(r"\((.+)\)\s*$", resp.text, re.S)
        if not m:
            return []
        try:
            payload = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            return []
        return _decode_v4_payload(payload)

    # ------------------------------------------------------------------ #
    # 版本回退 (新增 2026-08-21: 同花顺每个 ETF 适配的 v 路径不同)
    # ------------------------------------------------------------------ #
    # 优先级: v4 最常用, 其余作为兜底. 503/502/HTML 等端点不存在才回退,
    # 200 但 data 为空 (ETF 未上市) 不回退, 直接返回 [].
    _THS_VERSION_PRIORITY = ("v4", "v1", "v2", "v3", "v6")

    async def _try_fetch_year_variants(
        self, code: str, fqt_code: str, year: int,
    ) -> list[KLineRow]:
        """按版本优先级尝试拉取单年 K 线, 首个返回 JSONP 即用 (含空 data)."""
        tried: list[str] = []
        for version in self._THS_VERSION_PRIORITY:
            url = f"{self.base_url}/{version}/line/hs_{code}/{fqt_code}/{year}.js"
            try:
                resp = await self._get(url)
            except Exception as exc:
                # httpx.HTTPStatusError 等, 只记录简短类型名
                tried.append(f"{version}={type(exc).__name__}")
                continue
            if resp is None:
                tried.append(f"{version}=None")
                continue
            # 检查是否 JSONP 格式 (而非 HTML 502 错误页)
            m = re.search(r"\((.+)\)\s*$", resp.text, re.S)
            if not m:
                tried.append(f"{version}=html")
                continue
            try:
                payload = json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                tried.append(f"{version}=bad-json")
                continue
            # 成功: JSONP 已解析, 直接返回 (data 为空 → [], 表示 ETF 未上市)
            return _decode_v4_payload(payload)
        # 所有版本都失败 → 简洁记录, 避免日志被 stack trace 淹没
        print(
            f"[ths] all-versions-failed code={code} year={year} tried={','.join(tried)}",
            flush=True,
        )
        return []

    async def fetch(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> list[KLineRow]:
        if limit <= 0:
            return []
        if period not in (PERIOD.DAY,):
            return []
        code = _strip_market_prefix(symbol)
        fqt_code = _FQT_CODE_MAP[fqt]
        years = self._years_to_fetch(_date.today())
        # 并发拉取所有年份, 每个年份按版本优先级 (v4/v1/v2/v3/v6) 回退
        per_year = await asyncio.gather(
            *(self._try_fetch_year_variants(code, fqt_code, y) for y in years),
            return_exceptions=False,
        )
        all_rows: list[KLineRow] = []
        for rows in per_year:
            all_rows.extend(rows)
        # 按日期降序, 取最新 limit 条, 再升序返回
        all_rows.sort(key=lambda r: r.date, reverse=True)
        result = all_rows[:limit]
        result.sort(key=lambda r: r.date)
        return result

    async def aclose(self) -> None:
        await self._client.aclose()