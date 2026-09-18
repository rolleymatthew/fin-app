"""API tests for /api/admin/tdx/* endpoints."""
from __future__ import annotations

from datetime import datetime  # noqa: F401
from pathlib import Path  # noqa: F401
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state.tdx_fetch_state import TdxFetchStateStore


@pytest.fixture
def fake_state(monkeypatch) -> TdxFetchStateStore:
    store = TdxFetchStateStore()
    # 替换 lifespan 启动时挂的实例
    monkeypatch.setattr(app, "state", MagicMock(tdx_state=store))
    return store


def _client() -> TestClient:
    return TestClient(app)


def test_post_fetch_returns_started(fake_state):
    # start() 会真的起 asyncio.create_task — TestClient 同步驱动,
    # task 会在请求处理期间或之后跑. 这里只检查返回结构.
    from app.services.tdx_daily_fetcher.fetcher import TaskStatus
    fake_state.start = MagicMock(return_value=TaskStatus(task_id="abc12345"))

    r = _client().post("/api/admin/tdx/fetch")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["state"] == "started"
    assert body["data"]["task_id"] == "abc12345"


def test_post_fetch_busy_when_active(fake_state):
    from app.services.tdx_daily_fetcher.fetcher import TaskStatus
    # 模拟已有一个 active 任务
    fake_state.active = MagicMock(return_value=TaskStatus(task_id="existing01"))
    fake_state.start = MagicMock(side_effect=AssertionError("start should not be called"))

    r = _client().post("/api/admin/tdx/fetch")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["state"] == "busy"
    assert body["data"]["active_task_id"] == "existing01"


def test_get_status_unknown_task(fake_state):
    r = _client().get("/api/admin/tdx/status?task_id=nonexistent")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 404
    assert "不存在" in body["message"]


def test_get_status_known_task(fake_state):
    from app.services.tdx_daily_fetcher.fetcher import TaskStatus
    s = TaskStatus(task_id="known01")
    s.mark("downloading", "下载中 50%", progress=50)
    fake_state.get = MagicMock(return_value=s)

    r = _client().get("/api/admin/tdx/status?task_id=known01")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["task_id"] == "known01"
    assert body["data"]["state"] == "downloading"
    assert body["data"]["progress"] == 50
    assert body["data"]["message"] == "下载中 50%"
    assert body["data"]["started_at"]  # 非空字符串
