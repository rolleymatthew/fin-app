"""回归测试：finance_utils.cost() / gross_profit() 对 V2 接口数据兼容。

背景：
2026-05-18 提交 ``3ff06f9`` ``add fin http V2`` 引入
``FinanceEastmoneyV2Client``（默认开启 ``use_finance_eastmoney_v2 = True``）。
新接口 ``datacenter.eastmoney.com`` 的 ``sty=APP_F10_GINCOME`` 对
保险（orgTypeCode="2"）/ 银行（"3"）/ 债券（"1"）类型公司 **不再返回
``OPERATE_EXPENSE`` 字段**，对应数据被改放在 ``TOTAL_OPERATE_COST``。

老接口 ``lrbAjaxNew`` 数据：``operateExpense`` 有值。
新接口数据：``operateExpense = None``、``totalOperateCost`` 有值。

``cost()`` 在 ``operateExpense`` 为 None 时必须退回 ``totalOperateCost``，
否则 ``gross_profit()`` 退化为 (income - 0) / income * 100 = 100%。
"""

from types import SimpleNamespace

from app.utils import finance_utils


def _profit(**kwargs):
    """构造一个利润表 entity（只需用到的字段）。"""
    return SimpleNamespace(**kwargs)


def _entity(org_type_code):
    return SimpleNamespace(orgTypeCode=org_type_code)


# ---------- cost() fallback ----------

def test_cost_insurance_falls_back_to_total_operate_cost_when_operate_expense_missing():
    """保险类（orgTypeCode="2"）：V2 接口无 operateExpense，应退回 totalOperateCost。"""
    profit = _profit(totalOperateCost="651062000000")
    entity = _entity("2")
    assert finance_utils.cost(profit, entity) == 651062000000 / 10000


def test_cost_bank_falls_back_to_total_operate_cost_when_operate_expense_missing():
    """银行类（orgTypeCode="3"）：同上。"""
    profit = _profit(totalOperateCost="321518000000")
    entity = _entity("3")
    assert finance_utils.cost(profit, entity) == 321518000000 / 10000


def test_cost_bond_falls_back_to_total_operate_cost_when_operate_expense_missing():
    """债券类（orgTypeCode="1"）：同上。"""
    profit = _profit(totalOperateCost="123456000000")
    entity = _entity("1")
    assert finance_utils.cost(profit, entity) == 123456000000 / 10000


def test_cost_prefers_operate_expense_when_present():
    """老接口数据：operateExpense 有值时，必须使用它，不退回 totalOperateCost。"""
    profit = _profit(
        operateExpense="651062000000",
        totalOperateCost="999999999999",
    )
    entity = _entity("2")
    assert finance_utils.cost(profit, entity) == 651062000000 / 10000


def test_cost_zero_when_both_fields_missing():
    """operateExpense 与 totalOperateCost 都缺失时，回归到原行为 0.0。"""
    profit = _profit()
    entity = _entity("2")
    assert finance_utils.cost(profit, entity) == 0.0


def test_cost_universal_uses_operate_cost_unaffected():
    """普通股（orgTypeCode="4"）：走非 finance 分支，使用 operateCost。"""
    profit = _profit(operateCost="215732040946", totalOperateCost="223993082756")
    entity = _entity("4")
    assert finance_utils.cost(profit, entity) == 215732040946 / 10000


# ---------- gross_profit() end-to-end ----------

def test_gross_profit_insurance_v2_data_not_100_percent():
    """回归：601318 中国平安 V2 数据（无 operateExpense）下，gross_profit 不再恒为 100%。

    2025-09-30 数据：
      OPERATE_INCOME     = 832940000000
      TOTAL_OPERATE_COST = 651062000000
      期望 (832940 - 651062) / 832940 * 100 ≈ 21.85%
    """
    profit = _profit(
        operateIncome="832940000000",
        totalOperateCost="651062000000",
    )
    entity = _entity("2")
    result = finance_utils.gross_profit(profit, entity)
    # 老接口历史值约 21.85%；断言区间 (10, 30) 即可，不锁死
    assert 10 < result < 30, f"毛利率异常: {result}"