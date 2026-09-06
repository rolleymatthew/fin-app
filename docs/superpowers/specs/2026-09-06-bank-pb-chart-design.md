# 银行股 PB 时序图 — 设计文档

**日期**：2026-09-06
**目的**：在 `D:\vscodeproject\fin-app\` 现有 SPA 侧栏新增一个独立的"银行 PB 时序"模块，左侧按 pinyin / 备选列表选银行股，右侧实时计算并展示该银行的历史市净率（PB）折线图。所有计算实时完成、不落库。

---

## 1. 背景与动机

### 1.1 现状

- 三张银行表（`assets_bank` / `cash_flow_bank` / `assets_bank`）只存原始报表项，**不含**估值字段（市净率 / 市净率 / 每股净资产）。
- 现 SPA (`frontend/src/Etf.jsx`) 默认图表为 ETF 数据；侧栏已有一个 `HKFinanceCard`（`frontend/src/HKFinanceCard.jsx`）作为独立模块挂在 `Etf.jsx:1107` 旁。
- 仓内已有现成的"拼音搜索下拉框"组件 `frontend/src/StockCombobox.jsx`，后端走 `GET /api/sec/search`，支持代码 / 拼音首字母 / 中文名模糊匹配。
- 港股端 `backend/app/services/hk_finance_service.py:296` 已在用东财 `PER_SHARE_NETASSET` 字段。

### 1.2 目标

新增一个独立模块 `frontend/src/BankPBCard.jsx`，作为 `Etf.jsx` 侧栏的又一张卡片：
- 左侧 = pinyin 搜索 + 银行股备选列表（动态从后端拉 `orgTypeCode=="3"` 的股票）
- 右侧 = 一张 PB 时序折线图（横轴 = 报表日，纵轴 = 市净率）
- **实时计算**：每次切换股票现拉 `assets_bank` + `k_line` 现算 PB，不落库

### 1.3 非目标

- ❌ 不做 PB（市净率）—— 用户明确"银行股不要算 PB，只算 PB"
- ❌ 不做非银行股的 PB —— 仅 `orgTypeCode=="3"`
- ❌ 不做历史 PB 持久化 —— 全部实时算
- ❌ 不动 `Etf.jsx` 既有图表 / state / handler / style（仅追加 2 行：import + 挂载）
- ❌ 不引入新 pip / pnpm 依赖
- ❌ 不动 `app/clients/`、`app/repositories/`、`app/mappers/`、`app/models/entities.py`、`app/services/finance_service.py`
- ❌ 不引入路由 / 不改 `main.jsx`

---

## 2. 模块布局

### 2.1 在 SPA 中的位置

```
Etf.jsx (侧栏容器)
├── ETF 数据卡片
├── 股票数据卡片
├── HKFinanceCard    (已存在，line 1107)
└── BankPBCard       (新增，line 1108 旁)
```

Etf.jsx 仅追加：
- `import BankPBCard from './BankPBCard';`
- `<BankPBCard />` 挂在 `<HKFinanceCard />` 旁

### 2.2 BankPBCard 内部

```
┌─ BankPBCard ────────────────────────────────────────────────┐
│ [▾ 银行 PB 时序]                                            │
│ ┌────────────────────┬─────────────────────────────────────┐ │
│ │ ┌───────────────┐  │  ┌─────── PB 时序图 ────────────┐   │ │
│ │ │ StockCombobox │  │  │  x = reportDate              │   │ │
│ │ │  (限银行筛选) │  │  │  y = 市净率 (PB)            │   │ │
│ │ └───────────────┘  │  │  smooth line #dc2626         │   │ │
│ │ ┌─── 备选列表 ──┐  │  │  断点 connectNulls:false    │   │ │
│ │ │ 600036 招商银行│  │  │  tooltip: PB/BPS/收盘      │   │ │
│ │ │ 601398 工商银行│  │  └────────────────────────────┘   │ │
│ │ │ 601939 建设银行│  │                                    │ │
│ │ │ ... (~40 家)   │  │                                    │ │
│ │ │ [高亮选中]    │  │                                    │ │
│ │ └───────────────┘  │                                    │ │
│ └────────────────────┴────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 数据流

### 3.1 组件 mount（拉银行列表）

```js
useEffect(() => {
  apiGet('/api/sec/search?org_type_code=3&limit=1000').then(rows => setBankList(rows));
}, []);
```

### 3.2 用户选股（点击列表 / combobox）

```js
onSelect({ code, name }) → setSelected({ code, name }) → 触发 3.3
```

### 3.3 拉 PB 时序

```js
useEffect(() => {
  if (!selectedCode) return;
  apiGet(`/api/stock/bank/pb/history?code=${selectedCode}`).then(rows => setPbHistory(rows));
}, [selectedCode]);
```

### 3.4 后端计算每点 PB

```
对 assets_bank 每条记录 (reportDate):
  BPS = _pick_first(assets_bank[t], _BPS_CANDIDATES)
  close = kline.date >= t 的最早交易日 close
  PB = close / BPS

任一缺失 → PB=null, error 填人话原因
```

---

## 4. 后端设计

### 4.1 新文件 `backend/app/services/bank_pb_service.py`

```python
class BankPBService:
    _BPS_CANDIDATES = (
        "bps",
        "BPS",
        "perShareNetasset",
        "PER_SHARE_NETASSET",
        "netAssetPerShare",
        "NETASSET_PER_SHARE",
        "bookValuePerShare",
        "BOOK_VALUE_PER_SHARE",
        "navPerShare",
        "NAV_PER_SHARE",
        "bpsAdj",
        "BPS_ADJ",
        "perShareNetassetAdj",
        "PER_SHARE_NETASSET_ADJ",
    )

    async def calculate_pb_history(self, sec_code: str) -> list[BankPBHistoryPointDTO]
    async def calculate_pb(self, sec_code: str) -> BankPBDTO  # 单点最新值，保留
```

依赖：
- `MongoRepository(AssetsBankEntity)` — 复用 `app/repositories/base.py` 既有 repo
- `KLineService` — 复用 `app/services/kline_service.py` 既有 service
- `SecCodeService` — 复用 `app/services/seccode_service.py` 既有 service（仅用于校验 `orgTypeCode == "3"`，其它不需要）

**不新建 client，不重写 mapper。**

### 4.2 追加 DTO `backend/app/models/dto.py`

```python
class BankPBHistoryPointDTO(BaseModel):
    date: str | None = None              # kline 实际交易日
    reportDate: str | None = None        # 报表日
    bps: float | None = None
    bpsField: str | None = None          # 命中的 BPS 候选名
    close: float | None = None
    pe: float | None = None
    error: str | None = None             # 缺字段时填人话原因


class BankPBDTO(BaseModel):
    secCode: str | None = None
    securityNameAbbr: str | None = None
    reportDate: str | None = None
    bps: float | None = None
    bpsField: str | None = None
    close: float | None = None
    closeDate: str | None = None
    pe: float | None = None
    error: str | None = None
```

**只追加，不动既有 DTO。**

### 4.3 扩展 `backend/app/services/seccode_service.py` 的 `search_stocks`

```python
async def search_stocks(
    self,
    q: str | None = None,
    limit: int = 200,
    org_type_code: str | None = None,   # ← 新增，向后兼容
) -> list[dict]:
    base_filter: dict = {"listingState": "0"}
    if org_type_code is not None:
        base_filter["orgTypeCode"] = org_type_code
    ...
```

既有调用方不受影响（默认 `None` 时与旧行为一致）。

### 4.4 扩展 `backend/app/api/sec_code.py` 的 `/sec/search`

```python
@router.get("/search")
async def search(
    q: str | None = Query(default=None, ...),
    limit: int = Query(default=200, ge=1, le=1000),
    org_type_code: str | None = Query(default=None, description="公司类型代码: 1=证券 2=保险 3=银行 4=通用"),  # ← 新增
) -> dict:
    svc = _service()
    rows = await svc.search_stocks(q=q, limit=limit, org_type_code=org_type_code)
    return ResultVO.ok(rows).model_dump()
```

既有调用方（`apiUrl="/api/sec/search"`）零影响。

### 4.5 新增 endpoint `backend/app/api/stock.py`

```python
@router.get("/bank/pb/history")
async def get_bank_pb_history(code: str = Query(...)) -> dict:
    svc = _service()  # 复用既有 _services() 工厂
    entity = await svc.sec_code_entity_by_id(code)
    if not entity or entity.orgTypeCode != BankTypeCode:
        return ResultVO.fail(code=400, message="非银行 orgType，不适用").model_dump()
    rows = await svc.pb_service.calculate_pb_history(code)
    return ResultVO.ok(rows).model_dump()
```

**只追加，不动既有 endpoint。** 走 `ResultVO` 8 字段 envelope，保 `success` 字段。

---

## 5. 前端设计

### 5.1 新文件 `frontend/src/BankPBCard.jsx`

自包含模块，零外部依赖除：
- `ReactECharts` (`echarts-for-react`，已在 `package.json:14-15`)
- `StockCombobox` (`./StockCombobox`，已有)
- `apiGet` (`./api`，已有)

组件结构：
- state: `bankList[]`, `selectedCode`, `selectedName`, `peHistory[]`
- useEffect (mount): 拉 `/api/sec/search?org_type_code=3&limit=1000`
- useEffect (selectedCode change): 拉 `/api/stock/bank/pb/history?code=...`
- 折线图规格：x=reportDate 升序、y=PB 单 series、`#dc2626`、smooth、connectNulls=false、tooltip cross

### 5.2 `frontend/src/Etf.jsx` 仅追加 2 行

- line 6 旁：`import BankPBCard from './BankPBCard';`
- line 1107 旁：`<BankPBCard />` 挂在 `<HKFinanceCard />` 后

**不动既有图表 / state / handler / style。**

---

## 6. 容错与容错链

### 6.1 BPS 字段名候选链（按顺序尝试）

```
bps, BPS,
perShareNetasset, PER_SHARE_NETASSET,
netAssetPerShare, NETASSET_PER_SHARE,
bps, BPS,
bookValuePerShare, BOOK_VALUE_PER_SHARE,
bps,
navPerShare,
bpsAdj,
bpsAdj
```

首个非 None 即采纳，并在 DTO `bpsField` 记录命中名，便于排查。

### 6.2 缺字段处理

- 缺 BPS → `pe=null`, `error="未找到每股净资产字段（已尝试 {N} 个候选名）"`
- 缺 kline → `pe=null`, `error="无 K 线数据"`
- 任一缺失 → 该点 `pe=null`，前端 `connectNulls:false` 显示断点

---

## 7. 测试

### 7.1 后端

- `backend/tests/test_bank_pb_service.py`（新文件）
  - 正常 case：mock assets_bank + kline，断言 PB 计算
  - 缺 BPS case：断言 PB=null + error 含"未找到每股净资产"
  - 缺 kline case：断言 PB=null + error 含"无 K 线"
  - 单点 `calculate_pb` 最新值 = history 末项

- `backend/tests/test_seccode_service_org_type_filter.py`（新文件）
  - 默认行为不变（不传 `org_type_code` 时等价于既有逻辑）
  - `org_type_code="3"` 时仅返银行

### 7.2 前端

- `pnpm run lint` 零警告
- `pnpm run build` 成功
- 手动浏览器手测（subagent 不点）

---

## 8. 不动清单（强制）

| 路径 | 原因 |
|---|---|
| `backend/app/clients/` | 默认只读 |
| `backend/app/repositories/` | 默认只读 |
| `backend/app/mappers/zqh.py` | 默认只读 |
| `backend/app/models/entities.py` | 不需要新增字段 |
| `backend/app/services/finance_service.py` | 与本功能解耦 |
| `frontend/src/Etf.jsx` 既有图表/state/handler/style | 仅追加 2 行 |
| `frontend/src/main.jsx` | 无路由改动 |
| `backend/pyproject.toml` / `frontend/package.json` | 不引入新依赖 |

---

## 9. 提交粒度

```
1. docs(spec+plan)
2. feat(sec): /api/sec/search 支持 org_type_code 过滤（向后兼容）
3. feat(bank): BankPBService + DTO + /stock/bank/pb/history + 测试
4. feat(frontend): BankPBCard 模块
```

每个 commit 后：`pytest -q && ruff check app` + `pnpm run lint && pnpm run build`。