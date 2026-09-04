from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient


class TencentClient(BaseHttpClient):
    def __init__(self):
        super().__init__("http://web.ifzq.gtimg.cn")

    async def kline(self, params: dict[str, str]) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://gu.qq.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        return await self.get_text("/appstock/app/fqkline/get", params=params, headers=headers)

    async def kline_json(self, params: dict[str, str]) -> Any:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://gu.qq.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        return await self.get_json("/appstock/app/fqkline/get", params=params, headers=headers)
