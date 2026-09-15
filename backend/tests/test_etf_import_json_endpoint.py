"""POST /api/etf/szse/import-json endpoint 测试（FastAPI TestClient）

文件名约定：sz_etf_YYYY-MM-DD.json（与豆包下载约定一致）
body: {"filename": "sz_etf_2026-09-09.json"}
"""
from __future__ import annotations

import json
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
def tmp_json_dir(tmp_path: Path):
    json_dir = tmp_path / "etf_data"
    json_dir.mkdir()
    sample = json_dir / "sz_etf_2026-09-09.json"
    sample.write_text(
        json.dumps(
            [
                {
                    "code": "159792",
                    "name": "港股通互联网ETF富国",
                    "scale": "635.36",
                    "mgr": "富国基金",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return json_dir


@pytest.mark.asyncio
async def test_import_json_success(client, tmp_json_dir):
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_data_dir = str(tmp_json_dir)
        service = MagicMock()
        service._import_szse_json = AsyncMock(
            return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-09"}
        )
        svc.return_value = service

        resp = client.post(
            "/api/etf/szse/import-json",
            json={"filename": "sz_etf_2026-09-09.json"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["imported"] == 1
    service._import_szse_json.assert_awaited_once()
    args = service._import_szse_json.await_args.args
    assert args[1] == date(2026, 9, 9)
    assert "159792" in args[0].decode()


@pytest.mark.asyncio
async def test_import_json_filename_not_found(client, tmp_json_dir):
    with patch("app.api.etf.get_settings") as gs:
        gs.return_value.etf_data_dir = str(tmp_json_dir)

        resp = client.post(
            "/api/etf/szse/import-json",
            json={"filename": "sz_etf_2099-12-31.json"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "not found" in body["message"].lower() or "不存在" in body["message"]


@pytest.mark.asyncio
async def test_import_json_invalid_filename_pattern(client):
    resp = client.post(
        "/api/etf/szse/import-json",
        json={"filename": "bad.json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_import_json_rejects_old_csv_naming(client):
    """旧 CSV 文件名约定 sz_etf_YYYYMMDD.csv 不再被接受"""
    resp = client.post(
        "/api/etf/szse/import-json",
        json={"filename": "表格_20260908.csv"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_import_json_mongo_failure_returns_error_envelope(client, tmp_json_dir):
    """_import_szse_json 抛异常时，endpoint 返回 success=false 的 ResultVO envelope"""
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_data_dir = str(tmp_json_dir)
        service = MagicMock()
        service._import_szse_json = AsyncMock(side_effect=RuntimeError("mongo down"))
        svc.return_value = service

        resp = client.post(
            "/api/etf/szse/import-json",
            json={"filename": "sz_etf_2026-09-09.json"},
        )

    body = resp.json()
    assert body["success"] is False
    assert body["code"] != 0


@pytest.mark.asyncio
async def test_import_latest_success(client, tmp_json_dir):
    """POST /api/etf/szse/import-latest 选取 mtime 最新 json，幂等 upsert"""
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_data_dir = str(tmp_json_dir)
        service = MagicMock()
        service.count_szse_records_at = AsyncMock(return_value=42)
        service._import_szse_json = AsyncMock(
            return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-09"}
        )
        svc.return_value = service

        resp = client.post("/api/etf/szse/import-latest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["filename"] == "sz_etf_2026-09-09.json"
    assert data["stat_date"] == "2026-09-09"
    assert data["imported"] == 1
    assert data["skipped"] == 0
    assert data["pre_existing"] == 42
    assert data["mode"] == "upsert"
    service._import_szse_json.assert_awaited_once()
    args = service._import_szse_json.await_args.args
    assert args[1] == date(2026, 9, 9)
    assert "159792" in args[0].decode()
    service.count_szse_records_at.assert_awaited_once_with("2026-09-09")


@pytest.mark.asyncio
async def test_import_latest_no_file(client, tmp_path):
    """目录为空时返回 success=false (404)"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with patch("app.api.etf.get_settings") as gs:
        gs.return_value.etf_data_dir = str(empty_dir)

        resp = client.post("/api/etf/szse/import-latest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == 404
    assert "无文件" in body["message"] or "empty" in body["message"].lower()


@pytest.mark.asyncio
async def test_import_latest_skips_processed_dir(client, tmp_json_dir):
    """processed/ 下的 json 不参与"最新"选择（即使 mtime 更新）"""
    processed_dir = tmp_json_dir / "processed"
    processed_dir.mkdir()
    newer = processed_dir / "sz_etf_2026-09-10.json"
    newer.write_text(
        json.dumps([{"code": "159999", "name": "test", "scale": "1.0"}], ensure_ascii=False),
        encoding="utf-8",
    )
    import os
    future_mtime = tmp_json_dir / "sz_etf_2026-09-09.json"
    os.utime(future_mtime, (2000000000, 2000000000))
    os.utime(newer, (2000000001, 2000000001))

    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_data_dir = str(tmp_json_dir)
        service = MagicMock()
        service.count_szse_records_at = AsyncMock(return_value=0)
        service._import_szse_json = AsyncMock(
            return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-09"}
        )
        svc.return_value = service

        resp = client.post("/api/etf/szse/import-latest")

    body = resp.json()
    assert body["success"] is True
    assert body["data"]["filename"] == "sz_etf_2026-09-09.json"
    assert body["data"]["stat_date"] == "2026-09-09"


@pytest.mark.asyncio
async def test_import_latest_does_not_archive_file(client, tmp_json_dir):
    """手动触发不归档：原文件必须保留在原位"""
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_data_dir = str(tmp_json_dir)
        service = MagicMock()
        service.count_szse_records_at = AsyncMock(return_value=0)
        service._import_szse_json = AsyncMock(
            return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-09"}
        )
        svc.return_value = service

        resp = client.post("/api/etf/szse/import-latest")

    body = resp.json()
    assert body["success"] is True
    assert (tmp_json_dir / "sz_etf_2026-09-09.json").exists(), "原文件必须保留"
    assert not (tmp_json_dir / "processed" / "sz_etf_2026-09-09.json").exists()
