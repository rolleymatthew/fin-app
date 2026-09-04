from __future__ import annotations

from decimal import Decimal
from typing import List

from app.utils import num_utils
from app.constants.org_type import UniversalTypeCode


def return_on_net_assets(report_date: str, roe_list: List) -> float:
    def _norm(v: str | None) -> str:
        if not v:
            return ""
        return v.replace(" 00:00:00", "")

    target = _norm(report_date)
    for roe in roe_list:
        roe_date = _norm(getattr(roe, "reportDate", None))
        if roe_date == target and getattr(roe, "roe", None) is not None:
            return roe.roe
    return 0.0


def deb_ratio(profit, assets_list: List) -> float:
    for assets in assets_list:
        if getattr(assets, "reportDate", None) == getattr(profit, "reportDate", None):
            total_current = num_utils.string_to_double(getattr(assets, "totalCurrentLiab", None))
            total_non_current = num_utils.string_to_double(getattr(assets, "totalNoncurrentLiab", None))
            if total_current == 0:
                return 0.0
            return num_utils.round_double(total_non_current / total_current * 100)
    return 0.0


def cash_flow(profit, cash_flow_list: List) -> float:
    for cf in cash_flow_list:
        if getattr(cf, "reportDate", None) == getattr(profit, "reportDate", None):
            return num_utils.round_double(num_utils.string_to_double(getattr(cf, "netcashOperate", None)) / 10000 / 10000)
    return 0.0


def net_cash_flow_from_operating_activities(cash_flow) -> float:
    return num_utils.round_double(num_utils.string_to_double(getattr(cash_flow, "netcashOperate", None)) / 10000)


def net_cash_flow_from_investment_activities(cash_flow) -> float:
    return num_utils.round_double(num_utils.string_to_double(getattr(cash_flow, "netcashInvest", None)) / 10000)


def net_cash_flow_from_financing_activities(cash_flow) -> float:
    return num_utils.round_double(num_utils.string_to_double(getattr(cash_flow, "netcashFinance", None)) / 10000)


def liabil_per(assets) -> float:
    total_assets = num_utils.string_to_double(getattr(assets, "totalAssets", None))
    if total_assets > 0:
        total_liab = num_utils.string_to_double(getattr(assets, "totalLiabilities", None))
        return float((Decimal(total_liab) * Decimal(100) / Decimal(total_assets)).quantize(Decimal("0.0001")))
    return 0.0


def assets_per(assets) -> float:
    total_assets = num_utils.string_to_double(getattr(assets, "totalAssets", None))
    if total_assets > 0:
        total_current = num_utils.string_to_double(getattr(assets, "totalCurrentAssets", None))
        return float((Decimal(total_current) * Decimal(100) / Decimal(total_assets)).quantize(Decimal("0.0001")))
    return 0.0


def stock_per(assets, profit, sec_code_entity) -> float:
    inventory = num_utils.string_to_double(getattr(assets, "inventory", None))
    if inventory > 0:
        return float((Decimal(cost(profit, sec_code_entity)) * Decimal(100) / Decimal(inventory)).quantize(Decimal("0.0001")))
    return 100.0


def accounts_receivable_per(assets, profit, sec_code_entity) -> float:
    rece = num_utils.string_to_double(getattr(assets, "noteAccountsRece", None))
    if rece > 0:
        return float((Decimal(income(profit, sec_code_entity)) * Decimal(100) / Decimal(rece)).quantize(Decimal("0.0001")))
    return 100.0


def operat_profit(profit, sec_code_entity) -> float:
    inc = income(profit, sec_code_entity)
    if inc == 0:
        return 0.0
    return num_utils.round_double((num_utils.string_to_double(getattr(profit, "operateProfit", None)) / 10000) / inc * 100)


def gross_profit(profit, sec_code_entity) -> float:
    inc = income(profit, sec_code_entity)
    if inc == 0:
        return 0.0
    return num_utils.round_double((inc - cost(profit, sec_code_entity)) / inc * 100)


def cost(profit, sec_code_entity) -> float:
    if getattr(sec_code_entity, "orgTypeCode", None) in ["1", "2", "3"]:
        if getattr(profit, "operateExpense", None) is not None:
            return num_utils.string_to_double(getattr(profit, "operateExpense", None)) / 10000
        # V2 接口（datacenter.eastmoney.com APP_F10_GINCOME）对保险/银行/债券
        # 不返回 OPERATE_EXPENSE 字段，营业总成本放在 TOTAL_OPERATE_COST。
        total_op_cost = getattr(profit, "totalOperateCost", None)
        if total_op_cost is not None:
            return num_utils.string_to_double(total_op_cost) / 10000
        return 0.0
    return num_utils.string_to_double(getattr(profit, "operateCost", None)) / 10000


def net_profit(profit, sec_code_entity) -> float:
    inc = income(profit, sec_code_entity)
    if inc == 0:
        return 0.0
    if getattr(sec_code_entity, "orgTypeCode", None) in ["1", "2", "3"]:
        return num_utils.round_double((num_utils.string_to_double(getattr(profit, "netprofit", None)) / 10000) / inc * 100)
    if num_utils.string_to_double(getattr(profit, "continuedNetprofit", None)) != 0:
        return num_utils.round_double((num_utils.string_to_double(getattr(profit, "continuedNetprofit", None)) / 10000) / inc * 100)
    if num_utils.string_to_double(getattr(profit, "totalCompreIncome", None)) != 0:
        return num_utils.round_double((num_utils.string_to_double(getattr(profit, "totalCompreIncome", None)) / 10000) / inc * 100)
    return num_utils.round_double((num_utils.string_to_double(getattr(profit, "parentNetprofit", None)) / 10000) / inc * 100)


def income(profit, sec_code_entity) -> float:
    if getattr(sec_code_entity, "orgTypeCode", None) in ["1", "2", "3"]:
        return num_utils.string_to_double(getattr(profit, "operateIncome", None)) / 10000.0
    return num_utils.string_to_double(getattr(profit, "totalOperateIncome", None)) / 10000.0


def free_cash_flow(cash_flow) -> float:
    oper = num_utils.string_to_double(getattr(cash_flow, "netcashOperate", None))
    capex = num_utils.string_to_double(getattr(cash_flow, "constructLongAsset", None))
    return num_utils.round_double((oper - capex) / 10000 / 10000)


def null_st(sec_code_entity) -> bool:
    if sec_code_entity is None:
        return False
    if getattr(sec_code_entity, "listingState", None) != "0":
        return False
    name = getattr(sec_code_entity, "securityNameAbbr", "") or ""
    if "ST" in name or "*ST" in name or "退" in name:
        return False
    return True
