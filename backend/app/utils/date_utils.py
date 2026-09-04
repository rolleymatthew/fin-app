from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List

DATE_FMT = "%Y-%m-%d"
FULL_FMT = "%Y-%m-%d %H:%M:%S"
MARKET_TIMEZONE = timezone(timedelta(hours=8))


def today() -> date:
    return datetime.now(MARKET_TIMEZONE).date()


def now() -> datetime:
    return datetime.now()


def current_time() -> time:
    return datetime.now().time()


def get_year(d: date) -> int:
    return d.year


def get_month(d: date) -> int:
    return d.month


def get_day(d: date) -> int:
    return d.day


def customize_defined_date(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def equalse_date(d1: date, d2: date) -> bool:
    return d1 == d2


def plus_hours(t: time, add_hours: int) -> time:
    dt = datetime.combine(date.today(), t)
    return (dt + timedelta(hours=add_hours)).time()


def plus_weeks(d: date, add_weeks: int) -> date:
    return d + timedelta(weeks=add_weeks)


def previous_weeks(d: date, minus_weeks: int) -> date:
    return d - timedelta(weeks=minus_weeks)


def previous_months(d: date, minus_months: int) -> date:
    # simple month subtraction
    year = d.year
    month = d.month - minus_months
    while month <= 0:
        month += 12
        year -= 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def previous_years(d: date, years: int) -> date:
    return date(d.year - years, d.month, min(d.day, _days_in_month(d.year - years, d.month)))


def next_years(d: date, years: int) -> date:
    return date(d.year + years, d.month, min(d.day, _days_in_month(d.year + years, d.month)))


def period_to_next_date(start_date: date, end_date: date, type_: int) -> int:
    if type_ == 1:
        return (end_date - start_date).days
    if type_ == 2:
        return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    if type_ == 3:
        return end_date.year - start_date.year
    return 0


def format_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y%m%d").date()


def format_date_with_slip(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def format_full_date_with_slip(date_str: str) -> date:
    return datetime.strptime(date_str, FULL_FMT).date()


def get_current_time() -> int:
    return int(datetime.now().timestamp())


def date_to_full_string(dt: datetime) -> str:
    return dt.strftime("%Y年%m月%d日 %H:%M:%S")


def date_to_string(d: date) -> str:
    return d.strftime(DATE_FMT)


def string_to_local_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y/%m/%d").date()


def string_ch_to_local_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y年%m月%d日").date()


def previous_days(days: int) -> date:
    return today() - timedelta(days=days)


def is_working_day(d: date) -> bool:
    return d.weekday() < 5


def days_list(count: int) -> List[date]:
    lst: List[date] = []
    days = 1
    while len(lst) < count:
        d = previous_days(days)
        if is_working_day(d):
            lst.append(d)
        else:
            days += 1
            continue
        days += 1
    return lst


def get_last_year_same_quarter(date_str: str) -> str:
    d = format_date_with_slip(date_str)
    return previous_years(d, 1).isoformat()


def week_of_year(d: date) -> int:
    return int(d.strftime("%U"))


def current_quarter(d: date) -> date | None:
    m = d.month
    if 1 <= m <= 3:
        return date(d.year, 3, 31)
    if 4 <= m <= 6:
        return date(d.year, 6, 30)
    if 7 <= m <= 9:
        return date(d.year, 9, 30)
    if 10 <= m <= 12:
        return date(d.year, 12, 31)
    return None


def last_quarter(current_date: date) -> date:
    current_month = current_date.month
    quarter_month = ((current_month - 1) // 3) * 3 + 1
    last_month = quarter_month - 1
    year = current_date.year
    if last_month <= 0:
        last_month += 12
        year -= 1
    return date(year, last_month, _days_in_month(year, last_month))


def quarter_date_list(local_date: date, valite_date: bool, report_date: str | None) -> List[date]:
    quarter_date = last_quarter(local_date)
    if not valite_date and report_date:
        quarter_date = format_full_date_with_slip(report_date)
    dates = [
        quarter_date,
        previous_months(quarter_date, 3).replace(day=_days_in_month(previous_months(quarter_date, 3).year, previous_months(quarter_date, 3).month)),
        previous_months(quarter_date, 6).replace(day=_days_in_month(previous_months(quarter_date, 6).year, previous_months(quarter_date, 6).month)),
        previous_months(quarter_date, 9).replace(day=_days_in_month(previous_months(quarter_date, 9).year, previous_months(quarter_date, 9).month)),
        previous_months(quarter_date, 12).replace(day=_days_in_month(previous_months(quarter_date, 12).year, previous_months(quarter_date, 12).month)),
    ]
    return dates


def last_year_of_three_date_list(local_date: date, valite_date: bool, report_date: str | None) -> List[date]:
    quarter_date = last_quarter(local_date)
    if not valite_date and report_date:
        quarter_date = format_full_date_with_slip(report_date)
    dates: List[date] = []
    for _ in range(21):
        dates.append(quarter_date.replace(day=_days_in_month(quarter_date.year, quarter_date.month)))
        quarter_date = previous_months(quarter_date, 3)
    return dates


def year_date_list(local_date: date, valite_date: bool, report_date: str | None) -> List[date]:
    local_date_year = date(local_date.year, 12, 31)
    if not valite_date and report_date:
        local_date1 = format_full_date_with_slip(report_date)
        if local_date1.month < 12:
            local_date_year = date(local_date1.year, 12, 31)
    return [
        previous_years(local_date_year, 1),
        previous_years(local_date_year, 2),
        previous_years(local_date_year, 3),
        previous_years(local_date_year, 4),
        previous_years(local_date_year, 5),
    ]


def parse_date(value: str):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day
