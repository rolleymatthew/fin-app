from __future__ import annotations

from app.constants.cash_flow_type import CashFlowTypeEnum
from app.models.entities import CashFlowScoreEntity
from app.utils import num_utils


def to_entity(cash_flow_entity) -> CashFlowScoreEntity:
    e = CashFlowScoreEntity()
    e.date = str(cash_flow_entity.id).replace(cash_flow_entity.securityCode, "") if cash_flow_entity.id else None
    e.securityCode = cash_flow_entity.securityCode
    e.securityNameAbbr = cash_flow_entity.securityNameAbbr
    e.netCashFlowFromOperatingActivities = str(num_utils.round_double(num_utils.string_to_double(cash_flow_entity.netcashOperate) / 10000 / 10000))
    e.netCashFlowFromInvestmentActivities = str(num_utils.round_double(num_utils.string_to_double(cash_flow_entity.netcashInvest) / 10000 / 10000))
    e.netCashFlowFromFinancingActivities = str(num_utils.round_double(num_utils.string_to_double(cash_flow_entity.netcashFinance) / 10000 / 10000))
    t = CashFlowTypeEnum.cash_flow_type(cash_flow_entity.netcashOperate, cash_flow_entity.netcashInvest, cash_flow_entity.netcashFinance)
    e.type = CashFlowTypeEnum.type_name(t)
    e.properties = CashFlowTypeEnum.remark_name(t)
    return e
