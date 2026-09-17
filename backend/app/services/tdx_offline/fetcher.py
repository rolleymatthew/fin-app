"""编排层: 把 .day 解析、gbbq 还原、复权公式三件权威组件拼成一个离线函数.

公开 API:
    fetch_local_day(code, fq='qfq', tdx_home=None) -> pd.DataFrame
    list_codes(tdx_home=None) -> list[str]

设计契约 (与 FreshQuant 实战手记一致):
1. code 6 位; 交易所按前缀推断 (5/6/9/7 开头沪, 其余深, 北交所 8/4 开头走 BJ);
3. tdx_home 解析顺序: 入参 > settings.tdx_home > 环境变量 TDX_HOME > 默认 C:\\zd_zxzq_gm.
4. 复权失败 → 硬报错, 不静默降级 (回测污染源).
5. 跨交易日主动 GbbqXdxrReader.invalidate(); 长驻进程每日盘前调用一次.

返回 DataFrame:
    - DatetimeIndex 升序 (从最早一根到最新一根)
    - 不复权: open/high/low/close/amount/vol
    - qfq/hfq: open/high/low/close/amount/vol + adj + preclose

失败语义:
    - FileNotFoundError: 本地 .day 或 gbbq 缺失, 错误信息含绝对路径
    - ValueError: 复权请求但事件表为空 (硬报错, 不降级)
    - NotImplementedError: gbbq 解析器未集成 (见 gbbq_reader.py 注释)
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.services.tdx_offline.day_reader import (
    TdxDailyBarReader,
    TdxMarket,
    list_vipdoc_codes,
)
from app.services.tdx_offline.fq import apply_fq, normalize_fq
from app.services.tdx_offline.gbbq_reader import GbbqXdxrReader


# ---------------------------------------------------------------------- #
# 交易所推断
# ---------------------------------------------------------------------- #
def _infer_market(code: str) -> str:
    """6 位代码 -> 交易所 ('sh' / 'sz' / 'bj').

    规则:
      - 6 开头 / 9 开头 / 5 开头 → 上证 (sh) (A 股 600/601/603/605; B 股 900; 沪 ETF 5xxxxx)
      - 0 开头 / 3 开头 / 1 开头 → 深证 (sz) (A 股 000/001/002/003; 创业板 300; 深 ETF 1xxxxx)
      - 8 开头 / 4 开头 / 92 开头 → 北交所 (bj)
      - 4 开头: 沪北 (历史遗留, 暂归 sh)
    """
    if not code or len(code) != 6 or not code.isdigit():
        raise ValueError(f"非法股票代码: {code!r}, 期望 6 位数字")
    head2 = code[:2]
    head1 = code[0]
    if head1 in ("5", "6", "7", "9"):
        return "sh"
    if head1 in ("0", "1", "2", "3"):
        return "sz"
    if head2 in ("83", "87", "88", "43", "92"):
        return "bj"
    raise ValueError(f"无法推断交易所: {code!r}")


# ---------------------------------------------------------------------- #
# tdx_home 解析 (三级 fallback)
# ---------------------------------------------------------------------- #
def _resolve_tdx_home(tdx_home: str | os.PathLike | None) -> Path:
    """入参 > settings > 环境变量 > 默认 C:\\zd_zxzq_gm."""
    if tdx_home:
        return Path(tdx_home)
    # settings 走 lru_cache, 这里调一次即可
    settings = get_settings()
    home = settings.tdx_home or os.environ.get("TDX_HOME") or r"C:\zd_zxzq_gm"
    return Path(home)


# ---------------------------------------------------------------------- #
# 进程内 reader 缓存 (复用 TdxDailyBarReader 状态: 实际上无状态, 仅路径不同)
# ---------------------------------------------------------------------- #
_gbbq_reader_singleton: GbbqXdxrReader | None = None
_gbbq_home_resolved: Path | None = None


def _get_gbbq_reader(tdx_home: Path) -> GbbqXdxrReader:
    """进程级单例; 跨交易日调 invalidate_gbbq_cache() 即可重建."""
    global _gbbq_reader_singleton, _gbbq_home_resolved
    if _gbbq_reader_singleton is None or _gbbq_home_resolved != tdx_home:
        _gbbq_reader_singleton = GbbqXdxrReader(tdx_home=tdx_home)
        _gbbq_home_resolved = tdx_home
    return _gbbq_reader_singleton


def invalidate_gbbq_cache() -> None:
    """长驻进程每日盘前调用 — 让 gbbq 索引重新加载, 吃到当日新增事件."""
    global _gbbq_reader_singleton, _gbbq_home_resolved
    if _gbbq_reader_singleton is not None:
        _gbbq_reader_singleton.invalidate()
    _gbbq_reader_singleton = None
    _gbbq_home_resolved = None


# ---------------------------------------------------------------------- #
# 主入口
# ---------------------------------------------------------------------- #
def fetch_local_day(
    code: str,
    fq: str = "qfq",
    tdx_home: str | os.PathLike | None = None,
) -> pd.DataFrame:
    """从本地通达信目录读单只股票日线 + 复权.

    Args:
        code: 6 位股票代码, 例 '000910' / '600000' / '510300'
        fq: 'qfq'(默认) | 'hfq' | 'bfq'; 也接受 '01'/'02'/'00'
        tdx_home: 通达信主目录; None 时走 settings/环境变量/默认

    Returns:
        升序 DatetimeIndex DataFrame.
        qfq/hfq: 含 open/high/low/close/amount/vol + adj + preclose
        bfq:     含 open/high/low/close/amount/vol (adj=1.0, preclose=NaN)

    Raises:
        FileNotFoundError: 本地文件缺失 (错误信息含绝对路径)
        ValueError: code 非法 / fq 非法 / 复权请求但事件表空
        NotImplementedError: gbbq 私有解析器未集成 (见 gbbq_reader.py)
    """
    market_name = _infer_market(code)
    home = _resolve_tdx_home(tdx_home)
    market = TdxMarket.from_home(home, market_name)
    reader = TdxDailyBarReader(market, code)
    raw = reader.read()  # 已自带 FileNotFoundError 含路径

    mode = normalize_fq(fq)
    if mode == "bfq":
        # 不复权路径: 直接返回, 不碰 gbbq
        return raw.assign(adj=1.0, preclose=float("nan"))

    # qfq / hfq 路径: 必须先取事件
    gbbq = _get_gbbq_reader(home)
    events = gbbq.read(code)
    # apply_fq 内部按契约: events 空时抛 ValueError
    return apply_fq(raw, events, mode)


def list_codes(tdx_home: str | os.PathLike | None = None) -> list[str]:
    """枚举本地 vipdoc 全市场代码. 供全市场扫描 (AI 编排: 选股/缠论扫描)."""
    home = _resolve_tdx_home(tdx_home)
    return list_vipdoc_codes(home)