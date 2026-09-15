"""etf_data_watcher 单元测试（mock 文件系统与 service）

约定：扫描 sz_etf_YYYY-MM-DD.json 文件并调用 _import_szse_json。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.etf_data_watcher import (
    StateStore,
    _archive_path,
    _stat_date_from_filename,
    parse_state,
    tick,
)


def test_stat_date_from_filename():
    assert _stat_date_from_filename("sz_etf_2026-09-09.json") == date(2026, 9, 9)
    assert _stat_date_from_filename("sz_etf_2026-13-09.json") is None  # 非法月
    assert _stat_date_from_filename("bad.json") is None
    assert _stat_date_from_filename("表格_20260908.csv") is None  # 旧约定不再接受


def test_archive_path():
    p = _archive_path(Path("/tmp/etf"), "sz_etf_2026-09-09.json")
    assert p.as_posix().endswith("processed/sz_etf_2026-09-09.json")


def test_parse_state_empty():
    assert parse_state(None) == {}
    assert parse_state("") == {}
    assert parse_state('{"x":1}') == {"x": 1}


def test_state_store_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.set("sz_etf_2026-09-09.json", 12345.0)
    assert store.get("sz_etf_2026-09-09.json") == 12345.0
    store2 = StateStore(tmp_path / "state.json")
    assert store2.get("sz_etf_2026-09-09.json") == 12345.0


def _write_sample_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            [{"code": "159792", "name": "A", "scale": "635.36", "mgr": "X"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_tick_processes_new_files(tmp_path):
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    _write_sample_json(data_dir / "sz_etf_2026-09-09.json")

    settings = MagicMock()
    settings.etf_data_dir = str(data_dir)
    settings.etf_data_poll_seconds = 300

    service = MagicMock()
    service._import_szse_json = AsyncMock(
        return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-09"}
    )

    report = await tick(settings, service)

    assert report["scanned"] == 1
    assert report["imported"] == 1
    assert (data_dir / "processed" / "sz_etf_2026-09-09.json").exists()
    assert not (data_dir / "sz_etf_2026-09-09.json").exists()  # 已归档

    state = json.loads((data_dir / ".last_import.json").read_text())
    assert "sz_etf_2026-09-09.json" in state


@pytest.mark.asyncio
async def test_tick_skips_unchanged_mtime(tmp_path):
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    _write_sample_json(data_dir / "sz_etf_2026-09-09.json")

    settings = MagicMock()
    settings.etf_data_dir = str(data_dir)

    service = MagicMock()
    service._import_szse_json = AsyncMock(
        return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-09"}
    )

    # 第一次扫描 → 处理
    r1 = await tick(settings, service)
    assert r1["imported"] == 1
    service._import_szse_json.reset_mock()

    # 第二次扫描（mtime 未变） → 跳过
    r2 = await tick(settings, service)
    assert r2["imported"] == 0
    assert r2["skipped"] == 0
    service._import_szse_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_future_date_skipped(tmp_path):
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    (data_dir / "sz_etf_2099-12-31.json").write_text("[]", encoding="utf-8")

    settings = MagicMock()
    settings.etf_data_dir = str(data_dir)

    service = MagicMock()
    service._import_szse_json = AsyncMock()

    r = await tick(settings, service)
    assert r["imported"] == 0
    service._import_szse_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_empty_dir(tmp_path):
    data_dir = tmp_path / "in"
    data_dir.mkdir()

    settings = MagicMock()
    settings.etf_data_dir = str(data_dir)
    service = MagicMock()
    service._import_szse_json = AsyncMock()

    r = await tick(settings, service)
    assert r["scanned"] == 0
    service._import_szse_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_keeps_file_on_mongo_failure(tmp_path):
    """_import_szse_json 抛异常时，文件留在原位且 state 不更新"""
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    _write_sample_json(data_dir / "sz_etf_2026-09-09.json")

    settings = MagicMock()
    settings.etf_data_dir = str(data_dir)

    service = MagicMock()
    service._import_szse_json = AsyncMock(side_effect=RuntimeError("mongo down"))

    r = await tick(settings, service)

    assert r["errors"] == 1
    assert r["imported"] == 0
    assert (data_dir / "sz_etf_2026-09-09.json").exists(), "文件必须留在原位（重试机制）"
    assert not list((data_dir / "processed").glob("*.json")), "未归档"
    assert not (data_dir / ".last_import.json").exists(), "未写状态"


@pytest.mark.asyncio
async def test_tick_ignores_legacy_csv_files(tmp_path):
    """旧 CSV 命名（表格_*.csv）不再被 watcher 拾取"""
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    (data_dir / "表格_20260908.csv").write_text("legacy", encoding="utf-8")

    settings = MagicMock()
    settings.etf_data_dir = str(data_dir)

    service = MagicMock()
    service._import_szse_json = AsyncMock()

    r = await tick(settings, service)
    assert r["scanned"] == 0
    service._import_szse_json.assert_not_awaited()
