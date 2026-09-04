from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient


class EastmoneyDataCenterClient(BaseHttpClient):
    def __init__(self):
        super().__init__("https://datacenter-web.eastmoney.com")

    async def company(self, report_name: str, columns: str, filter_str: str) -> Any:
        params = {"reportName": report_name, "columns": columns, "filter": filter_str}
        return await self.get_json("/api/data/v1/get", params=params)

    async def company_with_raw(
        self, report_name: str, columns: str, filter_str: str
    ) -> tuple[Any | None, str]:
        params = {"reportName": report_name, "columns": columns, "filter": filter_str}
        response = await self.get("/api/data/v1/get", params=params)
        raw = response.text
        try:
            data = response.json()
        except ValueError:
            data = None
        return data, raw

    async def sshk(self, sort_columns: str, sort_types: str, page_size: int, report_name: str, page_number: int, columns: str, filter_str: str) -> Any:
        params = {
            "sortColumns": sort_columns,
            "sortTypes": sort_types,
            "pageSize": page_size,
            "reportName": report_name,
            "pageNumber": page_number,
            "columns": columns,
            "filter": filter_str,
        }
        return await self.get_json("/api/data/v1/get", params=params)

    async def margin_trade(self, report_name: str, columns: str, page_number: int, page_size: int, sort_types: str, filter_str: str) -> Any:
        params = {
            "reportName": report_name,
            "columns": columns,
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortTypes": sort_types,
            "filter": filter_str,
        }
        return await self.get_json("/api/data/v1/get", params=params)

    async def profit_forecast(self, report_name: str, columns: str, page_number: int, page_size: int, sort_types: str, sort_columns: str) -> Any:
        params = {
            "reportName": report_name,
            "columns": columns,
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortTypes": sort_types,
            "sortColumns": sort_columns,
        }
        return await self.get_json("/api/data/v1/get", params=params)

    async def share_bonus(self, sort_columns: str, sort_types: int, page_size: int, page_number: int, report_name: str, columns: str, source: str, client: str, filter_str: str) -> Any:
        params = {
            "sortColumns": sort_columns,
            "sortTypes": sort_types,
            "pageSize": page_size,
            "pageNumber": page_number,
            "reportName": report_name,
            "columns": columns,
            "source": source,
            "client": client,
            "filter": filter_str,
        }
        return await self.get_json("/api/data/v1/get", params=params)
