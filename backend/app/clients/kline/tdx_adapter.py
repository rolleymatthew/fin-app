"""本地通达信 (TDX) K 线适配器.

职责:
    - resolve_tdx_home(): 三级 fallback 解析 TDX_HOME 路径
    - TdxAdapter: 实现 KLineAdapter 协议, 包 fetch_local_day (Task 3 扩展)

设计: 本模块迁出自 tdx_offline/fetcher.py 的 _resolve_tdx_home, 让 KLinePipeline
能在不依赖 tdx_offline 子包的情况下使用同一路径解析逻辑. tdx_offline 改为
import shim, 保持向后兼容.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

from app.clients.kline.types import FQT, PERIOD, SOURCE, KLineRow
from app.config import get_settings

if TYPE_CHECKING:
    pass


def resolve_tdx_home(tdx_home: str | os.PathLike | None) -> Path:
    """解析 TDX 主目录. 三级 fallback: 入参 > settings.tdx_home > TDX_HOME 环境变量 > 默认.

    默认值 C:\\zd_zxzq_gm 与 tdx_offline 既有契约一致.
    """
    if tdx_home:
        return Path(tdx_home)
    settings = get_settings()
    home = settings.tdx_home or os.environ.get("TDX_HOME") or r"C:\zd_zxzq_gm"
    return Path(home)


def _symbol_to_code(symbol: str) -> str:
    """sh510500 / sz159915 / bj920982 → 6 位代码; 已是裸代码则原样返回."""
    if not symbol:
        return symbol
    if len(symbol) >= 3 and symbol[:2] in ("sh", "sz", "bj"):
        return symbol[2:]
    return symbol


def _df_to_klinerows(df) -> list[KLineRow]:
    """fetch_local_day 返回的 DataFrame → KLineRow 列表, 按 date 降序.

    字段映射:
        df.amount (元) → row.amount (元)
        df.vol    (手) → row.volume (股, ×100)
    """
    rows = [
        KLineRow(
            date=ts.strftime("%Y-%m-%d"),
            open=float(row["open"]),
            close=float(row["close"]),
            high=float(row["high"]),
            low=float(row["low"]),
            volume=int(row["vol"]) * 100,
            amount=float(row["amount"]) if row.get("amount") is not None
            and not (isinstance(row["amount"], float) and row["amount"] != row["amount"])
            else None,
        )
        for ts, row in df.iterrows()
    ]
    rows.sort(key=lambda r: r.date, reverse=True)
    return rows


class TdxAdapter:
    """KLineAdapter 协议 — 本地通达信 vipdoc+gbbq.

    fetch_local_day 内部已处理: 复权 (qfq 默认) + 升序 DataFrame.
    本适配器仅做: symbol → code, DataFrame → KLineRow, 降序排序.
    limit 参数被忽略 — .day 文件是全集, 切片由调用方按日期做.
    """

    source = SOURCE.TDX

    def __init__(self, tdx_home: str | os.PathLike | None = None):
        self._tdx_home = resolve_tdx_home(tdx_home)

    async def fetch(self, symbol: str, period: PERIOD, fqt: FQT,
                    limit: int) -> list[KLineRow]:
        """symbol='sh510500' → code='510500'; qfq 复权; 返降序 KLineRow 列表.

        Raises:
            FileNotFoundError: 本地 .day 或 gbbq 缺失 (透传, 不包).
        """
        # period / fqt 在 v1 仅支持 DAY+QFQ; 其它组合走 fetch_local_day 默认 (qfq).
        del period, fqt, limit  # 未使用
        code = _symbol_to_code(symbol)
        from app.services.tdx_offline import fetch_local_day
        df = await asyncio.to_thread(fetch_local_day, code, "qfq", self._tdx_home)
        return _df_to_klinerows(df)
