"""回归测试：V2 Client 按 orgTypeCode 选择正确的前缀端点。

背景：
``FinanceEastmoneyV2Client`` 默认走 ``RPT_F10_FINANCE_G*`` 系列接口，
对保险（orgTypeCode="2"）/银行（"3"）/证券（"1"）公司返回空集。

东方财富 F10 页面实际按公司类型走不同前缀的报表：
- Universal  (4) → G（通用）
- Insurance  (2) → I（保险专用）
- Bank      (3) → B（银行专用）
- Securities (1) → S（证券专用）

注：东方财富把证券公司归为 orgTypeCode="1"（在系统原代码中曾被误命名为
``BondTypeCode``）。真正的国债/可转债等债券（113044.SH 等）不在
``RPT_F10_ORG_BASICINFO``，走另一套 ``RPT_BOND_*`` 系统，**没有财务报表
数据**，因此本项目不再为债券提供专列。

实测：
| 公司         | G-prefix         | I/B/S-prefix                |
|--------------|------------------|------------------------------|
| 601318 保险   | GCASHFLOW 空     | ICASHFLOW ✅ (256 字段)     |
| 601398 银行   | GCASHFLOW 空     | BCASHFLOW ✅ (316 字段)     |
| 600030 证券   | GCASHFLOW 空     | SCASHFLOW ✅ (252 字段)     |
| 600019 通用   | GCASHFLOW ✅      | 不适用                       |
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.clients.finance_eastmoney_v2 import FinanceEastmoneyV2Client


def _make_v2_client() -> FinanceEastmoneyV2Client:
    return FinanceEastmoneyV2Client()


# ---------- _org prefix 选择 ----------

def test_universal_org_uses_g_prefix():
    """orgTypeCode='4'（通用）走 G 前缀。"""
    v2 = _make_v2_client()
    assert v2._org_prefix("4") == "G"


def test_insurance_org_uses_i_prefix():
    """orgTypeCode='2'（保险）走 I 前缀。"""
    v2 = _make_v2_client()
    assert v2._org_prefix("2") == "I"


def test_bank_org_uses_b_prefix():
    """orgTypeCode='3'（银行）走 B 前缀。"""
    v2 = _make_v2_client()
    assert v2._org_prefix("3") == "B"


def test_securities_org_uses_s_prefix():
    """orgTypeCode='1'（证券）走 S 前缀。

    修复前该 orgTypeCode 被错误命名为 ``BondTypeCode``，回退到 G 前缀导致
    SCASHFLOW/SBALANCE 拿不到数据。现在证券（"1"）改走 S 前缀。
    """
    v2 = _make_v2_client()
    assert v2._org_prefix("1") == "S"


def test_unknown_org_falls_back_to_g_prefix():
    """未识别 orgTypeCode 走 G 默认前缀。"""
    v2 = _make_v2_client()
    assert v2._org_prefix("9") == "G"
    assert v2._org_prefix("") == "G"


# ---------- _fetch 根据 org 选 type / sty ----------

@pytest.mark.asyncio
async def test_insurance_cashflow_uses_icashflow_endpoint():
    """保险（"2"）cash_flow 必须命中 RPT_F10_FINANCE_ICASHFLOW 而非 GCASHFLOW。"""
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"NETCASH_OPERATE": "100"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.cash_flow("2", "2025-09-30", "SH601318")
    assert captured["type"] == "RPT_F10_FINANCE_ICASHFLOW"
    assert captured["sty"] == "APP_F10_ICASHFLOW"


@pytest.mark.asyncio
async def test_bank_cashflow_uses_bcashflow_endpoint():
    """银行（"3"）cash_flow 命中 RPT_F10_FINANCE_BCASHFLOW。"""
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"NETCASH_OPERATE": "200"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.cash_flow("3", "2025-09-30", "SH601398")
    assert captured["type"] == "RPT_F10_FINANCE_BCASHFLOW"
    assert captured["sty"] == "APP_F10_BCASHFLOW"


@pytest.mark.asyncio
async def test_securities_cashflow_uses_scashflow_endpoint():
    """证券（"1"）cash_flow 命中 RPT_F10_FINANCE_SCASHFLOW。"""
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"NETCASH_OPERATE": "56202060885"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.cash_flow("1", "2025-09-30", "SH600030")
    assert captured["type"] == "RPT_F10_FINANCE_SCASHFLOW"
    assert captured["sty"] == "APP_F10_SCASHFLOW"


@pytest.mark.asyncio
async def test_universal_cashflow_keeps_gcashflow_endpoint():
    """通用（"4"）cash_flow 保持原 G 前缀。"""
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"NETCASH_OPERATE": "300"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.cash_flow("4", "2025-09-30", "SH600019")
    assert captured["type"] == "RPT_F10_FINANCE_GCASHFLOW"
    assert captured["sty"] == "APP_F10_GCASHFLOW"


# ---------- assets / profit 同步生效 ----------

@pytest.mark.asyncio
async def test_insurance_assets_uses_ibalance_endpoint():
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"TOTAL_ASSETS": "9"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.assets("2", "2025-09-30", "SH601318")
    assert captured["type"] == "RPT_F10_FINANCE_IBALANCE"
    assert captured["sty"] == "F10_FINANCE_IBALANCE"


@pytest.mark.asyncio
async def test_insurance_profit_uses_iincome_endpoint():
    """保险 profit 也切到 IINCOME，保留 OPERATE_EXPENSE 字段。"""
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"OPERATE_INCOME": "1"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.profit("2", "2025-09-30", "SH601318")
    assert captured["type"] == "RPT_F10_FINANCE_IINCOME"
    assert captured["sty"] == "APP_F10_IINCOME"


@pytest.mark.asyncio
async def test_securities_assets_uses_sbalance_endpoint():
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"TOTAL_ASSETS": "999"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.assets("1", "2025-09-30", "SH600030")
    assert captured["type"] == "RPT_F10_FINANCE_SBALANCE"
    assert captured["sty"] == "F10_FINANCE_SBALANCE"


@pytest.mark.asyncio
async def test_securities_profit_uses_sincome_endpoint():
    """证券 profit 走 SINCOME。"""
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        captured["sty"] = params.get("sty")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"OPERATE_INCOME": "55814696246"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.profit("1", "2025-09-30", "SH600030")
    assert captured["type"] == "RPT_F10_FINANCE_SINCOME"
    assert captured["sty"] == "APP_F10_SINCOME"


# ---------- dates 接口同步生效 ----------

@pytest.mark.asyncio
async def test_insurance_cashflow_dates_uses_icashflow_endpoint():
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"REPORT_DATE": "2025-09-30 00:00:00"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.cash_flow_dates("2", "SH601318")
    assert captured["type"] == "RPT_F10_FINANCE_ICASHFLOW"


@pytest.mark.asyncio
async def test_bank_assets_dates_uses_bbalance_endpoint():
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": []},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.assets_dates("3", "SH601398")
    assert captured["type"] == "RPT_F10_FINANCE_BBALANCE"


@pytest.mark.asyncio
async def test_securities_cashflow_dates_uses_scashflow_endpoint():
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": [{"REPORT_DATE": "2025-09-30 00:00:00"}]},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.cash_flow_dates("1", "SH600030")
    assert captured["type"] == "RPT_F10_FINANCE_SCASHFLOW"


@pytest.mark.asyncio
async def test_securities_assets_dates_uses_sbalance_endpoint():
    v2 = _make_v2_client()
    captured = {}

    async def fake_get_text(path, params, headers=None, base_url_override=None, *, retry=True):
        captured["type"] = params.get("type")
        return json.dumps(
            {
                "version": "x",
                "result": {"pages": 1, "data": []},
                "success": True,
            },
            ensure_ascii=False,
        )

    with patch.object(v2, "get_text", AsyncMock(side_effect=fake_get_text)):
        await v2.assets_dates("1", "SH600030")
    assert captured["type"] == "RPT_F10_FINANCE_SBALANCE"


# ---------- 端到端：字段名一致性 ----------

@pytest.mark.asyncio
async def test_securities_cashflow_returns_non_empty_data():
    """模拟 S-prefix 返回非空数据，验证 cash_flow() 透传字段不被改写。

    关键：确保 S-prefix 返回的字段名（NETCASH_OPERATE 等）与 OLD API 一致，
    无需任何字段重命名即可被 ``app.utils.finance_utils.net_cash_flow_from_operating_activities``
    等函数正确读取。
    """
    v2 = _make_v2_client()
    scashflow_payload = json.dumps(
        {
            "version": "x",
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECUCODE": "600030.SH",
                        "SECURITY_CODE": "600030",
                        "REPORT_DATE": "2025-09-30 00:00:00",
                        "NETCASH_OPERATE": "56202060885.02",
                        "NETCASH_INVEST": "34533121369.53",
                        "NETCASH_FINANCE": "35382512070.78",
                        "CONSTRUCT_LONG_ASSET": "801658895.48",
                    }
                ],
            },
            "success": True,
        },
        ensure_ascii=False,
    )

    with patch.object(v2, "get_text", AsyncMock(return_value=scashflow_payload)):
        result = await v2.cash_flow("1", "2025-09-30", "SH600030")

    parsed = json.loads(result)
    item = parsed["data"][0]
    # 字段名必须保持 NETCASH_OPERATE 等标准驼峰命名
    assert item["NETCASH_OPERATE"] == "56202060885.02"
    assert item["CONSTRUCT_LONG_ASSET"] == "801658895.48"
    assert item["REPORT_DATE"] == "2025-09-30 00:00:00"