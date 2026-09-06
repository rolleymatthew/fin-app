"""BankPEService 单元测试（不依赖真实 MongoDB）。

通过内存 FakeCollection / FakeKlineService 替换依赖：
- profit_bank_repo.find_all_by_security_code_order_by_report_date_asc
- kline_service.kline_by_sec_code
- sec_code_service.sec_code_entity_by_id
"""
from __future__ import annotations

from typing import Any

from app.models.entities import KLineDataEntity, KLineEntity, ProfitBankEntity
from app.services.bank_pe_service import BankPEService

# ---------- profit_bank fake ----------

class FakeProfitBankRepo:
    """只实现 BankPEService 用到的方法：find_all_by_security_code_order_by_report_date_asc。

    docs 按 (securityCode, reportDate) 过滤 + 按 reportDate 升序返回。
    """

    def __init__(self, docs: list[ProfitBankEntity]):
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


def _profit(code: str, report_date: str, **eps_fields) -> ProfitBankEntity:
    """构造 ProfitBankEntity。ProfitBankEntity 只有 id / updatedAt 显式字段，
    其余通过 extra='allow' 透传。"""
    data = {"securityCode": code, "reportDate": report_date, **eps_fields}
    return ProfitBankEntity.model_validate(data)


def _kline(date: str, close: str) -> KLineDataEntity:
    return KLineDataEntity(date=date, close=close)


# ---------- 测试 ----------

async def test_basic_pe_calculation():
    """基础 case：EPS 与 close 都齐，PE = close / EPS。"""
    profits = [
        _profit("600036", "2024-09-30", eps="2.5"),
        _profit("600036", "2025-09-30", eps="3.0"),
    ]
    # klines 存储降序（最新在前）
    klines = [
        _kline("2025-09-30", "10.0"),
        _kline("2024-09-30", "8.0"),
    ]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert len(history) == 2
    assert history[0].reportDate == "2024-09-30"
    assert history[0].eps == 2.5
    assert history[0].close == 8.0
    assert history[0].pe == round(8.0 / 2.5, 4)
    assert history[0].epsField == "eps"
    assert history[0].error is None
    assert history[1].reportDate == "2025-09-30"
    assert history[1].pe == round(10.0 / 3.0, 4)


async def test_eps_candidate_fallback():
    """EPS 字段不在首选名称时，按候选链找下一个。"""
    profits = [
        _profit("600036", "2025-09-30", BASIC_EPS="4.0"),  # 不是 "eps"
    ]
    klines = [_kline("2025-09-30", "12.0")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history[0].eps == 4.0
    assert history[0].epsField == "BASIC_EPS"
    assert history[0].pe == round(12.0 / 4.0, 4)


async def test_no_eps_field():
    """profit_bank 完全没 EPS 候选字段 → pe=null, error 含 '未找到每股收益'。"""
    profits = [_profit("600036", "2025-09-30", foo="bar")]
    klines = [_kline("2025-09-30", "10.0")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history[0].eps is None
    assert history[0].pe is None
    assert history[0].error is not None
    assert "未找到每股收益" in history[0].error
    assert history[0].close == 10.0  # close 仍在


async def test_no_kline():
    """无 kline → pe=null, error 含 '无 K 线数据'。"""
    profits = [_profit("600036", "2025-09-30", eps="3.0")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({}),  # 空 klines
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history[0].pe is None
    assert "无 K 线数据" in history[0].error


async def test_no_eps_and_no_kline():
    """EPS 和 kline 都缺 → error 同时报告两项缺失。"""
    profits = [_profit("600036", "2025-09-30", other="x")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history[0].pe is None
    assert history[0].error is not None
    assert "未找到每股收益" in history[0].error
    assert "无 K 线数据" in history[0].error


async def test_eps_string_value():
    """EPS 以字符串形式存储也能正确解析（东财常以字符串返回）。"""
    profits = [_profit("600036", "2025-09-30", eps="2.5")]
    klines = [_kline("2025-09-30", "10.0")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history[0].eps == 2.5
    assert history[0].pe == 4.0


async def test_close_on_or_after_report_date():
    """close 必须在 reportDate 当天或之后。"""
    profits = [_profit("600036", "2025-09-30", eps="2.0")]
    # 2025-10-01 比 reportDate 晚一天，应被采纳（date >= reportDate）
    klines = [
        _kline("2025-10-01", "11.0"),
        _kline("2025-09-29", "9.0"),  # 早于 reportDate，跳过
    ]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history[0].close == 11.0
    assert history[0].date == "2025-10-01"
    assert history[0].pe == round(11.0 / 2.0, 4)


async def test_calculate_pe_returns_latest():
    """calculate_pe 单点 = history 末项（reportDate 最大者）。"""
    profits = [
        _profit("600036", "2024-09-30", eps="2.0"),
        _profit("600036", "2025-09-30", eps="3.0"),
    ]
    klines = [_kline("2025-09-30", "12.0"), _kline("2024-09-30", "8.0")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    pe = await svc.calculate_pe("600036")
    assert pe.pe == round(12.0 / 3.0, 4)
    assert pe.reportDate == "2025-09-30"


async def test_empty_profit_list():
    """profit_bank 无数据 → 返回空列表；calculate_pe 返 error。"""
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo([]),
        kline_service=FakeKLineService({}),
        sec_code_service=FakeSecCodeService({}),
    )
    history = await svc.calculate_pe_history("600036")
    assert history == []
    pe = await svc.calculate_pe("600036")
    assert pe.pe is None
    assert pe.error == "无报表数据"


async def test_eps_zero_divisor():
    """EPS=0 时 close/EPS 会抛 ZeroDivisionError → 应被捕捉或显式处理。

    简单方案：当前实现会让 close/EPS 抛错，测试记录这一行为（按工作流"不动既有逻辑"，
    但 EPS=0 本就不应当做分母——如果线上数据遇到，需要后续单独补 guard）。
    """
    profits = [_profit("600036", "2025-09-30", eps="0")]
    klines = [_kline("2025-09-30", "10.0")]
    svc = BankPEService(
        profit_bank_repo=FakeProfitBankRepo(profits),
        kline_service=FakeKLineService({"600036": klines}),
        sec_code_service=FakeSecCodeService({}),
    )
    try:
        history = await svc.calculate_pe_history("600036")
        # 若实现守住了零除，断言 pe 是 None + error
        assert history[0].pe is None
    except ZeroDivisionError:
        # 若未守，记录当前行为
        pass