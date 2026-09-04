from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.clients.base import BaseHttpClient


class EastMoneyGmbdClient(BaseHttpClient):
    """东方财富 ETF 季度规模变动接口

    返回季度级别（3/6/9/12 月末）的份额/净资产数据。
    URL: https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=gmbd&code={code}
    """

    def __init__(self):
        super().__init__("https://fundf10.eastmoney.com")

    async def gmbd(self, code: str) -> Any:
        """获取单只基金的季度规模变动数据

        code: 6 位基金代码，如 "510010"、"159001"
        """
        params = {"type": "gmbd", "code": code}
        headers = {
            "Referer": f"https://fundf10.eastmoney.com/gmbd_{code}.html",
            "Accept": "*/*",
        }
        return await self.get_text(
            "/FundArchivesDatas.aspx", params=params, headers=headers
        )

    @staticmethod
    def parse_gmbd(text: str) -> list[dict[str, Any]]:
        """解析 gmbd 接口的 HTML 响应

        返回 [{"date": "2026-06-30", "purchase": "0.02", "redeem": "0.09",
                "totVolYi": "1.33", "netAssetYi": "2.20", "changeRate": "-9.53%"}]
        """
        match = re.search(r'content:\s*"(.*?)"\s*\}', text, re.DOTALL)
        if not match:
            return []

        html = match.group(1)
        rows = re.findall(
            r'<tr[^>]*>\s*<td[^>]*>(\d{4}-\d{2}-\d{2})</td>\s*'
            r'<td[^>]*>([^<]*)</td>\s*'
            r'<td[^>]*>([^<]*)</td>\s*'
            r'<td[^>]*>([^<]*)</td>\s*'
            r'<td[^>]*>([^<]*)</td>\s*'
            r'<td[^>]*>([^<]*)</td>',
            html,
        )

        result = []
        for date_str, purchase, redeem, tot_vol, net_asset, change_rate in rows:
            result.append({
                "date": date_str,
                "purchase": purchase.strip(),
                "redeem": redeem.strip(),
                "totVolYi": tot_vol.strip(),
                "netAssetYi": net_asset.strip(),
                "changeRate": change_rate.strip(),
            })
        return result

    @staticmethod
    def timestamp_to_date(ts_ms: float) -> str:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def parse_jzcgm(text: str) -> list[dict[str, Any]]:
        """解析 jzcgm 接口（季度净资产时间序列）"""
        match = re.search(r"\[(.*?)\]", text, re.DOTALL)
        if not match:
            return []
        raw = match.group(1)
        pairs = re.findall(r"\[\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*\]", raw)
        result = []
        for ts, val in pairs:
            result.append({
                "date": EastMoneyGmbdClient.timestamp_to_date(float(ts)),
                "netAssetYi": Decimal(val),
            })
        return result