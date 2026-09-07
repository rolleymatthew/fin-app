from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query

from app.models.result import ResultVO
from app.services.seccode_service import SecCodeService, SyncReport

router = APIRouter()


@lru_cache
def _service() -> SecCodeService:
    return SecCodeService()


@router.get("/search")
async def search(
    q: str | None = Query(default=None, description="代码 / 拼音首字母 / 名称"),
    limit: int = Query(default=200, ge=1, le=1000),
    org_type_code: str | None = Query(
        default=None,
        description="公司类型代码: 1=证券 2=保险 3=银行 4=通用",
    ),
) -> dict:
    """按 拼音首字母 / 代码 / 名称 模糊搜索上市公司，供下拉框使用。

    org_type_code 为可选过滤项，传 "3" 仅返回银行股，不传则返回所有上市股票。
    """
    svc = _service()
    rows = await svc.search_stocks(q=q, limit=limit, org_type_code=org_type_code)
    return ResultVO.ok(rows).model_dump()


@router.post("/backfill-pinyin")
async def backfill_pinyin(payload: dict[str, Any] | None = None) -> dict:
    """从中文名回填 securityPinyin（首字母），one-time 维护任务。"""
    only_missing = bool((payload or {}).get("only_missing", True))
    svc = _service()
    report = await svc.backfill_pinyin(only_missing=only_missing)
    return ResultVO.ok(report).model_dump()


@router.post("/sync")
async def sync(payload: dict[str, Any] | None = None) -> dict:
    force = bool((payload or {}).get("force", False))
    svc = _service()
    report = await svc.sync_from_exchanges(force=force)
    return ResultVO.ok(_report_to_dict(report)).model_dump()


@router.post("/refresh-details")
async def refresh_details(payload: dict[str, Any] | None = None) -> dict:
    body = payload or {}
    include_delisted = bool(body.get("include_delisted", True))
    only_missing = bool(body.get("only_missing", False))
    svc = _service()
    report = await svc.refresh_all_details(
        include_delisted=include_delisted,
        only_missing=only_missing,
    )
    return ResultVO.ok(_report_to_dict(report)).model_dump()


@router.get("/sync/status")
async def sync_status() -> dict:
    """Returns the most recently completed sync report; None before first sync."""
    svc = _service()
    if svc.last_sync_report is None:
        return ResultVO.ok(None).model_dump()
    return ResultVO.ok(_report_to_dict(svc.last_sync_report)).model_dump()


def _report_to_dict(report: SyncReport | dict) -> dict:
    if isinstance(report, dict):
        return report
    return {
        "total_in_official": report.total_in_official,
        "existing_in_db": report.existing_in_db,
        "new_added": report.new_added,
        "state_changed": report.state_changed,
        "details_refilled": report.details_refilled,
        "failed": report.failed,
        "by_exchange": report.by_exchange,
        "elapsed_ms": report.elapsed_ms,
        "cookie_warmed": report.cookie_warmed,
        "partial": report.partial,
    }