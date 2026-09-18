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
    payload = _build_minimal_zip()
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
    full = _build_minimal_zip()
    # split into3 chunks
    c1, c2, c3 = full[:len(full)//3], full[len(full)//3:2*len(full)//3], full[2*len(full)//3:]
    class _Resp:
        headers = {"Content-Length": str(len(full))}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            for c in (c1, c2, c3):
                yield c
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    calls = []
    download_zip(
        "https://x/y.zip", tmp_path / "o.zip",
        progress_cb=lambda d, t: calls.append((d, t)),
    )
    total = calls[-1][0] if calls else 0
    assert total == len(full)
    assert all(t == len(full) for _, t in calls)


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
    # .dl_tmp should also be cleaned
    assert not dest.with_suffix(dest.suffix + ".dl_tmp").exists()


def test_download_zip_progress_callback_when_no_content_length(tmp_path, monkeypatch):
    """chunked / Transfer-Encoding: chunked 没有 Content-Length, 也应触发最终回调."""
    full = _build_minimal_zip()
    c1, c2 = full[:len(full)//2], full[len(full)//2:]
    class _Resp:
        headers = {}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            for c in (c1, c2):
                yield c
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    calls = []
    download_zip("https://x/y.zip", tmp_path / "o.zip",
                 progress_cb=lambda d, t: calls.append((d, t)))
    total = calls[-1][0] if calls else 0
    assert total == len(full)
    assert calls[-1] == (len(full), len(full))


# ---- fetcher orchestrator ----

from app.services.tdx_daily_fetcher.fetcher import (
    ACTIVE_STATES,
    TaskStatus,
    TdxDailyFetcher,
)


_VALID_JS_FETCHER = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:14";
"""

_ZIP_FILES = {
    "sh/lday/sh600000.day": b"X" * 32,
    "sz/lday/sz000001.day": b"Y" * 32,
    "bj/lday/bj920982.day": b"Z" * 32,
}


def _build_minimal_zip() -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in _ZIP_FILES.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_active_states_constant():
    assert ACTIVE_STATES == frozenset({"pending", "checking", "downloading", "extracting"})


def test_fetcher_skip_when_already_today(tmp_path, monkeypatch):
    """当 .last_fetch.json 已记录今日 update_time, 应跳过下载 (zip 不应被请求)."""
    meta = parse_meta_info(_VALID_JS_FETCHER)
    last = LastFetch(target_dir=tmp_path)
    last.write(meta=meta, file_count=3, zip_size=100)

    # Mock fetcher 命名空间: fetch_meta 返回同 update_time; download_zip 一旦被调用就 fail
    monkeypatch.setattr(
        "app.services.tdx_daily_fetcher.fetcher.fetch_meta",
        lambda url, **kw: meta,
    )
    def _fail_if_called(*a, **k):
        raise AssertionError("download_zip 不应在 SKIPPED 时调用")
    monkeypatch.setattr(
        "app.services.tdx_daily_fetcher.fetcher.download_zip",
        _fail_if_called,
    )

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="x", meta_url="x")
    status = fetcher.run_sync()
    assert status.state == "skipped"
    assert status.update_time == meta.update_time


def test_fetcher_full_happy_path(tmp_path, monkeypatch):
    payload = _build_minimal_zip()

    class _MetaResp:
        text = _VALID_JS_FETCHER
        def raise_for_status(self): pass

    class _ZipResp:
        headers = {"Content-Length": str(len(payload))}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield payload

    def _mock_get(url, **k):
        if url.endswith(".js"):
            return _MetaResp()
        return _ZipResp()

    monkeypatch.setattr(requests, "get", _mock_get)

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="https://x/y.zip", meta_url="https://x/y.js")
    status = fetcher.run_sync()

    assert status.state == "done"
    assert status.file_count == 3
    assert status.update_time == "2026-09-17 15:59:14"
    assert (tmp_path / "hsjday.zip").exists()
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").exists()
    # .last_fetch.json 应已写入
    lf = LastFetch(target_dir=tmp_path).read()
    assert lf is not None
    assert lf["update_time"] == "2026-09-17 15:59:14"


def test_fetcher_progress_increases(tmp_path, monkeypatch):
    payload = _build_minimal_zip()

    class _MetaResp:
        text = _VALID_JS_FETCHER
        def raise_for_status(self): pass

    class _ZipResp:
        headers = {"Content-Length": str(len(payload))}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield payload

    def _mock_get(url, **k):
        return _MetaResp() if url.endswith(".js") else _ZipResp()

    monkeypatch.setattr(requests, "get", _mock_get)

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="x", meta_url="x.js")
    fetcher.run_sync()
    # 终态 progress 应该是 100
    assert fetcher.status().progress == 100


def test_fetcher_meta_failure_marks_failed(tmp_path, monkeypatch):
    def _raise(*a, **k):
        raise requests.ConnectionError("no net")
    monkeypatch.setattr(requests, "get", _raise)

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="x", meta_url="x")
    status = fetcher.run_sync()
    assert status.state == "failed"
    assert status.error is not None
    assert "TDX" in status.error or "元信息" in status.error or "连接" in status.error
