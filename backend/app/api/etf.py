"""ETF 下拉搜索 REST 接口（与前端 echart-etf EtfCombobox  对齐）。

端点：
  GET  /api/etf/search              query: q=...&limit=200
  POST /api/etf/backfill-pinyin     body: {"only_missing": true}

数据源：MongoDB `etf` 集合（secCode + secName），需先调 backfill-pinyin
从 secName 算首字母写入 pinyin 字段（一次性）。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter

from app.models.result import ResultVO
from app.services.etf_service import EtfService

router = APIRouter()


@lru_cache
def _service() -> EtfService:
    return EtfService()


@router.get("/search")
async def search(
    q: str | None = None,
    limit: int = 200,
) -> dict:
    """按 代码 / 拼音首字母 / 中文名 模糊搜索 ETF，返回每只 ETF 最新条目。"""
    rows = await _service().search_etfs(q=q, limit=limit)
    return ResultVO.ok(rows).model_dump()


@router.post("/backfill-pinyin")
async def backfill_pinyin(payload: dict[str, Any] | None = None) -> dict:
    """一次性维护：从 secName 计算首字母写入 pinyin 字段。"""
    only_missing = bool((payload or {}).get("only_missing", True))
    report = await _service().backfill_pinyin(only_missing=only_missing)
    return ResultVO.ok(report).model_dump()