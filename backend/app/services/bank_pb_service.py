"""银行股 PB（市净率）时序计算服务。

PB = close / BPS。

BPS 来源（按顺序尝试）：
1. assets_bank 上报字段直接读 BPS（候选链）
2. 银行表无 per-share 字段时：BPS = totalParentEquity / shareCapital
   （银行股本面值 1元，故 shareCapital(元) = 总股本(股)）
3. 任一缺失 → pb=null, error 填人话原因

不落库、不调用外部 client。

调用方:
- backend/app/api/stock.py  :: GET /stock/bank/pb/history
"""
from __future__ import annotations

from typing import Any, Iterable

from app.models.dto import BankPBDTO, BankPBHistoryPointDTO


class BankPBService:
    """实时计算银行股的 PB 时序（按报表日升序）。"""

    # 候选字段按顺序尝试，首个非空且能转 float 的字段即采纳。
    # 字段命名参考：东财 RPT_F10_FINANCE_BBALANCE 的银行报表口径。
    _BPS_CANDIDATES: tuple[str, ...] = (
        "bps",
        "BPS",
        "perShareNetasset",
        "PER_SHARE_NETASSET",
        "netAssetPerShare",
        "NETASSET_PER_SHARE",
        "bookValuePerShare",
        "BOOK_VALUE_PER_SHARE",
        "navPerShare",
        "NAV_PER_SHARE",
        "bpsAdj",
        "BPS_ADJ",
        "perShareNetassetAdj",
        "PER_SHARE_NETASSET_ADJ",
    )

    # 股东权益候选（用于回退计算 BPS）
    _EQUITY_CANDIDATES: tuple[str, ...] = (
        "totalParentEquity",
        "TOTAL_PARENT_EQUITY",
        "parentEquity",
        "PARENT_EQUITY",
        "equityParent",
        "EQUITY_PARENT",
        "totalEquity",
        "TOTAL_EQUITY",
    )

    # 总股本候选（银行股本面值 1 元，shareCapital(元) = 总股本(股)）
    _SHARES_CANDIDATES: tuple[str, ...] = (
        "shareCapital",
        "SHARE_CAPITAL",
        "totalShare",
        "TOTAL_SHARE",
        "shareTotal",
        "SHARE_TOTAL",
    )

    def __init__(self, assets_bank_repo, kline_service, sec_code_service):
        self.assets_bank_repo = assets_bank_repo
        self.kline_service = kline_service
        self.sec_code_service = sec_code_service

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _pick_first(self, doc: Any, candidates: Iterable[str]) -> tuple[float | None, str | None]:
        """在 doc 上按 candidates 顺序找第一个能转 float 的字段。

        doc 兼容 Pydantic 模型（用 getattr）和 dict（用 []）两种入口。
        返回 (value, matched_field_name)；找不到返 (None, None)。
        """
        return BankPBService._pick_first_static(doc, candidates)

    @staticmethod
    def _pick_first_static(doc: Any, candidates: Iterable[str]) -> tuple[float | None, str | None]:
        """纯函数版 `_pick_first`，便于从 staticmethod 内部调用。"""
        for key in candidates:
            if isinstance(doc, dict):
                raw = doc.get(key)
            else:
                raw = getattr(doc, key, None)
            f = BankPBService._coerce_float(raw)
            if f is not None:
                return f, key
        return None, None

    @staticmethod
    def _find_close_on_or_after(klines, report_date: str) -> tuple[float | None, str | None]:
        """klines 存储为按 date 降序（最新在前）；反向迭代找 date >= report_date 的第一个。

        返回 (close, date)；找不到返 (None, None)。
        """
        for k in reversed(klines or []):
            kdate = getattr(k, "date", None)
            if not kdate or kdate < report_date:
                continue
            close = BankPBService._coerce_float(getattr(k, "close", None))
            if close is not None:
                return close, kdate
        return None, None

    @staticmethod
    def _derive_bps(
        doc: Any,
    ) -> tuple[float | None, str | None]:
        """无现成 BPS 字段时：BPS = totalParentEquity / shareCapital。

        返回 (bps, 'totalParentEquity/shareCapital') 或 (None, None)。
        """
        equity, equity_field = BankPBService._pick_first_static(
            doc, BankPBService._EQUITY_CANDIDATES
        )
        shares, shares_field = BankPBService._pick_first_static(
            doc, BankPBService._SHARES_CANDIDATES
        )
        if equity is None or shares is None or shares == 0:
            return None, None
        return equity / shares, f"{equity_field}/{shares_field}"

    async def calculate_pb_history(self, sec_code: str) -> list[BankPBHistoryPointDTO]:
        assets_list = (
            await self.assets_bank_repo.find_all_by_security_code_order_by_report_date_asc(
                sec_code,
            )
        )
        kline_entity = await self.kline_service.kline_by_sec_code(sec_code)
        klines = kline_entity.klines if kline_entity and kline_entity.klines else []

        results: list[BankPBHistoryPointDTO] = []
        for a in assets_list or []:
            rdate = getattr(a, "reportDate", None)
            if not rdate:
                continue
            bps, bps_field = self._pick_first(a, self._BPS_CANDIDATES)
            if bps is None:
                bps, bps_field = self._derive_bps(a)
            close, close_date = self._find_close_on_or_after(klines, rdate)

            if bps is None and close is None:
                err = (
                    f"未找到每股净资产字段（已尝试 {len(self._BPS_CANDIDATES)} 个候选名 +"
                    " 净资产/股本回退）；且无 K 线数据"
                )
                pb = None
            elif bps is None:
                err = (
                    f"未找到每股净资产字段（已尝试 {len(self._BPS_CANDIDATES)} 个候选名 +"
                    " 净资产/股本回退）"
                )
                pb = None
            elif close is None:
                err = "无 K 线数据"
                pb = None
            elif bps == 0:
                err = "每股净资产为 0，无法计算 PB"
                pb = None
            else:
                err = None
                pb = round(close / bps, 4)

            results.append(
                BankPBHistoryPointDTO(
                    date=close_date,
                    reportDate=rdate,
                    bps=bps,
                    bpsField=bps_field,
                    close=close,
                    pb=pb,
                    error=err,
                )
            )
        return results

    async def calculate_pb(self, sec_code: str) -> BankPBDTO:
        """单点最新值 = 时序最后一项的 pb（按 reportDate 升序）。"""
        history = await self.calculate_pb_history(sec_code)
        entity = None
        try:
            entity = await self.sec_code_service.sec_code_entity_by_id(sec_code)
        except Exception:
            entity = None

        if not history:
            return BankPBDTO(
                secCode=sec_code,
                securityNameAbbr=getattr(entity, "securityNameAbbr", None) if entity else None,
                error="无报表数据",
            )

        latest = history[-1]
        return BankPBDTO(
            secCode=sec_code,
            securityNameAbbr=getattr(entity, "securityNameAbbr", None) if entity else None,
            reportDate=latest.reportDate,
            bps=latest.bps,
            bpsField=latest.bpsField,
            close=latest.close,
            closeDate=latest.date,
            pb=latest.pb,
            error=latest.error,
        )