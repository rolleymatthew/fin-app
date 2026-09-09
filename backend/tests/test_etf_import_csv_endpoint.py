"""POST /api/etf/szse/import-csv endpoint 测试（FastAPI TestClient）"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def tmp_csv_dir(tmp_path: Path):
    csv_dir = tmp_path / "etf_csv"
    csv_dir.mkdir()
    sample = csv_dir / "表格_20260908.csv"
    sample.write_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,A,635.36,X\n",
        encoding="utf-8-sig",
    )
    return csv_dir


@pytest.mark.asyncio
async def test_import_csv_success(client, tmp_csv_dir):
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_csv_dir = str(tmp_csv_dir)
        service = MagicMock()
        service._import_szse_csv = AsyncMock(
            return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-08"}
        )
        svc.return_value = service

        resp = client.post(
            "/api/etf/szse/import-csv",
            json={"filename": "表格_20260908.csv"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["imported"] == 1
    service._import_szse_csv.assert_awaited_once()
    args = service._import_szse_csv.await_args.args
    assert args[1] == date(2026, 9, 8)
    assert "港股通" not in args[0].decode() or "159792" in args[0].decode()


@pytest.mark.asyncio
async def test_import_csv_filename_not_found(client, tmp_csv_dir):
    with patch("app.api.etf.get_settings") as gs:
        gs.return_value.etf_csv_dir = str(tmp_csv_dir)

        resp = client.post(
            "/api/etf/szse/import-csv",
            json={"filename": "表格_99999999.csv"},
        )

    assert resp.status_code == 200  # ResultVO 包装
    body = resp.json()
    assert body["success"] is False
    assert "not found" in body["message"].lower() or "不存在" in body["message"]


@pytest.mark.asyncio
async def test_import_csv_invalid_filename_pattern(client):
    resp = client.post(
        "/api/etf/szse/import-csv",
        json={"filename": "bad.csv"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_import_csv_mongo_failure_returns_error_envelope(client, tmp_csv_dir):
    """_import_szse_csv 抛异常时，endpoint 返回 success=false 的 ResultVO envelope"""
    (tmp_csv_dir / "表格_20260908.csv").write_text(
        "排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,X\n",
        encoding="utf-8-sig",
    )
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_csv_dir = str(tmp_csv_dir)
        service = MagicMock()
        service._import_szse_csv = AsyncMock(side_effect=RuntimeError("mongo down"))
        svc.return_value = service

        resp = client.post(
            "/api/etf/szse/import-csv",
            json={"filename": "表格_20260908.csv"},
        )

    body = resp.json()
    assert body["success"] is False
    assert body["code"] != 0  # non-success code
