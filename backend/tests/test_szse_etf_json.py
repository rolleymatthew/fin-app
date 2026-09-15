"""szse_etf_json.parse_json 单元测试（纯函数，无 IO/无 DB）

新格式：JSON 数组，每行 {code, name, scale, mgr}
- scale 为字符串（与 CSV 同样的亿份口径，乘 10^8 转"份"）
- mgr 丢弃（已内嵌于 secName，如"港股通互联网 ETF 富国"含"富国"）
- 行级容错：code 非数字或 scale 解析失败 → skip 该行
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.clients.szse_etf_json import parse_json

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sz_etf_sample.json"


def _write_json(items: list[dict] | str) -> bytes:
    """辅助：把 dict 列表（或裸 JSON 字符串）写成 UTF-8 bytes。"""
    if isinstance(items, str):
        text = items
    else:
        text = json.dumps(items, ensure_ascii=False)
    return text.encode("utf-8")


def test_parse_json_happy_path():
    content = _write_json([
        {"code": "159792", "name": "港股通互联网ETF富国", "scale": "635.36", "mgr": "富国基金"},
        {"code": "159516", "name": "半导体设备ETF国泰", "scale": "618.59", "mgr": "国泰基金"},
    ])
    rows = parse_json(content, date(2026, 9, 9))
    assert len(rows) == 2
    assert rows[0] == {
        "SEC_CODE": "159792",
        "SEC_NAME": "港股通互联网ETF富国",
        "TOT_VOL_YI": Decimal("635.36"),
    }
    assert rows[1]["SEC_CODE"] == "159516"


def test_parse_json_skips_mgr_field():
    """mgr 字段不入 DTO（与 CSV 旧实现一致）"""
    content = _write_json([
        {"code": "159001", "name": "货币ETF", "scale": "1.0", "mgr": "管理人X"},
    ])
    rows = parse_json(content, date(2026, 9, 9))
    assert "MANAGER" not in rows[0]
    assert set(rows[0].keys()) == {"SEC_CODE", "SEC_NAME", "TOT_VOL_YI"}


def test_parse_json_skip_bad_code():
    content = _write_json([
        {"code": "159792", "name": "A", "scale": "1.0", "mgr": "X"},
        {"code": "ABC", "name": "B", "scale": "1.0", "mgr": "Y"},
        {"code": "159516", "name": "C", "scale": "1.0", "mgr": "Z"},
    ])
    rows = parse_json(content, date(2026, 9, 9))
    assert len(rows) == 2
    assert [r["SEC_CODE"] for r in rows] == ["159792", "159516"]


def test_parse_json_skip_bad_scale():
    content = _write_json([
        {"code": "159792", "name": "A", "scale": "not-a-number", "mgr": "X"},
        {"code": "159516", "name": "B", "scale": "", "mgr": "Y"},
        {"code": "159352", "name": "C", "scale": "267.90", "mgr": "Z"},
    ])
    rows = parse_json(content, date(2026, 9, 9))
    assert len(rows) == 1
    assert rows[0]["SEC_CODE"] == "159352"


def test_parse_json_skip_missing_fields():
    """缺少必填字段（code/name/scale）的行整行跳过"""
    content = _write_json([
        {"code": "159001", "name": "A", "scale": "1.0", "mgr": "X"},
        {"code": "159002"},  # 缺 name, scale
        {"name": "no_code", "scale": "2.0", "mgr": "Y"},
    ])
    rows = parse_json(content, date(2026, 9, 9))
    assert len(rows) == 1
    assert rows[0]["SEC_CODE"] == "159001"


def test_parse_json_empty_returns_empty_list():
    assert parse_json(_write_json([]), date(2026, 9, 9)) == []
    assert parse_json(b"", date(2026, 9, 9)) == []


def test_parse_json_invalid_json_returns_empty_list():
    """JSON 解析失败时返回空列表（与 CSV 行为一致，watcher 会报错）"""
    assert parse_json(b"not json", date(2026, 9, 9)) == []
    assert parse_json(b"{not array}", date(2026, 9, 9)) == []


def test_parse_json_preserves_scale_precision():
    """scale 是字符串，Decimal 解析应保留精度（'0.10' != '0.1'）"""
    content = _write_json([
        {"code": "159001", "name": "A", "scale": "0.10", "mgr": "X"},
    ])
    rows = parse_json(content, date(2026, 9, 9))
    assert rows[0]["TOT_VOL_YI"] == Decimal("0.10")


def test_parse_json_real_fixture():
    """10 行真实样式 fixture 全跑通"""
    content = FIXTURE_PATH.read_bytes()
    rows = parse_json(content, date(2026, 9, 9))
    assert len(rows) == 10
    assert rows[0]["SEC_CODE"] == "159001"
    assert rows[0]["TOT_VOL_YI"] == Decimal("1.23")
    assert all("MANAGER" not in r for r in rows)
    assert all(set(r.keys()) == {"SEC_CODE", "SEC_NAME", "TOT_VOL_YI"} for r in rows)


def test_parse_json_wrapped_dict_format():
    """豆包当前下载格式：顶层是 {stat_date, source, rows: [...]}"""
    content = _write_json({
        "stat_date": "2026-09-10",
        "source": "fund.szse.cn/api/report/ShowReport/data?CATALOGID=ssjjcp_1",
        "fetched_at": "2026-09-10T23:02:03+08:00",
        "total": 3,
        "rows": [
            {"code": "159001", "name": "货币ETF", "scale": "1.23", "mgr": "管理人A"},
            {"code": "159002", "name": "债券ETF", "scale": "0.10", "mgr": "管理人B"},
            {"code": "159003", "name": "股票ETF", "scale": "5.67", "mgr": "管理人C"},
        ],
    })
    rows = parse_json(content, date(2026, 9, 10))
    assert len(rows) == 3
    assert rows[0] == {
        "SEC_CODE": "159001",
        "SEC_NAME": "货币ETF",
        "TOT_VOL_YI": Decimal("1.23"),
    }
    assert all("MANAGER" not in r for r in rows)
    assert [r["SEC_CODE"] for r in rows] == ["159001", "159002", "159003"]


def test_parse_json_wrapped_dict_without_rows_returns_empty():
    """包装格式但缺少 rows 字段 → 返回空列表（与顶层非 list 一致）"""
    content = _write_json({"stat_date": "2026-09-10", "total": 0})
    assert parse_json(content, date(2026, 9, 10)) == []
