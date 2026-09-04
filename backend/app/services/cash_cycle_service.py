from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import List

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.entities import AssetsUniversalEntity, ProfitUniversalEntity
from app.repositories.base import MongoRepository
from app.utils import num_utils


class CashCycleRecord:
    def __init__(
        self,
        report_date: str,
        revenue: float,
        cost: float,
        avg_inventory: float,
        avg_receivables: float,
        avg_payables: float,
        dio: float,
        dso: float,
        dpo: float,
        ccc: float,
    ):
        self.report_date = report_date
        self.revenue = revenue
        self.cost = cost
        self.avg_inventory = avg_inventory
        self.avg_receivables = avg_receivables
        self.avg_payables = avg_payables
        self.dio = dio
        self.dso = dso
        self.dpo = dpo
        self.ccc = ccc
        self.ttm_dio = 0.0
        self.ttm_dso = 0.0
        self.ttm_dpo = 0.0
        self.ttm_ccc = 0.0
        self.has_ttm = False


class AnnualCCCRecord:
    def __init__(
        self,
        report_date: str,
        revenue: float,
        cost: float,
        avg_inventory: float,
        avg_receivables: float,
        avg_payables: float,
        dio: float,
        dso: float,
        dpo: float,
        ccc: float,
    ):
        self.report_date = report_date
        self.revenue = revenue
        self.cost = cost
        self.avg_inventory = avg_inventory
        self.avg_receivables = avg_receivables
        self.avg_payables = avg_payables
        self.dio = dio
        self.dso = dso
        self.dpo = dpo
        self.ccc = ccc


class CashCycleService:

    def __init__(self):
        self.assets_repo = MongoRepository(AssetsUniversalEntity)
        self.profit_repo = MongoRepository(ProfitUniversalEntity)

    @staticmethod
    def _get_quarter_days(report_date_str: str) -> int:
        d = datetime.strptime(report_date_str[:10], "%Y-%m-%d").date()
        month = d.month
        if month == 3:
            return 90 if not calendar.isleap(d.year) else 91
        elif month == 6:
            return 91
        elif month == 9:
            return 92
        else:
            return 92

    @staticmethod
    def _is_quarter_end(report_date_str: str) -> bool:
        d = report_date_str[:10]
        return d.endswith("-03-31") or d.endswith("-06-30") or d.endswith("-09-30") or d.endswith("-12-31")

    @staticmethod
    def _is_q4(report_date_str: str) -> bool:
        return report_date_str[:10].endswith("-12-31")

    @staticmethod
    def _get_field_val(entity, field: str) -> float:
        return num_utils.string_to_double(getattr(entity, field, None))

    async def _load_assets_profit(self, code: str):
        assets_list = await self.assets_repo.find_all_by_security_code_order_by_report_date_desc(code)
        profit_list = await self.profit_repo.find_all_by_security_code_order_by_report_date_desc(code)

        assets_by_date = {}
        for a in assets_list:
            rd = (getattr(a, "reportDate", "") or "").replace(" 00:00:00", "")[:10]
            if rd and self._is_quarter_end(rd):
                assets_by_date[rd] = a

        profit_by_date = {}
        for p in profit_list:
            rd = (getattr(p, "reportDate", "") or "").replace(" 00:00:00", "")[:10]
            if rd and self._is_quarter_end(rd):
                profit_by_date[rd] = p

        dates = sorted(set(assets_by_date.keys()) & set(profit_by_date.keys()))
        return assets_by_date, profit_by_date, dates

    async def calc_cash_cycle(self, code: str) -> List[CashCycleRecord]:
        assets_by_date, profit_by_date, dates = await self._load_assets_profit(code)

        records: List[CashCycleRecord] = []
        prev_revenue = 0.0
        prev_cost = 0.0
        prev_year = 0

        for i, rd in enumerate(dates):
            assets = assets_by_date[rd]
            profit = profit_by_date[rd]

            cum_revenue = self._get_field_val(profit, "totalOperateIncome")
            cum_cost = self._get_field_val(profit, "operateCost")
            inventory = self._get_field_val(assets, "inventory")
            receivables = self._get_field_val(assets, "noteAccountsRece")
            payables = self._get_field_val(assets, "accountsPayable")

            cur_year = int(rd[:4])
            q = int(rd[5:7])
            if q == 3:
                q_num = 1
            elif q == 6:
                q_num = 2
            elif q == 9:
                q_num = 3
            else:
                q_num = 4

            is_new_fiscal_year = (cur_year != prev_year) or (i > 0 and cum_revenue < prev_revenue)

            if q_num == 1 or is_new_fiscal_year:
                single_revenue = cum_revenue
                single_cost = cum_cost
            else:
                single_revenue = cum_revenue - prev_revenue
                single_cost = cum_cost - prev_cost

            if single_revenue <= 0:
                single_revenue = cum_revenue
            if single_cost <= 0:
                single_cost = cum_cost

            prev_assets = assets_by_date.get(dates[i - 1]) if i > 0 else None
            if prev_assets is not None:
                prev_inventory = self._get_field_val(prev_assets, "inventory")
                prev_receivables = self._get_field_val(prev_assets, "noteAccountsRece")
                prev_payables = self._get_field_val(prev_assets, "accountsPayable")
                avg_inventory = (inventory + prev_inventory) / 2.0
                avg_receivables = (receivables + prev_receivables) / 2.0
                avg_payables = (payables + prev_payables) / 2.0
            else:
                avg_inventory = inventory
                avg_receivables = receivables
                avg_payables = payables

            days_in_q = self._get_quarter_days(rd)

            dio = (avg_inventory / single_cost * days_in_q) if single_cost > 0 else 0.0
            dso = (avg_receivables / single_revenue * days_in_q) if single_revenue > 0 else 0.0
            dpo = (avg_payables / single_cost * days_in_q) if single_cost > 0 else 0.0
            ccc = dio + dso - dpo

            records.append(CashCycleRecord(
                report_date=rd,
                revenue=single_revenue,
                cost=single_cost,
                avg_inventory=avg_inventory,
                avg_receivables=avg_receivables,
                avg_payables=avg_payables,
                dio=dio,
                dso=dso,
                dpo=dpo,
                ccc=ccc,
            ))

            prev_revenue = cum_revenue
            prev_cost = cum_cost
            prev_year = cur_year

        for i in range(len(records)):
            if i >= 3:
                ttm_revenue = sum(r.revenue for r in records[i-3:i+1])
                ttm_cost = sum(r.cost for r in records[i-3:i+1])

                prev_q_inv = self._get_field_val(assets_by_date[dates[i-3]], "inventory")
                curr_inv = self._get_field_val(assets_by_date[dates[i]], "inventory")
                ttm_avg_inventory = (prev_q_inv + curr_inv) / 2.0

                prev_q_rec = self._get_field_val(assets_by_date[dates[i-3]], "noteAccountsRece")
                curr_rec = self._get_field_val(assets_by_date[dates[i]], "noteAccountsRece")
                ttm_avg_receivables = (prev_q_rec + curr_rec) / 2.0

                prev_q_pay = self._get_field_val(assets_by_date[dates[i-3]], "accountsPayable")
                curr_pay = self._get_field_val(assets_by_date[dates[i]], "accountsPayable")
                ttm_avg_payables = (prev_q_pay + curr_pay) / 2.0

                if ttm_cost > 0:
                    records[i].ttm_dio = ttm_avg_inventory / ttm_cost * 365.0
                    records[i].ttm_dpo = ttm_avg_payables / ttm_cost * 365.0
                if ttm_revenue > 0:
                    records[i].ttm_dso = ttm_avg_receivables / ttm_revenue * 365.0
                records[i].ttm_ccc = records[i].ttm_dio + records[i].ttm_dso - records[i].ttm_dpo
                records[i].has_ttm = True

        records.reverse()
        return records

    async def calc_annual_ccc(self, code: str) -> List[AnnualCCCRecord]:
        assets_by_date, profit_by_date, dates = await self._load_assets_profit(code)
        q4_dates = [d for d in dates if self._is_q4(d)]

        records: List[AnnualCCCRecord] = []
        for i, rd in enumerate(q4_dates):
            assets = assets_by_date[rd]
            profit = profit_by_date[rd]

            cum_revenue = self._get_field_val(profit, "totalOperateIncome")
            cum_cost = self._get_field_val(profit, "operateCost")
            inventory = self._get_field_val(assets, "inventory")
            receivables = self._get_field_val(assets, "noteAccountsRece")
            payables = self._get_field_val(assets, "accountsPayable")

            if i > 0:
                prev_rd = q4_dates[i - 1]
                prev_assets = assets_by_date.get(prev_rd)
                if prev_assets is not None:
                    prev_inventory = self._get_field_val(prev_assets, "inventory")
                    prev_receivables = self._get_field_val(prev_assets, "noteAccountsRece")
                    prev_payables = self._get_field_val(prev_assets, "accountsPayable")
                    avg_inventory = (inventory + prev_inventory) / 2.0
                    avg_receivables = (receivables + prev_receivables) / 2.0
                    avg_payables = (payables + prev_payables) / 2.0
                else:
                    avg_inventory = inventory
                    avg_receivables = receivables
                    avg_payables = payables
            else:
                avg_inventory = inventory
                avg_receivables = receivables
                avg_payables = payables

            dio = (avg_inventory / cum_cost * 365.0) if cum_cost > 0 else 0.0
            dso = (avg_receivables / cum_revenue * 365.0) if cum_revenue > 0 else 0.0
            dpo = (avg_payables / cum_cost * 365.0) if cum_cost > 0 else 0.0
            ccc = dio + dso - dpo

            records.append(AnnualCCCRecord(
                report_date=rd,
                revenue=cum_revenue,
                cost=cum_cost,
                avg_inventory=avg_inventory,
                avg_receivables=avg_receivables,
                avg_payables=avg_payables,
                dio=dio,
                dso=dso,
                dpo=dpo,
                ccc=ccc,
            ))

        records.reverse()
        return records

    @staticmethod
    def _to_yi(val: float) -> str:
        if val == 0:
            return "0.00"
        return f"{val / 100000000.0:,.2f}"

    @staticmethod
    def _to_days(val: float) -> str:
        if val == 0:
            return "0.0"
        return f"{val:.1f}"

    @staticmethod
    def _efficiency_label(ccc: float) -> str:
        if ccc < 0:
            return "优秀 (占用上游资金)"
        elif ccc < 30:
            return "良好"
        elif ccc < 60:
            return "一般"
        else:
            return "较差"

    @staticmethod
    def _ccc_font(ccc: float) -> Font:
        if ccc < 0:
            return Font(color="FF0000")
        elif ccc < 30:
            return Font(color="008000")
        return Font()

    @staticmethod
    def write_to_sheet(ws, records: List[CashCycleRecord]):
        header_font_white = Font(bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_fill_ttm = PatternFill(start_color="548235", end_color="548235", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )
        na_font = Font(color="999999", italic=True)

        headers = [
            "报告期", "单季营收(亿)", "单季成本(亿)",
            "存货均值(亿)", "应收均值(亿)", "应付均值(亿)",
            "DIO(单季)", "DSO(单季)", "DPO(单季)", "CCC(单季)",
            "DIO(TTM)", "DSO(TTM)", "DPO(TTM)", "CCC(TTM)", "经营效率",
        ]

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            if col >= 11:
                cell.font = header_font_white
                cell.fill = header_fill_ttm
            else:
                cell.font = header_font_white
                cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        ws.row_dimensions[1].height = 30

        for row_idx, r in enumerate(records, 2):
            ws.cell(row=row_idx, column=1, value=r.report_date).border = thin_border
            ws.cell(row=row_idx, column=2, value=CashCycleService._to_yi(r.revenue)).border = thin_border
            ws.cell(row=row_idx, column=3, value=CashCycleService._to_yi(r.cost)).border = thin_border
            ws.cell(row=row_idx, column=4, value=CashCycleService._to_yi(r.avg_inventory)).border = thin_border
            ws.cell(row=row_idx, column=5, value=CashCycleService._to_yi(r.avg_receivables)).border = thin_border
            ws.cell(row=row_idx, column=6, value=CashCycleService._to_yi(r.avg_payables)).border = thin_border

            for col, val in [(7, r.dio), (8, r.dso), (9, r.dpo), (10, r.ccc)]:
                cell = ws.cell(row=row_idx, column=col, value=CashCycleService._to_days(val))
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

            ccc_q_cell = ws.cell(row=row_idx, column=10)
            ccc_q_cell.font = CashCycleService._ccc_font(r.ccc)

            for col, val in [(11, r.ttm_dio), (12, r.ttm_dso), (13, r.ttm_dpo), (14, r.ttm_ccc)]:
                if r.has_ttm:
                    cell = ws.cell(row=row_idx, column=col, value=CashCycleService._to_days(val))
                else:
                    cell = ws.cell(row=row_idx, column=col, value="N/A")
                    cell.font = na_font
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

            ccc_t_cell = ws.cell(row=row_idx, column=14)
            if r.has_ttm:
                ccc_t_cell.font = CashCycleService._ccc_font(r.ttm_ccc)
            else:
                ccc_t_cell.font = na_font

            if r.has_ttm:
                eff = CashCycleService._efficiency_label(r.ttm_ccc)
            else:
                eff = "数据不足"
            eff_cell = ws.cell(row=row_idx, column=15, value=eff)
            eff_cell.border = thin_border
            eff_cell.alignment = Alignment(horizontal="center")

        col_widths = [12, 16, 16, 16, 16, 16, 11, 11, 11, 11, 11, 11, 11, 11, 22]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        summary_row = len(records) + 3
        ws.cell(row=summary_row, column=1, value="计算公式说明:").font = Font(bold=True, size=11)
        ws.cell(row=summary_row + 1, column=1, value="【单季】DIO = 存货均值 / 单季营业成本 × 季度天数（91天左右）")
        ws.cell(row=summary_row + 2, column=1, value="【单季】CCC = DIO + DSO - DPO")
        ws.cell(row=summary_row + 3, column=1, value="【TTM】DIO = 4季前存货与当季存货的均值 / 近4季营业成本合计 × 365天")
        ws.cell(row=summary_row + 4, column=1, value="【TTM】CCC = TTM_DIO + TTM_DSO - TTM_DPO  （滚动年化，消除季节性）")
        ws.cell(row=summary_row + 5, column=1, value="CCC < 0 表示企业在用上下游的钱做生意（强势公司特征）")

        ws.cell(row=summary_row + 7, column=1, value="数据来源:").font = Font(bold=True, size=11)
        ws.cell(row=summary_row + 8, column=1, value="中国A股财报（东方财富），季度累计值已轧差还原为单季数据")
        ws.cell(row=summary_row + 9, column=1, value="存货均值 = (期初存货 + 期末存货) / 2，应收/应付同理")
        ws.cell(row=summary_row + 10, column=1, value="适用行业: 制造业、消费品、零售等非金融行业")

    @staticmethod
    def write_annual_sheet(ws, records: List[AnnualCCCRecord]):
        header_font_white = Font(bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill(start_color="7030A0", end_color="7030A0", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        headers = [
            "报告期", "全年营收(亿)", "全年成本(亿)",
            "存货均值(亿)", "应收均值(亿)", "应付均值(亿)",
            "DIO(天)", "DSO(天)", "DPO(天)", "CCC(天)", "经营效率",
        ]

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = header_font_white
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        for row_idx, r in enumerate(records, 2):
            ws.cell(row=row_idx, column=1, value=r.report_date).border = thin_border
            ws.cell(row=row_idx, column=2, value=CashCycleService._to_yi(r.revenue)).border = thin_border
            ws.cell(row=row_idx, column=3, value=CashCycleService._to_yi(r.cost)).border = thin_border
            ws.cell(row=row_idx, column=4, value=CashCycleService._to_yi(r.avg_inventory)).border = thin_border
            ws.cell(row=row_idx, column=5, value=CashCycleService._to_yi(r.avg_receivables)).border = thin_border
            ws.cell(row=row_idx, column=6, value=CashCycleService._to_yi(r.avg_payables)).border = thin_border

            dio_cell = ws.cell(row=row_idx, column=7, value=CashCycleService._to_days(r.dio))
            dio_cell.border = thin_border
            dio_cell.alignment = Alignment(horizontal="center")

            dso_cell = ws.cell(row=row_idx, column=8, value=CashCycleService._to_days(r.dso))
            dso_cell.border = thin_border
            dso_cell.alignment = Alignment(horizontal="center")

            dpo_cell = ws.cell(row=row_idx, column=9, value=CashCycleService._to_days(r.dpo))
            dpo_cell.border = thin_border
            dpo_cell.alignment = Alignment(horizontal="center")

            ccc_cell = ws.cell(row=row_idx, column=10, value=CashCycleService._to_days(r.ccc))
            ccc_cell.border = thin_border
            ccc_cell.alignment = Alignment(horizontal="center")
            ccc_cell.font = CashCycleService._ccc_font(r.ccc)

            eff_cell = ws.cell(row=row_idx, column=11, value=CashCycleService._efficiency_label(r.ccc))
            eff_cell.border = thin_border
            eff_cell.alignment = Alignment(horizontal="center")

        col_widths = [12, 16, 16, 16, 16, 16, 12, 12, 12, 12, 24]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        summary_row = len(records) + 3
        ws.cell(row=summary_row, column=1, value="计算公式说明:").font = Font(bold=True, size=11)
        ws.cell(row=summary_row + 1, column=1, value="DIO = 存货均值 / 全年营业成本 × 365天")
        ws.cell(row=summary_row + 2, column=1, value="DSO = 应收均值 / 全年营业收入 × 365天")
        ws.cell(row=summary_row + 3, column=1, value="DPO = 应付均值 / 全年营业成本 × 365天")
        ws.cell(row=summary_row + 4, column=1, value="CCC = DIO + DSO - DPO  （取每年Q4年报数据，存货均值=(年初+年末)/2）")
        ws.cell(row=summary_row + 5, column=1, value="CCC < 0 表示企业在用上下游的钱做生意（强势公司特征）")

        ws.cell(row=summary_row + 7, column=1, value="数据来源:").font = Font(bold=True, size=11)
        ws.cell(row=summary_row + 8, column=1, value="中国A股财报（东方财富），仅取每年12-31年报数据")
        ws.cell(row=summary_row + 9, column=1, value="存货均值 = (年初存货余额 + 年末存货余额) / 2，应收/应付同理")
        ws.cell(row=summary_row + 10, column=1, value="适用行业: 制造业、消费品、零售等非金融行业")
