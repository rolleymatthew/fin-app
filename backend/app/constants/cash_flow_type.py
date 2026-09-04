from __future__ import annotations

from typing import List

from app.utils.num_utils import double_compare_zero, string_to_double


class CashFlowTypeEnum:
    YAOJING = (1, "妖精型", "关注投资项目情况")
    LAOMUJI = (2, "老母鸡性", "低PE高股息率")
    MANNIU = (3, "蛮牛型", "项目前景，资金支持")
    NAINIU = (4, "奶牛型", "可持续性")
    PIANCHIPIANHE = (5, "骗吃骗喝型", "不建议投资")
    HUICHIDENGSI = (6, "混吃等死型", "不建议投资")
    DUTU = (7, "赌徒型", "项目前景与管理层品行")
    DACHUXUE = (8, "大出血型", "拒绝参与")

    @staticmethod
    def type_name(type_value: int) -> str | None:
        for t, name, _ in CashFlowTypeEnum._values():
            if t == type_value:
                return name
        return None

    @staticmethod
    def remark_name(type_value: int) -> str | None:
        for t, _, remark in CashFlowTypeEnum._values():
            if t == type_value:
                return remark
        return None

    @staticmethod
    def cash_flow_type(operate: str, invest: str, finance: str) -> int:
        o = double_compare_zero(string_to_double(operate))
        i = double_compare_zero(string_to_double(invest))
        f = double_compare_zero(string_to_double(finance))
        if o and i and f:
            return 1
        if o and i and not f:
            return 2
        if o and not i and f:
            return 3
        if o and not i and not f:
            return 4
        if not o and i and f:
            return 5
        if not o and i and not f:
            return 6
        if not o and not i and f:
            return 7
        if not o and not i and not f:
            return 8
        return 0

    @staticmethod
    def _values() -> List[tuple[int, str, str]]:
        return [
            CashFlowTypeEnum.YAOJING,
            CashFlowTypeEnum.LAOMUJI,
            CashFlowTypeEnum.MANNIU,
            CashFlowTypeEnum.NAINIU,
            CashFlowTypeEnum.PIANCHIPIANHE,
            CashFlowTypeEnum.HUICHIDENGSI,
            CashFlowTypeEnum.DUTU,
            CashFlowTypeEnum.DACHUXUE,
        ]
