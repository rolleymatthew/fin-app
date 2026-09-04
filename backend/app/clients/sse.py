from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient


class SseClient(BaseHttpClient):
    def __init__(self):
        super().__init__("http://query.sse.com.cn")

    async def etf(self, stat_date: str) -> Any:
        headers = {"Referer": "http://www.sse.com.cn/"}
        params = {"STAT_DATE": stat_date}
        return await self.get_json(
            "/commonQuery.do", params={**params, "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L", "isPagination": "false"}, headers=headers
        )