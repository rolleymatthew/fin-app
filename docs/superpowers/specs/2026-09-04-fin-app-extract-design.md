# fin-app 项目抽取 — 设计文档

**日期**：2026-09-04
**目的**：把 `D:\vscodepro\react\` 下的 `echart-etf/` 前端页面与 `backend-python/` FastAPI 后端，整体抽到一个干净、独立的新仓库 `D:\vscodepro\fin-app\`。在抽离过程中顺手清理 backend 的 API 文件边界混乱与响应包装不一致两项遗留技术债。

---

## 1. 背景与动机

### 1.1 现状

`D:\vscodepro\react\` 当前并行 4 个 React 前端 + 2 个后端 + 历史 demo：

| 目录 | 角色 | 实际状态 |
|---|---|---|
| `echart-etf/` | 唯一在用的业务前端（Etf.jsx 1111 行 + HKFinanceCard + StockCombobox） | 活跃 |
| `ant-charts-etf-chart/`、`ant-plots-etf-chart/`、`uplot-etf-chart/` | 图库 demo | 长期未演进，仅 demo |
| `backend-python/` | FastAPI 金融数据服务 | 活跃 |
| `backend-java/` | Java 后端的并行版本 | 遗留/对照 |
| `docs/plans/`、`docs/fixbug/` | 历史计划/修复归档 | 历史 |

体感"乱"来自三个原因：
- 4 个前端项目并列写进 AGENTS.md，事实只有 1 个是生产代码
- backend-python 的 `app/api/stock.py` 单文件混了 ETF / K线 / 个股 / HK 4 类共 12 个路由，业务边界不清
- 响应包装 `ResultVO` 字段不齐（缺 `success`、缺 `timestamp`），错误返回与业务返回结构不一致

### 1.2 目标

抽出**单一干净仓库** `fin-app`，作为后续唯一迭代载体；原仓库保留全部历史资产不动。

### 1.3 非目标

- ❌ 不换图表库（保留 echarts）
- ❌ 不重构 `services/`（`finance_service.py` 1854 行、`hk_finance_service.py` 1288 行原样保留）
- ❌ 不动 Mongo schema、不动环境变量默认值
- ❌ 不删 `backend-java/`、不删三个 demo 前端
- ❌ 不动 docs 历史归档、不写 CI

---

## 2. 新仓库总体布局

**位置**：`D:\vscodepro\fin-app\`（独立 git 仓库，与 `D:\vscodepro\react\` 无 git 关联）

```
fin-app/
├── README.md
├── AGENTS.md                  # 工作流约定（承袭 react/AGENTS.md 的精神：先新增不覆盖、不顺
手重构、归档规则）
├── .gitignore
├── docs/
│   └── superpowers/
│       ├── specs/             # 本文档所在
│       └── plans/             # 后续实现计划
├── backend/                   # ← 由 backend-python/ 整库搬入
│   ├── pyproject.toml
│   ├── README.md
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── etf.py         # ETF 搜索 + (PR2 新增) /etf/* /etf/szse* /etf/quarter* 路由
│   │   │   ├── sec_code.py    # /sec/* 路由不变
│   │   │   ├── kline.py       # (PR2 新增) /etf/kline /kline/get /kline/refresh
│   │   │   └── stock.py       # /one /hk/one 路由（PR2 瘦身）
│   │   ├── services/          # 全部原样保留
│   │   ├── clients/           # 全部原样保留（外部数据源）
│   │   ├── repositories/      # 全部原样保留
│   │   ├── models/
│   │   │   └── result.py      # (PR3) 增 success + timestamp 字段
│   │   ├── config.py, db.py, …
│   │   └── constants/
│   ├── scripts/
│   ├── tests/                 # 现有 pytest 用例全搬
│   └── build_fin_service_exe.bat 等保留
└── frontend/                  # ← 由 echart-etf/ 搬入（去重后保留核心）
    ├── package.json
    ├── vite.config.js         # /api 代理指向 127.0.0.1:8080
    ├── index.html
    ├── public/                # 不含 examples/data（demo 静态文件）
    └── src/
        ├── main.jsx
        ├── App.jsx            # 顶部布局（去 demo h1）
        ├── Etf.jsx
        ├── HKFinanceCard.jsx
        ├── StockCombobox.jsx
        ├── HKStockCombobox.jsx
        ├── const.jsx
        ├── api.js             # (PR3 新增) apiGet / apiPost 封装
        ├── App.css, index.css
        └── assets/
```

### 不变量（迁移全程严守）

1. backend 的 16 个 FastAPI 路由在 PR1/PR2 期间**路径与响应字段完全不变**
2. frontend 的 12 个 fetch 调用在 PR1/PR2 期间**完全不改**
3. 三个 demo 前端、`backend-java/`、`docs/` 全部留在 `D:\vscodepro\react\` 不动
4. services / clients / repositories 内部代码不动

---

## 3. Backend API 文件拆分（PR2 范围）

### 3.1 当前 `app/api/stock.py` 路由分布

| 当前路径 | 业务域 | 目标文件 |
|---|---|---|
| `GET /etf`、`GET /etf/all`、`GET /etf/szse`、`POST /etf/szse/sync`、`GET /etf/quarter`、`GET /etf/quarter/get` | ETF | `app/api/etf.py`（与现有同名，**追加** 不重写已有 `/search`、`/backfill-pinyin`） |
| `GET /etf/kline`、`GET /kline/get`、`POST /kline/refresh` | K线 | `app/api/kline.py`（**新文件**） |
| `GET /one`、`GET /hk/one` | 个股抓取 | `app/api/stock.py`（保留，仅删除已被搬走的 ETF/K线段） |
| `GET /check` | 健康检查 | 移入 `app/main.py` 的 `/health` 旁 |

### 3.2 拆分原则

1. **路径零变化**：所有路由前缀与全路径完全保留
2. **函数签名零变化**：所有 `Query()`、`Body()` 参数、`async def` 签名原样
3. **`include_router` 注册顺序不变**：`stock_router` → `sec_code_router` → `etf_router` → `kline_router`
4. **`_services()` 工厂保留**：新文件按需 `lru_cache` 单 service
5. **`/api/etf/search`、`/api/etf/backfill-pinyin` 不动**（`app/api/etf.py` 当前内容已正确）

### 3.3 `app/api/kline.py` 骨架

```python
from functools import lru_cache
from fastapi import APIRouter, Query
from app.services.kline_service import KLineService

router = APIRouter()

@lru_cache
def _service():
    return KLineService()

@router.get("/etf/kline")
async def get_etf_kline(...): ...        # 原 stock.py 函数体不变

@router.get("/kline/get")
async def get_kline(...): ...

@router.post("/kline/refresh")
async def refresh_kline(...): ...
```

### 3.4 `app/main.py` 改动

```python
from app.api.kline import router as kline_router
app.include_router(kline_router, prefix="/api", tags=["kline"])
```

### 3.5 验证

- `curl -s http://127.0.0.1:8080/openapi.json | jq '.paths | keys'` 与 PR1 对比**完全一致**
- frontend `pnpm run dev` 后 Etf 主图 + SZSE sync + K线 refresh + HKFinance 全部正常
- `pytest -q`、`ruff check app` 全绿

---

## 4. 统一响应包装（PR3 范围）

### 4.1 新 `ResultVO`

```python
class ResultVO(BaseModel):
    success: bool            # 新增：true/false 取代 code==0 判定
    code: int = 0            # 保留：业务错误码（0/400/404/500/1001 等）
    message: str = "ok"
    data: Any | None = None
    timestamp: int           # 新增：服务端毫秒时间戳
    path: str = ""           # 新增：当前请求路径（middleware 注入 Request.url.path）
    durationMs: int = 0      # 新增：服务端处理耗时（middleware 注入）
    errorType: str | None = None  # 新增：失败分类（business / validation / unauthorized / service / http）

    @classmethod
    def ok(cls, data=None, *, path="", durationMs=0):
        return cls(success=True, code=0, message="ok", data=data, timestamp=..., path=path, durationMs=durationMs)
    @classmethod
    def fail(cls, code, message, *, errorType="business", path="", durationMs=0):
        return cls(success=False, code=code, message=message, data=None, timestamp=..., path=path, durationMs=durationMs, errorType=errorType)
```

**三个新字段填法**

| 字段 | 来源 | 何时填 |
|---|---|---|
| `path` | middleware 读 `Request.url.path` | 成功/失败都填 |
| `durationMs` | middleware 计时（`time.perf_counter()`） | 成功/失败都填 |
| `errorType` | service 层标记 + exception_handler 映射 | 仅失败时填 |

**`errorType` 取值约定**：
- `business`（默认）：service 主动抛的业务异常（如"ETF 不存在"）
- `validation`：Pydantic / FastAPI 请求体验证失败（422）
- `unauthorized`：401 类
- `not_found`：404 类
- `http`：其他 HTTPException
- `service`：未捕获异常（500）

### 4.2 全局异常处理 + middleware

注册两类组件：
- **middleware**：每个请求进来记 `start = perf_counter()`，请求结束用 `ResultVO.ok(...)` / `ResultVO.fail(...)` 的统一出口注入 `path` + `durationMs`
- **exception_handler**：把 `HTTPException` 和未捕获异常也包装成 `ResultVO.fail(...)`，保证所有路径返回结构一致 + 自动映射 `errorType`

### 4.3 前后端契约

```json
// 成功
{ "success": true,  "code": 0,     "message": "ok",         "data": {...},
  "timestamp": 1735901234567, "path": "/api/etf/get", "durationMs": 42,
  "errorType": null }

// 业务失败（service 抛业务异常）
{ "success": false, "code": 1001,  "message": "ETF 不存在", "data": null,
  "timestamp": 1735901234567, "path": "/api/etf/get", "durationMs": 12,
  "errorType": "business" }

// HTTP 失败（404）
{ "success": false, "code": 404,   "message": "Not Found",  "data": null,
  "timestamp": 1735901234567, "path": "/api/etf/get", "durationMs": 3,
  "errorType": "not_found" }
```

### 4.4 改动波及面

- 后端：`grep -rn "ResultVO\." app/` 全部调用点（预计 ≤40 处），保留 `ok`/`fail` 工厂签名
- 前端：12 处 fetch 调用点同步调整（详见 §5）

---

## 5. 前端同步调整（PR3 同步）

### 5.1 当前 12 处 fetch 调用点

- `frontend/src/Etf.jsx`：10 处
- `frontend/src/HKFinanceCard.jsx`：1 处
- `frontend/src/StockCombobox.jsx`：1 处

### 5.2 抽出 `frontend/src/api.js`

```js
export class ApiError extends Error {
  constructor({ message, code, errorType, path, durationMs }) {
    super(message || '请求失败');
    this.name = 'ApiError';
    this.code = code ?? -1;
    this.errorType = errorType ?? 'unknown';
    this.path = path ?? '';
    this.durationMs = durationMs ?? 0;
  }
}

export async function apiGet(url) {
  const r = await fetch(url);
  const json = await r.json();
  if (!json?.success) {
    throw new ApiError({
      message: json?.message || `HTTP ${r.status}`,
      code: json?.code,
      errorType: json?.errorType,
      path: json?.path,
      durationMs: json?.durationMs,
    });
  }
  return json.data;
}
export async function apiPost(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await r.json();
  if (!json?.success) {
    throw new ApiError({
      message: json?.message || `HTTP ${r.status}`,
      code: json?.code,
      errorType: json?.errorType,
      path: json?.path,
      durationMs: json?.durationMs,
    });
  }
  return json.data;
}
```

### 5.3 调用方改动模式

```js
// 旧（PR1/PR2）
const r = await fetch(url);
const json = await r.json();
const payload = json?.data ?? [];

// 新（PR3）：成功路径直接拿 data；失败路径 try/catch ApiError
try {
  const payload = await apiGet(url);
  // ... 用 payload
} catch (err) {
  if (err instanceof ApiError) {
    alert(err.message);  // 保留现有 alert 文案
    console.warn('[api]', err.errorType, err.path, err.code, err.message);
  } else {
    alert('网络异常');
  }
}
```

**简化说明**：12 处原代码片段已有 `try/catch` 或显式 `alert('调用后台接口失败！')`，只需把内部 `fetch + json.data` 替换为 `await apiGet(...)`、外层错误处理改为捕获 `ApiError`，UX 文案保持不变。

### 5.4 约束

- 12 个 fetch 点**只改取 data 的方式**，**不改 UI 文案、不改业务逻辑**
- 不改路由路径、不改请求参数
- 不引入新 npm 依赖
- 已有 `alert(...)` 文案保持不变（PR3 仅替换取数，不改 UX）

### 5.5 Vite 代理

`vite.config.js` 已配 `/api → 127.0.0.1:8080`，继续生效，零改动。

---

## 6. 迁移节奏

### 6.1 PR0（前置）— 仓库初始化 + spec 提交

已在 root commit 完成：`D:\vscodepro\fin-app\` 下 `git init -b main` 并提交 `docs/superpowers/specs/2026-09-04-fin-app-extract-design.md`。

### 6.2 PR1 — 字节级拷贝 + 双绿验收（1 commit）

1. 从 main 拉新分支
2. `git mv` 复制（保留文件权限）：
   - `D:\vscodepro\react\backend-python\*` → `D:\vscodepro\fin-app\backend\*`
     - **排除**：`__pycache__/`、`.pytest_cache/`、`*.egg-info/`、`app.log`、`build/`、`dist/`
   - `D:\vscodepro\react\echart-etf\*` → `D:\vscodepro\fin-app\frontend\*`
     - **排除**：`node_modules/`、`dist/`、`my-app.exe`
3. **不动文件内部任何一行**
4. 写 `README.md`、`AGENTS.md`、`.gitignore`
5. 验证：
   ```bash
   cd backend && pip install -e . && pytest -q
   python -m uvicorn app.main:app --port 8080   # 另一终端
   cd frontend && pnpm install && pnpm run lint && pnpm run build
   pnpm run dev   # 浏览器手测：Etf 主页加载、K线图渲染、ETF 搜索
   ```

### 6.3 PR2 — API 文件拆分（1~2 commit）

1. 新建 `app/api/kline.py`，搬 `stock.py` 里 `/etf/kline`、`/kline/get`、`/kline/refresh` 三个函数的 def + 函数体；删除 `stock.py` 中这三个函数
2. 把 `stock.py` 里 `/etf/*` 系列搬入 `app/api/etf.py`（**追加，不动已有** `/search`/`/backfill-pinyin`）
3. `/check` 端点搬入 `main.py` 的 `/health` 旁
4. `main.py` 加 `include_router(kline_router, prefix="/api", tags=["kline"])`
5. 验证：`pytest -q`、`ruff check app`、`/openapi.json` 路径与 PR1 一致、frontend Etf 主图 + SZSE sync + K线 refresh + HKFinance 全过

### 6.4 PR3 — 统一响应包装 + 前端同步（2~3 commit）

1. `ResultVO` 加 `success` + `timestamp` + `path` + `durationMs` + `errorType` 字段（详见 §4.1）
2. 加 middleware 注入 `path` + `durationMs`；加 `exception_handler` 包装 `HTTPException` 与未捕获异常，按 §4.1 `errorType` 映射
3. `grep -rn "ResultVO\." app/` 全仓替换调用，保留 `ok`/`fail` 工厂签名
4. frontend 新增 `src/api.js`（含 `ApiError` 类、`apiGet`、`apiPost`），12 处 fetch 改成 `apiGet`/`apiPost` + try/catch `ApiError`
5. 验证：
   - `pytest -q` 全绿（含 "HTTPException 包装" + "middleware 注入 path/duration" + "errorType 分类" 三个新增用例）
   - `curl http://127.0.0.1:8080/api/etf/get?code=999999` → 返回结构符合 §4.3（含 `errorType` 字段）
   - `curl http://127.0.0.1:8080/api/__nonexistent__` → 返回 `errorType: "not_found"`
   - frontend Etf + HKFinance + StockCombobox UI 行为不变；DevTools console 可见 `ApiError` 字段完整
   - `ruff check app`、`pnpm run lint` 全绿

---

## 7. 回滚策略

| 阶段 | 回滚动作 | 老仓库状态 |
|---|---|---|
| PR1 出问题 | `rm -rf fin-app`，重做 | 0 改动 |
| PR2 出问题 | 在新仓库 `git revert` | 0 改动 |
| PR3 出问题 | 在新仓库 `git revert`（可单独 revert 前端 commit） | 0 改动 |

> 注：PR0（spec root commit）失败 = 直接 `rm -rf fin-app`，无须 revert。

任意阶段 PR 失败，老仓库保持 `git status` 干净。

---

## 8. 验收清单

迁移完成的标志：

- [ ] `D:\vscodepro\fin-app\` 独立仓库，前端 + 后端在仓内
- [ ] `backend/app/api/` 下业务域清晰：`etf.py`、`sec_code.py`、`kline.py`、`stock.py`
- [ ] `openapi.json` 路径列表与原 backend-python 完全一致
- [ ] `ResultVO` 含 `success` + `code` + `message` + `data` + `timestamp` + `path` + `durationMs` + `errorType`；`HTTPException` 也被包装为 `ResultVO.fail(...)`
- [ ] frontend `src/api.js` 存在（含 `ApiError` 类），12 处 fetch 全走 `apiGet`/`apiPost` 并 try/catch `ApiError`
- [ ] `pytest -q`、`ruff check app`、`pnpm run lint`、`pnpm run build` 全部退出码 0
- [ ] 浏览器手测：Etf 主页加载、K线渲染、ETF 搜索、SZSE sync、HKFinance、StockCombobox 全部正常
- [ ] `D:\vscodepro\react\` 工作树干净（`git status` 无变更）

---

## 9. 后续（本次不做）

- 把 `backend-python` 跑成 docker 镜像（待 backend-python 当前 docker-compose 已稳定后再评估）
- 把前端跑成独立 docker（同一理由）
- 把 demo 前端三个（ant-charts / ant-plots / uplot）做成 npm workspace 内的对比页
- CI（GitHub Actions 等）
- 把 `ResultVO` 升级到 OpenAPI schema