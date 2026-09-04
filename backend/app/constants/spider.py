from __future__ import annotations


ETF_REFERER = "http://www.sse.com.cn/"

OFFICIAL_MARKET_SH = "SH"
OFFICIAL_MARKET_SZ = "SZ"

KLINE_SH_MARKET_CODE = 1
KLINE_SZ_MARKET_CODE = 0
KLINE_HK_MARKET_CODE = 116

SH_CODE_FS = "m:1+t:2,m:1+t:23"
SZ_CODE_FS = "m:0+t:6,m:0+t:80"
CODE_FIELDS = "f12,f14"

KLINE_TITLE = "1|date,2|open,3|close,4|higher,5|lower,6|vol,7|amount,8|amplitude,9|amountOfIncrease,10|UpDownAmount,11|turnOver"


def market(sec_code: str | None) -> int | None:
    if not sec_code:
        return None
    code = sec_code.upper()
    if code.endswith(".SH"):
        return KLINE_SH_MARKET_CODE
    if code.endswith(".SZ"):
        return KLINE_SZ_MARKET_CODE
    return None


def code(sec_code: str | None) -> str | None:
    if not sec_code:
        return None
    code_val = sec_code.upper()
    if code_val.endswith(".SH"):
        return sec_code[:-3]
    if code_val.endswith(".SZ"):
        return sec_code[:-3]
    return None


def market_code(sec_code: int | str | None) -> int | None:
    """根据纯数字代码判断所属交易所市场代码"""
    if sec_code is None:
        return None
    s = str(sec_code).strip()
    if not s.isdigit():
        return None
    if len(s) == 6:
        if s.startswith(("5", "6", "9")):
            return KLINE_SH_MARKET_CODE
        if s.startswith(("0", "1", "2", "3")):
            return KLINE_SZ_MARKET_CODE
    return None


def convert_dic_map(dic_string: str) -> dict[str, str]:
    ret: dict[str, str] = {}
    for chunk in dic_string.split(","):
        key, val = chunk.split("|")
        ret[key.strip()] = val.strip()
    return ret
