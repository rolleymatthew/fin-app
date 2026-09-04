"""Tests for Cookie diagnostics (新增 2026-08-21).

覆盖用户场景:
- 启动时打印 Cookie 状态 (mtime/年龄/字段数)
- Cookie 文件变化时打印 "热加载" 提示
- Cookie 失效时打印可执行的处理步骤
- 增量抓取全失败时打印每个 fallback 源的诊断
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.clients.eastmoney import EastmoneyClient
from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.types import FQT, PERIOD, SOURCE, KLineRow
from app.services.kline_service import KLineService

# ------------------- EastmoneyClient._log_cookie_status -------------------


def _make_client_with_cookie_dir(cookie_dir: Path, monkeypatch) -> EastmoneyClient:
    """构造一个 EastmoneyClient 实例, CookieStore 指向指定 tmp 目录."""
    monkeypatch.setenv("FIN_COOKIE_DIR", str(cookie_dir))
    # 重置 lru_cache 避免污染
    from app.clients.eastmoney import get_eastmoney_client
    get_eastmoney_client.cache_clear()
    client = get_eastmoney_client()
    return client


def test_log_cookie_status_prints_age_when_fresh(
    tmp_path: Path, monkeypatch, capsys
):
    """新文件: 打印 file + age + fields, 不带警告."""
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01.txt").write_text("a=1; b=2; c=3", encoding="utf-8")
    client = _make_client_with_cookie_dir(d, monkeypatch)
    client._log_cookie_status(tag="启动")
    captured = capsys.readouterr()
    assert "【COOKIE_启动】" in captured.out
    assert "01.txt" in captured.out
    assert "fields=3" in captured.out
    # 新文件 age < 7 天, 不应带警告
    assert "较旧" not in captured.out
    assert "7 天以上" not in captured.out


def test_log_cookie_status_warns_when_old(
    tmp_path: Path, monkeypatch, capsys
):
    """老文件 (>14天): 打印警告."""
    d = tmp_path / "cookies"
    d.mkdir()
    f = d / "01.txt"
    f.write_text("a=1", encoding="utf-8")
    # 把 mtime 改到 30 天前
    old_time = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(f, (old_time, old_time))

    client = _make_client_with_cookie_dir(d, monkeypatch)
    client._log_cookie_status(tag="启动")
    captured = capsys.readouterr()
    assert "【COOKIE_启动】" in captured.out
    assert "01.txt" in captured.out
    # 30 天前 → 应有警告
    assert "较旧" in captured.out or "14 天" in captured.out


def test_log_cookie_status_warns_when_dir_missing(
    tmp_path: Path, monkeypatch, capsys
):
    """目录不存在: 打印明确可执行的提示."""
    nonexistent = tmp_path / "no-such-dir"
    client = _make_client_with_cookie_dir(nonexistent, monkeypatch)
    client._log_cookie_status(tag="启动")
    captured = capsys.readouterr()
    assert "【COOKIE_启动】" in captured.out
    assert "不存在" in captured.out
    assert "kline 请求会被服务端静默拒绝" in captured.out


def test_log_cookie_status_warns_when_dir_empty(
    tmp_path: Path, monkeypatch, capsys
):
    """目录存在但无 *.txt 文件: 明确提示."""
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "README.md").write_text("# not cookie", encoding="utf-8")
    client = _make_client_with_cookie_dir(d, monkeypatch)
    client._log_cookie_status(tag="启动")
    captured = capsys.readouterr()
    assert "【COOKIE_启动】" in captured.out
    assert "无 *.txt 文件" in captured.out


def test_log_cookie_invalid_prints_actionable_steps(
    tmp_path: Path, monkeypatch, capsys
):
    """Cookie 失效时打印的处理步骤含: F12 / push2his / Cookie 文件路径 / 无需重启."""
    d = tmp_path / "cookies"
    d.mkdir()
    (d / "01.txt").write_text("a=1", encoding="utf-8")
    client = _make_client_with_cookie_dir(d, monkeypatch)
    client._log_cookie_invalid(reason="rc=100")
    captured = capsys.readouterr()
    assert "【COOKIE_INVALID】" in captured.out
    assert "rc=100" in captured.out
    # 必须有可执行提示
    assert "F12" in captured.out
    assert "push2his" in captured.out
    assert str(d) in captured.out
    assert "无需重启" in captured.out


# ------------------- EastmoneyClient.kline 调用 load_if_changed 后日志 -------------------


async def test_kline_logs_热加载_when_cookie_file_changes(
    tmp_path: Path, monkeypatch, capsys
):
    """Cookie 文件 mtime 变化时, kline() 应打印 'COOKIE_热加载'."""
    d = tmp_path / "cookies"
    d.mkdir()
    f = d / "01.txt"
    f.write_text("a=1", encoding="utf-8")

    client = _make_client_with_cookie_dir(d, monkeypatch)

    # 第一次调用 kline → load_if_changed 返回 False (初次加载不算变化)
    # 模拟服务端的最小有效响应 (避免走 CookieHealthChecker 错误分支)
    fake_text = '{"rc":0,"data":{"klines":["2026-08-20,1,1,1,1,1,1,0,0,0,0"]}}'

    async def fake_get_text(*args, **kwargs):
        return fake_text

    with patch.object(client, "get_text", fake_get_text):
        await client.kline(
            "f1", "f2", 0, 20500101, "1.510500", 101, 1,
        )

    # 修改 mtime, 第二次调用应触发 热加载 日志
    new_mtime = f.stat().st_mtime + 10
    os.utime(f, (new_mtime, new_mtime))

    capsys.readouterr()  # 清空上一次的输出

    with patch.object(client, "get_text", fake_get_text):
        await client.kline(
            "f1", "f2", 0, 20500101, "1.510500", 101, 1,
        )

    captured = capsys.readouterr()
    assert "【COOKIE_热加载】" in captured.out


# ------------------- KLineAggregator chain_results -------------------


def _row(date, o=1, c=1, h=1, lo=1, v=1):
    return KLineRow(date=date, open=o, close=c, high=h, low=lo, volume=v)


class _StubAdapter:
    def __init__(self, source, rows=None, raise_exc=None):
        self.source = source
        self._rows = rows or []
        self._raise = raise_exc

    async def fetch(self, symbol, period, fqt, limit):
        if self._raise is not None:
            raise self._raise
        return self._rows


async def test_aggregator_records_chain_results_on_success():
    """主源成功时 chain_results 应包含主源的成功记录."""
    primary = _StubAdapter(SOURCE.EASTMONEY, [_row("2026-08-20")])
    fb = _StubAdapter(SOURCE.THS, [])
    agg = KLineAggregator(primary=primary, fallbacks=[fb])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert result.source == SOURCE.EASTMONEY
    assert result.chain_results is not None
    # 主源成功 + fb 失败/未调用都不在 chain (first-non-empty wins)
    statuses = [c[1] for c in result.chain_results]
    assert "ok" in statuses


async def test_aggregator_records_chain_results_on_all_empty():
    """所有源都返回空时 chain_results 应包含所有源的尝试记录."""
    primary = _StubAdapter(SOURCE.EASTMONEY, [])
    fb1 = _StubAdapter(SOURCE.THS, [])
    fb2 = _StubAdapter(SOURCE.SINA, [_row("2026-08-21")])
    agg = KLineAggregator(primary=primary, fallbacks=[fb1, fb2])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    # fb2 返回非空, 应使用 fb2
    assert result.source == SOURCE.SINA
    # chain 应记录前两个 empty + 第三个 ok
    chain = result.chain_results
    assert chain is not None and len(chain) == 3
    assert (chain[0][0], chain[0][1]) == ("eastmoney", "empty")
    assert (chain[1][0], chain[1][1]) == ("ths", "empty")
    assert (chain[2][0], chain[2][1]) == ("sina", "ok")


async def test_aggregator_records_chain_results_on_exception():
    """源抛异常时 chain_results 应记录 error 状态."""
    primary = _StubAdapter(SOURCE.EASTMONEY, raise_exc=TimeoutError("boom"))
    fb = _StubAdapter(SOURCE.THS, [_row("2026-08-21")])
    agg = KLineAggregator(primary=primary, fallbacks=[fb])
    result = await agg.fetch("sh510500", PERIOD.DAY, FQT.QFQ, limit=5)
    assert result.source == SOURCE.THS
    chain = result.chain_results
    assert chain is not None and len(chain) == 2
    assert chain[0][1] == "error"
    assert "TimeoutError" in (chain[0][3] or "")


# ------------------- KLineService diagnostic helpers -------------------


def test_format_chain_results_includes_status_and_error():
    """_format_chain_results 应展示每个源的状态 + 错误."""
    chain = [
        ("eastmoney", "empty", 0, None),
        ("ths", "error", 0, "ConnectionError: timeout"),
        ("sina", "ok", 5, None),
    ]
    formatted = KLineService._format_chain_results(chain)
    assert "eastmoney=empty" in formatted
    assert "ths=error:ConnectionError" in formatted
    assert "sina=ok:5" in formatted


def test_format_chain_results_handles_empty():
    chain_results = []
    assert "no chain info" in KLineService._format_chain_results(chain_results)


def test_format_chain_results_truncates_long_error():
    """错误信息超过 80 字符应截短."""
    long_err = "x" * 200
    chain = [("ths", "error", 0, long_err)]
    formatted = KLineService._format_chain_results(chain)
    # 不应包含原始 200 个 x
    assert formatted.count("x") <= 80