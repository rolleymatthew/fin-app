# 银行股 PB 时序图 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `D:\vscodeproject\fin-app\` SPA 侧栏新增 `BankPBCard` 模块，左侧 pinyin 选银行股 + 备选列表，右侧实时计算的历史 PB 折线图。所有计算实时完成、不落库。

**Architecture:**
- 后端：新增 `BankPBService`（实时算 PB）+ `GET /stock/bank/pb/history` endpoint；扩展 `/api/sec/search` 支持 `org_type_code` 过滤（向后兼容）
- 前端：新增自包含 `BankPBCard.jsx`（用现成 `StockCombobox` + `ReactECharts` + `apiGet`），在 `Etf.jsx:1107` 旁追加 `<BankPBCard />` 一行挂载
- 数据源：`assets_bank`（取 BPS）+ `k_line`（取收盘价），不需要 `sec_code` 参与计算（仅校验 `orgTypeCode=="3"`）

**Tech Stack:** FastAPI / Pydantic / MongoDB (motor) / React + ECharts / pnpm。

---

## Global Constraints

1. **不引入新 pip / pnpm 依赖**
2. **不动 `app/clients/`、`app/repositories/`、`app/mappers/`、`app/models/entities.py`、`app/services/finance_service.py`**
3. **不动 `Etf.jsx` 既有图表 / state / handler / style** —— 仅追加 2 行（import + 挂载）
4. **既有 `/api/sec/search` 调用方（ETF 数据卡 + HKFinanceCard 等）零影响** —— `org_type_code` 参数必须 Optional 默认 None
5. **PB = close / BPS**，BPS 直读 `assets_bank` 候选字段，**不依赖总股本**
6. **不落库** —— 实时计算，无新增 collection
7. **每个 task 结束 git commit**，Conventional Commits
8. **ResultVO 8 字段 envelope** —— 新 endpoint 必须保 `success` 字段
9. **subagent 不能点浏览器** —— UI 验证由 user 手动

---

## File Structure（任务结束时的最终落点）

```
fin-app/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   └── bank_pb_service.py            ← 新增
│   │   ├── models/
│   │   │   └── dto.py                        ← 追加 BankPBHistoryPointDTO / BankPBDTO
│   │   └── api/
│   │       ├── stock.py                      ← 追加 GET /stock/bank/pb/history
│   │       └── sec_code.py                   ← 扩展 /sec/search 接 org_type_code
│   └── tests/
│       ├── test_bank_pb_service.py           ← 新增
│       └── test_seccode_service_org_type_filter.py  ← 新增
├── frontend/
│   └── src/
│       ├── BankPBCard.jsx                    ← 新增
│       └── Etf.jsx                           ← 仅追加 2 行（import + 挂载）
└── docs/superpowers/
    ├── specs/2026-09-06-bank-pb-chart-design.md   ← 已写
    └── plans/2026-09-06-bank-pb-chart.md           ← 当前文件
```

---

## Task 1: 文档（spec + plan）

**Files:**
- Create: `D:\vscodeproject\fin-app\docs\superpowers\specs\2026-09-06-bank-pb-chart-design.md`
- Create: `D:\vscodeproject\fin-app\docs\superpowers\plans\2026-09-06-bank-pb-chart.md`

**Commit:** `docs(spec+plan): 银行股 PB 时序图设计 + 实施计划`

✅ Done by writing these two files.

### Step 1.1 — 验证

```bash
cd D:\vscodeproject\fin-app
git add docs/superpowers/
git status
git commit -m "docs(spec+plan): 银行股 PB 时序图设计 + 实施计划"
```

---

## Task 2: 扩展 `/api/sec/search` 支持 `org_type_code` 过滤

**Files:**
- Modify: `D:\vscodeproject\fin-app\backend\app\services\seccode_service.py`
- Modify: `D:\vscodeproject\fin-app\backend\app\api\sec_code.py`
- Create: `D:\vscodeproject\fin-app\backend\tests\test_seccode_service_org_type_filter.py`

**Commit:** `feat(sec): /api/sec/search 支持 org_type_code 过滤（向后兼容）`

### Step 2.1 — 修改 `seccode_service.py` 的 `search_stocks`

在 `backend/app/services/seccode_service.py:187` 的 `search_stocks` 方法签名加 `org_type_code` 参数；`base_filter` 在传入时附加 `orgTypeCode` 字段。

**关键点**：默认 `None` 时行为完全等价于旧版；既有调用方不受影响。

### Step 2.2 — 修改 `sec_code.py` 的 `/search` endpoint

`backend/app/api/sec_code.py:19-26` 加可选 `org_type_code: str | None = Query(default=None)`，透传到 service。

### Step 2.3 — 写测试 `test_seccode_service_org_type_filter.py`

- 用 moto / mongomock 或现有 repo mock 机制（看仓内既有测试风格）
- 覆盖：
  - 默认 `org_type_code=None` 时返回所有上市股票
  - `org_type_code="3"` 时仅返银行

### Step 2.4 — 验证

```bash
cd D:\vscodeproject\fin-app\backend
pytest tests/test_seccode_service_org_type_filter.py -q
ruff check app/services/seccode_service.py app/api/sec_code.py
```

预期：测试通过、ruff 零警告。

### Step 2.5 — Commit

```bash
git add backend/app/services/seccode_service.py backend/app/api/sec_code.py backend/tests/test_seccode_service_org_type_filter.py
git commit -m "feat(sec): /api/sec/search 支持 org_type_code 过滤（向后兼容）"
```

---

## Task 3: BankPBService + DTO + endpoint + 测试

**Files:**
- Create: `D:\vscodeproject\fin-app\backend\app\services\bank_pb_service.py`
- Modify: `D:\vscodeproject\fin-app\backend\app\models\dto.py`（仅追加）
- Modify: `D:\vscodeproject\fin-app\backend\app\api\stock.py`（仅追加）
- Create: `D:\vscodeproject\fin-app\backend\tests\test_bank_pb_service.py`

**Commit:** `feat(bank): BankPBService + DTO + /stock/bank/pb/history + 测试`

### Step 3.1 — 写 `BankPBService`

`backend/app/services/bank_pb_service.py` 新建：

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

    def __init__(self, assets_bank_repo, kline_service, sec_code_service):
        self.assets_bank_repo = assets_bank_repo
        self.kline_service = kline_service
        self.sec_code_service = sec_code_service

    @staticmethod
    def _pick_first(doc, candidates):
        for k in candidates:
            v = getattr(doc, k, None) or doc.get(k) if isinstance(doc, dict) else getattr(doc, k, None)
            if v is not None and v != "":
                try:
                    return float(v), k
                except (TypeError, ValueError):
                    continue
        return None, None

    async def calculate_pb_history(self, sec_code: str) -> list[BankPBHistoryPointDTO]:
        profit_list = await self.assets_bank_repo.find_all_by_security_code_order_by_report_date_asc(sec_code)
        kline_entity = await self.kline_service.kline_by_sec_code(sec_code)
        klines = kline_entity.klines if kline_entity else []
        results = []
        for p in profit_list:
            rdate = p.reportDate
            if not rdate:
                continue
            bps, bps_field = self._pick_first(p, self._BPS_CANDIDATES)
            close, close_date = self._find_close_on_or_after(klines, rdate)
            err = None
            pe = None
            if bps is None or close is None:
                err_parts = []
                if bps is None:
                    err_parts.append(f"未找到每股净资产字段（已尝试 {len(self._BPS_CANDIDATES)} 个候选名）")
                if close is None:
                    err_parts.append("无 K 线数据")
                err = "；".join(err_parts)
            else:
                pe = round(close / bps, 4)
            results.append(BankPBHistoryPointDTO(
                date=close_date, reportDate=rdate, bps=bps, bpsField=bps_field,
                close=close, pe=pe, error=err,
            ))
        return results

    @staticmethod
    def _find_close_on_or_after(klines, report_date: str):
        for k in klines:
            if k.date and k.date >= report_date:
                try:
                    return float(k.close), k.date
                except (TypeError, ValueError):
                    continue
        return None, None
```

### Step 3.2 — 追加 DTO

`backend/app/models/dto.py` 末尾追加：

```python
class BankPBHistoryPointDTO(BaseModel):
    date: str | None = None
    reportDate: str | None = None
    bps: float | None = None
    bpsField: str | None = None
    close: float | None = None
    pe: float | None = None
    error: str | None = None


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

### Step 3.3 — 追加 endpoint

`backend/app/api/stock.py` 末尾追加：

```python
@router.get("/bank/pb/history")
async def get_bank_pb_history(code: str = Query(...)) -> dict:
    _, _, seccode_service, _ = _services()
    from app.services.bank_pb_service import BankPBService
    entity = await seccode_service.sec_code_entity_by_id(code)
    if not entity or getattr(entity, "orgTypeCode", None) != BankTypeCode:
        return ResultVO.fail(code=400, message="非银行 orgType，不适用").model_dump()
    from app.repositories.base import MongoRepository
    from app.models.entities import AssetsBankEntity
    pb_service = BankPBService(
        assets_bank_repo=MongoRepository(AssetsBankEntity),
        kline_service=_services()[1],
        sec_code_service=seccode_service,
    )
    rows = await pb_service.calculate_pb_history(code)
    return ResultVO.ok(rows).model_dump()
```

### Step 3.4 — 写测试 `test_bank_pb_service.py`

- mock assets_bank_repo + kline_service，断言 PB 计算正确
- 缺 BPS → pe=null + error
- 缺 kline → pe=null + error

### Step 3.5 — 验证

```bash
cd D:\vscodeproject\fin-app\backend
pytest tests/test_bank_pb_service.py -q
ruff check app/services/bank_pb_service.py app/models/dto.py app/api/stock.py
```

### Step 3.6 — Commit

```bash
git add backend/app/services/bank_pb_service.py backend/app/models/dto.py backend/app/api/stock.py backend/tests/test_bank_pb_service.py
git commit -m "feat(bank): BankPBService + DTO + /stock/bank/pb/history + 测试"
```

---

## Task 4: BankPBCard 前端模块 + Etf.jsx 挂载

**Files:**
- Create: `D:\vscodeproject\fin-app\frontend\src\BankPBCard.jsx`
- Modify: `D:\vscodeproject\fin-app\frontend\src\Etf.jsx`（仅追加 2 行）

**Commit:** `feat(frontend): BankPBCard 模块（备选银行列表 + 拼音搜索 + PB 图）`

### Step 4.1 — 写 `BankPBCard.jsx`

自包含组件：
- mount 时拉 `/api/sec/search?org_type_code=3&limit=1000` → bankList
- 选中股票时拉 `/api/stock/bank/pb/history?code=...` → peHistory
- 左侧：StockCombobox + 滚动备选列表
- 右侧：ReactECharts 折线图（x=reportDate, y=PB）

### Step 4.2 — 修改 `Etf.jsx`

仅追加 2 行：

```diff
+ import BankPBCard from './BankPBCard';
```

```diff
              <HKFinanceCard />
+             <BankPBCard />
```

**不动既有图表 / state / handler / style**。

### Step 4.3 — 验证

```bash
cd D:\vscodeproject\fin-app\frontend
pnpm run lint
pnpm run build
```

预期：lint 零警告，build 成功。

### Step 4.4 — Commit

```bash
git add frontend/src/BankPBCard.jsx frontend/src/Etf.jsx
git commit -m "feat(frontend): BankPBCard 模块（备选银行列表 + 拼音搜索 + PB 图）"
```

---

## 最终验证（所有 commit 后）

```bash
cd D:\vscodeproject\fin-app\backend
pytest -q
ruff check app

cd D:\vscodeproject\fin-app\frontend
pnpm run lint
pnpm run build

git log --oneline -10
git status
```

预期：
- 所有 pytest 通过（旧测试零回归）
- ruff 零警告
- pnpm lint + build 零警告
- git status 干净
- git log 显示 4 个 commit

---

## 残留风险（透明）

- mongo 不在线验证实际字段名 → 容错链兜底；DTO `error` 字段显式上报
- BPS 字段名若不在候选链里 → DTO 报"未找到每股净资产字段"
- 银行列表条数取决于 mongo `orgTypeCode=="3"` 数量，预计 ≤ 50 条
- 银行业 BPS 受拨备影响波动大 → PB 时序可能抖动明显（属正常）