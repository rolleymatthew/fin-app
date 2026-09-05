"""KLine adapter types shared across sources."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class PERIOD(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    M5 = "m5"
    M15 = "m15"
    M30 = "m30"
    M60 = "m60"


class FQT(str, Enum):
    """复权方式."""
    NONE = "none"      # 不复权
    QFQ = "qfq"        # 前复权
    HFQ = "hfq"        # 后复权


class SOURCE(str, Enum):
    TENCENT = "tencent"
    SINA = "sina"
    EASTMONEY = "eastmoney"


@dataclass
class KLineRow:
    date: str           # YYYY-MM-DD
    open: float
    close: float
    high: float
    low: float
    volume: int         # 单位: 股
    amount: float | None = None      # 成交额(元)
    turnover: float | None = None    # 换手率(%), 按金额
    amplitude: float | None = None      # 振幅(%)
    amount_of_increase: float | None = None  # 涨跌幅(%)
    up_down_amount: float | None = None     # 涨跌额(元)


@dataclass
class FetchResult:
    rows: list[KLineRow]
    source: SOURCE | None = None
    fell_back: bool = False
    error: str | None = None
    # 每个源的尝试结果 (新增 2026-08-21): 用于增量抓取失败时诊断
    # 格式: [(source_name, status, rows_count, error_or_None)]
    # status: "ok" | "empty" | "error"
    chain_results: list[tuple[str, str, int, str | None]] | None = None


class KLineAdapter(Protocol):
    source: SOURCE

    async def fetch(
        self,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> list[KLineRow]:
        ...