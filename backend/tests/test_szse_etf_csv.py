"""szse_etf_csv.parse_csv 单元测试（纯函数，无 IO/无 DB）"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.clients.szse_etf_csv import parse_csv


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "etf_csv_sample.csv"


def _row_csv_text(text: str) -> bytes:
    return text.encode("utf-8-sig")


def test_parse_csv_happy_path():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,港股通互联网 ETF 富国,635.36,富国基金\n"
        "2,159516,半导体设备 ETF 国泰,618.59,国泰基金\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 2
    assert rows[0] == {
        "SEC_CODE": "159792",
        "SEC_NAME": "港股通互联网 ETF 富国",
        "TOT_VOL_YI": Decimal("635.36"),
    }
    assert rows[1]["SEC_CODE"] == "159516"


def test_parse_csv_skip_bad_code():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,A,635.36,X\n"
        "2,ABC,B,12.34,Y\n"
        "3,159516,C,618.59,Z\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 2
    assert [r["SEC_CODE"] for r in rows] == ["159792", "159516"]


def test_parse_csv_skip_bad_scale():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,A,not-a-number,X\n"
        "2,159516,B,,Y\n"
        "3,159352,C,267.90,Z\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 1
    assert rows[0]["SEC_CODE"] == "159352"


def test_parse_csv_empty_returns_empty_list():
    assert parse_csv(_row_csv_text(""), date(2026, 9, 8)) == []
    assert parse_csv(_row_csv_text("排名,代码,简称,规模 (亿),管理人\n"), date(2026, 9, 8)) == []


def test_parse_csv_bom_handled():
    content = b"\xef\xbb\xbf" + "排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,X\n".encode("utf-8")
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 1


def test_parse_csv_drops_manager_and_rank():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,富国基金\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert "MANAGER" not in rows[0]
    assert "排名" not in rows[0]
    assert set(rows[0].keys()) == {"SEC_CODE", "SEC_NAME", "TOT_VOL_YI"}


def test_parse_csv_real_fixture():
    """10 行真实样式 fixture 全跑通"""
    content = FIXTURE_PATH.read_bytes()
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 10
    assert rows[0]["SEC_CODE"] == "159792"
    assert rows[0]["TOT_VOL_YI"] == Decimal("635.36")
    assert all("MANAGER" not in r for r in rows)
