"""TdxAdapter 单测: .day → KLineRow 字段映射, FileNotFoundError 透传, limit 忽略.

不依赖真实 hsjday.zip — 在 tmp_path 下合成最小化 .day + gbbq + tdx_home.
"""
from __future__ import annotations

import asyncio
import struct
from datetime import datetime
from pathlib import Path

import pytest

from app.clients.kline.tdx_adapter import TdxAdapter, _symbol_to_code
from app.clients.kline.types import FQT, PERIOD, SOURCE
from app.services.tdx_offline.gbbq_reader import HEXDUMP_KEYS, MASK32


# ------------------- _symbol_to_code -------------------


def test_symbol_to_code_strips_sh_prefix():
    assert _symbol_to_code("sh510500") == "510500"


def test_symbol_to_code_strips_sz_prefix():
    assert _symbol_to_code("sz159915") == "159915"


def test_symbol_to_code_passes_through_bare_code():
    assert _symbol_to_code("510500") == "510500"


# ------------------- TdxAdapter basic -------------------


def test_source_is_tdx():
    assert TdxAdapter().source == SOURCE.TDX


# ------------------- TdxAdapter.fetch with synthetic .day -------------------


def _round_function(key: bytes, num: int, j: int) -> int:
    """Inverse of pytdx reader's Feistel round (port from _decrypt_block)."""
    ebx16 = (num >> 16) & 0xFF
    eax = int.from_bytes(key[ebx16 * 4 + 0x448:ebx16 * 4 + 0x44C], "little")
    ebx24 = (num >> 24) & 0xFF
    eax = (eax + int.from_bytes(key[ebx24 * 4 + 0x48:ebx24 * 4 + 0x4C], "little")) & MASK32
    ebx8 = (num >> 8) & 0xFF
    eax ^= int.from_bytes(key[ebx8 * 4 + 0x848:ebx8 * 4 + 0x84C], "little")
    eax &= MASK32
    ebx0 = num & 0xFF
    eax = (eax + int.from_bytes(key[ebx0 * 4 + 0xC48:ebx0 * 4 + 0xC4C], "little")) & MASK32
    eax ^= int.from_bytes(key[j:j + 4], "little")
    eax &= MASK32
    return eax


def _encrypt_block(key: bytes, plaintext_block: bytes) -> bytes:
    """Inverse of _decrypt_block: encrypt 8 plaintext bytes to 8 ciphertext bytes."""
    final_numold = int.from_bytes(plaintext_block[0:4], "little")
    final_num = int.from_bytes(plaintext_block[4:8], "little")
    numold = (final_numold ^ int.from_bytes(key[0:4], "little")) & MASK32
    num = final_num
    for j in range(4, 0x44, 4):
        old_num = numold
        old_numold = (num ^ _round_function(key, numold, j)) & MASK32
        num = old_num
        numold = old_numold
    enc_0_4 = ((num ^ int.from_bytes(key[0x44:0x48], "little")) & MASK32).to_bytes(4, "little")
    enc_4_8 = numold.to_bytes(4, "little")
    return enc_0_4 + enc_4_8


def _write_synthetic_gbbq(path: Path, code: str) -> None:
    """合成最小化 gbbq 文件: 1 条 cat=1 / fenhong=0 事件 (对 qfq 路径而言为 no-op).

    事件日设为远古日 (2020-01-01), 早于所有 .day 数据, 这样 qfq 复权因子=1.0
    (apply_fq 内 cat=1 且 fenhong=0 时跳过该事件).

    加密算法反向 port 自 _decrypt_block (16 轮 Feistel + 头尾 XOR).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    market = "sh"  # 简化: 测试只用 sh
    target_d = (
        bytes([1 if market == "sh" else 0])  # d[0]: market
        + code.encode("ascii")[:6].ljust(6, b"\x00")  # d[1:7]: code (6 字)
        + b"\x00"  # d[7]: padding
        + struct.pack("<I", 20200101)  # d[8:12]: date=20200101 LE
        + b"\x01"  # d[12]: cat=1 (除权除息)
        + b"\x00\x00\x00"  # d[13:16]: first 3 bytes of f1=0.0
        + b"\x00"  # d[16]: last byte of f1
        + b"\x00\x00\x00\x00"  # d[17:21]: f2=0.0
        + b"\x00\x00\x00"  # d[21:24]: first 3 bytes of f3
        + b"\x00"  # d[24]: last byte of f3
        + b"\x00\x00\x00\x00"  # d[25:29]: f4=0.0
    )
    assert len(target_d) == 29, f"target_d should be 29 bytes, got {len(target_d)}"

    enc_body = b""
    for i in range(3):  # 3 × 8-byte encrypted blocks = 24 bytes
        enc_body += _encrypt_block(HEXDUMP_KEYS, target_d[i*8:(i+1)*8])
    enc_body += target_d[24:29]  # 5 raw bytes appended

    gbbq_data = struct.pack("<I", 1) + enc_body  # count=1 + body
    path.write_bytes(gbbq_data)


def _write_synthetic_day(path: Path, code: str, n_days: int = 3) -> None:
    """合成最小化 .day 文件: n_days 条记录, 第 i 天日期 = 2026-09-0(i+1).

    字段格式 (struct.iter_unpack("<IIIIIfII")) 与 day_reader.py:160 注释一致.

    注: vol 字段以"股"写入 (A_STOCK vol_coeff=0.01 后变手, ETF vol_coeff=1.0
    后仍是 shares). 这里 vol=10000 raw → 100 手 → TdxAdapter ×100 = 10000 股,
    与断言 `r.volume == 100 * 100` (100 手 × 100 = 10000 股) 对应.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        for i in range(n_days):
            date_int = int((datetime(2026, 9, 1 + i)).strftime("%Y%m%d"))
            open_p = 1000
            high_p = 1100
            low_p = 900
            close_p = 1050
            # amount 取 105000 以满足 day_reader 自洽校验:
            # ratio = amount / (close_yuan × shares) = 105000 / (10.5 × 10000) = 1.0 ✓
            amount = 105_000.0
            vol = 10000  # raw 股 → 100 手 → TdxAdapter ×100 = 10000 股
            f.write(struct.pack("<IIIIIfII", date_int, open_p, high_p, low_p,
                                close_p, amount, vol, 0))


def _setup_minimal_tdx_home(tmp_path: Path, code: str = "510500") -> Path:
    """铺最小化 tdx_home: vipdoc/sh/lday/sh600519.day + T0002/hq_cache/gbbq.

    qfq 路径必须 gbbq 至少含 1 条事件 (apply_fq 在 events 为空时硬报错);
    这里塞一条 cat=1 / fenhong=0 的远古事件作为 qfq 路径的"哑事件".
    """
    home = tmp_path / "tdx"
    market_dir = home / "vipdoc" / "sh" / "lday"
    _write_synthetic_day(market_dir / "sh600519.day", "600519", n_days=5)
    _write_synthetic_gbbq(home / "T0002" / "hq_cache" / "gbbq", "600519")
    return home


def test_fetch_returns_klinerows_descending():
    home = _setup_minimal_tdx_home(Path("/tmp/test_tdx_adapter_fetch"))

    async def _run():
        adapter = TdxAdapter(tdx_home=home)
        rows = await adapter.fetch("sh600519", PERIOD.DAY, FQT.QFQ, limit=99999)
        return rows

    rows = asyncio.run(_run())
    assert len(rows) == 5
    # 按 date 降序
    dates = [r.date for r in rows]
    assert dates == sorted(dates, reverse=True)
    # 字段映射: open/high/low/close × 0.01, amount 经自洽校验后保留 (vol ×100 = 股)
    r = rows[0]
    assert r.open == pytest.approx(1000 * 0.01)
    assert r.high == pytest.approx(1100 * 0.01)
    assert r.low == pytest.approx(900 * 0.01)
    assert r.close == pytest.approx(1050 * 0.01)
    assert r.amount == pytest.approx(105_000)  # 经 day_reader 自洽校验后保留
    assert r.volume == 100 * 100  # 手 → 股


def test_fetch_raises_filenotodo_when_missing():
    home = Path("/tmp/test_tdx_adapter_missing") / "tdx"
    home.mkdir(parents=True, exist_ok=True)
    # 不写任何 .day / gbbq, 期望 fetch_local_day 抛 FileNotFoundError (透传)

    async def _run():
        adapter = TdxAdapter(tdx_home=home)
        await adapter.fetch("sh600519", PERIOD.DAY, FQT.QFQ, limit=99999)

    with pytest.raises(FileNotFoundError):
        asyncio.run(_run())


def test_fetch_ignores_limit():
    """spec: limit 参数被忽略, .day 全集返回."""
    home = _setup_minimal_tdx_home(Path("/tmp/test_tdx_adapter_limit"))

    async def _run():
        adapter = TdxAdapter(tdx_home=home)
        rows_limit1 = await adapter.fetch("sh600519", PERIOD.DAY, FQT.QFQ, limit=1)
        rows_limit999 = await adapter.fetch("sh600519", PERIOD.DAY, FQT.QFQ, limit=99999)
        return rows_limit1, rows_limit999

    rows_limit1, rows_limit999 = asyncio.run(_run())
    # 两个调用返同样的全集 (5 行)
    assert len(rows_limit1) == 5
    assert len(rows_limit999) == 5
    assert [r.date for r in rows_limit1] == [r.date for r in rows_limit999]