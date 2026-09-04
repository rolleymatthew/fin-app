from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient


class EastmoneyDataNewClient(BaseHttpClient):
    def __init__(self):
        super().__init__("https://datacenter.eastmoney.com")

    async def dupond(self, report_name: str, columns: str, filter_str: str, page_number: int, page_size: int, sort_types: str, sort_columns: str, source: str, client: str, v: str) -> Any:
        params = {
            "reportName": report_name,
            "columns": columns,
            "filter": filter_str,
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortTypes": sort_types,
            "sortColumns": sort_columns,
            "source": source,
            "client": client,
            "v": v,
        }
        return await self.get_json("/securities/api/data/v1/get", params=params)

    async def bonus(self, report_name: str, columns: str, filter_str: str, page_number: int, page_size: int, sort_types: str, sort_columns: str, source: str, client: str, v: str) -> Any:
        params = {
            "reportName": report_name,
            "columns": columns,
            "filter": filter_str,
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortTypes": sort_types,
            "sortColumns": sort_columns,
            "source": source,
            "client": client,
            "v": v,
        }
        return await self.get_json("/securities/api/data/v1/get", params=params)

    async def hk_finance(self, report_name: str, columns: str, filter_str: str, page_number: int, page_size: int, sort_types: str, sort_columns: str, source: str, client: str, v: str) -> Any:
        params = {
            "reportName": report_name,
            "columns": columns,
            "filter": filter_str,
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortTypes": sort_types,
            "sortColumns": sort_columns,
            "source": source,
            "client": client,
            "v": v,
        }
        return await self.get_json("/securities/api/data/v1/get", params=params)
