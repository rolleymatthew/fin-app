"""银行股 PE 时序计算服务。

按 profit_bank 每条记录（升序）+ kline 现算 PE = close / EPS。
不依赖总股本（直接读 EPS 候选字段），不落库。

调用方:
- backend/app/api/stock.py  :: GET /stock/bank/pe/history
"""
from __future__ import annotations

from typing import Any, Iterable

from app.models.dto import BankPEDTO, BankPEHistoryPointDTO


class BankPEService:
    """实时计算银行股的 PE 时序（按报表日升序）。"""

    # 候选字段按顺序尝试，首个非空且能转 float 的字段即采纳。
    # 字段命名参考：东财 RPT_F10_FINANCE_BINCOME 与港股端 BASIC_EPS 习惯。
    _EPS_CANDIDATES: tuple[str, ...] = (
        "eps",
        "EPS",
        "basicEps",
        "BASIC_EPS",
        "dilutedEps",
        "DILUTED_EPS",
        "parentNetEps",
        "PARENT_NETS",
        "epsBasic",
        "EPS_BASIC",
        "parentCompanyEps",
        "epsParent",
        "epsBelongParent",
        "epsBelongToParent",
    )

    def __init__(self, profit_bank_repo, kline_service, sec_code_service):
        self.profit_bank_repo = profit_bank_repo
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
        for key in candidates:
            if isinstance(doc, dict):
                raw = doc.get(key)
            else:
                raw = getattr(doc, key, None)
            f = self._coerce_float(raw)
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
            close = BankPEService._coerce_float(getattr(k, "close", None))
            if close is not None:
                return close, kdate
        return None, None

    async def calculate_pe_history(self, sec_code: str) -> list[BankPEHistoryPointDTO]:
        profit_list = (
            await self.profit_bank_repo.find_all_by_security_code_order_by_report_date_asc(
                sec_code,
            )
        )
        kline_entity = await self.kline_service.kline_by_sec_code(sec_code)
        klines = kline_entity.klines if kline_entity and kline_entity.klines else []

        results: list[BankPEHistoryPointDTO] = []
        for p in profit_list or []:
            rdate = getattr(p, "reportDate", None)
            if not rdate:
                continue
            eps, eps_field = self._pick_first(p, self._EPS_CANDIDATES)
            close, close_date = self._find_close_on_or_after(klines, rdate)

            if eps is None and close is None:
                err = (
                    f"未找到每股收益字段（已尝试 {len(self._EPS_CANDIDATES)} 个候选名）；"
                    "且无 K 线数据"
                )
                pe = None
            elif eps is None:
                err = f"未找到每股收益字段（已尝试 {len(self._EPS_CANDIDATES)} 个候选名）"
                pe = None
            elif close is None:
                err = "无 K 线数据"
                pe = None
            else:
                err = None
                pe = round(close / eps, 4)

            results.append(
                BankPEHistoryPointDTO(
                    date=close_date,
                    reportDate=rdate,
                    eps=eps,
                    epsField=eps_field,
                    close=close,
                    pe=pe,
                    error=err,
                )
            )
        return results

    async def calculate_pe(self, sec_code: str) -> BankPEDTO:
        """单点最新值 = 时序最后一项的 pe（按 reportDate 升序）。"""
        history = await self.calculate_pe_history(sec_code)
        entity = None
        try:
            entity = await self.sec_code_service.sec_code_entity_by_id(sec_code)
        except Exception:
            entity = None

        if not history:
            return BankPEDTO(
                secCode=sec_code,
                securityNameAbbr=getattr(entity, "securityNameAbbr", None) if entity else None,
                error="无报表数据",
            )

        latest = history[-1]
        return BankPEDTO(
            secCode=sec_code,
            securityNameAbbr=getattr(entity, "securityNameAbbr", None) if entity else None,
            reportDate=latest.reportDate,
            eps=latest.eps,
            epsField=latest.epsField,
            close=latest.close,
            closeDate=latest.date,
            pe=latest.pe,
            error=latest.error,
        )