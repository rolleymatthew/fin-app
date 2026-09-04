from __future__ import annotations

import io
from typing import Any

import openpyxl

from app.clients.base import BaseHttpClient
from app.clients.exchange_base import OfficialStock

SZSE_BASE_URL = "https://www.szse.cn"


class SzseXlsxClient(BaseHttpClient):
    """SZSE 在市 A 股列表客户端：下载 ShowReport xlsx 并解析。"""

    def __init__(self, http_client: Any | None = None):
        super().__init__(SZSE_BASE_URL, http2=False)

    async def fetch_list(self) -> list[OfficialStock]:
        params = {
            "SHOWTYPE": "xlsx",
            "CATALOGID": "1110",
            "TABKEY": "tab1",
            "random": "0.5",
        }
        headers = {
            "Referer": "https://www.szse.cn/market/product/stock/list/index.html",
        }
        try:
            resp = await self.get(
                "/api/report/ShowReport", params=params, headers=headers
            )
            content = resp.content
        except Exception as exc:
            raise Exception(f"SZSE xlsx request failed: {exc}") from exc
        return self._parse_xlsx(content)

    def _parse_xlsx(self, content: bytes) -> list[OfficialStock]:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        except Exception as exc:
            raise Exception(f"SZSE xlsx parse failed: {exc}") from exc
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(c) if c is not None else "" for c in rows[0]]
        header_map = {i: h for i, h in enumerate(header)}
        result: list[OfficialStock] = []
        for raw in rows[1:]:
            stock = self._row_to_official(list(raw), header_map)
            if stock is not None:
                result.append(stock)
        return result

    @staticmethod
    def _row_to_official(row: list, header_map: dict[int, str]) -> OfficialStock | None:
        idx_code = idx_name = idx_date = idx_board = None
        for i, header in header_map.items():
            if header == "A股代码":
                idx_code = i
            elif header == "A股简称":
                idx_name = i
            elif header == "A股上市日期":
                idx_date = i
            elif header == "板块":
                idx_board = i
        if idx_code is None or idx_name is None:
            return None
        if idx_code >= len(row) or idx_name >= len(row):
            return None
        code = str(row[idx_code] or "").strip()
        name = str(row[idx_name] or "").strip()
        if not code.isdigit() or len(code) != 6 or not name:
            return None
        listing_date = None
        if idx_date is not None and idx_date < len(row) and row[idx_date]:
            listing_date = str(row[idx_date]).strip() or None
        board = None
        if idx_board is not None and idx_board < len(row) and row[idx_board]:
            board = str(row[idx_board]).strip() or None
        raw = {header_map[i]: row[i] for i in header_map if i < len(row)}
        return OfficialStock(
            code=code,
            name=name,
            market="SZ",
            listingDate=listing_date,
            listingState="0",
            type=board,
            raw=raw,
        )

    async def close(self):
        await super().close()
