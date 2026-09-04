from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from app.utils import date_utils, num_utils


def quarter_of_kline(kline_entities: List, start_date):
    end_date = date_utils.previous_years(start_date, 1)
    return [
        k for k in kline_entities
        if (start_date >= date_utils.format_date_with_slip(k.date))
        and end_date < date_utils.format_date_with_slip(k.date)
    ]


def month_of_kline(kline_entities: List, start_date, end_date):
    return [
        k for k in kline_entities
        if (start_date <= date_utils.format_date_with_slip(k.date))
        and end_date > date_utils.format_date_with_slip(k.date)
    ]


def month_of_kline_map(kline_entities: List):
    mp = defaultdict(list)
    for k in kline_entities:
        d = date_utils.format_date_with_slip(k.date)
        key = f"{date_utils.get_year(d)}{date_utils.get_month(d)}"
        mp[key].append(k)
    return mp


def high(kline_entities: List):
    return Decimal(max(num_utils.string_to_double(k.higher) for k in kline_entities)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def low(kline_entities: List):
    return Decimal(min(num_utils.string_to_double(k.lower) for k in kline_entities)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def avarage(part_map: dict[str, List]):
    kline_in_part = [v[0] for v in part_map.values() if v]
    kline_in_part.sort(key=lambda x: x.date)
    values = [num_utils.string_to_double(k.close) for k in kline_in_part]
    return sum(values) / len(values) if values else 0.0


def avarage_list(kline_list: List):
    amount = sum(num_utils.string_to_double(k.amount) for k in kline_list if k.amount)
    vol = sum(num_utils.string_to_double(k.vol) * 100 for k in kline_list if k.vol)
    if vol == 0:
        return Decimal(0)
    return (Decimal(amount) / Decimal(vol)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
