from __future__ import annotations

from datetime import date as dt_date
from decimal import Decimal

from pydantic import BaseModel


class RoeDTO(BaseModel):
    id: str | None = None
    securityCode: str | None = None
    reportDate: str | None = None
    roe: float | None = None


class EpsDTO(BaseModel):
    date: dt_date | None = None
    eps: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    avg: Decimal | None = None
    highEps: Decimal | None = None
    lowEps: Decimal | None = None
    avgEps: Decimal | None = None


class BankPEHistoryPointDTO(BaseModel):
    """银行股 PE 时序单点：PE = close / EPS。

    由 profit_bank 每条记录 + kline 现算。
    任一关键字段缺失时 pe=null, error 填人话原因。
    """

    date: str | None = None
    reportDate: str | None = None
    eps: float | None = None
    epsField: str | None = None
    close: float | None = None
    pe: float | None = None
    error: str | None = None


class BankPEDTO(BaseModel):
    """银行股 PE 单点最新值（等于 BankPEHistoryPointDTO 最新非空 pe 那一项 + 附加元数据）。"""

    secCode: str | None = None
    securityNameAbbr: str | None = None
    reportDate: str | None = None
    eps: float | None = None
    epsField: str | None = None
    close: float | None = None
    closeDate: str | None = None
    pe: float | None = None
    error: str | None = None
