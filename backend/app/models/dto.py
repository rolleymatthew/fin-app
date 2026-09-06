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


class BankPBHistoryPointDTO(BaseModel):
    """银行股 PB（市净率）时序单点：PB = close / BPS。

    由 assets_bank 每条记录 + kline 现算。
    任一关键字段缺失时 pb=null, error 填人话原因。
    """

    date: str | None = None
    reportDate: str | None = None
    bps: float | None = None
    bpsField: str | None = None
    close: float | None = None
    pb: float | None = None
    error: str | None = None


class BankPBDTO(BaseModel):
    """银行股 PB 单点最新值（等于 BankPBHistoryPointDTO 最新非空 pb 那一项 + 附加元数据）。"""

    secCode: str | None = None
    securityNameAbbr: str | None = None
    reportDate: str | None = None
    bps: float | None = None
    bpsField: str | None = None
    close: float | None = None
    closeDate: str | None = None
    pb: float | None = None
    error: str | None = None
