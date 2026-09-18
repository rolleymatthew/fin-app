"""Unit tests for tdx_daily_fetcher."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import requests

from app.services.tdx_daily_fetcher.exceptions import (
    DownloadError,
    ExtractError,
    MetaParseError,
)
from app.services.tdx_daily_fetcher.downloader import download_zip, fetch_meta
from app.services.tdx_daily_fetcher.last_fetch import LastFetch
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


# ---- last_fetch ----

def test_last_fetch_empty_when_no_file(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    assert lf.read() is None
    assert lf.should_skip("2026-09-17 15:59:01") is False


def test_last_fetch_round_trip(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    lf.write(meta=_META_INFO, file_count=12420, zip_size=524927539)
    loaded = lf.read()
    assert loaded is not None
    assert loaded["file_count"] == 12420
    assert loaded["zip_size"] == 524927539
    assert "fetched_at" in loaded


def test_last_fetch_should_skip_when_same_update_time(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    lf.write(meta=_META_INFO, file_count=12420, zip_size=100)
    assert lf.should_skip(_META_INFO.update_time) is True


def test_last_fetch_should_skip_false_when_different(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    lf.write(meta=_META_INFO, file_count=12420, zip_size=100)
    assert lf.should_skip("2099-01-01 00:00:00") is False


# ---- downloader ----

_VALID_JS_DOWNLOADER = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";
"""

_META_INFO = parse_meta_info(_VALID_JS_DOWNLOADER)


def test_fetch_meta_ok(monkeypatch):
    class _Resp:
        text = _VALID_JS_DOWNLOADER
        def raise_for_status(self): pass
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    info = fetch_meta("https://x/y.js")
    assert info.update_time == "2026-09-17 15:59:01"
    assert info.file_size == 335544320


def test_fetch_meta_raises_on_network_error(monkeypatch):
    def _raise(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr("requests.get", _raise)
    with pytest.raises(MetaParseError):
        fetch_meta("https://x/y.js")


def test_download_zip_streams_to_disk(tmp_path, monkeypatch):
    payload = b"hello zip content"
    class _Resp:
        def __init__(self):
            self.headers = {"Content-Length": str(len(payload))}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield payload
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    dest = tmp_path / "out.zip"
    n = download_zip("https://x/y.zip", dest)
    assert n == len(payload)
    assert dest.read_bytes() == payload


def test_download_zip_progress_callback(tmp_path, monkeypatch):
    chunks = [b"a" * 100, b"b" * 100, b"c" * 100]
    class _Resp:
        headers = {"Content-Length": "300"}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            for c in chunks:
                yield c
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    calls = []
    download_zip(
        "https://x/y.zip", tmp_path / "o.zip",
        progress_cb=lambda d, t: calls.append((d, t)),
    )
    assert calls[-1] == (300, 300)
    assert all(t == 300 for _, t in calls)


def test_download_zip_removes_partial_on_error(tmp_path, monkeypatch):
    """下载中途抛错 → 半成品文件应被删除."""
    def _half(*a, **k):
        class _R:
            headers = {"Content-Length": "1000"}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield b"abc"
                raise requests.ConnectionError("drop")
        return _R()
    monkeypatch.setattr("requests.get", _half)
    dest = tmp_path / "o.zip"
    with pytest.raises(DownloadError):
        download_zip("https://x/y.zip", dest)
    assert not dest.exists()


def test_download_zip_progress_callback_when_no_content_length(tmp_path, monkeypatch):
    """chunked / Transfer-Encoding: chunked 没有 Content-Length, 也应触发最终回调."""
    chunks = [b"a" * 100, b"b" * 100]
    class _Resp:
        # 故意不设 Content-Length
        headers = {}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            for c in chunks:
                yield c
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    calls = []
    download_zip("https://x/y.zip", tmp_path / "o.zip",
                 progress_cb=lambda d, t: calls.append((d, t)))
    # 最终回调应该是 (200, 200) — 让上层认为 "下载完成 200/200"
    assert calls[-1] == (200, 200)
