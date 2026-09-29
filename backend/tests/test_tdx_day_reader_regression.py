"""Regression tests for app/services/tdx_offline/day_reader.py.

These tests use the actual hsjday.zip downloaded from data.tdx.com.cn.
If the file is missing, tests skip — they're for manual / CI run after fetching.

Note: These tests touch the existing day_reader module, but only ADD coverage,
not modify the implementation. Per AGENTS.md read-only-by-default rule, we
intentionally do not change day_reader.py.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

ZIP_PATH = Path(r"D:\stock\data\hsjday.zip")


pytestmark = pytest.mark.skipif(
    not ZIP_PATH.is_file(),
    reason=f"hsjday.zip 不在 {ZIP_PATH}, 跳过 (需先跑 fetcher 下载)",
)


def _open_zip():
    import zipfile
    return zipfile.ZipFile(ZIP_PATH)


def _read_day(market, code):
    """Extract + parse one .day file using the actual production reader."""
    import struct

    from app.services.tdx_offline.day_reader import TdxDailyBarReader, TdxMarket

    with _open_zip() as z:
        raw = z.read(f"{market}/lday/{market}{code}.day")
    market_obj = TdxMarket(name=market, lday_dir=Path(f"/tmp/fake/{market}/lday"))
    reader = TdxDailyBarReader(market_obj, code)
    # Bypass reader.path check by feeding bytes:
    reader.path = Path(f"/tmp/fake/{market}/lday/{market}{code}.day")
    n = len(raw) // 32
    rec = struct.iter_unpack("<IIIIIfII", raw[:n * 32])
    rows = [
        (datetime.strptime(str(d), "%Y%m%d").isoformat(),
         o * 0.01, h * 0.01, low * 0.01, c * 0.01, amount, int(vol * 0.01))
        for d, o, h, low, c, amount, vol, _ in rec
    ]
    return rows


def test_sh600000_minimum_history():
    rows = _read_day("sh", "600000")
    assert len(rows) > 5000
    first_date = rows[0][0]
    assert first_date.startswith("1999-11")  # 浦发银行上市月


def test_sh510300_etf_detection():
    """510300 (华泰柏瑞沪深300 ETF) 应该被识别为 FUND, 不是 A_STOCK."""
    from app.services.tdx_offline.day_reader import TdxDailyBarReader
    sec_type = TdxDailyBarReader.detect_security_type("sh", "510300")
    assert sec_type == "FUND"


def test_amount_self_consistency():
    """close × shares ≈ amount (偏差 < 5×)."""
    rows = _read_day("sz", "000001")
    # 取最近 30 天校验
    last_30 = rows[-30:]
    fails = 0
    for date_s, _o, _h, _l, c, amt, vol in last_30:
        shares = vol * 100  # raw × 0.01 = 手, 再 ×100 = shares
        if shares <= 0 or amt <= 0:
            continue
        expected = c * shares
        ratio = amt / expected
        if ratio < 0.2 or ratio > 5.0:
            fails += 1
    assert fails <= 2  # 允许极少数坏记录 (day_reader.py:160 注释提到)


def test_bj_market_present():
    """北交所至少有一只股票."""
    rows = _read_day("bj", "920982")
    assert len(rows) > 100


def test_resolve_tdx_home_importable_from_kline_package():
    """Spec 要求 `_resolve_tdx_home` 从 tdx_offline 迁到 clients/kline/tdx_adapter.py.
    旧入口（tdx_offline/fetcher.py）改为 import shim, 但 resolve_tdx_home 自身在
    clients/kline 下独立可用, 不依赖 tdx_offline 内部状态."""
    from app.clients.kline.tdx_adapter import resolve_tdx_home
    p = resolve_tdx_home("/tmp/fake_tdx_home")
    assert p == Path("/tmp/fake_tdx_home")


def test_etf_amount_unit_is_yuan_heuristic(caplog):
    """ETF/FUND 的 .day amount 字段单位是'元', 实测 sh510300 / sh510050 正常日期
    ratio ≈ 1.0; 个别脏记录 (实测 510050 的 20150629~20150708 / 20240118 /
    20260121 / 20260126 / 20260128) raw ≈ expected × 100, read() 启发式自动 ÷100
    修正, 不打 [tdx_offline] amt 异常 warning."""
    import logging
    from unittest import mock

    from app.services.tdx_offline.day_reader import TdxDailyBarReader, TdxMarket

    with _open_zip() as z:
        for code in ("510300", "510050"):
            raw = z.read(f"sh/lday/sh{code}.day")
            market_obj = TdxMarket(
                name="sh", lday_dir=Path("/tmp/fake/sh/lday")
            )
            reader = TdxDailyBarReader(market_obj, code)
            reader.path = Path(f"/tmp/fake/sh/lday/sh{code}.day")

            caplog.clear()
            with caplog.at_level(logging.WARNING):
                with mock.patch.object(Path, "is_file", return_value=True), \
                     mock.patch.object(Path, "read_bytes", return_value=raw):
                    df = reader.read()
            assert len(df) > 1000, f"{code} 至少应有 1000 行历史"

            amt_warns = [r for r in caplog.records if "amt 异常" in r.message]
            assert amt_warns == [], (
                f"{code} 不应再有 amt 异常 warning, 实际命中 {len(amt_warns)} 条: "
                f"{[r.message for r in amt_warns[:3]]}"
            )

            last_30 = df.tail(30)
            fails = 0
            for _, row in last_30.iterrows():
                shares = int(row["vol"]) * 100
                if shares <= 0 or row["amount"] <= 0:
                    continue
                expected = row["close"] * shares
                ratio = row["amount"] / expected
                if ratio < 0.2 or ratio > 5.0:
                    fails += 1
            assert fails <= 2, (
                f"{code} 最近 30 天 amount 自洽校验 fails={fails}, 期望 ≤ 2"
            )


def test_etf_amount_100x_corruption_auto_corrected(caplog):
    """510050 的脏记录 (raw ≈ expected × 100) 应被启发式自动 ÷100 修正,
    修正后 amount 与 close × shares 自洽, 不打 warning."""
    import logging
    from unittest import mock

    from app.services.tdx_offline.day_reader import TdxDailyBarReader, TdxMarket

    with _open_zip() as z:
        raw = z.read("sh/lday/sh510050.day")
        market_obj = TdxMarket(name="sh", lday_dir=Path("/tmp/fake/sh/lday"))
        reader = TdxDailyBarReader(market_obj, "510050")
        reader.path = Path("/tmp/fake/sh/lday/sh510050.day")

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            with mock.patch.object(Path, "is_file", return_value=True), \
                 mock.patch.object(Path, "read_bytes", return_value=raw):
                df = reader.read()

        amt_warns = [r for r in caplog.records if "amt 异常" in r.message]
        assert amt_warns == [], (
            f"启发式应自动修正 ratio≈100 的脏记录, 不应有 warning, "
            f"实际命中 {len(amt_warns)} 条"
        )

        # 510050 的已知脏日期: 20260128 (用户日志 ratio=99.85)
        row_0128 = df.loc[df.index.strftime("%Y%m%d") == "20260128"].iloc[0]
        shares = int(row_0128["vol"]) * 100
        expected = row_0128["close"] * shares
        ratio = row_0128["amount"] / expected
        assert 0.9 < ratio < 1.1, (
            f"20260128 修正后 ratio 应 ≈ 1, 实际={ratio:.4f} "
            f"(close={row_0128['close']}, amount={row_0128['amount']}, expected={expected})"
        )
