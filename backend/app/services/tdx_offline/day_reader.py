"""本地通达信 .day 二进制日线解析器.

每根 K 线 32 字节, 结构 (little-endian):
    date  uint32  YYYYMMDD
    open  uint32  ×100 (分→元)
    high  uint32  ×100
    low   uint32  ×100
    close uint32  ×100
    amount float32 元
    vol   uint32  股 (非手)
    _     uint32  保留字段

约定:
- 返回升序 DatetimeIndex DataFrame, 列: open/high/low/close/amount/vol.
- 与项目既有 kline_service 落库口径一致: amount 单位元, vol 单位股 (落库时再 ÷100 转手).
- 文件缺失: 抛 FileNotFoundError 并附绝对路径.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

DAY_RECORD_SIZE = 32
DAY_STRUCT_FMT = "<IIIIIfII"  # 8 个字段 × 32 字节


@dataclass(frozen=True)
class TdxMarket:
    """通达信本地 vipdoc 目录定位."""

    name: str          # 'sh' / 'sz' / 'bj'
    lday_dir: Path     # vipdoc/{name}/lday

    @classmethod
    def from_home(cls, tdx_home: str | os.PathLike, market: str) -> "TdxMarket":
        lday = Path(tdx_home) / "vipdoc" / market / "lday"
        if not lday.is_dir():
            raise FileNotFoundError(
                f"通达信本地目录不存在: {lday} (请检查 TDX_HOME 或通达信是否已安装)"
            )
        return cls(name=market, lday_dir=lday)

    def day_path(self, code: str) -> Path:
        """code='000910' -> 'sh000910.day' (前缀与交易所一致)."""
        return self.lday_dir / f"{self.name}{code}.day"


class TdxDailyBarReader:
    """通达信本地日线读取器 (单文件实例, 复用无状态)."""

    # 不同证券类型的 .day 解码系数 (port 自 pytdx TdxDailyBarReader)
    # 格式: (price_coeff, vol_coeff) — raw × coeff 得出手与手
    #   A 股 / 指数:         price × 0.01 (分→元), vol × 0.01 (raw=shares, 输出=手)
    #   B 股:                price × 0.001 (毫→元), vol × 0.01
    #   基金 (ETF/LOF):       price × 0.001 (毫→元), vol × 1.0  (raw=shares, × 100 = 手)
    #   债券:                price × 0.001 (毫→元), vol × 0.01
    #
    # 验证口径: close × vol_lots × 100 = amount (恒成立)
    #   600000:  9.06 × 456711 × 100 = 414M ≈ 415M ✓
    #   510300:  4.725 × 84977822 × 100 = 40.15B ≈ 40.1B ✓
    SECURITY_COEFFICIENT = {
        ("sh", "A_STOCK"): (0.01, 0.01),
        ("sh", "B_STOCK"): (0.001, 0.01),
        ("sh", "INDEX"):   (0.01, 1.0),    # 指数 vol 按手输出
        ("sh", "FUND"):    (0.001, 1.0),   # ETF: raw 已是 shares, × 1.0 = shares
        ("sh", "BOND"):    (0.001, 0.01),
        ("sz", "A_STOCK"): (0.01, 0.01),
        ("sz", "B_STOCK"): (0.01, 0.01),
        ("sz", "INDEX"):   (0.01, 1.0),
        ("sz", "FUND"):    (0.001, 1.0),
        ("sz", "BOND"):    (0.001, 0.01),
        ("bj", "A_STOCK"): (0.01, 0.01),   # 北交所 92xxxx 等
        ("bj", "B_STOCK"): (0.01, 0.01),
        ("bj", "INDEX"):   (0.01, 1.0),
        ("bj", "FUND"):    (0.001, 1.0),
        ("bj", "BOND"):    (0.001, 0.01),
    }

    @classmethod
    def detect_security_type(cls, market: str, code: str) -> str:
        """根据市场 + code 前缀识别证券类型 (与 pytdx get_security_type 一致)."""
        head2 = code[:2]
        if market == "sh":
            if head2 == "60":
                return "A_STOCK"
            if head2 == "90":
                return "B_STOCK"
            if head2 in ("00", "88", "99"):
                return "INDEX"
            if head2 in ("50", "51"):
                return "FUND"
            if head2 in ("01", "10", "11", "12", "13", "14"):
                return "BOND"
        elif market == "sz":
            if head2 in ("00", "30"):
                return "A_STOCK"
            if head2 == "20":
                return "B_STOCK"
            if head2 == "39":
                return "INDEX"
            if head2 in ("15", "16"):
                return "FUND"
            if head2 in ("10", "11", "12", "13", "14"):
                return "BOND"
        elif market == "bj":
            if head2 in ("92", "83", "87", "88", "43"):
                return "A_STOCK"   # 北交所 A 股
            if head2 == "20":
                return "B_STOCK"
            if head2 in ("39",):
                return "INDEX"
            if head2 in ("15", "16"):
                return "FUND"
            if head2 in ("10", "11", "12", "13", "14"):
                return "BOND"
        return "A_STOCK"  # 兜底: 按 A 股解析

    def __init__(self, market: TdxMarket, code: str):
        self.market = market
        self.code = code
        self.path = market.day_path(code)
        sec_type = self.detect_security_type(market.name, code)
        self._price_coeff, self._vol_coeff = self.SECURITY_COEFFICIENT[
            (market.name, sec_type)
        ]

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> pd.DataFrame:
        """读取 .day, 返回升序 DataFrame (DatetimeIndex).

        列: open / high / low / close / amount / vol
        单位: 元 / 元 / 元 / 元 / 元 / 股
        """
        if not self.exists():
            raise FileNotFoundError(
                f"通达信本地日线缺失: {self.path} "
                f"(请在通达信里完成盘后下载, 或检查 code 交易所归属)"
            )
        raw = self.path.read_bytes()
        if len(raw) % DAY_RECORD_SIZE != 0:
            raise ValueError(
                f".day 文件长度非 32 整数倍: {self.path} size={len(raw)}"
            )
        rec = struct.iter_unpack(DAY_STRUCT_FMT, raw)

        dates, opens, highs, lows, closes = [], [], [], [], []
        amounts, volumes = [], []

        for yyyymmdd, o, h, low, c, amount, vol, _ in rec:
            dates.append(datetime.strptime(str(yyyymmdd), "%Y%m%d"))
            close_yuan = c * self._price_coeff
            open_yuan = o * self._price_coeff
            high_yuan = h * self._price_coeff
            low_yuan = low * self._price_coeff
            opens.append(open_yuan)
            highs.append(high_yuan)
            lows.append(low_yuan)
            closes.append(close_yuan)
            # vol 单位: A 股 raw×0.01=手; ETF raw×1.0=shares (需 ×100 转手)
            # 输出统一为手 (DB 口径)
            if self._vol_coeff == 1.0:
                # ETF/指数: raw 是 shares, 转手
                vol_lots = int(vol) // 100
            else:
                # A 股 / 债券: raw × 0.01 = 手
                vol_lots = int(vol * self._vol_coeff)
            volumes.append(vol_lots)
            # amt 自洽校验: amount_raw 与 close × shares 应在 5× 内
            # 部分 .day 文件个别记录损坏 (如 510300 的 2026-01-28, amt 偏 100×),
            # 此时用 close × shares × 100 替代 (元×手×100=元)
            shares = vol_lots * 100
            if shares > 0 and amount > 0:
                expected_amt = close_yuan * shares
                ratio = amount / expected_amt
                if ratio < 0.2 or ratio > 5.0:
                    # 异常 — 用估值替代并打 warn
                    print(
                        f"[tdx_offline] {yyyymmdd} amt 异常 (raw={amount:.0f}, "
                        f"expected≈{expected_amt:.0f}, ratio={ratio:.2f}), 用 close×shares 替代",
                        flush=True,
                    )
                    amounts.append(close_yuan * shares)
                    continue
            amounts.append(float(amount))

        df = pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "amount": amounts,
                "vol": volumes,
            },
            index=pd.DatetimeIndex(dates, name="date"),
        )
        df.sort_index(inplace=True)
        return df


def list_vipdoc_codes(tdx_home: str | os.PathLike) -> list[str]:
    """枚举通达信本地全市场代码 (沪+深, 去重).

    返回: ['000001', '000002', ..., '600000', '600001', ...]
    """
    home = Path(tdx_home)
    codes: set[str] = set()
    for mkt in ("sh", "sz"):
        lday = home / "vipdoc" / mkt / "lday"
        if not lday.is_dir():
            continue
        for p in lday.glob(f"{mkt}*.day"):
            stem = p.stem  # 'sh600000' / 'sz000001'
            if len(stem) == 8 and stem[:2] == mkt:
                codes.add(stem[2:])
    return sorted(codes)