from __future__ import annotations

import json
from typing import Any

from app.clients.base import BaseHttpClient


class FinanceEastmoneyV2Client(BaseHttpClient):
    """
    东方财富新版数据中心接口兼容 Client。

    与 FinanceEastmoneyClient 保持完全一致的方法签名，
    内部调用 datacenter.eastmoney.com 新接口，并将返回格式转换为旧接口格式，
    保证上层业务代码无需任何修改即可切换。
    """

    # 按公司类型选不同前缀：
    #   G = 通用（UniversalTypeCode="4"）
    #   I = 保险（InsuranceTypeCode="2"）
    #   B = 银行（BankTypeCode="3"）
    #   S = 证券（SecuritiesTypeCode="1"）
    # 东方财富 F10 页面（https://emweb.securities.eastmoney.com/pc_hsf10/
    # pages/index.html?code=SH601318#/cwfx/cwbb）对保险/银行/证券走专用报表接口
    # （RPT_F10_FINANCE_I*/B*/S*），通用 G* 接口对这三类返回空集。真正的国债/可转债
    # 等债券在 RPT_F10_ORG_BASICINFO 中无记录，不进入本 V2 流程。
    _REPORT_TYPES_BY_PREFIX = {
        "G": {
            "profit": "RPT_F10_FINANCE_GINCOME",
            "cashflow": "RPT_F10_FINANCE_GCASHFLOW",
            "assets": "RPT_F10_FINANCE_GBALANCE",
        },
        "I": {
            "profit": "RPT_F10_FINANCE_IINCOME",
            "cashflow": "RPT_F10_FINANCE_ICASHFLOW",
            "assets": "RPT_F10_FINANCE_IBALANCE",
        },
        "B": {
            "profit": "RPT_F10_FINANCE_BINCOME",
            "cashflow": "RPT_F10_FINANCE_BCASHFLOW",
            "assets": "RPT_F10_FINANCE_BBALANCE",
        },
        "S": {
            "profit": "RPT_F10_FINANCE_SINCOME",
            "cashflow": "RPT_F10_FINANCE_SCASHFLOW",
            "assets": "RPT_F10_FINANCE_SBALANCE",
        },
    }

    _STY_FULL_BY_PREFIX = {
        "G": {
            "profit": "APP_F10_GINCOME",
            "cashflow": "APP_F10_GCASHFLOW",
            "assets": "F10_FINANCE_GBALANCE",
        },
        "I": {
            "profit": "APP_F10_IINCOME",
            "cashflow": "APP_F10_ICASHFLOW",
            "assets": "F10_FINANCE_IBALANCE",
        },
        "B": {
            "profit": "APP_F10_BINCOME",
            "cashflow": "APP_F10_BCASHFLOW",
            "assets": "F10_FINANCE_BBALANCE",
        },
        "S": {
            "profit": "APP_F10_SINCOME",
            "cashflow": "APP_F10_SCASHFLOW",
            "assets": "F10_FINANCE_SBALANCE",
        },
    }

    _STY_DATES = "SECUCODE,SECURITY_CODE,REPORT_DATE,REPORT_TYPE,REPORT_DATE_NAME"

    # orgTypeCode → V2 前缀。未识别默认 G
    _ORG_TYPE_TO_PREFIX = {
        "4": "G",  # UniversalTypeCode
        "2": "I",  # InsuranceTypeCode
        "3": "B",  # BankTypeCode
        "1": "S",  # SecuritiesTypeCode
    }

    def __init__(self):
        super().__init__("https://datacenter.eastmoney.com")

    @staticmethod
    def _to_secucodes(code: str) -> str:
        """将 SH600519 / SZ000001 转换为 600519.SH / 000001.SZ"""
        if code.startswith("SH"):
            return code[2:] + ".SH"
        if code.startswith("SZ"):
            return code[2:] + ".SZ"
        return code

    @staticmethod
    def _format_date_in(date: str) -> str:
        """将逗号分隔的日期列表转换为 SQL IN 语法所需的单引号分隔格式。"""
        dates = [d.strip() for d in date.split(",") if d.strip()]
        return ",".join(f"'{d}'" for d in dates)

    @classmethod
    def _org_prefix(cls, company_type: str | None) -> str:
        """orgTypeCode → V2 接口前缀（G / I / B）。未识别返回 G。"""
        return cls._ORG_TYPE_TO_PREFIX.get(company_type or "", "G")

    async def _fetch(self, report_type: str, code: str, date: str, company_type: str = "4") -> str:
        """通用报表数据拉取，返回与旧接口一致的 JSON 字符串。"""
        prefix = self._org_prefix(company_type)
        report_name = self._REPORT_TYPES_BY_PREFIX[prefix][report_type]
        sty = self._STY_FULL_BY_PREFIX[prefix][report_type]
        secucode = self._to_secucodes(code)
        date_clause = self._format_date_in(date)
        params = {
            "type": report_name,
            "sty": sty,
            "filter": f'(SECUCODE="{secucode}")(REPORT_DATE in ({date_clause}))',
            "p": 1,
            "ps": 5,
            "sr": -1,
            "st": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
            "v": "1234567890",
        }
        resp_text = await self.get_text("/securities/api/data/get", params=params)
        payload = json.loads(resp_text)
        result = payload.get("result") or {}
        # 包装为旧接口格式 {"pages": 1, "data": [...]}
        wrapped = {"pages": result.get("pages", 1), "data": result.get("data", [])}
        return json.dumps(wrapped, ensure_ascii=False)

    async def _fetch_dates(self, report_type: str, code: str, company_type: str = "4") -> Any:
        """通用日期列表拉取，返回与旧接口一致的字典结构。"""
        prefix = self._org_prefix(company_type)
        report_name = self._REPORT_TYPES_BY_PREFIX[prefix][report_type]
        secucode = self._to_secucodes(code)
        params = {
            "type": report_name,
            "sty": self._STY_DATES,
            "filter": f'(SECUCODE="{secucode}")',
            "p": 1,
            "ps": 200,
            "sr": -1,
            "st": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
            "v": "1234567890",
        }
        resp_text = await self.get_text("/securities/api/data/get", params=params)
        payload = json.loads(resp_text)
        result = payload.get("result") or {}
        items = result.get("data", [])
        # 转换字段名为旧接口格式（小写驼峰），兼容 _get_date_list 等消费代码
        mapped = []
        for item in items:
            mapped.append(
                {
                    "reportDate": item.get("REPORT_DATE"),
                    "reportType": item.get("REPORT_TYPE"),
                    "reportDateName": item.get("REPORT_DATE_NAME"),
                }
            )
        return {"pages": result.get("pages", 1), "data": mapped}

    # ------------------------------------------------------------------
    # 对外接口（与 FinanceEastmoneyClient 签名完全一致）
    # ------------------------------------------------------------------

    async def profit(self, company_type: str, date: str, code: str) -> str:
        """利润表。按 orgTypeCode 选择 G/I/B 前缀。"""
        return await self._fetch("profit", code, date, company_type)

    async def cash_flow(self, company_type: str, date: str, code: str) -> str:
        """现金流量表。按 orgTypeCode 选择 G/I/B 前缀。"""
        return await self._fetch("cashflow", code, date, company_type)

    async def assets(self, company_type: str, date: str, code: str) -> str:
        """资产负债表。按 orgTypeCode 选择 G/I/B 前缀。"""
        return await self._fetch("assets", code, date, company_type)

    async def profit_dates(self, company_type: str, code: str) -> Any:
        """利润表可用日期列表。按 orgTypeCode 选择 G/I/B 前缀。"""
        return await self._fetch_dates("profit", code, company_type)

    async def cash_flow_dates(self, company_type: str, code: str) -> Any:
        """现金流量表可用日期列表。按 orgTypeCode 选择 G/I/B 前缀。"""
        return await self._fetch_dates("cashflow", code, company_type)

    async def assets_dates(self, company_type: str, code: str) -> Any:
        """资产负债表可用日期列表。按 orgTypeCode 选择 G/I/B 前缀。"""
        return await self._fetch_dates("assets", code, company_type)
