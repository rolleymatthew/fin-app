from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ReportDateType:
    index: int
    date: str
    name: str


REPORT_DATE_TYPES = [
    ReportDateType(1, "03-31", "一季报"),
    ReportDateType(2, "06-30", "二季报"),
    ReportDateType(3, "09-30", "三季报"),
    ReportDateType(4, "12-31", "四季报"),
]


def latest_quarter_by_date(date: str, year: int) -> List[str]:
    ret: List[str] = []
    match = next((x for x in REPORT_DATE_TYPES if x.date == date), None)
    if not match:
        return ret
    for x in REPORT_DATE_TYPES:
        if x.index <= match.index:
            ret.append(f"{year}-{x.date}")
        else:
            ret.append(f"{year - 1}-{x.date}")
    ret.append(f"{year - 1}-{match.date}")
    return sorted(ret, reverse=True)


def latest_quarter_by_year_date(date: str) -> List[str] | None:
    if "-" not in date:
        return None
    parts = date.split("-")
    if len(parts) != 3:
        return None
    return latest_quarter_by_date(f"{parts[1]}-{parts[2]}", int(parts[0]))


def latest_quarter_identity(date: str) -> str:
    return date
