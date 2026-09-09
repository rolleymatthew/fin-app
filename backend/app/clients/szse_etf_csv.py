"""深交所 ETF 份额日终 CSV 解析器。

输入：豆包定时任务下载的 UTF-8 BOM CSV 文件（10 行 ~ 全市场）。
输出：与 app.clients.szse.SzseClient.parse_etf_rows 同形的 DTO 列表，
      可直接喂给 etf_szse_dto_to_entity mapper。

CSV 列：排名, 代码, 简称, 规模 (亿), 管理人
- 规模 (亿) 为亿份单位（与 SSE 口径一致 → 乘 10^8 转"份"）
- 管理人丢弃（已内嵌于 secName 末尾，例如 "港股通互联网 ETF 富国"）
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import TypedDict


class SzseEtfRow(TypedDict):
    SEC_CODE: str
    SEC_NAME: str
    TOT_VOL_YI: Decimal


def parse_csv(content: bytes, _stat_date: date) -> list[SzseEtfRow]:
    """解析 CSV 字节流为 DTO 列表。

    Args:
        content: CSV 文件的原始字节（自动处理 UTF-8 BOM）
        _stat_date: 文件对应的交易日；当前实现未在 DTO 中使用（mapper 注入）

    Returns:
        [{SEC_CODE, SEC_NAME, TOT_VOL_YI}, ...]

    行级容错：单行解析失败不影响其它行。无任何有效行时返回 []。
    """
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows: list[SzseEtfRow] = []
    try:
        header = next(reader)
    except StopIteration:
        return []

    code_idx = _find_col(header, {"代码", "code", "sec_code"})
    name_idx = _find_col(header, {"简称", "name", "sec_name"})
    scale_idx = _find_col(header, {"规模 (亿)", "规模(亿)", "规模", "scale"})

    if code_idx is None or name_idx is None or scale_idx is None:
        return []

    for raw in reader:
        if not raw:
            continue
        code = raw[code_idx].strip()
        if not code.isdigit():
            continue
        name = raw[name_idx].strip()
        scale_raw = raw[scale_idx].strip()
        try:
            scale = Decimal(scale_raw)
        except Exception:
            continue
        rows.append(
            {
                "SEC_CODE": code,
                "SEC_NAME": name,
                "TOT_VOL_YI": scale,
            }
        )
    return rows


def _find_col(header: list[str], candidates: set[str]) -> int | None:
    for i, h in enumerate(header):
        if h.strip() in candidates:
            return i
    return None
