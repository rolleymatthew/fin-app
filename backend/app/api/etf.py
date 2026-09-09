"""ETF 下拉搜索 REST 接口（与前端 echart-etf EtfCombobox  对齐）。

端点：
  GET  /api/etf/search              query: q=...&limit=200
  POST /api/etf/backfill-pinyin     body: {"only_missing": true}

数据源：MongoDB `etf` 集合（secCode + secName），需先调 backfill-pinyin
从 secName 算首字母写入 pinyin 字段（一次性）。
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.clients.szse_etf_csv import parse_csv  # noqa: F401  用于 Task 4
from app.config import get_settings
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


_FILENAME_PATTERN = re.compile(r"^表格_(\d{8})\.csv$")


@router.post("/szse/import-csv")
async def import_szse_csv(payload: dict[str, str]) -> dict:
    """手工导入指定 CSV 文件。

    body: {"filename": "表格_20260908.csv"}
    文件必须位于 FIN_ETF_CSV_DIR 目录下，文件名必须匹配 表格_YYYYMMDD.csv 格式。
    """
    filename = (payload or {}).get("filename", "").strip()
    match = _FILENAME_PATTERN.match(filename)
    if not match:
        return ResultVO.fail(
            code=400, message=f"文件名格式错误: {filename!r}（应为 表格_YYYYMMDD.csv）"
        ).model_dump()

    csv_path = Path(get_settings().etf_csv_dir) / filename
    if not csv_path.is_file():
        return ResultVO.fail(
            code=404, message=f"CSV 文件不存在: {csv_path}"
        ).model_dump()

    stat_date = date.fromisoformat(
        f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
    )
    content = csv_path.read_bytes()
    report = await _service()._import_szse_csv(content, stat_date)
    return ResultVO.ok(report).model_dump()