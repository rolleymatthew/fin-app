"""前/后复权公式 (与项目既有 MongoDB 落库口径一致).

来源对照: QUANTAXIS.QAData.QA_data_stock_to_fq
- 前复权 (qfq): 历史价格向最新价看齐, 复权因子按"从事件日向前回溯"累乘.
- 后复权 (hfq): 最新价向历史看齐, 复权因子按"从上市日向后累乘".
- 不复权 (bfq): 原始价格, adj=1.0.

复权因子定义 (与 QUANTAXIS 一致):
    前复权: adj[t] = Π_{e: date_e <= t} (1 + 分红率 + 配股率) × 缩股系数
                          其中分红率 = 分红 / 除权前价格
    后复权: adj[t] = Π_{e: date_e >  t} (1 + 分红率 + 配股率) × 缩股系数
                          其中除权前价格取"事件日收盘"

    调整后:
        close_adj[t] = close_raw[t] × adj[t]
        preclose_adj[t] = preclose_raw[t] × adj[t]

设计要点:
- 缩股 (suogu) 必须并入因子, 否则送转 + 缩股混合时复权价偏差.
- 'preclose' 用 adj[t-1] 推算 (即"昨日 adj × 今日 raw preclose"),
  与既有 kline_service 落库语义一致.
- 复权失败 (无事件但要求复权) 抛硬错, 不静默降级.
- cat=1 (除权除息): 分红率 = fenhong / 10 / preclose (per QUANTAXIS 公式)
  cat=11/12 (缩股): factor = (10 - suogu) / 10
  其他类目: 暂不参与因子计算 (网络 get_xdxr_info 用 'IIfI' 解, 字段语义不同,
            当前实现只覆盖 cat in {1, 11, 12})
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FQMode:
    QFQ = "qfq"
    HFQ = "hfq"
    BFQ = "bfq"


_FQ_ALIASES = {
    "qfq": FQMode.QFQ,
    "01": FQMode.QFQ,
    "hfq": FQMode.HFQ,
    "02": FQMode.HFQ,
    "bfq": FQMode.BFQ,
    "00": FQMode.BFQ,
}


def normalize_fq(fq: str) -> str:
    """归一化复权标记: 'qfq'/'01' -> 'qfq'; 'hfq'/'02' -> 'hfq'; 'bfq'/'00' -> 'bfq'."""
    if not fq:
        return FQMode.QFQ
    key = fq.strip().lower()
    if key not in _FQ_ALIASES:
        raise ValueError(
            f"未知复权模式: {fq!r}, 期望 qfq/hfq/bfq 或 01/02/00"
        )
    return _FQ_ALIASES[key]


def _compute_preclose(adj: np.ndarray, raw_close: np.ndarray) -> np.ndarray:
    """从 adj 与 raw_close 推算 '复权后的前收' 序列.

    公式: preclose_adj[t] = raw_close[t-1] × adj[t-1]
    首日无 preclose, 填 NaN.
    """
    n = len(adj)
    preclose = np.full(n, np.nan, dtype=np.float64)
    if n > 1:
        preclose[1:] = raw_close[:-1] * adj[:-1]
    return preclose


def _event_factors(events: pd.DataFrame) -> pd.DataFrame:
    """从 xdxr 事件构造 (date, factor) — 因子按"事件日"生效, 当日及之后累计.

    对每条事件, 单期因子:
        if cat == 1 (除权除息):
            base = 1 - (fenhong/10) / preclose_at_event
            注: preclose_at_event 来自 raw K 线 (事件日前一收盘),
                调用方通过 ref_prices 注入. 此处无法计算, 返回 (None, ...) 标记待注入.
        if cat in {11, 12} (缩股):
            base = (10 - suogu) / 10

    返回: DataFrame[date, factor] — 仅含可即时计算的因子 (缩股);
          分红类因子的 'preclose' 部分由 apply_fq 在合并阶段注入.
    """
    if events.empty:
        return pd.DataFrame(columns=["date", "factor"])
    out = []
    for _, e in events.iterrows():
        cat = int(e["category"])
        if cat in (11, 12):
            factor = (10.0 - float(e["suogu"])) / 10.0
            out.append({"date": e["date"], "factor": factor})
        # cat == 1 的分红因子需要 preclose, 在 apply_fq 里基于 raw K 线算
    return pd.DataFrame(out, columns=["date", "factor"])


def apply_fq(
    raw: pd.DataFrame,
    events: pd.DataFrame,
    fq: str,
) -> pd.DataFrame:
    """对原始 K 线应用复权.

    Args:
        raw: TdxDailyBarReader 读出的 K 线 (DatetimeIndex, 列含 open/high/low/close)
        events: GbbqXdxrReader.read() 返回的事件
        fq: 'qfq' | 'hfq' | 'bfq' (或别名 01/02/00)

    Returns:
        升序 DataFrame, 列: open/high/low/close/amount/vol + adj + preclose

    Raises:
        ValueError: fq 非法, 或 qfq/hfq 但 events 为空 (硬报错契约)
    """
    mode = normalize_fq(fq)

    if raw.empty:
        return raw.copy()

    out = raw.copy()
    if mode == FQMode.BFQ:
        out["adj"] = 1.0
        out["preclose"] = np.nan
        return out

    # qfq / hfq 必须有事件
    if events.empty:
        raise ValueError(
            f"请求复权模式 {mode!r} 但除权除息事件表为空. "
            f"按契约不静默降级到不复权 — 请检查 gbbq 解析是否启用, "
            f"或确认该股票在通达信 gbbq 中确实无事件."
        )

    # -------------------------------------------------------------- #
    # 复权因子计算:
    # 1) 缩股因子 (cat=11/12): 立即可算
    # 2) 分红因子 (cat=1):     需要 '事件日前一交易日收盘价' 作为参考价.
    #                          在 raw K 线中, 找事件日的前一根 K 线 close.
    # -------------------------------------------------------------- #
    # 按事件日聚合每日因子
    raw_close = out["close"].to_numpy(dtype=np.float64)
    raw_index = out.index  # DatetimeIndex

    # 单期因子按事件日期累乘
    daily_factors = pd.Series(1.0, index=raw_index, name="日期_产品")

    # (a) 缩股
    sg = events[events["category"].isin([11, 12])].copy()
    for _, e in sg.iterrows():
        f = (10.0 - float(e["suogu"])) / 10.0
        daily_factors.loc[e["date"]:] *= f

    # (b) 除权除息 (cat=1)
    xr = events[events["category"] == 1].copy()
    for _, e in xr.iterrows():
        ev_date = e["date"]
        fenhong_per10 = float(e["fenhong"])  # 元 / 10 股
        if fenhong_per10 <= 0:
            continue
        # 找 raw 中事件日前一交易日 (事件日已除权, 用 [事件日 - 1] 索引)
        # raw_index 是 DatetimeIndex, 用 searchsorted 定位
        if ev_date not in raw_index:
            # 事件日不在 raw 中 (股票停牌或文件未覆盖), 跳过该事件
            continue
        pos = raw_index.get_loc(ev_date)
        if pos == 0:
            # 事件日是 raw 第一根, 无 preclose 可参考, 跳过
            continue
        preclose = raw_close[pos - 1]
        if preclose <= 0:
            continue
        # 单期因子 = 1 - 分红率
        # 分红率 = (fenhong/10) / preclose
        f = 1.0 - (fenhong_per10 / 10.0) / preclose
        daily_factors.loc[ev_date:] *= f

    adj = daily_factors.to_numpy(dtype=np.float64)
    if mode == FQMode.QFQ:
        # 前复权: 历史向最新价看齐, adj[latest] = 1.0.
        # adj[t] = daily_factors[latest] / daily_factors[t]
        # → 单次除权 (r) 时: adj[before]=1-r=0.97, adj[after]=1.0 ✓ (文章描述)
        adj = adj[-1] / adj
    elif mode == FQMode.HFQ:
        # 后复权: 以首期价为基准, adj[earliest] = 1.0.
        # adj[t] = daily_factors[earliest] / daily_factors[t]
        adj = adj[0] / adj

    out["adj"] = adj
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].to_numpy(dtype=np.float64) * adj
    out["preclose"] = _compute_preclose(adj, raw_close)
    return out