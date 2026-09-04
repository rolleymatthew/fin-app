from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict

from app.mappers.analysis import AnalysisEntityMapper
from app.mappers.kline_data import quarter_of_kline, month_of_kline, month_of_kline_map, high, low, avarage, avarage_list
from app.utils import date_utils, num_utils


class YbEpsEntityMapper:
    def __init__(self):
        self.analysis = AnalysisEntityMapper()

    def creat(self, profit_entities: List, sec_code_entity, klines: List, force: int):
        kline_week_map: Dict[str, List] = {}
        report_date = self._get_financial_report_date(profit_entities)
        week = date_utils.quarter_date_list(date_utils.today(), self._valite_date(force), report_date)
        for i in range(len(week) - 1):
            kline_week_map[week[i].isoformat()] = quarter_of_kline(klines, week[i])

        quarter_eps_list = [self.analysis.eps_quarter(profit_entities, s) for s in week][:4]
        quarter_year_eps_list = [self.analysis.eps_quarter_split_year(profit_entities, date_utils.date_to_string(s), sec_code_entity.securityCode) for s in week][:4]
        self._fill_quarter_eps(kline_week_map, quarter_eps_list, week, quarter_year_eps_list)

        kline_months: Dict[str, Dict[str, List]] = {}
        kline_year_map: Dict[str, List] = {}
        year = date_utils.year_date_list(date_utils.today(), self._valite_date(force), report_date)
        for i in range(len(year) - 1):
            kline_year_map[year[i].isoformat()] = month_of_kline(klines, year[i + 1], year[i])
            kline_months[year[i].isoformat()] = month_of_kline_map(kline_year_map[year[i].isoformat()])

        year_eps_list = [self.analysis.eps_date_by_year(profit_entities, s) for s in year][:4]
        self._fill_year_eps(kline_months, kline_year_map, year_eps_list)

        return self._get_yb_roe_entity(quarter_eps_list, year_eps_list, quarter_year_eps_list)

    def _get_financial_report_date(self, profit_entities: List):
        if profit_entities:
            o = profit_entities[0]
            if o:
                return getattr(o[0], "reportDate", None)
        return None

    def _valite_date(self, force: int) -> bool:
        return force == 1

    def _fill_year_eps(self, kline_months, kline_year_map, year_eps_list):
        for x in year_eps_list:
            if not x:
                continue
            key = x["date"].isoformat()
            kline_year = kline_year_map.get(key) or []
            kline_month = kline_months.get(key) or {}
            if not kline_year or not kline_month:
                x["__invalid"] = True
                continue
            high_v = high(kline_year)
            low_v = low(kline_year)
            avg_v = Decimal(avarage(kline_month)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            x["high"] = high_v
            x["low"] = low_v
            x["avg"] = avg_v
            x["highEps"] = self._divide(high_v, x["eps"])
            x["lowEps"] = self._divide(low_v, x["eps"])
            x["avgEps"] = self._divide(avg_v, x["eps"])

    def _fill_quarter_eps(self, kline_week_map, quarter_eps_list, quarter_name, quarter_year_eps_list):
        quarter_total_eps = {}
        for i in range(len(quarter_name) - 1):
            local_date = quarter_name[i]
            total_eps = next((s["eps"] for s in quarter_year_eps_list if s and s["date"] == local_date), Decimal(0))
            quarter_total_eps[local_date] = total_eps
        for x in quarter_eps_list:
            if not x:
                continue
            key = x["date"].isoformat()
            kline_week = kline_week_map.get(key) or []
            if not kline_week:
                x["__invalid"] = True
                continue
            high_v = high(kline_week)
            low_v = low(kline_week)
            avg_v = avarage_list(kline_week)
            x["high"] = high_v
            x["low"] = low_v
            x["avg"] = avg_v
            x["highEps"] = self._divide(high_v, quarter_total_eps.get(x["date"], Decimal(0)))
            x["lowEps"] = self._divide(low_v, quarter_total_eps.get(x["date"], Decimal(0)))
            x["avgEps"] = self._divide(avg_v, quarter_total_eps.get(x["date"], Decimal(0)))

    def _get_yb_roe_entity(self, quarter_eps_list, year_eps_list, quarter_year_eps_list):
        from app.models.entities import YbRoeEntity

        def _get(idx, key, default=Decimal(0)):
            return quarter_eps_list[idx].get(key, default)

        # Guard against missing eps data to avoid crashes when source data is incomplete
        if (
            len(quarter_eps_list) < 4
            or len(year_eps_list) < 4
            or len(quarter_year_eps_list) < 4
            or any(x is None for x in quarter_eps_list[:4])
            or any(x is None for x in year_eps_list[:4])
            or any(x is None for x in quarter_year_eps_list[:4])
            or any((x or {}).get("__invalid") for x in quarter_eps_list[:4])
            or any((x or {}).get("__invalid") for x in year_eps_list[:4])
        ):
            return None

        yb = YbRoeEntity()
        yb.lastonequarterhigher = _get(0, "high")
        yb.lastonequarteraverage = _get(0, "avg")
        yb.lastonequarterlower = _get(0, "low")
        yb.lasttwoquarterhigher = _get(1, "high")
        yb.lasttwoquarteraverage = _get(1, "avg")
        yb.lasttwoquarterlower = _get(1, "low")
        yb.lastthreequarterhigher = _get(2, "high")
        yb.lastthreequarteraverage = _get(2, "avg")
        yb.lastthreequarterlower = _get(2, "low")
        yb.lastfourquarterhigher = _get(3, "high")
        yb.lastfourquarteraverage = _get(3, "avg")
        yb.lastfourquarterlower = _get(3, "low")

        yb.lastoneyearhigher = year_eps_list[0].get("high")
        yb.lastoneyearaverage = year_eps_list[0].get("avg")
        yb.lastoneyearlower = year_eps_list[0].get("low")
        yb.lasttwoyearhigher = year_eps_list[1].get("high")
        yb.lasttwoyearaverage = year_eps_list[1].get("avg")
        yb.lasttwoyearlower = year_eps_list[1].get("low")
        yb.lastthreeyearhigher = year_eps_list[2].get("high")
        yb.lastthreeyearaverage = year_eps_list[2].get("avg")
        yb.lastthreeyearlower = year_eps_list[2].get("low")
        yb.lastfouryearhigher = year_eps_list[3].get("high")
        yb.lastfouryearaverage = year_eps_list[3].get("avg")
        yb.lastfouryearlower = year_eps_list[3].get("low")

        yb.onequarterdate = str(quarter_eps_list[0]["date"])
        yb.oneepstotal = num_utils.add(quarter_eps_list[0]["eps"], quarter_eps_list[1]["eps"], quarter_eps_list[2]["eps"], quarter_eps_list[3]["eps"])
        yb.oneepscurrent = quarter_eps_list[0]["eps"]

        yb.twoquarterdate = str(quarter_eps_list[1]["date"])
        yb.twoepstotal = num_utils.add(quarter_eps_list[1]["eps"], quarter_eps_list[2]["eps"], quarter_eps_list[3]["eps"])
        yb.twoepscurrent = quarter_eps_list[1]["eps"]

        yb.threequarterdate = str(quarter_eps_list[2]["date"])
        yb.threeepstotal = num_utils.add(quarter_eps_list[2]["eps"], quarter_eps_list[3]["eps"])
        yb.threeepscurrent = quarter_eps_list[2]["eps"]

        yb.fourquarterdate = str(quarter_eps_list[3]["date"])
        yb.fourepstotal = quarter_eps_list[3]["eps"]
        yb.fourepscurrent = quarter_eps_list[3]["eps"]

        yb.oneyeardate = str(year_eps_list[0]["date"])
        yb.oneyearepstotal = year_eps_list[0]["eps"]
        yb.twoyeardate = str(year_eps_list[1]["date"])
        yb.twoyearepstotal = year_eps_list[1]["eps"]
        yb.threeyeardate = str(year_eps_list[2]["date"])
        yb.threeyearepstotal = year_eps_list[2]["eps"]
        yb.fouryeardate = str(year_eps_list[3]["date"])
        yb.fouryearepstotal = year_eps_list[3]["eps"]

        yb.fouryearavarageepstotal = self._divide(num_utils.add(year_eps_list[0]["eps"], year_eps_list[1]["eps"], year_eps_list[2]["eps"], year_eps_list[3]["eps"]), Decimal(4))

        yb.oneyearpedate = str(year_eps_list[0]["date"])
        yb.oneyearpehigher = year_eps_list[0]["highEps"]
        yb.oneyearpeaverage = year_eps_list[0]["avgEps"]
        yb.oneyearpelower = year_eps_list[0]["lowEps"]
        yb.twoyearpedate = str(year_eps_list[1]["date"])
        yb.twoyearpehigher = year_eps_list[1]["highEps"]
        yb.twoyearpeaverage = year_eps_list[1]["avgEps"]
        yb.twoyearpelower = year_eps_list[1]["lowEps"]
        yb.threeyearpedate = str(year_eps_list[2]["date"])
        yb.threeyearpehigher = year_eps_list[2]["highEps"]
        yb.threeyearpeaverage = year_eps_list[2]["avgEps"]
        yb.threeyearpelower = year_eps_list[2]["lowEps"]
        yb.fouryearpedate = str(year_eps_list[3]["date"])
        yb.fouryearpehigher = year_eps_list[3]["highEps"]
        yb.fouryearpeaverage = year_eps_list[3]["avgEps"]
        yb.fouryearpelower = year_eps_list[3]["lowEps"]

        yb.fouryearavagpehigher = self._divide(num_utils.add(year_eps_list[0]["highEps"], year_eps_list[1]["highEps"], year_eps_list[2]["highEps"], year_eps_list[3]["highEps"]), Decimal(4))
        yb.fouryearavagpemiddle = self._divide(num_utils.add(year_eps_list[0]["avgEps"], year_eps_list[1]["avgEps"], year_eps_list[2]["avgEps"], year_eps_list[3]["avgEps"]), Decimal(4))
        yb.fouryearavagpelower = self._divide(num_utils.add(year_eps_list[0]["lowEps"], year_eps_list[1]["lowEps"], year_eps_list[2]["lowEps"], year_eps_list[3]["lowEps"]), Decimal(4))

        yb.onequarterpedate = str(quarter_eps_list[0]["date"])
        yb.onequarterpehigher = self._divide(quarter_eps_list[0]["high"], quarter_year_eps_list[0]["eps"])
        yb.onequarterpeaverage = self._divide(quarter_eps_list[0]["avg"], quarter_year_eps_list[0]["eps"])
        yb.onequarterpelower = self._divide(quarter_eps_list[0]["low"], quarter_year_eps_list[0]["eps"])
        yb.laterfirstqepstotal = quarter_year_eps_list[0]["eps"]

        yb.twoquarterpedate = str(quarter_eps_list[1]["date"])
        yb.twoquarterpehigher = self._divide(quarter_eps_list[1]["high"], quarter_year_eps_list[1]["eps"])
        yb.twoquarterpeaverage = self._divide(quarter_eps_list[1]["avg"], quarter_year_eps_list[1]["eps"])
        yb.twoquarterpelower = self._divide(quarter_eps_list[1]["low"], quarter_year_eps_list[1]["eps"])
        yb.latertwoqepstotal = quarter_year_eps_list[1]["eps"]

        yb.threequarterpedate = str(quarter_eps_list[2]["date"])
        yb.threequarterpehigher = self._divide(quarter_eps_list[2]["high"], quarter_year_eps_list[2]["eps"])
        yb.threequarterpeaverage = self._divide(quarter_eps_list[2]["avg"], quarter_year_eps_list[2]["eps"])
        yb.threequarterpelower = self._divide(quarter_eps_list[2]["low"], quarter_year_eps_list[2]["eps"])
        yb.laterthreeqepstotal = quarter_year_eps_list[2]["eps"]

        yb.fourquarterpedate = str(quarter_eps_list[3]["date"])
        yb.fourquarterpehigher = self._divide(quarter_eps_list[3]["high"], quarter_year_eps_list[3]["eps"])
        yb.fourquarterpeaverage = self._divide(quarter_eps_list[3]["avg"], quarter_year_eps_list[3]["eps"])
        yb.fourquarterpelower = self._divide(quarter_eps_list[3]["low"], quarter_year_eps_list[3]["eps"])
        yb.laterfourqepstotal = quarter_year_eps_list[3]["eps"]

        yb.fourquarteravagpehigher = self._divide(num_utils.add(quarter_eps_list[0]["highEps"], quarter_eps_list[1]["highEps"], quarter_eps_list[2]["highEps"], quarter_eps_list[3]["highEps"]), Decimal(4))
        yb.fourquarteravagpemiddle = self._divide(num_utils.add(quarter_eps_list[0]["avgEps"], quarter_eps_list[1]["avgEps"], quarter_eps_list[2]["avgEps"], quarter_eps_list[3]["avgEps"]), Decimal(4))
        yb.fourquarteravagpelower = self._divide(num_utils.add(quarter_eps_list[0]["lowEps"], quarter_eps_list[1]["lowEps"], quarter_eps_list[2]["lowEps"], quarter_eps_list[3]["lowEps"]), Decimal(4))

        yb.laterfourqavaepstotal = (num_utils.add(yb.laterfirstqepstotal, yb.latertwoqepstotal, yb.laterthreeqepstotal, yb.laterfourqepstotal) / Decimal(4)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        yb.pricehigher = self._price(yb.oneepstotal, yb.fouryearavarageepstotal, yb.fouryearavagpehigher)
        yb.pricemiddle = self._price(yb.oneepstotal, yb.fouryearavarageepstotal, yb.fouryearavagpemiddle)
        yb.pricelower = self._price(yb.oneepstotal, yb.fouryearavarageepstotal, yb.fouryearavagpelower)
        yb.pricequarterhigher = self._price(yb.oneepstotal, yb.laterfourqavaepstotal, yb.fourquarteravagpehigher)
        yb.pricequartermiddle = self._price(yb.oneepstotal, yb.laterfourqavaepstotal, yb.fourquarteravagpemiddle)
        yb.pricequarterlower = self._price(yb.oneepstotal, yb.laterfourqavaepstotal, yb.fourquarteravagpelower)

        return yb

    def _price(self, epstotal: Decimal, avg_eps_total: Decimal, avg_pe: Decimal) -> Decimal:
        return (epstotal + avg_eps_total) / Decimal(2) * avg_pe

    def _divide(self, dividend: Decimal, devider: Decimal) -> Decimal:
        if devider == 0:
            return Decimal(0)
        return (Decimal(dividend) / Decimal(devider)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
