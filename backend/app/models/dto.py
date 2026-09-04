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
