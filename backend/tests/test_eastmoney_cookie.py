import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest

from app.clients.eastmoney import EastmoneyClient
from app.clients.eastmoney_cookie import CookieHealthChecker, CookieStore


@pytest.fixture
def cookie_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01-a.txt").write_text("a=1; b=2", encoding="utf-8")
    (d / "02-b.txt").write_text("c=3", encoding="utf-8")
    (d / "ignore.md").write_text("# not cookie", encoding="utf-8")
    return d


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient() as c:
        yield c


async def test_load_if_changed_returns_false_initially(
    cookie_dir: Path, http_client: httpx.AsyncClient
):
    store = CookieStore(cookie_dir)
    assert store.load_if_changed(http_client) is False
    assert "a=1" in store.current_string()


async def test_load_if_changed_returns_true_when_mtime_changes(
    cookie_dir: Path, http_client: httpx.AsyncClient
):
    store = CookieStore(cookie_dir)
    store.load_if_changed(http_client)
    f = cookie_dir / "01-a.txt"
    new_mtime = f.stat().st_mtime + 10
    os.utime(f, (new_mtime, new_mtime))
    assert store.load_if_changed(http_client) is True


async def test_load_if_changed_returns_true_when_file_added(
    tmp_path: Path, http_client: httpx.AsyncClient
):
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01.txt").write_text("a=1", encoding="utf-8")
    store = CookieStore(d)
    store.load_if_changed(http_client)
    (d / "02.txt").write_text("b=2", encoding="utf-8")
    assert store.load_if_changed(http_client) is True
    assert "b=2" in store.current_string()


async def test_load_if_changed_writes_jar_with_domain(
    cookie_dir: Path, http_client: httpx.AsyncClient
):
    store = CookieStore(cookie_dir)
    store.load_if_changed(http_client)
    jar = http_client.cookies.jar
    domains = {c.domain for c in jar if c.value}
    assert ".eastmoney.com" in domains


async def test_load_if_changed_missing_dir_does_not_raise(
    tmp_path: Path, http_client: httpx.AsyncClient
):
    store = CookieStore(tmp_path / "nope")
    assert store.load_if_changed(http_client) is False
    assert store.current_string() == ""


def test_iter_files_skips_hidden_files(tmp_path: Path):
    """Spec eastmoney-cookie-refresh-design.md:84 — skip files starting with '.'."""
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01-real.txt").write_text("a=1", encoding="utf-8")
    (d / ".hidden.txt").write_text("h=9", encoding="utf-8")
    (d / ".gitkeep").write_text("", encoding="utf-8")
    store = CookieStore(d)
    snap = store.file_snapshot()
    assert set(snap.keys()) == {"01-real.txt"}
    assert "h=9" not in store.load_combined_string()


def test_load_combined_string_concatenates_in_filename_order(cookie_dir: Path):
    store = CookieStore(cookie_dir)
    s = store.load_combined_string()
    assert s == "a=1; b=2; c=3"


def test_load_combined_string_skips_empty_files(tmp_path: Path):
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01.txt").write_text("x=1", encoding="utf-8")
    (d / "02.txt").write_text("", encoding="utf-8")
    store = CookieStore(d)
    assert store.load_combined_string() == "x=1"


def test_load_combined_string_overrides_duplicate_keys(tmp_path: Path):
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01.txt").write_text("token=old", encoding="utf-8")
    (d / "02.txt").write_text("token=new", encoding="utf-8")
    store = CookieStore(d)
    parts = store.load_combined_string().split("; ")
    assert parts.count("token=new") == 1
    assert "token=old" not in parts


def test_load_combined_string_returns_empty_when_dir_missing(tmp_path: Path):
    store = CookieStore(tmp_path / "nope")
    assert store.load_combined_string() == ""


def test_file_snapshot_reflects_mtime_and_size(cookie_dir: Path):
    store = CookieStore(cookie_dir)
    snap = store.file_snapshot()
    assert set(snap.keys()) == {"01-a.txt", "02-b.txt"}
    for _, (mtime, size) in snap.items():
        assert isinstance(mtime, float)
        assert isinstance(size, int) and size > 0


def test_check_invalid_rc():
    h = CookieHealthChecker().check('{"rc": 100, "data": {}}')
    assert h.invalid is True
    assert h.reason is not None and "rc=100" in h.reason


def test_check_keyword_invalid():
    h = CookieHealthChecker().check("<html>访问频次过高，请稍后再试</html>")
    assert h.invalid is True
    assert h.reason is not None and "访问频次" in h.reason


def test_check_keyword_captcha():
    h = CookieHealthChecker().check("请输入验证码")
    assert h.invalid is True


def test_check_valid_rc_zero():
    h = CookieHealthChecker().check('{"rc": 0, "data": {"klines": []}}')
    assert h.invalid is False


def test_check_parse_failure_returns_valid():
    h = CookieHealthChecker().check("not-json-{{{")
    assert h.invalid is False


def test_check_empty_string_returns_valid():
    assert CookieHealthChecker().check("").invalid is False


async def test_refresh_once_returns_true_when_jar_changes(
    cookie_dir: Path, http_client: httpx.AsyncClient
):
    store = CookieStore(cookie_dir)
    store.load_if_changed(http_client)

    fake_client = AsyncMock()
    fake_client._refresh_cookie_from_server = AsyncMock(return_value=True)
    checker = CookieHealthChecker()
    assert await checker.refresh_once(fake_client) is True
    fake_client._refresh_cookie_from_server.assert_awaited_once()


async def test_refresh_once_returns_false_when_no_change(
    cookie_dir: Path, http_client: httpx.AsyncClient
):
    store = CookieStore(cookie_dir)
    store.load_if_changed(http_client)
    fake_client = AsyncMock()
    fake_client._refresh_cookie_from_server = AsyncMock(return_value=False)
    fake_client.try_next_cookie_file = MagicMock(return_value=False)
    checker = CookieHealthChecker()
    assert await checker.refresh_once(fake_client) is False


async def test_seed_cookie_jar_uses_default_directory_when_no_cookie_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.chdir(tmp_path)
    for name in (
        "FIN_COOKIE_DIR",
        "EASTMONEY_COOKIE_DIR",
        "EASTMONEY_COOKIE_FILE",
        "EASTMONEY_COOKIE",
    ):
        monkeypatch.delenv(name, raising=False)

    client = EastmoneyClient()
    try:
        assert client._cookie_store is not None
        assert client._cookie_store.dir_path == tmp_path / ".eastmoney_cookies"
        assert client._seeded is True
        assert client._cookie_store.current_string() == ""
    finally:
        await client.close()


async def test_code_list_uses_cookie_store_cookie(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cookie_dir = tmp_path / "cookies"
    cookie_dir.mkdir()
    (cookie_dir / "01.txt").write_text("token=directory", encoding="utf-8")
    monkeypatch.setenv("FIN_COOKIE_DIR", str(cookie_dir))
    for name in ("EASTMONEY_COOKIE_DIR", "EASTMONEY_COOKIE_FILE", "EASTMONEY_COOKIE"):
        monkeypatch.delenv(name, raising=False)

    client = EastmoneyClient()
    get_json = AsyncMock(return_value={})
    client.get_json = get_json
    try:
        await client.code_list(1, 2, 3, "f", "fields")
    finally:
        await client.close()

    assert get_json.await_args.kwargs["headers"]["Cookie"] == "token=directory"


async def test_kline_does_not_persist_cookie_in_directory_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cookie_dir = tmp_path / "cookies"
    cookie_dir.mkdir()
    (cookie_dir / "01.txt").write_text("token=directory", encoding="utf-8")
    monkeypatch.setenv("FIN_COOKIE_DIR", str(cookie_dir))
    for name in ("EASTMONEY_COOKIE_DIR", "EASTMONEY_COOKIE_FILE", "EASTMONEY_COOKIE"):
        monkeypatch.delenv(name, raising=False)

    client = EastmoneyClient()
    client.get_text = AsyncMock(side_effect=['{"rc": 100}', '{"rc": 0}'])
    client._cookie_health.refresh_once = AsyncMock(return_value=True)
    persist_cookie = Mock()
    client._persist_cookie = persist_cookie
    try:
        result = await client.kline("f1", "f2", 0, 0, "1.000001", 101, 1)
    finally:
        await client.close()

    assert result == '{"rc": 0}'
    persist_cookie.assert_not_called()


# ------------------- CookieStore single-file helpers (2026-09-02) -------------------


def test_latest_file_returns_newest(tmp_path):
    """latest_file() 应返回 mtime 最大的 *.txt 文件."""
    import time as _time
    (tmp_path / "old.txt").write_text("a=1")
    _time.sleep(0.05)
    (tmp_path / "new.txt").write_text("b=2")
    store = CookieStore(tmp_path)
    result = store.latest_file()
    assert result is not None
    assert result.name == "new.txt"


def test_latest_file_returns_none_when_empty(tmp_path):
    """目录无 *.txt 时返回 None."""
    store = CookieStore(tmp_path)
    assert store.latest_file() is None


def test_files_by_mtime_desc_orders_newest_first(tmp_path):
    """files_by_mtime_desc() 应按 mtime 倒序返回."""
    import time as _time
    (tmp_path / "a.txt").write_text("a=1")
    _time.sleep(0.05)
    (tmp_path / "b.txt").write_text("b=2")
    _time.sleep(0.05)
    (tmp_path / "c.txt").write_text("c=3")
    store = CookieStore(tmp_path)
    files = store.files_by_mtime_desc()
    assert [f.name for f in files] == ["c.txt", "b.txt", "a.txt"]


def test_load_file_returns_content(tmp_path):
    """load_file() 应返回文件内容（strip）."""
    (tmp_path / "x.txt").write_text("  qgqp_b_id=abc; st_nvi=xyz  ")
    store = CookieStore(tmp_path)
    assert store.load_file(tmp_path / "x.txt") == "qgqp_b_id=abc; st_nvi=xyz"


def test_load_file_returns_empty_on_missing(tmp_path):
    """load_file() 读失败时返回空字符串."""
    store = CookieStore(tmp_path)
    assert store.load_file(tmp_path / "no_such.txt") == ""


async def test_refresh_once_returns_true_when_jar_changes_shortcut(
    cookie_dir: Path, http_client: httpx.AsyncClient
):
    """HTTP 兜底成功 → 不尝试切次新 cookie 文件."""
    store = CookieStore(cookie_dir)
    store.load_if_changed(http_client)

    fake_client = AsyncMock()
    fake_client._refresh_cookie_from_server = AsyncMock(return_value=True)
    fake_client.try_next_cookie_file = MagicMock(return_value=False)

    checker = CookieHealthChecker()
    result = await checker.refresh_once(fake_client)

    assert result is True
    fake_client._refresh_cookie_from_server.assert_awaited_once()
    fake_client.try_next_cookie_file.assert_not_called()
