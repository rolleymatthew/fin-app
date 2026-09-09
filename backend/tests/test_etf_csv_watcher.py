"""etf_csv_watcher 单元测试（mock 文件系统与 service）"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.etf_csv_watcher import (
    StateStore,
    _archive_path,
    _stat_date_from_filename,
    parse_state,
    tick,
)


def test_stat_date_from_filename():
    assert _stat_date_from_filename("表格_20260908.csv") == date(2026, 9, 8)
    assert _stat_date_from_filename("表格_99999999.csv") is None
    assert _stat_date_from_filename("bad.csv") is None
    assert _stat_date_from_filename("表格_20261301.csv") is None  # 非法月


def test_archive_path():
    p = _archive_path(Path("/tmp/etf"), "表格_20260908.csv")
    assert p.as_posix().endswith("processed/表格_20260908.csv")


def test_parse_state_empty():
    assert parse_state(None) == {}
    assert parse_state("") == {}
    assert parse_state('{"x":1}') == {"x": 1}


def test_state_store_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.set("表格_20260908.csv", 12345.0)
    assert store.get("表格_20260908.csv") == 12345.0
    store2 = StateStore(tmp_path / "state.json")
    assert store2.get("表格_20260908.csv") == 12345.0


@pytest.mark.asyncio
async def test_tick_processes_new_files(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()
    (csv_dir / "表格_20260908.csv").write_text(
        "排名,代码,简称,规模 (亿),管理人\n1,159792,A,635.36,X\n",
        encoding="utf-8-sig",
    )

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)
    settings.etf_csv_poll_seconds = 300

    service = MagicMock()
    service._import_szse_csv = AsyncMock(
        return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-08"}
    )

    report = await tick(settings, service)

    assert report["scanned"] == 1
    assert report["imported"] == 1
    assert (csv_dir / "processed" / "表格_20260908.csv").exists()
    assert not (csv_dir / "表格_20260908.csv").exists()  # 已归档

    state = json.loads((csv_dir / ".last_import.json").read_text())
    assert "表格_20260908.csv" in state


@pytest.mark.asyncio
async def test_tick_skips_unchanged_mtime(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()
    f = csv_dir / "表格_20260908.csv"
    f.write_text("排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,X\n", encoding="utf-8-sig")

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)

    service = MagicMock()
    service._import_szse_csv = AsyncMock(
        return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-08"}
    )

    # 第一次扫描 → 处理
    r1 = await tick(settings, service)
    assert r1["imported"] == 1
    service._import_szse_csv.reset_mock()

    # 第二次扫描（mtime 未变） → 跳过
    r2 = await tick(settings, service)
    assert r2["imported"] == 0
    assert r2["skipped"] == 0
    service._import_szse_csv.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_future_date_skipped(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()
    (csv_dir / "表格_20990101.csv").write_text("header\n", encoding="utf-8-sig")

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)

    service = MagicMock()
    service._import_szse_csv = AsyncMock()

    r = await tick(settings, service)
    assert r["imported"] == 0
    service._import_szse_csv.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_empty_dir(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)
    service = MagicMock()
    service._import_szse_csv = AsyncMock()

    r = await tick(settings, service)
    assert r["scanned"] == 0
    service._import_szse_csv.assert_not_awaited()