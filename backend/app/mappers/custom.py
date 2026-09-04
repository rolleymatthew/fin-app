from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime
from decimal import Decimal

from app.models.entities import (
    BonusEntity,
    DuPondEntity,
    EtfEntity,
    EtfQuarterEntity,
    FinEntity,
    SecCodeEntity,
    ShareBonusEntity,
)
from app.utils.transform import normalize_keys


def _id_from_report_date(security_code: str, report_date: str) -> str:
    return f"{security_code}{report_date.replace(' 00:00:00', '')}"


def bonus_dto_to_entity(data: dict) -> BonusEntity:
    d = normalize_keys(data)
    entity = BonusEntity.model_validate(d)
    report_date = d.get("reportDate", "")
    sec_code = d.get("securityCode", "")
    if "年报" in report_date:
        entity.id = f"{sec_code}{report_date.replace('年报', '-12-31')}"
    elif "半年报" in report_date:
        entity.id = f"{sec_code}{report_date.replace('半年报', '-06-30')}"
    elif "一季报" in report_date:
        entity.id = f"{sec_code}{report_date.replace('一季报', '-03-31')}"
    elif "三季报" in report_date:
        entity.id = f"{sec_code}{report_date.replace('三季报', '-09-30')}"
    if entity.id is None:
        entity.id = _id_from_report_date(sec_code, report_date)
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def share_bonus_dto_to_entity(data: dict) -> ShareBonusEntity:
    d = normalize_keys(data)
    entity = ShareBonusEntity.model_validate(d)
    entity.id = _id_from_report_date(d.get("securityCode", ""), d.get("reportDate", ""))
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def dupond_dto_to_entity(data: dict) -> DuPondEntity:
    d = normalize_keys(data)
    entity = DuPondEntity.model_validate(d)
    entity.id = _id_from_report_date(d.get("securityCode", ""), d.get("reportDate", ""))
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def etf_dto_to_entity(today_data: dict, yesterday_data: dict | None) -> EtfEntity:
    d = normalize_keys(today_data)
    y = normalize_keys(yesterday_data) if yesterday_data else None
    entity = EtfEntity.model_validate(d)
    entity.id = f"{entity.secCode}{entity.statDate}"
    if d and y:
        tot_vol = Decimal(str(d.get("totVol", 0))) * Decimal(10000)
        before_value = Decimal(str(y.get("totVol", 0))) * Decimal(10000)
        entity.totVol = tot_vol
        entity.beforeValue = before_value
        entity.addVol = int(tot_vol - before_value)
        entity.beforeDate = y.get("statDate")
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def etf_szse_dto_to_entity(row: dict, stat_date: dt_date) -> EtfEntity | None:
    """深交所 ETF 数据 -> EtfEntity
    row: {"SEC_CODE": "159001", "SEC_NAME": "...", "TOT_VOL_YI": Decimal("0.23"), "MANAGER": "..."}
    深交所原始单位为亿份，乘以 10^8 转为"份"，与 SSE 存储口径一致。
    """
    code = row.get("SEC_CODE")
    if not code:
        return None
    try:
        sec_code = int(code)
    except (TypeError, ValueError):
        return None
    tot_vol_yi = row.get("TOT_VOL_YI")
    if tot_vol_yi is None:
        return None
    tot_vol = (tot_vol_yi * Decimal(100000000)).quantize(Decimal("1."))
    stat_date_str = stat_date.isoformat() if isinstance(stat_date, dt_date) else str(stat_date)
    entity = EtfEntity(
        secCode=sec_code,
        secName=row.get("SEC_NAME") or "",
        statDate=stat_date_str,
        totVol=tot_vol,
        etfType="深市",
    )
    entity.id = f"{sec_code}{stat_date_str}"
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def fin_to_entity(zqh, sec_code: str) -> FinEntity:
    entity = FinEntity.model_validate(zqh.model_dump()) if hasattr(zqh, "model_dump") else FinEntity.model_validate(zqh.__dict__)
    entity.secCode = sec_code
    entity.id = f"{sec_code}{getattr(zqh, 'reportDate', '')}"
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def seccode_from_company(data: dict) -> SecCodeEntity:
    d = normalize_keys(data)
    entity = SecCodeEntity.model_validate(d)
    entity.id = entity.securityCode
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity


def etf_quarter_dto_to_entity(row: dict, sec_name: str | None = None) -> EtfQuarterEntity | None:
    """东方财富 gmbd 单行 -> EtfQuarterEntity

    row: {"date": "2026-06-30", "purchase": "0.02", "redeem": "0.09",
          "totVolYi": "1.33", "netAssetYi": "2.20", "changeRate": "-9.53%"}

    期末总份额单位为亿份，乘以 10^8 转为"份"，与 SSE 日度口径一致。
    """
    date_str = row.get("date")
    if not date_str:
        return None

    def _to_decimal(val, default=None):
        if val is None or val == "" or val == "---":
            return default
        try:
            return Decimal(str(val))
        except Exception:
            return default

    tot_vol_yi = _to_decimal(row.get("totVolYi"))
    if tot_vol_yi is None:
        return None

    tot_vol = (tot_vol_yi * Decimal(100000000)).quantize(Decimal("1."))

    entity = EtfQuarterEntity(
        statDate=date_str,
        secName=sec_name or "",
        totVol=tot_vol,
        netAsset=_to_decimal(row.get("netAssetYi")),
        purchaseVol=_to_decimal(row.get("purchase")),
        redeemVol=_to_decimal(row.get("redeem")),
        changeRate=row.get("changeRate") or None,
        frequency="quarter",
        source="eastmoney_gmbd",
    )
    entity.id = None  # secCode 在 service 层补
    entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return entity
