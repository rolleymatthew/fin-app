from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient


class SinaClient(BaseHttpClient):
    def __init__(self):
        super().__init__("https://vip.stock.finance.sina.com.cn")

    async def kline(self, params: dict[str, str]) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://finance.sina.com.cn/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        return await self.get_text("/quotes_service/api/json_v2.php/CN_MarketData.getKLineData", params=params, headers=headers)

    async def kline_json(self, params: dict[str, str]) -> Any:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://finance.sina.com.cn/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        return await self.get_json("/quotes_service/api/json_v2.php/CN_MarketData.getKLineData", params=params, headers=headers)
