from __future__ import annotations

from typing import List

from app.models.entities import ZqhFinEntity
from app.utils import finance_utils, num_utils


def creat_for_universal(profit_list: List, cash_flow_list: List, assets_list: List, roe_list: List, sec_code_entity):
    result = []
    for s in profit_list:
        z = ZqhFinEntity()
        z.reportDate = s.reportDate
        z.operatingIncome = num_utils.round_double(finance_utils.income(s, sec_code_entity) / 10000)
        z.revenueGrowthRate = num_utils.round_double(num_utils.string_to_double(getattr(s, "totalOperateIncomeYoy", None)))
        z.netProfit = num_utils.round_double(num_utils.string_to_double(getattr(s, "parentNetprofit", None)) / 10000 / 10000)
        z.netProfitGrowthRate = num_utils.round_double(num_utils.string_to_double(getattr(s, "parentNetprofitYoy", None)))
        z.operatingGrossProfitMargin = finance_utils.gross_profit(s, sec_code_entity)
        z.netInterestRate = finance_utils.net_profit(s, sec_code_entity)
        z.operatingProfitMargin = finance_utils.operat_profit(s, sec_code_entity)
        z.returnOnNetAssets = finance_utils.return_on_net_assets(s.reportDate, roe_list)
        z.netOperatingCashFlow = finance_utils.cash_flow(s, cash_flow_list)
        z.lAndLiabRatioww = finance_utils.deb_ratio(s, assets_list)
        result.append(z)
    return result


def creats_for_bond(profit_list: List, cash_flow_list: List, roe_list: List, sec_code_entity):
    result = []
    for s in profit_list:
        z = ZqhFinEntity()
        z.reportDate = s.reportDate
        z.operatingIncome = num_utils.round_double(finance_utils.income(s, sec_code_entity) / 10000)
        z.revenueGrowthRate = num_utils.round_double(num_utils.string_to_double(getattr(s, "operateIncomeYoy", None)))
        z.netProfit = num_utils.round_double(num_utils.string_to_double(getattr(s, "netprofit", None)) / 10000 / 10000)
        z.netProfitGrowthRate = num_utils.round_double(num_utils.string_to_double(getattr(s, "netprofitYoy", None)))
        z.operatingGrossProfitMargin = finance_utils.gross_profit(s, sec_code_entity)
        z.netInterestRate = finance_utils.net_profit(s, sec_code_entity)
        z.operatingProfitMargin = finance_utils.operat_profit(s, sec_code_entity)
        z.returnOnNetAssets = finance_utils.return_on_net_assets(s.reportDate, roe_list)
        z.netOperatingCashFlow = finance_utils.cash_flow(s, cash_flow_list)
        z.lAndLiabRatioww = 0
        result.append(z)
    return result


def creats_for_bank(profit_list: List, cash_flow_list: List, roe_list: List, sec_code_entity):
    return creats_for_bond(profit_list, cash_flow_list, roe_list, sec_code_entity)


def creats_for_insurance(profit_list: List, cash_flow_list: List, roe_list: List, sec_code_entity):
    return creats_for_bond(profit_list, cash_flow_list, roe_list, sec_code_entity)
