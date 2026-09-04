from datetime import date, datetime, timezone

from app.constants import spider
from app.utils import date_utils


class MarketDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 20, 22, 30, tzinfo=timezone.utc).astimezone(tz)


def test_spider_market():
    assert spider.market("600519.SH") == 1
    assert spider.market("000001.SZ") == 0


def test_date_utils(monkeypatch):
    monkeypatch.setattr(date_utils, "datetime", MarketDateTime)

    d = date_utils.format_date_with_slip("2022-01-01")
    assert d.year == 2022
    assert date_utils.today() == date(2026, 7, 21)
    assert date_utils.previous_days(1) == date(2026, 7, 20)
