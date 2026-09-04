from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient


class FinanceEastmoneyClient(BaseHttpClient):
    def __init__(self):
        super().__init__("https://emweb.securities.eastmoney.com")

    async def profit(self, company_type: str, date: str, code: str) -> str:
        params = {"companyType": company_type, "dates": date, "code": code}
        return await self.get_text("/PC_HSF10/NewFinanceAnalysis/lrbAjaxNew", params={**params, "reportDateType": 0, "reportType": 1})

    async def cash_flow(self, company_type: str, date: str, code: str) -> str:
        params = {"companyType": company_type, "dates": date, "code": code}
        return await self.get_text("/PC_HSF10/NewFinanceAnalysis/xjllbAjaxNew", params={**params, "reportDateType": 0, "reportType": 1})

    async def assets(self, company_type: str, date: str, code: str) -> str:
        params = {"companyType": company_type, "dates": date, "code": code}
        return await self.get_text("/PC_HSF10/NewFinanceAnalysis/zcfzbAjaxNew", params={**params, "reportDateType": 0, "reportType": 1})

    async def profit_dates(self, company_type: str, code: str) -> Any:
        params = {"companyType": company_type, "code": code, "reportDateType": 0}
        return await self.get_json("/PC_HSF10/NewFinanceAnalysis/lrbDateAjaxNew", params=params)

    async def cash_flow_dates(self, company_type: str, code: str) -> Any:
        params = {"companyType": company_type, "code": code, "reportDateType": 0}
        return await self.get_json("/PC_HSF10/NewFinanceAnalysis/xjllbDateAjaxNew", params=params)

    async def assets_dates(self, company_type: str, code: str) -> Any:
        params = {"companyType": company_type, "code": code, "reportDateType": 0}
        return await self.get_json("/PC_HSF10/NewFinanceAnalysis/zcfzbDateAjaxNew", params=params)
