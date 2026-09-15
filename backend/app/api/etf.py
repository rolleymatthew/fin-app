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


_FILENAME_PATTERN = re.compile(r"^sz_etf_(\d{4}-\d{2}-\d{2})\.json$")


@router.post("/szse/import-json")
async def import_szse_json(payload: dict[str, str]) -> dict:
    """手工导入指定 JSON 文件。

    body: {"filename": "sz_etf_2026-09-09.json"}
    文件必须位于 FIN_ETF_DATA_DIR 目录下，文件名必须匹配 sz_etf_YYYY-MM-DD.json 格式。
    """
    filename = (payload or {}).get("filename", "").strip()
    match = _FILENAME_PATTERN.match(filename)
    if not match:
        return ResultVO.fail(
            code=400, message=f"文件名格式错误: {filename!r}（应为 sz_etf_YYYY-MM-DD.json）"
        ).model_dump()

    json_path = Path(get_settings().etf_data_dir) / filename
    if not json_path.is_file():
        return ResultVO.fail(
            code=404, message=f"JSON 文件不存在: {json_path}"
        ).model_dump()

    stat_date = date.fromisoformat(match.group(1))
    content = json_path.read_bytes()
    report = await _service()._import_szse_json(content, stat_date)
    return ResultVO.ok(report).model_dump()


@router.post("/szse/import-latest")
async def import_latest_szse_json() -> dict:
    """扫描 FIN_ETF_DATA_DIR 下最新的 sz_etf_*.json 并幂等 upsert。

    返回: {filename, stat_date, imported, skipped, pre_existing, mode}
    - pre_existing: DB 中 stat_date 当天已有的深市 ETF 条数（用于 UI 区分"新增/覆盖"）
    - 不移动文件到 processed/（仅 watcher 自动归档；UI 手动触发保留原文件，便于复核/重试）
    """
    data_dir = Path(get_settings().etf_data_dir)
    candidates = [
        p for p in data_dir.glob("sz_etf_*.json")
        if p.is_file() and not str(p).startswith(str(data_dir / "processed"))
    ]
    if not candidates:
        return ResultVO.fail(
            code=404, message=f"目录无文件: {data_dir}"
        ).model_dump()

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    match = _FILENAME_PATTERN.match(latest.name)
    if not match:
        return ResultVO.fail(
            code=400, message=f"文件名格式错误: {latest.name!r}"
        ).model_dump()

    stat_date = date.fromisoformat(match.group(1))
    pre_existing = await _service().count_szse_records_at(stat_date.isoformat())
    content = latest.read_bytes()
    report = await _service()._import_szse_json(content, stat_date)
    return ResultVO.ok({
        "filename": latest.name,
        "stat_date": stat_date.isoformat(),
        "imported": report["imported"],
        "skipped": report["skipped"],
        "pre_existing": pre_existing,
        "mode": "upsert",
    }).model_dump()