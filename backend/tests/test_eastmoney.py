"""Tests for EastmoneyClient cookie seeding behaviors (Task 6 - 2026-09-02).

Covers:
- ``_seed_cookie_jar`` 优先加载 ``CookieStore.latest_file()``, 旧文件不进 jar
- ``try_next_cookie_file`` 按 mtime 倒序切到次新文件, 没有更多文件时返回 False
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.clients.eastmoney import EastmoneyClient
from app.clients.eastmoney_cookie import CookieStore


def _bare_client() -> EastmoneyClient:
    """Skip ``__init__`` but give ``_client`` a real httpx client.

    ``EastmoneyClient.__init__`` 会实例化 ``CookieHealthChecker``, 这些测试不依赖
    cookie 健康检查, 所以用 ``__new__`` 跳过 ``__init__``, 只挂一个真的 ``httpx.AsyncClient``
    让 ``cookies.set()`` / ``cookies.jar`` 真实可用.
    """
    client = EastmoneyClient.__new__(EastmoneyClient)
    client._client = httpx.AsyncClient()
    return client


# ------------------- _seed_cookie_jar prefers latest_file (2026-09-02) -------------------


def test_seed_cookie_jar_prefers_latest_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """多文件存在时, 优先加载 mtime 最新的; 旧文件不应进入 jar."""
    import time as _time

    (tmp_path / "old.txt").write_text("st_nvi=OLD")
    _time.sleep(0.05)
    (tmp_path / "new.txt").write_text("qgqp_b_id=NEW")

    monkeypatch.setenv("FIN_COOKIE_DIR", str(tmp_path))
    for name in ("EASTMONEY_COOKIE_DIR", "EASTMONEY_COOKIE_FILE", "EASTMONEY_COOKIE"):
        monkeypatch.delenv(name, raising=False)

    client = _bare_client()
    seeded = client._seed_cookie_jar()

    assert seeded is True
    cookies = {c.name: c.value for c in client._client.cookies.jar}
    assert cookies.get("qgqp_b_id") == "NEW"
    assert cookies.get("st_nvi") is None


# ------------------- try_next_cookie_file (2026-09-02) -------------------


def test_try_next_cookie_file_switches_to_older(tmp_path: Path):
    """try_next_cookie_file 应切到 mtime 次新的文件."""
    import time as _time

    (tmp_path / "old.txt").write_text("st_nvi=OLD")
    _time.sleep(0.05)
    (tmp_path / "new.txt").write_text("qgqp_b_id=NEW")

    client = _bare_client()
    # 先模拟当前 jar 已加载 new.txt 的内容
    client._seed_from_string("qgqp_b_id=NEW")
    client._cookie_store = CookieStore(tmp_path)

    ok = client.try_next_cookie_file()
    assert ok is True
    cookies = {c.name: c.value for c in client._client.cookies.jar}
    assert cookies.get("st_nvi") == "OLD"


def test_try_next_cookie_file_returns_false_when_no_more(tmp_path: Path):
    """目录只有 1 个文件 (且与当前 jar 内容一致) 时, 切换失败."""
    (tmp_path / "only.txt").write_text("qgqp_b_id=X")

    client = _bare_client()
    client._seed_from_string("qgqp_b_id=X")
    client._cookie_store = CookieStore(tmp_path)

    ok = client.try_next_cookie_file()
    assert ok is False


def test_try_next_cookie_file_syncs_cookie_store_last_string(tmp_path: Path):
    """切换到次新文件后, ``CookieStore._last_string`` 必须同步为新内容.

    不变量: ``try_next_cookie_file`` 是单文件胜出路径, 切完后
    ``CookieStore._last_string`` 必须等于被加载的 cookie 字符串.
    否则下一次 ``kline()`` 调用 ``CookieStore.load_if_changed()`` 时,
    即使目录无变化也会因 ``_last_string`` 不匹配而误判为"文件变化",
    触发 ``load_combined_string()`` 合并所有 ``*.txt`` 文件, 覆盖
    单文件胜出的不变性, 让旧 cookie 重新进入 jar.
    """
    import time as _time

    (tmp_path / "old.txt").write_text("st_nvi=OLD")
    _time.sleep(0.05)
    (tmp_path / "new.txt").write_text("qgqp_b_id=NEW")

    client = _bare_client()
    # 当前 jar 已加载 new.txt 的内容
    client._seed_from_string("qgqp_b_id=NEW")
    client._cookie_store = CookieStore(tmp_path)

    ok = client.try_next_cookie_file()
    assert ok is True
    # 关键不变性: CookieStore 必须把切到的新内容登记为 _last_string
    assert client._cookie_store._last_string == "st_nvi=OLD"