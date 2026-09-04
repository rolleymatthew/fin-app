from __future__ import annotations

import random
import re
from decimal import Decimal
from typing import Any

from app.clients.base import BaseHttpClient


class SzseClient(BaseHttpClient):
    def __init__(self):
        super().__init__("https://fund.szse.cn")

    async def etf(self) -> Any:
        params = {
            "SHOWTYPE": "JSON",
            "CATALOGID": "ssjjcp_1",
            "txtJjlb": "ETF",
            "random": str(random.random()),
        }
        headers = {
            "Referer": "https://fund.szse.cn/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        return await self.get_json(
            "/api/report/ShowReport/data", params=params, headers=headers
        )

    async def etf_date(self) -> str | None:
        params = {
            "SHOWTYPE": "JSON",
            "CATALOGID": "fund_etf",
            "loading": "first",
            "random": str(random.random()),
        }
        headers = {
            "Referer": "https://fund.szse.cn/marketdata/etf/index.html",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        raw = await self.get_json(
            "/api/report/ShowReport/data", params=params, headers=headers
        )
        if not isinstance(raw, list) or not raw:
            return None
        metadata = raw[0].get("metadata", {})
        value = metadata.get("subname") if isinstance(metadata, dict) else None
        return (
            value
            if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            else None
        )

    @staticmethod
    def parse_etf_rows(raw: Any) -> list[dict[str, Any]]:
        if not raw or not isinstance(raw, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            for row in item.get("data", []) or []:
                code = _strip_html(row.get("jjdm", ""))
                name = _strip_html(row.get("jjjc", ""))
                if not code or not code.isdigit():
                    continue
                scale_raw = row.get("dqgm", "0")
                try:
                    scale_yi = Decimal(str(scale_raw))
                except Exception:
                    continue
                rows.append(
                    {
                        "SEC_CODE": code,
                        "SEC_NAME": name,
                        "TOT_VOL_YI": scale_yi,
                        "MANAGER": row.get("glrmc", "") or "",
                    }
                )
        return rows


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", "", html).strip()