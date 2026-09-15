"""深交所 ETF 份额日终 JSON 解析器。

输入：豆包定时任务下载的 UTF-8 JSON 文件
输出：与 app.clients.szse.SzseClient.parse_etf_rows 同形的 DTO 列表，
      可直接喂给 etf_szse_dto_to_entity mapper。

支持两种顶层结构：
1. 数组（旧格式）：[{code, name, scale, mgr}, ...]
2. 包装 dict（当前豆包输出）：{"stat_date", "source", "fetched_at", "total", "rows": [...]}，
   真实数据在 rows 字段里

JSON 字段：code / name / scale / mgr
- scale 为字符串（亿份单位，与 SSE 口径一致 → 乘 10^8 转"份"）
- mgr 丢弃（已内嵌于 secName 末尾，例如 "港股通互联网 ETF 富国"）
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict


class SzseEtfRow(TypedDict):
    SEC_CODE: str
    SEC_NAME: str
    TOT_VOL_YI: Decimal


def parse_json(content: bytes, _stat_date: date) -> list[SzseEtfRow]:
    """解析 JSON 字节流为 DTO 列表。

    Args:
        content: JSON 文件的原始字节（自动处理 UTF-8 BOM）
        _stat_date: 文件对应的交易日；当前实现未在 DTO 中使用（mapper 注入）

    Returns:
        [{SEC_CODE, SEC_NAME, TOT_VOL_YI}, ...]

    行级容错：单行解析失败不影响其它行。无任何有效行或 JSON 解析失败时返回 []。
    支持顶层为 list 或 {rows: [...]} 两种格式。
    """
    if not content:
        return []
    try:
        text = content.decode("utf-8-sig")
        raw: Any = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []

    if isinstance(raw, dict):
        raw = raw.get("rows")
    if not isinstance(raw, list):
        return []

    rows: list[SzseEtfRow] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        name = item.get("name")
        scale_raw = item.get("scale")
        if not code.isdigit() or not isinstance(name, str) or scale_raw is None:
            continue
        try:
            scale = Decimal(str(scale_raw).strip())
        except Exception:
            continue
        rows.append(
            {
                "SEC_CODE": code,
                "SEC_NAME": name.strip(),
                "TOT_VOL_YI": scale,
            }
        )
    return rows
