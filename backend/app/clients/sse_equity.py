from __future__ import annotations

from typing import Any

from app.clients.base import BaseHttpClient
from app.clients.exchange_base import OfficialStock

SSE_EQUITY_URL = "https://yunhq.sse.com.cn:32042"


class SseEquityClient(BaseHttpClient):
    """SSE 在市股票列表客户端：yunhq.sse.com.cn:32042/v1/sh1/list/exchange/equity

    返回 JSON：{"total": 2351, "list": [[code, name, tradephase], ...]}
    一次拉全，无需 cookie/Referer。
    """

    def __init__(self, http_client: Any | None = None):
        super().__init__(SSE_EQUITY_URL, http2=False)

    async def fetch_list(self) -> list[OfficialStock]:
        params = {
            "select": "code,name,tradephase",
            "begin": 0,
            "end": 3000,
        }
        headers = {"Referer": "https://www.sse.com.cn/market/price/report/"}
        try:
            payload = await self.get_json(
                "/v1/sh1/list/exchange/equity", params=params, headers=headers
            )
        except Exception as exc:
            raise Exception(f"SSE equity request failed: {exc}") from exc
        return self._parse(payload)

    @staticmethod
    def _parse(payload: dict) -> list[OfficialStock]:
        result: list[OfficialStock] = []
        for row in payload.get("list") or []:
            stock = SseEquityClient._row_to_official(row)
            if stock is not None:
                result.append(stock)
        return result

    @staticmethod
    def _row_to_official(row: list | dict) -> OfficialStock | None:
        """SSE equity 行 → OfficialStock。

        row 是 [code, name, tradephase] 列表，trailing space 保留（服务端填的）。
        listingState: "0" (E110 正常) / "2" (其它 = 暂停/退市/异常)。
        """
        if not isinstance(row, list) or len(row) < 3:
            return None
        code = str(row[0]).strip()
        name = str(row[1]).strip()
        tradephase = str(row[2]).strip()
        if not code.isdigit() or len(code) != 6 or not name:
            return None
        return OfficialStock(
            code=code,
            name=name,
            market="SH",
            listingDate=None,
            listingState="0" if tradephase == "E110" else "2",
            type=None,
            raw={"code": code, "name": name, "tradephase": row[2]},
        )

    async def close(self):
        await super().close()