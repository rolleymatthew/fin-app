"""Unit tests for tdx_daily_fetcher."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.services.tdx_daily_fetcher.exceptions import ExtractError, MetaParseError
from app.services.tdx_daily_fetcher.meta import MetaInfo, parse_meta_info


# ---- meta parser ----

_VALID_JS = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";
"""


def test_parse_meta_info_valid():
    info = parse_meta_info(_VALID_JS)
    assert info.update_time == "2026-09-17 15:59:01"
    assert info.file_size == 335544320


def test_parse_meta_info_size_with_commas():
    info = parse_meta_info(
        'var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";\n'
        'var HSJDAY_SOFT_SIZE = "524,927,539";'
    )
    assert info.file_size == 524927539


def test_parse_meta_info_size_missing_returns_none():
    info = parse_meta_info('HSJDAY_SOFT_TIME="2026-09-17 15:15:00";')
    assert info.file_size is None


def test_parse_meta_info_no_time_raises():
    with pytest.raises(MetaParseError, match="HSJDAY_SOFT_TIME"):
        parse_meta_info("var OTHER_VAR = 'foo';")


def test_parse_meta_info_empty_raises():
    with pytest.raises(MetaParseError):
        parse_meta_info("")


# ---- atomic extract ----

from app.services.tdx_daily_fetcher.extract import atomic_extract_zip


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)


def test_atomic_extract_happy(tmp_path: Path):
    zip_path = tmp_path / "in.zip"
    _make_zip(zip_path, {
        "sh/lday/sh600000.day": b"X" * 32,
        "sz/lday/sz000001.day": b"Y" * 32,
    })
    count = atomic_extract_zip(zip_path, tmp_path)
    assert count == 2
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").read_bytes() == b"X" * 32
    assert (tmp_path / "vipdoc" / "sz" / "lday" / "sz000001.day").read_bytes() == b"Y" * 32
    assert not (tmp_path / "vipdoc.tmp").exists()


def test_atomic_extract_failure_leaves_existing_intact(tmp_path: Path):
    """预先放一个 'good' vipdoc/, 然后构造会触发解压失败的情况, 验证 vipdoc/ 不被改."""
    # 1) 先做一次成功解压, 建立基线
    zip_path = tmp_path / "good.zip"
    _make_zip(zip_path, {"sh/lday/sh600000.day": b"GOOD" * 8})
    atomic_extract_zip(zip_path, tmp_path)
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").read_bytes() == b"GOOD" * 8

    # 2) 现在构造一个会失败的场景 — 制造一个文件占位 vipdoc.tmp 让 shutil.move 失败
    #    (move 会因为目标已存在而失败 — 但本实现在 move 前会清 .tmp, 所以这里走 zip 损坏路径)
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    with pytest.raises(ExtractError):
        atomic_extract_zip(bad_zip, tmp_path)
    # vipdoc/ 保持原状
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").read_bytes() == b"GOOD" * 8
    assert not (tmp_path / "vipdoc.tmp").exists()


def test_atomic_extract_creates_vipdoc_subdir(tmp_path: Path):
    zip_path = tmp_path / "x.zip"
    _make_zip(zip_path, {"bj/lday/bj920982.day": b"Z" * 32})
    count = atomic_extract_zip(zip_path, tmp_path)
    assert count == 1
    assert (tmp_path / "vipdoc" / "bj" / "lday" / "bj920982.day").exists()
