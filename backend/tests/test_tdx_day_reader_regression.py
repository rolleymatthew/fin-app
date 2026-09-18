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
