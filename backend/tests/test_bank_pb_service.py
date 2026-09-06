"""BankPBService 单元测试（不依赖真实 MongoDB）。

通过内存 FakeCollection / FakeKlineService 替换依赖：
- assets_bank_repo.find_all_by_security_code_order_by_report_date_asc
- kline_service.kline_by_sec_code
- sec_code_service.sec_code_entity_by_id
"""
from __future__ import annotations

from typing import Any

from app.models.entities import AssetsBankEntity, KLineDataEntity, KLineEntity
from app.services.bank_pb_service import BankPBService

# ---------- assets_bank fake ----------

class FakeAssetsBankRepo:
    """只实现 BankPBService 用到的方法：find_all_by_security_code_order_by_report_date_asc。

    docs 按 (securityCode, reportDate) 过滤 + 按 reportDate 升序返回。
    """

    def __init__(self, docs: list[AssetsBankEntity]):
        self._docs = docs

    async def find_all_by_security_code_order_by_report_date_asc(self, security_code: str):
        rows = [d for d in self._docs if getattr(d, "securityCode", None) == security_code]
        rows.sort(key=lambda x: getattr(x, "reportDate", "") or "")
        return rows


# ---------- kline fake ----------

class FakeKLineService:
    """只实现 kline_by_sec_code。klines 存储为按 date 降序（与生产一致）。"""

    def __init__(self, klines_by_code: dict[str, list[KLineDataEntity]]):
        self._klines = klines_by_code

    async def kline_by_sec_code(self, sec_code: str, **kwargs) -> KLineEntity | None:
        klines = self._klines.get(sec_code)
        if not klines:
            return None
        return KLineEntity(code=sec_code, klines=klines)


class FakeSecCodeService:
    def __init__(self, entities: dict[str, Any]):
        self._entities = entities

    async def sec_code_entity_by_id(self, code: str):
        return self._entities.get(code)


def _assets(code: str, report_date: str, **bps_fields) -> AssetsBankEntity:
    """构造 AssetsBankEntity。AssetsBankEntity 只有 id / updatedAt 显式字段，
    其余通过 extra='allow' 透传。"""
    data = {"securityCode": code, "reportDate": report_date, **bps_fields}
    return AssetsBankEntity.model_validate(data)


def _kline(date: str, close: str) -> KLineDataEntity:
    return KLineDataEntity(date=date, close=close)


# ---------- 测试 ----------

async def test_basic_pb_calculation():
    """基础 case：BPS 与 close 都齐，PB = close / BPS。"""
    assets = [
        _assets("600036", "2024-09-30", bps="20.0"),
        _assets("600036", "2025-09-30", bps="25.0"),
    ]
    # klines 存储降序（最新在前）
    klines = [
        _kline("2025-09-30", "50.0"),
        _kline("2024-09-30", "40.0"),
    ]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert len(history) == 2
    assert history[0].reportDate == "2024-09-30"
    assert history[0].bps == 20.0
    assert history[0].close == 40.0
    assert history[0].pb == round(40.0 / 20.0, 4)
    assert history[0].bpsField == "bps"
    assert history[0].error is None
    assert history[1].reportDate == "2025-09-30"
    assert history[1].pb == round(50.0 / 25.0, 4)


async def test_bps_candidate_fallback():
    """BPS 字段不在首选名称时，按候选链找下一个。"""
    assets = [
        _assets("600036", "2025-09-30", PER_SHARE_NETASSET="30.0"),
    ]
    klines = [_kline("2025-09-30", "45.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].bps == 30.0
    assert history[0].bpsField == "PER_SHARE_NETASSET"
    assert history[0].pb == round(45.0 / 30.0, 4)


async def test_no_bps_field():
    """assets_bank 完全没 BPS 候选字段 → pb=null, error 含 '未找到每股净资产'。"""
    assets = [_assets("600036", "2025-09-30", foo="bar")]
    klines = [_kline("2025-09-30", "10.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].bps is None
    assert history[0].pb is None
    assert history[0].error is not None
    assert "未找到每股净资产" in history[0].error
    assert history[0].close == 10.0


async def test_no_kline():
    """无 kline → pb=null, error 含 '无 K 线数据'。"""
    assets = [_assets("600036", "2025-09-30", bps="20.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].pb is None
    assert "无 K 线数据" in history[0].error


async def test_no_bps_and_no_kline():
    """BPS 和 kline 都缺 → error 同时报告两项缺失。"""
    assets = [_assets("600036", "2025-09-30", other="x")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].pb is None
    assert history[0].error is not None
    assert "未找到每股净资产" in history[0].error
    assert "无 K 线数据" in history[0].error


async def test_bps_string_value():
    """BPS 以字符串形式存储也能正确解析。"""
    assets = [_assets("600036", "2025-09-30", bps="20.5")]
    klines = [_kline("2025-09-30", "41.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].bps == 20.5
    assert history[0].pb == 2.0


async def test_close_on_or_after_report_date():
    """close 必须在 reportDate 当天或之后。"""
    assets = [_assets("600036", "2025-09-30", bps="20.0")]
    # 2025-10-01 比 reportDate 晚一天，应被采纳
    klines = [
        _kline("2025-10-01", "22.0"),
        _kline("2025-09-29", "19.0"),
    ]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].close == 22.0
    assert history[0].date == "2025-10-01"
    assert history[0].pb == round(22.0 / 20.0, 4)


async def test_calculate_pb_returns_latest():
    """calculate_pb 单点 = history 末项（reportDate 最大者）。"""
    assets = [
        _assets("600036", "2024-09-30", bps="20.0"),
        _assets("600036", "2025-09-30", bps="25.0"),
    ]
    klines = [_kline("2025-09-30", "50.0"), _kline("2024-09-30", "40.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    pb = await svc.calculate_pb("600036")
    assert pb.pb == round(50.0 / 25.0, 4)
    assert pb.reportDate == "2025-09-30"


async def test_empty_assets_list():
    """assets_bank 无数据 → 返回空列表；calculate_pb 返 error。"""
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo([]),
        kline_service=FakeKLineService({}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history == []
    pb = await svc.calculate_pb("600036")
    assert pb.pb is None
    assert pb.error == "无报表数据"


async def test_bps_zero_divisor_guard():
    """BPS=0 时不应抛 ZeroDivisionError，应返回 pb=null + 显式 error。"""
    assets = [_assets("600036", "2025-09-30", bps="0")]
    klines = [_kline("2025-09-30", "10.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].bps == 0.0
    assert history[0].pb is None
    assert history[0].error is not None
    assert "每股净资产为 0" in history[0].error


async def test_derive_bps_from_total_parent_equity_and_share_capital():
    """assets_bank 无 BPS 字段时，回退用 totalParentEquity / shareCapital 计算 BPS。

    模拟东财银行资产负债表真实字段（招商银行 2025-Q1）：
      shareCapital (元) = 总股本(股)（银行面值 1元）
      totalParentEquity (元) = 归母净资产
    """
    # 招商银行 2025-Q1 简化: 25.22 亿股, 归母 12462 亿元
    assets = [
        _assets(
            "600036",
            "2025-03-31",
            totalParentEquity="1246207000000",
            shareCapital="25220000000",
        )
    ]
    klines = [_kline("2025-04-01", "45.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    expected_bps = 1246207000000 / 25220000000  # ≈ 49.41
    assert history[0].bps is not None
    assert abs(history[0].bps - expected_bps) < 0.01
    assert history[0].bpsField == "totalParentEquity/shareCapital"
    assert history[0].pb is not None
    assert abs(history[0].pb - 45.0 / expected_bps) < 0.01
    assert history[0].error is None


async def test_derive_bps_missing_share_capital():
    """回退路径：totalParentEquity 在但 shareCapital 缺失 → bps 仍 null。"""
    assets = [
        _assets(
            "600036",
            "2025-03-31",
            totalParentEquity="1246207000000",
        )
    ]
    klines = [_kline("2025-04-01", "45.0")]
    svc = BankPBService(
        assets_bank_repo=FakeAssetsBankRepo(assets),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pb_history("600036")
    assert history[0].bps is None
    assert history[0].pb is None
    assert history[0].error is not None
    assert "未找到每股净资产" in history[0].error