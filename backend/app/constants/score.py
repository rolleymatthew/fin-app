from __future__ import annotations


def _include_start(value: float | None, ranges: list[tuple[float, float, int]]) -> int:
    if value is None:
        return 0
    score = 0
    for start, end, s in ranges:
        if (start <= value <= end) or value == start:
            score = s
    return score


def _include_end(value: float | None, ranges: list[tuple[float, float, int]]) -> int:
    if value is None:
        return 0
    score = 0
    for start, end, s in ranges:
        if (start <= value <= end) or value == end:
            score = s
    return score


def _include_start_str(value: float | None, ranges: list[tuple[float, float, int]], total: int) -> str:
    if value is None:
        return f"0/{total}"
    return f"{_include_start(value, ranges)}/{total}"


class GrossProfitScore:
    _ranges = [(0.0, 20.0, 3), (20.0, 30.0, 6), (30.0, 40.0, 9), (40.0, 50.0, 12), (50.0, 999999.0, 15)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, GrossProfitScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, GrossProfitScore._ranges, 15)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, GrossProfitScore._ranges)


class GrossProfitBankScore:
    _ranges = [(0.0, 20.0, 6), (20.0, 30.0, 9), (30.0, 40.0, 10), (40.0, 50.0, 12), (50.0, 999999.0, 15)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, GrossProfitBankScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, GrossProfitBankScore._ranges, 15)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, GrossProfitBankScore._ranges)


class OperateProfitScore:
    _ranges = [(0.0, 5.0, 3), (5.0, 10.0, 6), (10.0, 20.0, 9), (20.0, 40.0, 12), (40.0, 99999999.0, 15)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, OperateProfitScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, OperateProfitScore._ranges, 15)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, OperateProfitScore._ranges)


class OperateProfitBankScore:
    _ranges = [(0.0, 20.0, 6), (20.0, 30.0, 9), (30.0, 40.0, 10), (40.0, 50.0, 12), (50.0, 99999999.0, 15)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, OperateProfitBankScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, OperateProfitBankScore._ranges, 15)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, OperateProfitBankScore._ranges)


class NetProfitScore:
    _ranges = [(0.0, 5.0, 3), (5.0, 10.0, 6), (10.0, 15.0, 9), (15.0, 30.0, 12), (30.0, 99999999.0, 15)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, NetProfitScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, NetProfitScore._ranges, 15)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, NetProfitScore._ranges)


class NetProfitBankScore:
    _ranges = [(0.0, 5.0, 3), (5.0, 10.0, 5), (10.0, 15.0, 10), (15.0, 40.0, 15), (40.0, 99999999.0, 20)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, NetProfitBankScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, NetProfitBankScore._ranges, 20)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, NetProfitBankScore._ranges)


class NetAssetsWeightScore:
    _ranges = [(0.0, 3.0, 3), (3.0, 6.0, 6), (6.0, 10.0, 9), (10.0, 15.0, 12), (15.0, 99999999.0, 15)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, NetAssetsWeightScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, NetAssetsWeightScore._ranges, 15)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, NetAssetsWeightScore._ranges)


class NetAssetsWeightBankScore:
    _ranges = [(0.0, 10.0, 20), (10.0, 15.0, 25), (15.0, 20.0, 30), (20.0, 30.0, 35), (30.0, 99999999.0, 40)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, NetAssetsWeightBankScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, NetAssetsWeightBankScore._ranges, 20)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, NetAssetsWeightBankScore._ranges)


class LiabilScore:
    _ranges = [(0.0, 20.0, 5), (20.0, 40.0, 4), (40.0, 60.0, 3), (60.0, 90.0, 2), (90.0, 99999999.0, 1)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, LiabilScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, LiabilScore._ranges, 5)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, LiabilScore._ranges)


class AssetsScore:
    _ranges = [(10.0, 20.0, 1), (20.0, 40.0, 2), (40.0, 60.0, 3), (60.0, 90.0, 4), (90.0, 99999999.0, 5)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, AssetsScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, AssetsScore._ranges, 5)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, AssetsScore._ranges)


class StockScore:
    _ranges = [(0.0, 0.5, 2), (0.5, 1.0, 4), (1.0, 1.5, 6), (1.5, 2.0, 8), (2.0, 99999999.0, 10)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, StockScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        if digits == 100.0:
            return "无存货满分"
        return _include_start_str(digits, StockScore._ranges, 10)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, StockScore._ranges)


class AccountsRecivableScore:
    _ranges = [(0.0, 4.0, 2), (4.0, 6.0, 4), (6.0, 8.0, 6), (8.0, 10.0, 8), (10.0, 99999999.0, 10)]

    @staticmethod
    def includeStart(digits: float) -> int:
        return _include_start(digits, AccountsRecivableScore._ranges)

    @staticmethod
    def includeStartString(digits: float) -> str:
        return _include_start_str(digits, AccountsRecivableScore._ranges, 10)

    @staticmethod
    def includeEnd(digits: float) -> int:
        return _include_end(digits, AccountsRecivableScore._ranges)


class CashFlowScore:
    @staticmethod
    def netCashFlowFromOperatingActivities(s: float | None) -> int:
        return 5 if s and s > 0 else 0

    @staticmethod
    def netCashFlowFromOperatingActivitiesString(s: float | None) -> str:
        return "5/5" if s and s > 0 else "0/5"

    @staticmethod
    def netCashFlowFromInvestmentActivities(s: float | None) -> int:
        return 3 if s and s < 0 else 0

    @staticmethod
    def netCashFlowFromInvestmentActivitiesString(s: float | None) -> str:
        return "3/3" if s and s < 0 else "0/3"

    @staticmethod
    def netCashFlowFromFinancingActivities(s: float | None) -> int:
        return 2 if s and s > 0 else 0

    @staticmethod
    def netCashFlowFromFinancingActivitiesString(s: float | None) -> str:
        return "2/2" if s and s > 0 else "0/2"


class ResultScore:
    _ranges = [(0, 50, "观望"), (50, 60, "中等"), (60, 100, "优等")]

    @staticmethod
    def includeStart(digits: int | None) -> str:
        if digits is None:
            return ""
        score = ""
        for start, end, s in ResultScore._ranges:
            if (start <= digits <= end) or digits == start:
                score = s
        return score

    @staticmethod
    def includeEnd(digits: int | None) -> str:
        if digits is None:
            return ""
        score = ""
        for start, end, s in ResultScore._ranges:
            if (start <= digits <= end) or digits == end:
                score = s
        return score
