"""Tests for THS adapter version fallback (新增 2026-08-21).

同花顺 d.10jqka.com.cn 每个 ETF 适配的 v 路径不同:
- 510500 用 v4
- 510050 用 v1/v6 (v4 返回 502)
- 159915 用 v2 (v4 返回 502)
- 159919 用 v4
修复方案: 按优先级 v4 → v1 → v2 → v3 → v6 依次尝试, 首个返回 JSONP 即用
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.clients.kline.ths_adapter import ThsAdapter
from app.clients.kline.types import FQT, PERIOD


def _fake_resp(text: str) -> MagicMock:
    """构造一个 _get 返回的假 response 对象."""
    fake = MagicMock()
    fake.text = text
    fake.raise_for_status = MagicMock()
    return fake


def _jsonp(version: str, code: str, year: int, n_rows: int = 1) -> str:
    """构造一个有效的 JSONP 响应 (类似 quotebridge_v4_line_hs_510500_01_2024(...))."""
    rows = []
    for i in range(n_rows):
        date_str = f"{year}{i+1:02d}01"
        rows.append(
            f"{date_str},1.0,1.1,0.9,1.05,100000,100000000.000,1.0,,0"
        )
    data_str = ";".join(rows)
    payload = '{"total":%d,"data":"%s"}' % (n_rows, data_str)
    return f"quotebridge_{version}_line_hs_{code}_01_{year}({payload})"


def _html_error() -> str:
    return "<html><body>502 Bad Gateway</body></html>"


# ----------------------------------------------------------------------- #
# 版本回退核心逻辑
# ----------------------------------------------------------------------- #


async def test_falls_back_to_v1_when_v4_returns_html():
    """v4 返回 HTML 错误页 → 回退到 v1 成功."""
    adapter = ThsAdapter()

    async def fake_get(url):
        if "/v4/" in url:
            return _fake_resp(_html_error())
        if "/v1/" in url:
            return _fake_resp(_jsonp("v1", "510050", 2024))
        return _fake_resp(_html_error())

    import unittest.mock as _mock
    with _mock.patch.object(adapter, "_get", fake_get):
        rows = await adapter._try_fetch_year_variants("510050", "01", 2024)

    assert len(rows) == 1
    assert rows[0].date == "2024-01-01"


async def test_falls_back_to_v2_when_v4_returns_html():
    """v4 返回 HTML → 回退到 v2 成功 (159915 场景)."""
    adapter = ThsAdapter()

    async def fake_get(url):
        if "/v4/" in url:
            return _fake_resp(_html_error())
        if "/v2/" in url:
            return _fake_resp(_jsonp("v2", "159915", 2024, n_rows=2))
        return _fake_resp(_html_error())

    import unittest.mock as _mock
    with _mock.patch.object(adapter, "_get", fake_get):
        rows = await adapter._try_fetch_year_variants("159915", "01", 2024)

    assert len(rows) == 2


async def test_v4_success_returns_immediately_without_fallback():
    """v4 返回有效 JSONP → 立即用 v4, 不尝试其他版本."""
    adapter = ThsAdapter()
    visited: list[str] = []

    async def fake_get(url):
        visited.append(url)
        if "/v4/" in url:
            return _fake_resp(_jsonp("v4", "510500", 2024, n_rows=3))
        return _fake_resp(_html_error())  # 其他版本不应被调用

    import unittest.mock as _mock
    with _mock.patch.object(adapter, "_get", fake_get):
        rows = await adapter._try_fetch_year_variants("510500", "01", 2024)

    assert len(rows) == 3
    # v4 应被调用, v1/v2/v3/v6 不应
    versions_called = [u.split("/")[3].strip("v") for u in visited if "/v" in u]
    assert versions_called.count("4") == 1
    assert "1" not in versions_called
    assert "2" not in versions_called


async def test_empty_data_on_v4_does_not_fallback():
    """v4 返回 200 但 data 为空 (ETF 未上市) → 直接返回 [], 不回退."""
    adapter = ThsAdapter()
    visited: list[str] = []

    empty_payload = '{"total":0,"data":""}'
    v4_empty = f"quotebridge_v4_line_hs_510500_01_2012({empty_payload})"

    async def fake_get(url):
        visited.append(url)
        # v4 返回 200 + 空 data, 其他版本如果被调用会返回真实数据 (用以验证不回退)
        if "/v4/" in url:
            return _fake_resp(v4_empty)
        return _fake_resp(_jsonp("v1", "510500", 2012, n_rows=5))

    import unittest.mock as _mock
    with _mock.patch.object(adapter, "_get", fake_get):
        rows = await adapter._try_fetch_year_variants("510500", "01", 2012)

    assert rows == []
    # v4 应被调用, 但 v1 不应被调用 (因 v4 返回了有效 JSONP)
    v4_called = any("/v4/" in u for u in visited)
    v1_called = any("/v1/" in u for u in visited)
    assert v4_called is True
    assert v1_called is False


async def test_all_versions_fail_returns_empty():
    """所有版本都返回 HTML 错误页 → 返回 [], 记录日志."""
    adapter = ThsAdapter()

    async def fake_get(url):
        return _fake_resp(_html_error())

    import unittest.mock as _mock
    with _mock.patch.object(adapter, "_get", fake_get):
        rows = await adapter._try_fetch_year_variants("999999", "01", 2024)

    assert rows == []


async def test_version_priority_order():
    """验证回退顺序是 v4 → v1 → v2 → v3 → v6."""
    assert ThsAdapter._THS_VERSION_PRIORITY == ("v4", "v1", "v2", "v3", "v6")


# ----------------------------------------------------------------------- #
# fetch() 集成测试
# ----------------------------------------------------------------------- #


async def test_fetch_uses_version_fallback_for_unsupported_v4():
    """510050 全量拉取: v4 都 502, 应回退到 v1 获取数据."""
    adapter = ThsAdapter()
    visited_urls: list[str] = []

    async def fake_get(url):
        visited_urls.append(url)
        if "/v4/" in url:
            # 510050 v4 全 502
            return _fake_resp(_html_error())
        if "/v1/" in url:
            # v1 给完整数据 (假设每个年份 1 行)
            year_match = url.split("/")[-1].replace(".js", "")
            return _fake_resp(_jsonp("v1", "510050", int(year_match), n_rows=1))
        return _fake_resp(_html_error())

    import unittest.mock as _mock
    with _mock.patch.object(adapter, "_get", fake_get):
        rows = await adapter.fetch("sh510050", PERIOD.DAY, FQT.QFQ, limit=99999)

    # 510050 在 v4 失败 → 应回退 v1 → 应该有数据
    assert len(rows) > 0
    # 验证至少有一年 v1 调用成功
    v1_calls = [u for u in visited_urls if "/v1/" in u]
    assert len(v1_calls) > 0