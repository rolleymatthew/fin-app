"""Unit tests for tdx_daily_fetcher."""
from __future__ import annotations

import pytest

from app.services.tdx_daily_fetcher.exceptions import MetaParseError
from app.services.tdx_daily_fetcher.meta import MetaInfo, parse_meta_info


# ---- meta parser ----

_VALID_JS = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";
"""


def test_parse_meta_info_valid():
    info = parse_meta_info(_VALID_JS)
    assert info.update_time == "2026-09-17 15:59:01"
    assert info.file_size == 335544320


def test_parse_meta_info_size_with_commas():
    info = parse_meta_info(
        'var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";\n'
        'var HSJDAY_SOFT_SIZE = "524,927,539";'
    )
    assert info.file_size == 524927539


def test_parse_meta_info_size_missing_returns_none():
    info = parse_meta_info('HSJDAY_SOFT_TIME="2026-09-17 15:15:00";')
    assert info.file_size is None


def test_parse_meta_info_no_time_raises():
    with pytest.raises(MetaParseError, match="HSJDAY_SOFT_TIME"):
        parse_meta_info("var OTHER_VAR = 'foo';")


def test_parse_meta_info_empty_raises():
    with pytest.raises(MetaParseError):
        parse_meta_info("")
