from __future__ import annotations

from typing import List, Dict, Any
from decimal import Decimal, ROUND_HALF_UP

from app.utils import class_util, date_utils
from app.constants.report_date_type import latest_quarter_by_year_date


class AnalysisEntityMapper:
    def get_strings_list(self, temp: str) -> List[List[str]]:
        lines = temp.split("\r\n")
        return [l.strip().split(",") for l in lines if len(l) > 10]

    def get_headers(self, collect: List[List[str]]) -> List[str]:
        col = [s[0] for s in collect if len(s) >= 2]
        return [s for s in col if s]

    def get_column_len(self, collect: List[List[str]]) -> int:
        return len(collect[0]) if collect else 0

    def fill_strings_array(self, collect: List[List[str]]) -> List[List[str]]:
        column_len = self.get_column_len(collect)
        line_len = len(collect)
        org_data = [["" for _ in range(column_len)] for _ in range(line_len)]
        for i, split in enumerate(collect):
            for j in range(1, column_len):
                org_data[i][j - 1] = split[j]
        return org_data

    def line_to_columns_array(self, org_data: List[List[str]], collect: List[List[str]]) -> List[List[str]]:
        line_len = len(self.get_headers(collect))
        column_len = self.get_column_len(collect)
        new_data = [["" for _ in range(line_len)] for _ in range(column_len)]
        for i in range(line_len):
            for j in range(column_len):
                new_data[j][i] = org_data[i][j]
        return new_data

    def get_array_dates(self, temp: str) -> List[List[str]] | None:
        collect = self.get_strings_list(temp)
        if not collect:
            return None
        org_data = self.fill_strings_array(collect)
        return self.line_to_columns_array(org_data, collect)

    def convert_string_to_beans(self, temp: str, dic_map: Dict[str, str], cls: type) -> List[Any] | None:
        collect = self.get_strings_list(temp)
        if not collect:
            return None
        header = self.get_headers(collect)
        if not header:
            return None
        new_data = self.get_array_dates(temp)
        if new_data is None:
            return None
        ret: List[Any] = []
        column_len = self.get_column_len(collect)
        for line in range(column_len):
            obj = cls()
            for col, head in enumerate(header):
                field = dic_map.get(head.strip())
                if field:
                    class_util.set_field_value_by_field_name(obj, field.strip(), new_data[line][col])
            ret.append(obj)
        return ret

    def eps_date_by_year(self, profit_dtos: List[Any], report_date) -> Any:
        items = profit_dtos[0]
        for s in items:
            if date_utils.equalse_date(date_utils.format_full_date_with_slip(str(class_util.get_field_value_by_name("reportDate", s))), report_date):
                eps = Decimal(str(class_util.get_field_value_by_name("basicEps", s) or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return {"date": report_date, "eps": eps}
        return None

    def eps_quarter(self, object_list: List[Any], report_date) -> Any:
        items = object_list[0]
        for i in range(len(items) - 1):
            obj = items[i]
            obj_1 = items[i + 1]
            _report_date = str(class_util.get_field_value_by_name("reportDate", obj) or "0")
            _basic_eps = str(class_util.get_field_value_by_name("basicEps", obj) or "0")
            _basic_eps_latest = str(class_util.get_field_value_by_name("basicEps", obj_1) or "0")
            if date_utils.equalse_date(date_utils.format_full_date_with_slip(_report_date), report_date):
                if "03-31" in _report_date:
                    v = Decimal(_basic_eps)
                else:
                    v = Decimal(_basic_eps) - Decimal(_basic_eps_latest)
                return {"date": report_date, "eps": v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)}
        return None

    def eps_quarter_split_year(self, profit_dtos: List[Any], report_date: str, sec_code: str):
        items = profit_dtos[0]
        strings = latest_quarter_by_year_date(report_date)
        if not strings:
            return None
        collect = []
        for s in strings:
            found = next((p for p in items if str(class_util.get_field_value_by_name("id", p)) == f"{sec_code}{s}"), None)
            collect.append(found)
        if len([c for c in collect if c is not None]) != 5:
            return None
        total = Decimal(0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for i in range(len(collect) - 1):
            profit = collect[i]
            profit_1 = collect[i + 1]
            if "03-31" in str(class_util.get_field_value_by_name("reportDate", profit)):
                v = Decimal(str(class_util.get_field_value_by_name("basicEps", profit) or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                v = Decimal(str(class_util.get_field_value_by_name("basicEps", profit) or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) - Decimal(str(class_util.get_field_value_by_name("basicEps", profit_1) or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += v
        return {"date": date_utils.format_date_with_slip(report_date), "eps": total}
