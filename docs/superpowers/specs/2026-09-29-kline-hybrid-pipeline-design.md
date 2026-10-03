# K 线抓取逻辑重组：TDX 优先 + 网络补 gap（Hybrid Pipeline）

日期：2026-09-29
范围：`backend/app/`（clients、services、config、tests）

## 背景

当前 K 线抓取分两个互斥模式（`source=online` / `source=offline`），各有缺陷：

1. **本地 TDX（通达信 vipdoc + gbbq）** 是当前数据质量最好的来源（全字段、复权正确、无频率限制），但被锁定在 `source=offline` 模式下，不与网络源形成协作链。用户必须手动切换 radio 才能用，且不能与网络源互补。
2. **网络三源（东方财富 / 腾讯 / 新浪）** 仅在 `source=online` 模式下工作，按"增量优先腾讯、全量优先东财"硬编码在 `kline_service.py:89-99` 两套并行 `_aggregator` 中，灵活性差。
3. **TDX 不必天天下载**（自动下载靠 `tdx_daily_fetcher`，每包 525MB），但今天的设计把 TDX 当作"全有或全无"：下载了就纯本地，没下载就纯网络，没有"用 TDX 覆盖历史 + 网络补最近几天 gap"的混合路径。

**核心问题**：用户被迫在"开本地后还要每天下 525MB"和"用纯网络拿 11 字段东财但限流严重"之间二选一。

## 目标

引入单一 `KLinePipeline` 编排器，让 `source=online` 默认走 hybrid 路径——

- **TDX 优先**：本地 `.day` + `gbbq` 覆盖历史（无网络、零频率限制、字段完整）
- **网络补 gap**：TDX 的 `max_date` 距今天数 = gap，用网络链（Sina → Tencent → Eastmoney）补最近几天
- **TDX 不可用时纯网络**：env 驱动的 `kline_primary` + `kline_fallbacks` 兜底
- **API/前端零改动**：`source=online/offline` 顶层开关保持，前端 Etf.jsx 不动

## 设计

### 文件清单

```
新增 4 个文件:
  backend/app/clients/kline/tdx_adapter.py          # KLineAdapter 协议, 包 fetch_local_day
  backend/app/services/kline_pipeline.py            # 主编排器 (HybridFetchResult + 4 phase)
  backend/tests/test_tdx_adapter.py                 # 适配器单测
  backend/tests/test_hybrid_pipeline.py             # pipeline 三阶段 + 边界单测

改动 4 个文件:
  backend/app/config.py                             +1 字段: kline_network_chain
  backend/app/services/kline_service.py             spider/refresh/backfill 三入口改走 pipeline
  backend/app/clients/kline/__init__.py             +1 export: TdxAdapter
  backend/app/clients/kline/types.py                +1 枚举值: SOURCE.TDX
  backend/README.md                                 更新 KLine 多源章节描述

零改动:
  backend/app/services/tdx_offline/                 fetch_local_day 不重写; 仅 fetcher.py +1 行 import (见实施步骤 2)
  backend/app/services/tdx_daily_fetcher/           自动下载逻辑不变
  backend/app/services/etf_service.py                内部仍调 kline_service, 接口不变
  backend/app/services/finance_service.py           同上
  api/kline.py / api/etf.py                         source 参数语义不变
  frontend/src/Etf.jsx                              radio/按钮完全不动
  docker/docker-compose.yml                         无 env 变更
```

**模块边界**：
- `tdx_adapter.py`：单职责——`fetch_local_day` → `KLineRow[]`。不碰 gap、不碰网络、不碰 Mongo。
- `kline_pipeline.py`：编排逻辑，三阶段独立可测。`HybridFetchResult` 是顶层返回类型；`FetchResult` 继续在网络内部使用。
- `kline_service.py`：业务入口仍拥有增量/全量判断、`_merge_klines`、`_rows_to_entities`、`save_mongodb`，仅把"网络取数"委托给 pipeline。

### 数据结构

新增 `HybridFetchResult`（不复用 `FetchResult`——后者是单源链设计，表达不了两源合并）：

```python
@dataclass
class HybridFetchResult:
    rows: list[KLineRow]                              # 合并后行, 按日期降序
    sources_used: list[str]                           # 实际触发的源, 例 ["tdx", "sina"]
    tdx_rows_count: int = 0
    network_rows_count: int = 0
    gap_days: int | None = None                       # today - tdx_max_date, TDX 缺失时 None
    network_attempted: bool = False                   # 是否尝试过 gap 补抓
    network_error: str | None = None                  # 网络阶段最后一错
    tdx_available: bool = True                        # .day 文件存在与否
```

`SOURCE` 枚举新增 `TDX = "tdx"`：

```python
class SOURCE(str, Enum):
    TENCENT = "tencent"
    SINA = "sina"
    EASTMONEY = "eastmoney"
    TDX = "tdx"
```

### 流程

`KLinePipeline.fetch_hybrid(code, market, symbol, period, fqt, limit)`：

```
Phase 1: TDX 探测
  try TdxAdapter().fetch(symbol, period, fqt, limit)
    catch FileNotFoundError  → tdx_available=False, rows=[]
    catch 其他异常           → tdx_available=False, rows=[], 记 warn
  tdx_rows, tdx_available, tdx_err ← phase1

Phase 2: 网络补 gap (仅 tdx_available=True 时执行)
  if not tdx_rows:
    goto Phase 3
  tdx_max_date = tdx_rows[0].date                    # rows 降序
  gap = (date.today() - parse(tdx_max_date)).days
  if gap <= 0:
    network_rows = []; network_attempted = False
  else:
    network_attempted = True
    network_chain = build_aggregator(self.network_chain_cfg)   # 默认 sina,tencent,eastmoney
    result = network_chain.fetch(symbol, period, fqt, limit=gap + 5)
    network_rows = result.rows
    network_error = result.error if not result.rows else None

Phase 3: 纯网络兜底 (仅 tdx_available=False 时执行)
  pure_chain = build_aggregator([kline_primary, *kline_fallbacks])
  # 默认 tencent,eastmoney,sina (复用既有 kline_primary/kline_fallbacks env)
  # 与改造前的 online 行为一致: TDX 不可用时 = 老 online 模式
  pure_result = pure_chain.fetch(symbol, period, fqt, limit)
  rows = pure_result.rows

Phase 4: 合并与切片
  by_date = {}
  for r in tdx_rows: by_date[r.date] = r
  for r in network_rows: by_date[r.date] = r        # network 覆盖同日 TDX (EM11 字段 > TDX 6 字段)
  rows = sorted(by_date.values(), key=lambda r: r.date, reverse=True)[:limit]
  → HybridFetchResult
```

**Pipeline 公开方法**：`fetch_hybrid(...)` 完整走 4 phase；另暴露 `fetch_pure_network(symbol, period, fqt, limit)` 仅走 Phase 3，供 kline_service 在增量窗口错位时跳过 TDX 重抓。

### 配置

新增 1 个 env：

```python
# config.py
kline_network_chain: str = Field(
    default="sina,tencent,eastmoney",
    description="Hybrid 模式下, TDX gap 补抓的网络源链顺序. 顺序敏感, 先轻后全.",
    validation_alias=AliasChoices("FIN_KLINE_NETWORK_CHAIN", "KLINE_NETWORK_CHAIN"),
)
```

保留不动：
- `kline_primary`（默认 `tencent`）—— 驱动 TDX 不可用时的纯网络兜底链
- `kline_fallbacks`（默认 `eastmoney,sina`）—— 同上

`docker-compose.yml` / `.env` 不需改：用默认即可。

### TdxAdapter 细节

```python
class TdxAdapter:
    source = SOURCE.TDX

    def __init__(self, tdx_home: str | None = None):
        self._tdx_home = _resolve_tdx_home(tdx_home)

    async def fetch(self, symbol: str, period: PERIOD, fqt: FQT,
                    limit: int) -> list[KLineRow]:
        """symbol='sh510500' → code='510500', 调 fetch_local_day(code, 'qfq'),
        DataFrame → KLineRow.list. limit 参数忽略 (.day 是全集).
        返回按 date 降序. """
        code = _symbol_to_code(symbol)
        df = await asyncio.to_thread(fetch_local_day, code, "qfq", self._tdx_home)
        return _df_to_klinerows(df)
```

`_df_to_klinerrows` 字段映射：

```python
rows = [
    KLineRow(
        date=ts.strftime("%Y-%m-%d"),
        open=float(row["open"]),
        close=float(row["close"]),
        high=float(row["high"]),
        low=float(row["low"]),
        volume=int(row["vol"]) * 100,            # .day vol 单位是手; KLineRow.volume 是股
        amount=float(row["amount"]) if pd.notna(row["amount"]) else None,
        # turnover / amplitude / up_down_amount / amount_of_increase — TDX 无, 留 None
    )
    for ts, row in df.iterrows()
]
rows.sort(key=lambda r: r.date, reverse=True)
return rows
```

`_resolve_tdx_home` 从 `tdx_offline/fetcher.py:68` 提取（迁出 `tdx_offline` 包），保持三级 fallback：入参 > `settings.tdx_home` > 环境变量 `TDX_HOME` > 默认 `C:\zd_zxzq_gm`。

### kline_service 改动点

`__init__`：

```python
# 删 self._aggregator / self._full_aggregator (不再需要, hybrid 统一处理)
self._pipeline = KLinePipeline(
    network_chain_cfg=settings.kline_network_chain.split(","),
    fallback_chain_cfg=[settings.kline_primary, *settings.kline_fallbacks.split(",")],
)
```

`spider_kline_data`（简化：不再需要"limit > 90 走全量"分支，hybrid 自适应）：

```python
async def spider_kline_data(self, code, market, name):
    if market == 116:                                # HK 特殊路径保留
        return await self._fetch_eastmoney_direct(code, market)
    if market is None:
        return None
    symbol = self._secid_to_symbol(market, code)
    existing = await self.repo.find_by_id(code)
    last_date = self._last_kline_date(existing.klines if existing else None)
    limit = self._incremental_limit(last_date) if last_date else self.DEFAULT_LIMIT
    # hybrid 内部:
    #   - TDX 有数据 → 返 TDX[:limit] ∪ 网络 gap rows
    #   - TDX 无数据 → Phase 3 纯网络 (limit 行)
    result = await self._pipeline.fetch_hybrid(
        code=code, market=market, symbol=symbol,
        period=PERIOD.DAY, fqt=FQT.QFQ, limit=limit,
    )
    if not result.rows:
        self._log_incremental_no_data(code, last_date, limit, _to_legacy(result))
        return existing
    new_rows = [r for r in result.rows if r.date > last_date] if last_date else result.rows
    if last_date and not new_rows:
        # 增量窗口错位 — 保留既有行为: 仅打日志, 不重抓
        self._log_incremental_window_mismatch(code, last_date, limit, _to_legacy(result))
        return existing
    new_entities = self._rows_to_entities(new_rows)
    # 增量路径 prefer="existing" 防止 6 字段覆盖 11 字段 (与改造前一致)
    merged = self._merge_klines(existing.klines, new_entities, prefer="existing")
    final_name = name or (existing.name if existing else None)
    return KLineEntity(code=code, name=final_name, klines=merged)
```

**`_to_legacy(result)` 桥接**：既有 `_log_incremental_no_data` / `_log_incremental_window_mismatch` 签名要求 `FetchResult`，新建一个轻量 adapter 把 `HybridFetchResult` 投影成 `FetchResult`（只填 `rows` / `source` / `fell_back` / `error`），不动既有日志格式。

`refresh_kline_data` / `backfill_kline_window`：同样改调 `self._pipeline.fetch_hybrid(...)`，传 `data_source="offline"` 时仍走 `kline_by_sec_code_offline`（既有行为零改动）。

### 数据流示例

**输入**：`code=510330`, `market=1`, `limit=90`, today=2026-09-29

```
Phase 1: TdxAdapter.fetch("sh510500") → 86 行, max=2026-09-25, gap=4
Phase 2: build_aggregator(["sina","tencent","eastmoney"]).fetch(limit=9)
         → sina OK, 5 行 (2026-09-26~30)
Phase 4: tdx[:90] ∪ sina = 90 行 (2026-09-25 同日 sina 覆盖 tdx)
         sources_used=["tdx", "sina"]

日志:
  [kline/pipeline] phase1=tdx rows=86 max=2026-09-25 gap=4 status=ok
  [kline/pipeline] phase2 chain=sina,tencent,eastmoney attempt=yes
  [kline/pipeline] phase2 source=sina rows=5 status=ok
  [kline/pipeline] merged total=90 sources=[tdx, sina] limit=90
```

### 错误处理

| # | 场景 | 行为 | 用户感知 |
|---|---|---|---|
| 1 | TDX .day 不存在 | phase1 捕 `FileNotFoundError` → `tdx_available=False` → Phase 3 纯网络 | 日志 "phase1=tdx rows=0 status=missing → phase3=pure-network" |
| 2 | TDX gbbq 解析失败 | phase1 捕异常 → 同上, 记 warn | 日志 "phase1=tdx error=..." |
| 3 | TDX stale, gap ≤ 0 | phase2 不调网络, 直接返 TDX | 日志 "phase2 skipped (gap=0)" |
| 4 | TDX stale, sina 挂 tencent 挂 EM 挂 | phase2 网络链全空 → 返 TDX rows, `network_error="all sources empty"`, `network_attempted=True` | 日志 "phase2 all empty, fallback to tdx rows=N" |
| 5 | TDX stale, sina OK | phase2 sina 返行 → 合并 TDX + sina | 日志 "phase2 source=sina rows=5" |
| 6 | TDX 缺失, 网络也挂 | Phase 3 返空 → 上层走"无数据"分支 | 日志 "phase3 source=NONE" |
| 7 | 网络链 source 解析失败（env 配错名） | pipeline `__init__` 抛 ValueError | 启动即崩, 日志明确 |
| 8 | TDX 返 0 行（文件存在但全空） | `tdx_available=True, rows=[]` → Phase 3 纯网络 | 日志 "phase1=tdx rows=0 status=empty" |
| 9 | `market=None` 且 TDX code 无法推断 | pipeline 入口返 `HybridFetchResult(rows=[], tdx_available=False)` | 日志 "phase1 unavailable: cannot derive code" |
| 10 | TDX 数据陈旧但今天非交易日（周末/假期） | gap > 0 仍会调网络；网络可能在假期无新数据 → 返 TDX + warn | 日志 "phase2 empty (holiday?), fallback to tdx" |

**错误类型保留**：TdxAdapter 不抛业务异常（除 `FileNotFoundError`）——错误转 `HybridFetchResult` 字段，不让 Pipeline 抛。

### 测试

| 文件 | 类型 | 覆盖 |
|---|---|---|
| `test_tdx_adapter.py` (new) | 单元 (3 必写) | ① .day → KLineRow 字段映射（fixture 用 `tests/fixtures/kline/sh510500`）；② .day 缺失抛 `FileNotFoundError`；③ limit 被忽略（rows 数 = 全集） |
| `test_hybrid_pipeline.py` (new) | 单元 (6 必写) | ① phase1=tdx gap=0 不调网络（mock aggregator 计数=0）；② phase1=tdx gap=4 调 sina 合并；③ phase1 空 → phase3 纯网络；④ phase1 stale + 网络全空 → fallback TDX；⑤ phase2 fell_back 到 tencent（sina 挂）；⑥ 网络链顺序与 config 一致（参数化 ["a,b,c"]） |
| `test_kline_service_hybrid.py` (new) | 集成 (2 必写) | ① `spider_kline_data` 整体走 hybrid（mock pipeline）；② `refresh_kline_data` 在 hybrid 模式下正确清理 + 重抓 |
| `test_kline_adapters.py` 现有 | 回归 | 新增 `test_source_enum_includes_tdx`，确保 `SOURCE.TDX = "tdx"` |
| `test_kline_gap_backfill.py` 现有 | 回归 | 不动，确保 `backfill_kline_window` 仍兼容 |

**Test fixtures**：复用 `tests/fixtures/kline/` 已有 sh510500 / sh600000 子集；`test_tdx_adapter` 沿用 `test_tdx_day_reader_regression.py` 的 vipdoc 测试 fixture。

### 兼容性 / 回滚

- API 端点（`/api/etf/kline`、`/api/kline/get`、`/api/kline/refresh`）签名 0 改动
- 前端 Etf.jsx radio / 按钮 / `source=online/offline` 选择完全 0 改动
- `source=offline` 路径仍走纯 `kline_by_sec_code_offline`（既有行为完全保留）
- `source=online` 行为变化：从"纯网络（tencent → eastmoney → sina）"变为"hybrid（TDX 优先 + 网络补 gap）"
- 回滚：所有新逻辑集中在 `kline_pipeline.py` + `tdx_adapter.py` + `kline_service.__init__` 的 1 行 import + 3 行 `__init__` 改动 + spider/refresh/backfill 三入口改造。`git revert` 单个 commit 即可完全回滚。

### 不做（v1 明确不实现）

- ❌ TDX 数据自动陈旧检测（gap > N 天告警）—— v1 信任用户判断
- ❌ 多市场并行 TDX 读取优化（按市场分组并发）—— v1 串行调用足够
- ❌ 网络链自适应（按历史成功率排序）—— v1 用固定 env 配置
- ❌ TDX gbbq 自动下载 —— 网站不提供
- ❌ 增量场景单独配 chain —— 增量/全量都走同一 hybrid 路径
- ❌ 前端展示数据来源 badge —— 服务端日志已有，UI v1 不展示

### 实施顺序（写作计划时细化）

1. `config.py` 加 `kline_network_chain` 字段
2. `tdx_offline/fetcher.py` 抽 `_resolve_tdx_home` 到 `clients/kline/tdx_adapter.py`（保持向后兼容，`tdx_offline` 仍可导入）
3. `clients/kline/tdx_adapter.py` 实现 `TdxAdapter` + `_df_to_klinerows`
4. `clients/kline/__init__.py` 加 `TdxAdapter` export；`types.py` 加 `SOURCE.TDX`
5. `services/kline_pipeline.py`（含 4 个 phase + `HybridFetchResult`）
6. `services/kline_service.py`：`__init__` 改用 pipeline；`spider_kline_data`/`refresh_kline_data`/`backfill_kline_window` 三入口改造
7. `tests/test_tdx_adapter.py` + `tests/test_hybrid_pipeline.py` + `tests/test_kline_service_hybrid.py`
8. `backend/README.md` 更新 KLine 多源章节
9. 跑 `pytest -q && ruff check app`
10. 单 commit：`feat(kline): hybrid pipeline with TDX-first + network gap-fill`