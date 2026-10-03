"""TDX vipdata fetcher 管理端点.

端点:
  POST /api/admin/tdx/fetch          启动一次下载 (busy 时返已有 task_id)
  GET  /api/admin/tdx/status?task_id= 查任务进度

状态从 app.state.tdx_state (TdxFetchStateStore 单例) 取.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.result import ResultVO

router = APIRouter()


@router.post("/fetch")
async def post_fetch(request: Request):
    state = request.app.state.tdx_state
    existing = state.active()
    if existing is not None:
        return ResultVO.ok({
            "state": "busy",
            "active_task_id": existing.task_id,
            "current_state": existing.state,
            "progress": existing.progress,
        }).model_dump()
    status = state.start(request.app.state.settings)
    return ResultVO.ok({
        "state": "started",
        "task_id": status.task_id,
    }).model_dump()


@router.get("/status")
async def get_status(task_id: str, request: Request):
    state = request.app.state.tdx_state
    status = state.get(task_id)
    if status is None:
        return ResultVO.fail(
            code=404, message=f"task 不存在: {task_id}",
        ).model_dump()
    return ResultVO.ok({
        "task_id": status.task_id,
        "state": status.state,
        "progress": status.progress,
        "message": status.message,
        "error": status.error,
        "update_time": status.update_time,
        "file_count": status.file_count,
        "zip_size": status.zip_size,
        "started_at": status.started_at.isoformat() if status.started_at else None,
        "finished_at": status.finished_at.isoformat() if status.finished_at else None,
    }).model_dump()
