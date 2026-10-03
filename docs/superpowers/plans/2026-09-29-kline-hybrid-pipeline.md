# K 线 Hybrid Pipeline 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 K 线抓取 hybrid 编排器（TDX 本地优先 + 网络补 gap），消除 source=online/offline 互斥模式，TDX 不必天天下载。

**Architecture:** 新增 `KLinePipeline`（4 阶段：TDX 探测 → 网络补 gap → 纯网络兜底 → 合并切片），新增 `TdxAdapter`（实现 `KLineAdapter` 协议，包 `fetch_local_day`）。`kline_service` 三入口（spider/refresh/backfill）改走 pipeline，其余不动。前端/Api 0 改动。

**Tech Stack:** FastAPI / Pydantic / MongoDB / pandas / pytest。无需新依赖。

---

## Global Constraints

来源 spec `2026-09-29-kline-hybrid-pipeline-design.md`，逐字搬运：

- 不引入新 pip / pnpm 依赖。
- backend `app/services/`、`app/clients/`、`app/repositories/` 默认只读 —— 仅按 spec 列入改动清单的函数/字段可改。
- 跨 task 改动必须独立 commit；commit message 用 Conventional Commits。
- 单一 commit 收尾：`feat(kline): hybrid pipeline with TDX-first + network gap-fill`。
- `source=offline` 路径走 `kline_by_sec_code_offline`，行为完全保留（既有 0 回归）。
- `source=online` 新行为：TDX-first + 网络补 gap（Sina → Tencent → Eastmoney）。
- TdxAdapter 不抛业务异常（除 `FileNotFoundError`）—— 错误转 `HybridFetchResult` 字段。
- Pipeline 日志格式：`[kline/pipeline] phase1=tdx rows=N max=DATE gap=D status=...`。
- 测试运行：`cd backend && pytest -q && ruff check app`。
- 测试 fixture：复用 `tests/fixtures/` 已有目录；TDX 单测用合成 .day 文件（tmp_path），无需真 zip。

---

## File Structure

| 路径 | 状态 | 职责 |
|---|---|---|
| `backend/app/clients/kline/types.py` | 改 | `+SOURCE.TDX = "tdx"` |
| `backend/app/clients/kline/__init__.py` | 改 | `+TdxAdapter` export |
| `backend/app/clients/kline/tdx_adapter.py` | 新建 | `resolve_tdx_home()` + `TdxAdapter` + `_df_to_klinerows()` + `_symbol_to_code()` |
| `backend/app/services/tdx_offline/fetcher.py` | 改 | `_resolve_tdx_home` → import from `tdx_adapter`（仅 1 行） |
| `backend/app/config.py` | 改 | `+kline_network_chain` 字段 |
| `backend/app/services/kline_pipeline.py` | 新建 | `HybridFetchResult` + `KLinePipeline.fetch_hybrid()` + `fetch_pure_network()` |
| `backend/app/services/kline_service.py` | 改 | `__init__` 用 pipeline；`spider_kline_data`/`refresh_kline_data`/`backfill_kline_window` 三入口改造；`_to_legacy` 桥接 |
| `backend/tests/test_kline_adapters.py` | 改 | `+test_source_enum_includes_tdx` |
| `backend/tests/test_tdx_day_reader_regression.py` | 改 | `+test_resolve_tdx_home_importable_from_kline_package` |
| `backend/tests/test_tdx_adapter.py` | 新建 | 3 必写单测 |
| `backend/tests/test_config_kline_chain.py` | 新建 | `test_kline_network_chain_default` + env override |
| `backend/tests/test_hybrid_pipeline.py` | 新建 | 6 必写单测 |
| `backend/tests/test_kline_service_hybrid.py` | 新建 | 2 必写集成 |
| `backend/README.md` | 改 | 更新 KLine 多源章节 |

任务-文件映射（防止越界）：

```
Task 1: types.py + __init__.py + tests/test_kline_adapters.py
Task 2: tdx_offline/fetcher.py + tests/test_tdx_day_reader_regression.py + clients/kline/tdx_adapter.py
Task 3: clients/kline/tdx_adapter.py (扩展) + tests/test_tdx_adapter.py
Task 4: config.py + tests/test_config_kline_chain.py + services/kline_pipeline.py + tests/test_hybrid_pipeline.py
Task 5: services/kline_service.py + tests/test_kline_service_hybrid.py
Task 6: backend/README.md
```

---

## Task 1: 加 SOURCE.TDX 枚举值 + 回归测试

**Files:**
- Modify: `backend/app/clients/kline/types.py:26-29`
- Modify: `backend/app/clients/kline/__init__.py:1-20`
- Modify: `backend/tests/test_kline_adapters.py:1-50`（在文件末尾追加 1 个测试）

**Interfaces:**
- Consumes: 既有 `SOURCE` 枚举
- Produces: `SOURCE.TDX = "tdx"`（供后续 Task 3 的 `TdxAdapter.source` 使用）

### Steps

- [ ] **Step 1: 写失败的回归测试**

打开 `backend/tests/test_kline_adapters.py`，在文件末尾追加：

```python
# ------------------- SOURCE.TDX -------------------


def test_source_enum_includes_tdx():
    from app.clients.kline.types import SOURCE
    assert SOURCE.TDX == "tdx"
    assert SOURCE("tdx") is SOURCE.TDX
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_kline_adapters.py::test_source_enum_includes_tdx -v`
Expected: FAIL with `AttributeError: type object 'SOURCE' has no attribute 'TDX'`

- [ ] **Step 3: 在 types.py 加 TDX 枚举值**

打开 `backend/app/clients/kline/types.py`，把：

```python
class SOURCE(str, Enum):
    TENCENT = "tencent"
    SINA = "sina"
    EASTMONEY = "eastmoney"
```

改为：

```python
class SOURCE(str, Enum):
    TENCENT = "tencent"
    SINA = "sina"
    EASTMONEY = "eastmoney"
    TDX = "tdx"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_kline_adapters.py::test_source_enum_includes_tdx -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd D:/vscodepro/fin-app
git add backend/app/clients/kline/types.py backend/tests/test_kline_adapters.py
git commit -m "feat(kline): add SOURCE.TDX enum value for local TDX adapter"
```

---

## Task 2: 提取 `_resolve_tdx_home` 到 `clients/kline/` 包

**Files:**
- Create: `backend/app/clients/kline/tdx_adapter.py`（仅 `resolve_tdx_home` 函数 + 模块 docstring）
- Modify: `backend/app/services/tdx_offline/fetcher.py:68-75`（替换为 import）
- Modify: `backend/tests/test_tdx_day_reader_regression.py:1-87`（追加 1 个测试）

**Interfaces:**
- Consumes: `app.config.get_settings`、`os.environ`
- Produces: `app.clients.kline.tdx_adapter.resolve_tdx_home(tdx_home) -> Path`（保留原 `_resolve_tdx_home` 的三级 fallback 语义）

### Steps

- [ ] **Step 1: 写失败的回归测试**

打开 `backend/tests/test_tdx_day_reader_regression.py`，在文件末尾追加：

```python
def test_resolve_tdx_home_importable_from_kline_package():
    """Spec 要求 `_resolve_tdx_home` 从 tdx_offline 迁到 clients/kline/tdx_adapter.py.
    旧入口（tdx_offline/fetcher.py）改为 import shim, 但 resolve_tdx_home 自身在
    clients/kline 下独立可用, 不依赖 tdx_offline 内部状态."""
    from app.clients.kline.tdx_adapter import resolve_tdx_home
    p = resolve_tdx_home("/tmp/fake_tdx_home")
    assert p == Path("/tmp/fake_tdx_home")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_tdx_day_reader_regression.py::test_resolve_tdx_home_importable_from_kline_package -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.clients.kline.tdx_adapter'`

- [ ] **Step 3: 创建 `tdx_adapter.py`（仅 resolve_tdx_home + docstring）**

新建 `backend/app/clients/kline/tdx_adapter.py`：

```python
"""本地通达信 (TDX) K 线适配器.

职责:
    - resolve_tdx_home(): 三级 fallback 解析 TDX_HOME 路径
    - TdxAdapter: 实现 KLineAdapter 协议, 包 fetch_local_day (Task 3 扩展)

设计: 本模块迁出自 tdx_offline/fetcher.py 的 _resolve_tdx_home, 让 KLinePipeline
能在不依赖 tdx_offline 子包的情况下使用同一路径解析逻辑. tdx_offline 改为
import shim, 保持向后兼容.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings


def resolve_tdx_home(tdx_home: str | os.PathLike | None) -> Path:
    """解析 TDX 主目录. 三级 fallback: 入参 > settings.tdx_home > TDX_HOME 环境变量 > 默认.

    默认值 C:\\zd_zxzq_gm 与 tdx_offline 既有契约一致.
    """
    if tdx_home:
        return Path(tdx_home)
    settings = get_settings()
    home = settings.tdx_home or os.environ.get("TDX_HOME") or r"C:\zd_zxzq_gm"
    return Path(home)
```

- [ ] **Step 4: 改 `tdx_offline/fetcher.py` 为 import shim**

打开 `backend/app/services/tdx_offline/fetcher.py`，删掉 line 66-75（`# tdx_home 解析 (三级 fallback)` 整块，包含 `_resolve_tdx_home` 函数定义）。

在该位置之前/之后插入：

```python
# tdx_home 解析 (三级 fallback) — shim, 实际实现在 clients/kline/tdx_adapter.py
# 保留旧符号名 _resolve_tdx_home 让本包内其他调用方无需改动.
from app.clients.kline.tdx_adapter import resolve_tdx_home as _resolve_tdx_home  # noqa: E402
```

确保 `_resolve_tdx_home` 在文件后续被 `fetch_local_day` / `list_codes` 调用（line 129 / 148）时仍能找到。删掉原 `get_settings` 在 line 73 的引用（迁移到 `tdx_adapter.py` 后，`tdx_offline/fetcher.py` 已无直接 `tdx_home` 解析代码，`os` 还在用，import 不动）。

- [ ] **Step 5: 运行测试确认通过 + 既有测试无回归**

Run:
```bash
cd D:/vscodepro/fin-app/backend && \
  pytest tests/test_tdx_day_reader_regression.py::test_resolve_tdx_home_importable_from_kline_package -v && \
  pytest tests/test_tdx_day_reader_regression.py -v
```
Expected: 新测试 PASS；既有 4 个测试在 `hsjday.zip` 缺失时 SKIP（既有行为），存在时 PASS。

- [ ] **Step 6: Commit**

```bash
cd D:/vscodepro/fin-app
git add backend/app/clients/kline/tdx_adapter.py \
        backend/app/services/tdx_offline/fetcher.py \
        backend/tests/test_tdx_day_reader_regression.py
git commit -m "refactor(kline): extract resolve_tdx_home to clients/kline package"
```

---

## Task 3: 实现 TdxAdapter + 3 个单测

**Files:**
- Modify: `backend/app/clients/kline/tdx_adapter.py`（扩展 Task 2 创建的文件）
- Modify: `backend/app/clients/kline/__init__.py:1-20`
- Create: `backend/tests/test_tdx_adapter.py`

**Interfaces:**
- Consumes: `app.services.tdx_offline.fetch_local_day`、`app.clients.kline.types.{KLineRow, PERIOD, FQT, SOURCE}`
- Produces:
  - `TdxAdapter` 类（实现既有 `KLineAdapter` Protocol）
    - `source: SOURCE = SOURCE.TDX`
    - `__init__(tdx_home=None)`
    - `async fetch(symbol, period, fqt, limit) -> list[KLineRow]`（按 date 降序）
  - `_symbol_to_code(symbol: str) -> str`（模块级 helper）

### Steps

- [ ] **Step 1: 写失败的 3 个测试**

新建 `backend/tests/test_tdx_adapter.py`：

```python
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


def _write_synthetic_day(path: Path, code: str, n_days: int = 3) -> None:
    """合成最小化 .day 文件: n_days 条记录, 第 i 天日期 = 2026-09-0(i+1).

    字段格式 (struct.iter_unpack("<IIIIIfII")) 与 day_reader.py:160 注释一致.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        for i in range(n_days):
            date_int = int((datetime(2026, 9, 1 + i)).strftime("%Y%m%d"))
            open_p = 1000
            high_p = 1100
            low_p = 900
            close_p = 1050
            amount = 1_000_000
            vol = 100  # 手
            f.write(struct.pack("<IIIIIfII", date_int, open_p, high_p, low_p,
                                close_p, amount, vol, 0))


def _setup_minimal_tdx_home(tmp_path: Path, code: str = "510500") -> Path:
    """铺最小化 tdx_home: vipdoc/sh/lday/sh600519.day (qfq 不需要事件, 用 bfq 路径)."""
    home = tmp_path / "tdx"
    market_dir = home / "vipdoc" / "sh" / "lday"
    _write_synthetic_day(market_dir / "sh600519.day", "600519", n_days=5)
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
    # 字段映射: open/high/low/close × 0.01, amount 原值, vol(手) → 股 (×100)
    r = rows[0]
    assert r.open == pytest.approx(1000 * 0.01)
    assert r.high == pytest.approx(1100 * 0.01)
    assert r.low == pytest.approx(900 * 0.01)
    assert r.close == pytest.approx(1050 * 0.01)
    assert r.amount == pytest.approx(1_000_000)
    assert r.volume == 100 * 100  # 手 → 股


def test_fetch_raises_filenotodo_when_missing():
    home = Path("/tmp/test_tdx_adapter_missing") / "tdx"
    home.mkdir(parents=True, exist_ok=True)
    # 不写任何 .day, 期望 fetch_local_day 抛 FileNotFoundError (透传)

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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_tdx_adapter.py -v`
Expected: 全部 FAIL（`ImportError: cannot import name 'TdxAdapter'` 等）。

- [ ] **Step 3: 实现 TdxAdapter（扩展 tdx_adapter.py）**

打开 `backend/app/clients/kline/tdx_adapter.py`，在末尾追加：

```python
import asyncio
from typing import TYPE_CHECKING

from app.clients.kline.types import FQT, KLineRow, PERIOD, SOURCE

if TYPE_CHECKING:
    pass


def _symbol_to_code(symbol: str) -> str:
    """sh510500 / sz159915 / bj920982 → 6 位代码; 已是裸代码则原样返回."""
    if not symbol:
        return symbol
    if len(symbol) >= 3 and symbol[:2] in ("sh", "sz", "bj"):
        return symbol[2:]
    return symbol


def _df_to_klinerows(df) -> list[KLineRow]:
    """fetch_local_day 返回的 DataFrame → KLineRow 列表, 按 date 降序.

    字段映射:
        df.amount (元) → row.amount (元)
        df.vol    (手) → row.volume (股, ×100)
    """
    rows = [
        KLineRow(
            date=ts.strftime("%Y-%m-%d"),
            open=float(row["open"]),
            close=float(row["close"]),
            high=float(row["high"]),
            low=float(row["low"]),
            volume=int(row["vol"]) * 100,
            amount=float(row["amount"]) if row.get("amount") is not None
            and not (isinstance(row["amount"], float) and row["amount"] != row["amount"])
            else None,
        )
        for ts, row in df.iterrows()
    ]
    rows.sort(key=lambda r: r.date, reverse=True)
    return rows


class TdxAdapter:
    """KLineAdapter 协议 — 本地通达信 vipdoc+gbbq.

    fetch_local_day 内部已处理: 复权 (qfq 默认) + 升序 DataFrame.
    本适配器仅做: symbol → code, DataFrame → KLineRow, 降序排序.
    limit 参数被忽略 — .day 文件是全集, 切片由调用方按日期做.
    """

    source = SOURCE.TDX

    def __init__(self, tdx_home: str | os.PathLike | None = None):
        self._tdx_home = resolve_tdx_home(tdx_home)

    async def fetch(self, symbol: str, period: PERIOD, fqt: FQT,
                    limit: int) -> list[KLineRow]:
        """symbol='sh510500' → code='510500'; qfq 复权; 返降序 KLineRow 列表.

        Raises:
            FileNotFoundError: 本地 .day 或 gbbq 缺失 (透传, 不包).
        """
        # period / fqt 在 v1 仅支持 DAY+QFQ; 其它组合走 fetch_local_day 默认 (qfq).
        del period, fqt, limit  # 未使用
        code = _symbol_to_code(symbol)
        from app.services.tdx_offline import fetch_local_day
        df = await asyncio.to_thread(fetch_local_day, code, "qfq", self._tdx_home)
        return _df_to_klinerows(df)
```

- [ ] **Step 4: 加 `__init__.py` export**

打开 `backend/app/clients/kline/__init__.py`，在已有 `from ... import ...` 列表中加入：

```python
from app.clients.kline.tdx_adapter import TdxAdapter  # noqa: E402,F401
```

（具体位置视现有 __init__.py 风格而定——若用 `__all__` 列表，则同时加入字符串 `"TdxAdapter"`。）

- [ ] **Step 5: 运行测试确认通过**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_tdx_adapter.py -v`
Expected: 全部 9 个测试 PASS（3 个 `_symbol_to_code` + 1 个 `source` + 3 个 fetch 行为）。

- [ ] **Step 6: 跑既有测试确认无回归**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_kline_adapters.py tests/test_kline_gap_backfill.py tests/test_tdx_day_reader_regression.py -v`
Expected: 既有测试 PASS / SKIP（依既有逻辑）。

- [ ] **Step 7: Commit**

```bash
cd D:/vscodepro/fin-app
git add backend/app/clients/kline/tdx_adapter.py \
        backend/app/clients/kline/__init__.py \
        backend/tests/test_tdx_adapter.py
git commit -m "feat(kline): TdxAdapter with KLineRow output and descending sort"
```

---

## Task 4: 加 `kline_network_chain` 配置 + 实现 KLinePipeline + 6 个单测

**Files:**
- Modify: `backend/app/config.py:38-50`
- Modify: `backend/app/services/kline_service.py:89-117`（仅 `__init__`，加 `self._pipeline = ...`，**不动既有方法**——确保 Task 5 之前的中间状态可独立运行）
- Create: `backend/app/services/kline_pipeline.py`
- Create: `backend/tests/test_config_kline_chain.py`
- Create: `backend/tests/test_hybrid_pipeline.py`

**Interfaces:**
- Consumes:
  - `app.clients.kline.factory.build_aggregator(primary, fallbacks) -> KLineAggregator`
  - `app.clients.kline.types.{PERIOD, FQT}`
  - `app.clients.kline.tdx_adapter.TdxAdapter`
- Produces:
  - `app.config.Settings.kline_network_chain: str`（默认 `"sina,tencent,eastmoney"`，env `FIN_KLINE_NETWORK_CHAIN`）
  - `app.services.kline_pipeline.HybridFetchResult`（dataclass，字段见 spec §数据结构）
  - `app.services.kline_pipeline.KLinePipeline`:
    - `__init__(network_chain_cfg: list[str], fallback_chain_cfg: list[str])`
    - `async fetch_hybrid(code, market, symbol, period, fqt, limit) -> HybridFetchResult`
    - `async fetch_pure_network(symbol, period, fqt, limit) -> HybridFetchResult`（仅 Phase 3，供 kline_service 增量窗口错位时跳过 TDX 重抓）
    - `async aclose()`

### Steps

- [ ] **Step 1: 写失败的 config 测试**

新建 `backend/tests/test_config_kline_chain.py`：

```python
"""kline_network_chain 配置字段测试."""
from __future__ import annotations

import os
from unittest.mock import patch

from app.config import Settings


def test_kline_network_chain_default():
    s = Settings()
    assert s.kline_network_chain == "sina,tencent,eastmoney"


def test_kline_network_chain_env_override():
    with patch.dict(os.environ, {"FIN_KLINE_NETWORK_CHAIN": "tencent,sina,eastmoney"}):
        s = Settings()
        assert s.kline_network_chain == "tencent,sina,eastmoney"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_config_kline_chain.py -v`
Expected: 全部 FAIL（`AttributeError: 'Settings' object has no attribute 'kline_network_chain'`）。

- [ ] **Step 3: 加 config 字段**

打开 `backend/app/config.py`，在 `kline_fallbacks` 字段（line 47-50）后追加：

```python
    # Hybrid 模式下, TDX gap 补抓的网络源链顺序. 顺序敏感, 先轻后全.
    # 增量场景用此链覆盖最近 gap; TDX 不可用时 kline_primary + kline_fallbacks 兜底.
    kline_network_chain: str = Field(
        default="sina,tencent,eastmoney",
        description="Hybrid 模式下, TDX gap 补抓的网络源链顺序. 顺序敏感, 先轻后全.",
        validation_alias=AliasChoices("FIN_KLINE_NETWORK_CHAIN", "KLINE_NETWORK_CHAIN"),
    )
```

- [ ] **Step 4: 运行 config 测试确认通过**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_config_kline_chain.py -v`
Expected: 2 个 PASS。

- [ ] **Step 5: 写失败的 6 个 pipeline 测试**

新建 `backend/tests/test_hybrid_pipeline.py`：

```python
"""KLinePipeline 单测: 4 阶段 + 边界 + 配置驱动顺序.

通过 monkeypatch 替换 TdxAdapter / KLineAggregator, 不发真实网络, 不读真实 .day.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.factory import build_aggregator
from app.clients.kline.sina_adapter import SinaAdapter
from app.clients.kline.tencent_adapter import TencentAdapter
from app.clients.kline.types import KLineRow
from app.services.kline_pipeline import HybridFetchResult, KLinePipeline


def _row(date: str, source_tag: str = "any", price: float = 1.0) -> KLineRow:
    return KLineRow(date=date, open=price, close=price, high=price,
                    low=price, volume=100, amount=None)


def _make_pipeline_with_mocks(
    monkeypatch,
    tdx_rows: list[KLineRow] | None,
    tdx_available: bool = True,
    network_rows_by_source: dict[str, list[KLineRow]] | None = None,
) -> KLinePipeline:
    """构造 Pipeline: mock TdxAdapter, mock KLineAggregator 行为.

    network_rows_by_source 形如 {"sina": [...], "tencent": [...]} — 提供哪个 key 就让
    该源返行; 缺省源返空 (模拟失败).
    """
    # 1) mock TdxAdapter
    fake_tdx_adapter = MagicMock()
    fake_tdx_adapter.source = MagicMock(value="tdx")
    fake_tdx_adapter.fetch = AsyncMock(return_value=tdx_rows or [])
    fake_tdx_adapter.aclose = AsyncMock()

    # 2) mock KLineAggregator — 用真实 build_aggregator 但替换内部 adapters
    network_rows_by_source = network_rows_by_source or {}

    def _adapter_factory(source_name: str):
        adapter = MagicMock()
        adapter.source = MagicMock(value=source_name)
        adapter.fetch = AsyncMock(return_value=network_rows_by_source.get(source_name, []))
        adapter.aclose = AsyncMock()
        return adapter

    monkeypatch.setattr(
        "app.services.kline_pipeline.build_aggregator",
        lambda primary, fallbacks: _FakeAggregator(primary, fallbacks, _adapter_factory),
    )

    pipeline = KLinePipeline(
        network_chain_cfg=["sina", "tencent", "eastmoney"],
        fallback_chain_cfg=["tencent", "eastmoney", "sina"],
    )
    # 替换 _gap_chain / _pure_chain 为 mock
    pipeline._gap_chain = _FakeAggregator(
        ["sina", "tencent", "eastmoney"], ["tencent", "eastmoney"], _adapter_factory,
    )
    pipeline._pure_chain = _FakeAggregator(
        ["tencent", "eastmoney", "sina"], ["eastmoney", "sina"], _adapter_factory,
    )
    pipeline._tdx_adapter = fake_tdx_adapter
    return pipeline


class _FakeAggregator(KLineAggregator):
    """用 _adapter_factory 替换内部 adapter 的 fake aggregator."""

    def __init__(self, primary: str, fallbacks: list[str], adapter_factory):
        self._primary = adapter_factory(primary)
        self._fallbacks = [adapter_factory(f) for f in fallbacks]

    @property
    def primary(self):
        return self._primary

    @property
    def fallbacks(self):
        return self._fallbacks

    async def fetch(self, symbol, period, fqt, limit):
        from app.clients.kline.types import FetchResult, SOURCE
        chain = [self._primary, *self._fallbacks]
        for idx, ad in enumerate(chain):
            rows = await ad.fetch(symbol, period, fqt, limit)
            if rows:
                return FetchResult(
                    rows=rows,
                    source=ad.source,
                    fell_back=idx > 0,
                )
        return FetchResult(rows=[], source=None, fell_back=True,
                           error="all sources empty")

    async def aclose(self):
        await self._primary.aclose()
        for f in self._fallbacks:
            await f.aclose()


# ------------------- Phase 1 + Phase 2 -------------------


def test_phase1_gap_zero_skips_network():
    """TDX 有数据且 max_date == today → 不调网络链."""
    today_str = date.today().strftime("%Y-%m-%d")
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(today_str)],
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert isinstance(result, HybridFetchResult)
    assert result.tdx_available is True
    assert result.network_attempted is False
    assert result.gap_days == 0
    assert len(result.rows) == 1
    assert result.sources_used == ["tdx"]


def test_phase2_gap_positive_fills_via_sina():
    """TDX max_date = today - 4 → gap=4 → 网络链补 5 行 (sina)."""
    from datetime import timedelta
    tdx_max = (date.today() - timedelta(days=4)).strftime("%Y-%m-%d")
    today_str = date.today().strftime("%Y-%m-%d")
    sina_rows = [
        _row((date.today() - timedelta(days=i)).strftime("%Y-%m-%d"))
        for i in range(5)
    ]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(tdx_max)],
        network_rows_by_source={"sina": sina_rows},
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is True
    assert result.gap_days == 4
    assert result.network_attempted is True
    assert "sina" in result.sources_used
    assert "tdx" in result.sources_used
    # 合并: tdx 1 行 + sina 5 行 = 6 行 (同日期去重不重, 因为 tdx_max 是 4 天前)
    assert len(result.rows) == 6
    # 按日期降序
    dates = [r.date for r in result.rows]
    assert dates == sorted(dates, reverse=True)


def test_phase1_empty_falls_to_pure_network():
    """TDX 不可用 → Phase 3 纯网络 (fallback_chain_cfg)."""
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[],
        tdx_available=False,
        network_rows_by_source={"tencent": [_row("2026-09-29")]},
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is False
    assert result.gap_days is None
    assert result.network_attempted is True  # phase3 也算 attempt
    assert "tencent" in result.sources_used
    assert "tdx" not in result.sources_used
    assert len(result.rows) == 1


def test_phase2_all_empty_falls_back_to_tdx():
    """TDX 有数据, 网络链全空 → 仍返 TDX rows, network_error 记录."""
    tdx_max = "2026-09-25"
    tdx_rows = [_row(tdx_max)]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=tdx_rows,
        network_rows_by_source={},  # 所有网络源都返空
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert result.tdx_available is True
    assert result.network_attempted is True
    assert result.network_error is not None
    assert len(result.rows) == 1
    assert result.sources_used == ["tdx"]


def test_phase2_falls_back_to_tencent_when_sina_empty():
    """Phase 2 网络链 sina 空, tencent 返行 → fell_back 到 tencent."""
    from datetime import timedelta
    tdx_max = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
    tencent_rows = [_row(date.today().strftime("%Y-%m-%d"))]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(tdx_max)],
        network_rows_by_source={"tencent": tencent_rows},  # sina 缺省 = 空
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert "tencent" in result.sources_used
    assert "sina" not in result.sources_used
    assert result.gap_days == 3


def test_network_chain_order_respects_config():
    """spec: 默认 sina,tencent,eastmoney 顺序, 即使 sina 返空也按顺序试."""
    from datetime import timedelta
    tdx_max = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    eastmoney_rows = [_row(date.today().strftime("%Y-%m-%d"))]
    pipeline = _make_pipeline_with_mocks(
        tdx_rows=[_row(tdx_max)],
        network_rows_by_source={"eastmoney": eastmoney_rows},
        # sina/tencent 都没返, 验证确实跳到 eastmoney
    )

    async def _run():
        return await pipeline.fetch_hybrid(
            code="510500", market=1, symbol="sh510500",
            period="day", fqt="qfq", limit=90,
        )

    result = asyncio.run(_run())
    assert "eastmoney" in result.sources_used
    # sources_used 顺序反映实际触发顺序
    assert result.sources_used.index("eastmoney") > result.sources_used.index("tdx")
```

- [ ] **Step 6: 运行测试确认失败**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_hybrid_pipeline.py -v`
Expected: 全部 FAIL（`ModuleNotFoundError: No module named 'app.services.kline_pipeline'`）。

- [ ] **Step 7: 实现 KLinePipeline + HybridFetchResult**

新建 `backend/app/services/kline_pipeline.py`：

```python
"""K 线 Hybrid 编排器: TDX 优先 + 网络补 gap + 纯网络兜底.

设计契约 (见 docs/superpowers/specs/2026-09-29-kline-hybrid-pipeline-design.md):
    Phase 1: TdxAdapter.fetch() — 读本地 .day, 失败降级
    Phase 2: 网络链 (默认 sina,tencent,eastmoney) 补 gap
    Phase 3: 纯网络链 (kline_primary + kline_fallbacks) — TDX 不可用时兜底
    Phase 4: 合并 + 切片 [:limit]
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List

from app.clients.kline.factory import build_aggregator
from app.clients.kline.tdx_adapter import TdxAdapter
from app.clients.kline.types import FQT, KLineRow, PERIOD


@dataclass
class HybridFetchResult:
    """Hybrid 编排器顶层返回. 不复用 FetchResult (后者是单源链设计)."""
    rows: list[KLineRow] = field(default_factory=list)            # 合并后, 降序
    sources_used: list[str] = field(default_factory=list)
    tdx_rows_count: int = 0
    network_rows_count: int = 0
    gap_days: int | None = None
    network_attempted: bool = False
    network_error: str | None = None
    tdx_available: bool = True


class KLinePipeline:
    """TDX-first + 网络补 gap 编排器."""

    def __init__(self, network_chain_cfg: list[str], fallback_chain_cfg: list[str]):
        # 网络补 gap 链 — 默认 sina,tencent,eastmoney
        self._gap_chain = build_aggregator(
            primary=network_chain_cfg[0],
            fallbacks=network_chain_cfg[1:],
        )
        # TDX 不可用时的纯网络兜底链 — 默认 tencent,eastmoney,sina
        self._pure_chain = build_aggregator(
            primary=fallback_chain_cfg[0],
            fallbacks=fallback_chain_cfg[1:],
        )
        self._tdx_adapter = TdxAdapter()

    async def fetch_hybrid(
        self,
        code: str,
        market: int | None,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> HybridFetchResult:
        # ---- Phase 1: TDX 探测 ----
        tdx_rows, tdx_available, tdx_err = await self._phase1_tdx(symbol, period, fqt, limit)
        if tdx_err:
            print(f"[kline/pipeline] phase1=tdx error={tdx_err}", flush=True)
        print(
            f"[kline/pipeline] phase1=tdx rows={len(tdx_rows)} "
            f"status={'ok' if tdx_available else 'unavailable'}",
            flush=True,
        )

        # ---- Phase 3 (TDX 不可用时) ----
        if not tdx_available:
            return await self._run_pure_network(symbol, period, fqt, limit)

        # ---- Phase 2 (TDX 有数据) ----
        if not tdx_rows:
            # TDX 存在但全空 — 退回 Phase 3
            print(
                "[kline/pipeline] phase1=tdx rows=0 status=empty → phase3=pure-network",
                flush=True,
            )
            return await self._run_pure_network(symbol, period, fqt, limit)

        tdx_max_date = tdx_rows[0].date  # 降序
        try:
            tdx_last = datetime.strptime(tdx_max_date[:10], "%Y-%m-%d").date()
            gap_days = (date.today() - tdx_last).days
        except ValueError as exc:
            print(
                f"[kline/pipeline] phase2 gap 解析失败 tdx_max={tdx_max_date!r}: {exc}",
                flush=True,
            )
            gap_days = 0

        network_rows: list[KLineRow] = []
        network_error: str | None = None
        network_attempted = gap_days > 0
        network_source_name: str | None = None

        if gap_days > 0:
            print(
                f"[kline/pipeline] phase2 chain="
                f"{','.join([self._gap_chain.primary.source.value, *(a.source.value for a in self._gap_chain.fallbacks)])} "
                f"attempt=yes",
                flush=True,
            )
            gap_result = await self._gap_chain.fetch(symbol, period, fqt,
                                                            gap_days + 5)
            if gap_result.rows:
                network_rows = gap_result.rows
                network_source_name = (gap_result.source.value
                                       if gap_result.source else "unknown")
            else:
                network_error = gap_result.error or "all sources empty"
                print(
                    f"[kline/pipeline] phase2 all empty, fallback to tdx rows={len(tdx_rows)}",
                    flush=True,
                )
        else:
            print("[kline/pipeline] phase2 skipped (gap=0)", flush=True)

        # ---- Phase 4: 合并 + 切片 ----
        sources_used: list[str] = ["tdx"]
        if network_source_name:
            sources_used.append(network_source_name)
        by_date: dict[str, KLineRow] = {r.date: r for r in tdx_rows}
        for r in network_rows:
            by_date[r.date] = r  # 网络覆盖同日 TDX (EM11 字段 > TDX 6 字段)
        merged = sorted(by_date.values(), key=lambda r: r.date, reverse=True)[:limit]
        print(
            f"[kline/pipeline] merged total={len(merged)} sources={sources_used} limit={limit}",
            flush=True,
        )

        return HybridFetchResult(
            rows=merged,
            sources_used=sources_used,
            tdx_rows_count=len(tdx_rows),
            network_rows_count=len(network_rows),
            gap_days=gap_days,
            network_attempted=network_attempted,
            network_error=network_error,
            tdx_available=True,
        )

    async def fetch_pure_network(
        self,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> HybridFetchResult:
        """跳过 TDX, 直接走纯网络链 (供 kline_service 增量窗口错位时使用)."""
        return await self._run_pure_network(symbol, period, fqt, limit)

    async def _run_pure_network(
        self,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> HybridFetchResult:
        result = await self._pure_chain.fetch(symbol, period, fqt, limit)
        sources_used: list[str] = []
        if result.source:
            sources_used.append(result.source.value)
        return HybridFetchResult(
            rows=result.rows[:limit],
            sources_used=sources_used,
            tdx_rows_count=0,
            network_rows_count=len(result.rows),
            gap_days=None,
            network_attempted=True,
            network_error=result.error,
            tdx_available=False,
        )

    async def _phase1_tdx(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> tuple[list[KLineRow], bool, str | None]:
        try:
            rows = await self._tdx_adapter.fetch(symbol, period, fqt, limit)
        except FileNotFoundError:
            return [], False, None
        except Exception as exc:
            return [], False, f"{type(exc).__name__}: {exc}"
        return rows, True, None

    async def aclose(self) -> None:
        await asyncio.gather(
            self._gap_chain.aclose(),
            self._pure_chain.aclose(),
            self._tdx_adapter.aclose(),
            return_exceptions=True,
        )
```

- [ ] **Step 8: 运行测试确认通过**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_hybrid_pipeline.py -v`
Expected: 6 个 PASS。

- [ ] **Step 9: 跑既有测试确认无回归**

Run: `cd D:/vscodepro/fin-app/backend && pytest -q`
Expected: 既有测试 PASS / SKIP（kline_pipeline 还未被 kline_service 使用，pipeline 自身的测试已 PASS）。

- [ ] **Step 10: Commit**

```bash
cd D:/vscodepro/fin-app
git add backend/app/config.py \
        backend/tests/test_config_kline_chain.py \
        backend/app/services/kline_pipeline.py \
        backend/tests/test_hybrid_pipeline.py
git commit -m "feat(kline): KLinePipeline hybrid with TDX-first + network gap-fill"
```

---

## Task 5: 改造 `kline_service.py` 三入口改走 pipeline + 2 个集成测试

**Files:**
- Modify: `backend/app/services/kline_service.py`（line 87-156 / 700-781 / 783-823 三块）
- Create: `backend/tests/test_kline_service_hybrid.py`

**Interfaces:**
- Consumes: `KLinePipeline.fetch_hybrid(...)` / `fetch_pure_network(...)`
- Produces:
  - `KLineService._pipeline: KLinePipeline`（替换既有 `_aggregator` / `_full_aggregator`）
  - `KLineService._to_legacy(result: HybridFetchResult) -> FetchResult`（桥接到既有日志格式）

### Steps

- [ ] **Step 1: 写失败的 2 个集成测试**

新建 `backend/tests/test_kline_service_hybrid.py`：

```python
"""kline_service 集成测试: spider/refresh 入口走 hybrid pipeline.

通过 monkeypatch 替换 MongoRepository + KLinePipeline, 不发真实网络/DB.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.clients.kline.types import KLineRow
from app.models.entities import KLineDataEntity, KLineEntity
from app.services.kline_pipeline import HybridFetchResult
from app.services.kline_service import KLineService


def _row(date: str) -> KLineRow:
    return KLineRow(date=date, open=1.0, close=1.0, high=1.0, low=1.0,
                    volume=100, amount=1000.0)


def _make_service(monkeypatch, existing=None, pipeline_result=None):
    """构造 KLineService, mock MongoRepository + Pipeline + 跳过反爬延时."""
    fake_repo = AsyncMock()
    fake_repo.find_by_id = AsyncMock(return_value=existing)
    fake_repo.delete_by_id = AsyncMock(return_value=True)
    fake_repo.save = AsyncMock(return_value=None)

    poly_result = pipeline_result or HybridFetchResult(
        rows=[_row(date.today().strftime("%Y-%m-%d"))],
        sources_used=["tdx"],
        tdx_rows_count=1,
    )
    fake_pipeline = MagicMock()
    fake_pipeline.fetch_hybrid = AsyncMock(return_value=poly_result)
    fake_pipeline.fetch_pure_network = AsyncMock(return_value=poly_result)
    fake_pipeline.aclose = AsyncMock()

    monkeypatch.setattr(
        "app.services.kline_service.MongoRepository",
        lambda *a, **kw: fake_repo,
    )
    monkeypatch.setattr(
        "app.services.kline_service.KLinePipeline",
        lambda *a, **kw: fake_pipeline,
    )
    # 跳过反爬随机延时 1~2s, 测试不实际等待
    monkeypatch.setattr("app.services.kline_service.asyncio.sleep", AsyncMock())

    service = KLineService()
    # 替换既有 client (kline_service.__init__ 会建一个 eastmoney client; 测试不需要)
    service.client = MagicMock()
    return service, fake_repo, fake_pipeline


# ------------------- spider_kline_data hybrid path -------------------


def test_spider_kline_data_uses_pipeline_when_db_empty(monkeypatch):
    """DB 无历史 → pipeline.fetch_hybrid(DEFAULT_LIMIT)."""
    service, fake_repo, fake_pipeline = _make_service(monkeypatch, existing=None)

    async def _run():
        return await service.spider_kline_data(code="510500", market=1, name="测试 ETF")

    result = asyncio.run(_run())
    assert fake_pipeline.fetch_hybrid.called
    call_kwargs = fake_pipeline.fetch_hybrid.call_args.kwargs
    assert call_kwargs["code"] == "510500"
    assert call_kwargs["market"] == 1
    assert call_kwargs["symbol"] == "sh510500"
    assert call_kwargs["limit"] == KLineService.DEFAULT_LIMIT
    assert isinstance(result, KLineEntity)
    assert len(result.klines) == 1


def test_spider_kline_data_incremental_limit(monkeypatch):
    """DB 有历史 → limit = 今天 - last_date 天数 (增量窗口)."""
    last_db_date = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    existing = KLineEntity(
        code="510500",
        name="old",
        klines=[KLineDataEntity(date=last_db_date, open="1", close="1",
                                higher="1", lower="1", vol="100", amount="1000",
                                amountOfAverage="10.000")],
    )
    service, fake_repo, fake_pipeline = _make_service(monkeypatch, existing=existing)

    async def _run():
        return await service.spider_kline_data(code="510500", market=1)

    asyncio.run(_run())
    call_kwargs = fake_pipeline.fetch_hybrid.call_args.kwargs
    # 增量窗口 = 5 天
    assert call_kwargs["limit"] == 5


def test_spider_kline_data_keeps_hk_special_path(monkeypatch):
    """market=116 走 HK 直连, 不进 pipeline."""
    service, fake_repo, fake_pipeline = _make_service(monkeypatch)
    service._fetch_eastmoney_direct = AsyncMock(return_value=None)

    async def _run():
        return await service.spider_kline_data(code="00700", market=116, name="HK")

    asyncio.run(_run())
    assert not fake_pipeline.fetch_hybrid.called
    assert service._fetch_eastmoney_direct.called


# ------------------- refresh_kline_data hybrid path -------------------


def test_refresh_kline_data_uses_pipeline(monkeypatch):
    """refresh 入口: 删旧 doc → pipeline.fetch_hybrid → save."""
    service, fake_repo, fake_pipeline = _make_service(
        monkeypatch,
        existing=KLineEntity(code="510500", name="old", klines=[]),
    )

    async def _run():
        return await service.refresh_kline_data(
            code="510500", market=1, name="ETF", data_source="online",
        )

    result = asyncio.run(_run())
    assert fake_repo.delete_by_id.called
    assert fake_pipeline.fetch_hybrid.called
    assert fake_repo.save.called
    assert isinstance(result, KLineEntity)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_kline_service_hybrid.py -v`
Expected: 全部 FAIL（既有 `KLineService` 仍调 `_aggregator`，未走 pipeline）。

- [ ] **Step 3: 改造 `KLineService.__init__`**

打开 `backend/app/services/kline_service.py`，在 line 14 之后追加 import：

```python
from app.services.kline_pipeline import HybridFetchResult, KLinePipeline
```

修改 `__init__`（line 85-99），把：

```python
    def __init__(self):
        self.client = get_eastmoney_client()
        self.repo = MongoRepository(KLineEntity)
        settings = get_settings()
        # 增量主源 + 回退链: tencent → eastmoney → sina (env 驱动)
        self._aggregator = build_aggregator(
            primary=settings.kline_primary,
            fallbacks=settings.kline_fallbacks.split(","),
        )
        # 全量主源 + 回退链: eastmoney → sina → tencent
        # 全量抓取覆盖历史最全, 东财字段最完整
        self._full_aggregator = build_aggregator(
            primary="eastmoney",
            fallbacks=["sina", "tencent"],
        )
```

替换为：

```python
    def __init__(self):
        self.client = get_eastmoney_client()
        self.repo = MongoRepository(KLineEntity)
        settings = get_settings()
        # Hybrid pipeline: TDX 优先 + 网络补 gap (Sina → Tencent → Eastmoney)
        # TDX 不可用时回落到既有 env 驱动的网络链 (kline_primary + kline_fallbacks)
        self._pipeline = KLinePipeline(
            network_chain_cfg=settings.kline_network_chain.split(","),
            fallback_chain_cfg=[settings.kline_primary, *settings.kline_fallbacks.split(",")],
        )
```

- [ ] **Step 4: 改 `spider_kline_data`**

打开 `backend/app/services/kline_service.py`，替换 `spider_kline_data` 方法（line 109-221）。

把整个方法（含内部 incremental/full 分支）替换为：

```python
    async def spider_kline_data(
        self,
        code: str,
        market: int | None,
        name: str | None = None,
    ) -> KLineEntity | None:
        if market is None:
            return None
        # 反爬随机延时 1~2 秒
        await asyncio.sleep(random.uniform(1.0, 2.0))

        # HK 市场 (market=116) 仅有东财支持, 不走 hybrid
        if market == 116:
            entity = await self._fetch_eastmoney_direct(code, market)
            if entity and name and not entity.name:
                entity.name = name
            return entity

        # 1) 检查 DB 现有数据, 决定 limit
        existing = await self.repo.find_by_id(code)
        existing_klines = existing.klines if existing else None
        last_date = self._last_kline_date(existing_klines)
        symbol = self._secid_to_symbol(market, code)
        limit = (
            self._incremental_limit(last_date) if last_date
            else self.DEFAULT_LIMIT
        )

        # 2) 调 pipeline (内部 TDX-first, 网络 fallback)
        result = await self._pipeline.fetch_hybrid(
            code=code, market=market, symbol=symbol,
            period=PERIOD.DAY, fqt=FQT.QFQ, limit=limit,
        )
        legacy = self._to_legacy(result)

        if not result.rows:
            self._log_incremental_no_data(code, last_date, limit, legacy)
            return existing

        # 3) 过滤出真正的新日期 (大于 last_date)
        new_rows = (
            [r for r in result.rows if r.date > last_date]
            if last_date else result.rows
        )
        if last_date and not new_rows:
            # 增量窗口错位 — 仅打日志, 不重抓 (与既有行为一致)
            self._log_incremental_window_mismatch(code, last_date, limit, legacy)
            return existing

        # 4) 转 entity + 合并 + 保留 history (已有 11 字段不被 6 字段覆盖)
        new_entities = self._rows_to_entities(new_rows)
        merged = self._merge_klines(existing_klines, new_entities, prefer="existing")
        final_name = name or (existing.name if existing else None)
        print(
            f"[kline] hybrid-source code={code} rows={len(merged)} "
            f"sources={result.sources_used} "
            f"tdx={result.tdx_rows_count} network={result.network_rows_count} "
            f"gap={result.gap_days}",
            flush=True,
        )
        return KLineEntity(code=code, name=final_name, klines=merged)
```

- [ ] **Step 5: 加 `_to_legacy` 桥接方法**

打开 `backend/app/services/kline_service.py`，在 `_last_kline_date`（line 291）之前插入：

```python
    @staticmethod
    def _to_legacy(result: HybridFetchResult):
        """HybridFetchResult → FetchResult 桥接, 供既有 _log_incremental_* 方法使用.

        FetchResult 字段: rows / source / fell_back / error / chain_results.
        Hybrid 模式下 chain_results 不再适用, 留 None.
        """
        from app.clients.kline.types import FetchResult, SOURCE
        source = None
        # sources_used 最后一项是网络源 (若有); 否则 tdx.
        if result.sources_used:
            last = result.sources_used[-1]
            try:
                source = SOURCE(last)
            except ValueError:
                source = None
        return FetchResult(
            rows=result.rows,
            source=source,
            fell_back=result.network_attempted and len(result.sources_used) > 1,
            error=result.network_error,
            chain_results=None,
        )
```

- [ ] **Step 6: 改 `refresh_kline_data` 和 `backfill_kline_window`**

打开 `backend/app/services/kline_service.py`。

`refresh_kline_data`（line 223-289）已经在内部调用 `self.spider_kline_data(...)`，由于 Task 5 step 4 已让 `spider_kline_data` 走 hybrid，**refresh 自动获得新行为，无需单独改 refresh 的 fetch 调用**。仅需把 line 257-260 的日志文字微调：

```python
        print(
            f"[kline/refresh] start code={code} source={data_source} "
            f"path={'local TDX vipdoc+gbbq' if data_source == 'offline' else 'hybrid pipeline (TDX-first + network gap-fill)'}",
            flush=True,
        )
```

定位 `backfill_kline_window`（line 700-781），替换 line 747-749：

```python
        result = await self._aggregator.fetch(
            symbol, PERIOD.DAY, FQT.QFQ, limit=days_back,
        )
        if not result.rows:
            return None
```

为：

```python
        result = await self._pipeline.fetch_hybrid(
            code=code, market=market, symbol=symbol,
            period=PERIOD.DAY, fqt=FQT.QFQ, limit=days_back,
        )
        if not result.rows:
            return None
        # HybridFetchResult.rows 类型与 FetchResult.rows 同 (list[KLineRow]),
        # 下游 target_rows 过滤 / merged 合并逻辑保持不变.
```

替换 line 776-779 的日志：

```python
        print(
            f"[kline/backfill-ths] code={code} window=[{start_date},{end_date}] "
            f"new={len(target_rows)} merged_total={len(merged)} "
            f"source={result.source.value if result.source else 'none'}",
            flush=True,
        )
```

为：

```python
        print(
            f"[kline/backfill-hybrid] code={code} window=[{start_date},{end_date}] "
            f"new={len(target_rows)} merged_total={len(merged)} "
            f"sources={result.sources_used}",
            flush=True,
        )
```

（保留 `backfill_kline_window` 既有签名；`data_source="offline"` 路径走 `_backfill_kline_window_offline` 不动。）

- [ ] **Step 7: 运行新集成测试**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_kline_service_hybrid.py -v`
Expected: 4 个 PASS（spider empty / incremental / HK / refresh）。

- [ ] **Step 8: 跑既有 kline_service 测试**

Run: `cd D:/vscodepro/fin-app/backend && pytest tests/test_kline_gap_backfill.py tests/test_ensure_kline_complete.py tests/test_kline_adapters.py tests/test_hybrid_pipeline.py tests/test_tdx_adapter.py -v`
Expected: 既有测试按既有断言行为 PASS（`_incremental_limit` / `_last_kline_date` / `_merge_klines` / `_rows_to_entities` 等私有方法未动；既有日志格式由 `_to_legacy` 桥接保持）。

- [ ] **Step 9: Commit**

```bash
cd D:/vscodepro/fin-app
git add backend/app/services/kline_service.py \
        backend/tests/test_kline_service_hybrid.py
git commit -m "feat(kline): kline_service uses hybrid pipeline (3 entry points)"
```

---

## Task 6: 更新 README + 全量验证 + 最终 commit

**Files:**
- Modify: `backend/README.md`（KLine 多源章节）
- Verify: `cd backend && pytest -q && ruff check app`

### Steps

- [ ] **Step 1: 读现有 README 的 KLine 章节**

Run: `grep -n "KLine\|kline" D:/vscodepro/fin-app/backend/README.md | head -20`

找到 `KLine 多源` / `kline_primary` / `kline_fallbacks` 相关段落。

- [ ] **Step 2: 改写 KLine 多源章节**

打开 `backend/README.md`，把 KLine 多源章节的描述从「两套并行链」改为「hybrid pipeline」：

找到描述增量/全量两套 aggregator 的段落（grep "增量主源\|全量主源"），改为：

```markdown
### K 线多源：hybrid pipeline（TDX 优先 + 网络补 gap）

**架构**：`KLinePipeline` 编排器 4 阶段：TDX 探测 → 网络补 gap → 纯网络兜底 → 合并切片。
`source=online`（默认）走 hybrid；`source=offline` 走纯 TDX（既有行为保留）。

**TDX-first**：本地通达信 vipdoc + gbbq 覆盖历史（无网络、零频率限制、字段完整）。
`TdxAdapter` 复用 `app/services/tdx_offline/fetch_local_day`，不重写。

**网络补 gap**：TDX 的 `max_date` 距今天数 = gap，用网络链补最近 gap+5 天。
网络链顺序默认 `sina,tencent,eastmoney`（env `FIN_KLINE_NETWORK_CHAIN` 覆盖），先轻后全。

**TDX 不可用时**：env `FIN_KLINE_PRIMARY`（默认 `tencent`）+ `FIN_KLINE_FALLBACKS`（默认 `eastmoney,sina`）
驱动纯网络兜底链——与改造前 online 行为一致，零回归。

**TDX 不必天天下载**：`tdx_daily_fetcher` 每包 525MB，hybrid 自动用网络补最近 gap。

**env 总览**：
- `FIN_KLINE_PRIMARY`（默认 `tencent`）— TDX 不可用时纯网络主源
- `FIN_KLINE_FALLBACKS`（默认 `eastmoney,sina`）— 同上回退
- `FIN_KLINE_NETWORK_CHAIN`（默认 `sina,tencent,eastmoney`）— TDX gap 补抓网络链
- `FIN_TDX_HOME`（默认 `D:\stock\data`）— TDX 主目录

**详见**：`docs/superpowers/specs/2026-09-29-kline-hybrid-pipeline-design.md`
```

- [ ] **Step 3: 全量验证**

Run:
```bash
cd D:/vscodepro/fin-app/backend && \
  pytest -q 2>&1 | tail -30 && \
  ruff check app
```

Expected: `pytest` 既有测试 + 11 个新测试（3 tdx_adapter + 6 hybrid_pipeline + 2 config + 4 service hybrid）全 PASS / SKIP；`ruff check` 0 报错。

若 `ruff check` 报 unused import 或 line-too-long，按其建议就地修。

- [ ] **Step 4: 最终 commit**

```bash
cd D:/vscodepro/fin-app
git add backend/README.md
git diff --cached --stat   # 确认只改 README
git commit -m "docs(backend): document hybrid pipeline K-line multi-source"
```

（按 spec 要求本应是单一 feature commit。中间 5 个 commit 已记录过程性变更；本 commit 收尾更新文档。如需 squash：可交互式 rebase 合并前 5 个 + 本 commit 为一个。）

---

## Self-Review Checklist（执行前自查）

- [ ] spec §数据结构（`HybridFetchResult` 8 字段）→ Task 4 step 7 ✅
- [ ] spec §4 阶段（Phase 1-4）→ Task 4 step 7 ✅
- [ ] spec §TdxAdapter（3 个方法 + 降序）→ Task 3 step 3 ✅
- [ ] spec §`_resolve_tdx_home` 迁出 → Task 2 step 3-4 ✅
- [ ] spec §kline_service 改造（spider/refresh/backfill）→ Task 5 step 3-6 ✅
- [ ] spec §`_to_legacy` 桥接 → Task 5 step 5 ✅
- [ ] spec §测试 11 个（3+6+2+4）→ Task 3-5 测试 ✅
- [ ] spec §env `FIN_KLINE_NETWORK_CHAIN` → Task 4 step 3 ✅
- [ ] spec §`SOURCE.TDX` → Task 1 ✅
- [ ] spec §README 更新 → Task 6 step 2 ✅
- [ ] spec §single feature commit → Task 6 step 4（说明 squash 路径） ✅
- [ ] placeholder scan：无 TBD / TODO / "similar to" / 空代码块 ✅
- [ ] type consistency：`HybridFetchResult` 在 Task 4 定义、Task 5 引用一致 ✅
- [ ] 接口一致性：`KLinePipeline.fetch_hybrid(...)` 在 Task 4 / Task 5 签名一致 ✅