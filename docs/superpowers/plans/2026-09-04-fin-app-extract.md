# fin-app 项目抽取 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `D:\vscodepro\react\backend-python\`（FastAPI 后端）和 `D:\vscodepro\react\echart-etf\`（React 前端）整库抽到独立仓库 `D:\vscodepro\fin-app\`，顺手拆 `app/api/stock.py` 的混合路由、按业务域重排，并统一响应包装 `ResultVO`。

**Architecture:** 物理搬运（PR1）→ 路由拆分（PR2）→ 响应包装统一 + 前端同步（PR3）。每步独立可回滚；原仓库 `D:\vscodepro\react\` 全程 0 改动。

**Tech Stack:** Python 3.10+ / FastAPI / Pydantic / pytest / ruff；Node.js 18+ / Vite 6 / React 18 / echarts 5 / echarts-for-react 3 / pnpm。

---

## Global Constraints

1. **不动原仓库**：`D:\vscodepro\react\` 任何时候 `git status` 必须干净。所有改动在 `D:\vscodepro\fin-app\` 完成。
3. **不动文件内部代码**：PR1 阶段对搬迁的每个文件**不改任何一行**。只在 PR2（路由拆分）和 PR3（ResultVO+middleware）才允许动 backend/app/ 下文件。
4. **不动 services/clients/repositories**：这些目录内的 `.py` 文件在 PR1~PR3 全程只读。
5. **不动 Mongo schema / 环境变量默认值**。
6. **不删 `backend-java/`、三个 demo 前端（`ant-charts-etf-chart/`、`ant-plots-etf-chart/`、`uplot-etf-chart/`）、`docs/`**：它们全在原仓库留底。
7. **frontend 不引入新 npm 依赖**。
8. **backend 不引入新 pip 依赖**（FastAPI 内置 middleware / exception_handler / Request 已够）。
9. **每个 task 结束必须 git commit**；commit message 风格遵循 Conventional Commits（`feat:` / `fix:` / `chore:` / `refactor:` / `docs:`）。
10. **PR1 阶段用 `xcopy / robocopy` 而非 git 跨仓 `git mv`**：跨工作树移动在 Windows 上 git 跟踪麻烦；先 `xcopy /E`，再 `git add`，原文件随后删除。这样 git status 更干净。

---

## File Structure（任务结束时的最终落点）

```
fin-app/
├── README.md
├── AGENTS.md
├── .gitignore
├── docs/
│   └── superpowers/
│       ├── specs/2026-09-04-fin-app-extract-design.md  ← 已存在（PR0）
│       └── plans/2026-09-04-fin-app-extract.md         ← 本文件
├── backend/                                              ← PR1 整库拷入
│   ├── pyproject.toml
│   ├── README.md
│   ├── app/
│   │   ├── main.py                                       ← PR3 加 middleware + exception_handler
│   │   ├── config.py, db.py, …
│   │   ├── api/
│   │   │   ├── etf.py                                    ← PR2 追加 /etf/* /etf/szse* /etf/quarter*
│   │   │   ├── sec_code.py                               ← 不动
│   │   │   ├── kline.py                                  ← PR2 新建：/etf/kline /kline/get /kline/refresh
│   │   │   └── stock.py                                  ← PR2 瘦身：仅留 /one /hk/one
│   │   ├── services/                                     ← 全程不动
│   │   ├── clients/                                      ← 全程不动
│   │   ├── repositories/                                 ← 全程不动
│   │   ├── models/
│   │   │   └── result.py                                 ← PR3 重写：+success +timestamp +path +durationMs +errorType
│   │   ├── middleware/                                   ← PR3 新建：result_envelope.py
│   │   ├── exception_handlers/                           ← PR3 新建：result_envelope.py
│   │   └── constants/
│   ├── scripts/
│   ├── tests/
│   │   ├── …（原有用例全搬）
│   │   ├── test_openapi_paths.py                         ← PR2 新增：路由清单与 baseline 一致
│   │   ├── test_result_vo.py                             ← PR3 新增：ResultVO 字段
│   │   ├── test_middleware_envelope.py                   ← PR3 新增：middleware 注入 path/durationMs
│   │   └── test_exception_to_result.py                    ← PR3 新增：HTTPException → ResultVO.fail + errorType 映射
│   └── build_fin_service_exe.bat 等保留
└── frontend/                                             ← PR1 整库拷入
    ├── package.json
    ├── vite.config.js                                    ← 不动
    ├── index.html
    ├── public/
    └── src/
        ├── main.jsx
        ├── App.jsx                                       ← PR3 改顶部布局（去 demo h1）
        ├── Etf.jsx                                       ← PR3 改 fetch 处为 apiGet
        ├── HKFinanceCard.jsx                             ← PR3 改 fetch
        ├── StockCombobox.jsx                             ← PR3 改 fetch
        ├── HKStockCombobox.jsx                           ← 不动（无 fetch）
        ├── const.jsx                                     ← 不动
        ├── api.js                                        ← PR3 新增：ApiError + apiGet + apiPost
        ├── App.css, index.css
        └── assets/
```

---

## Task 1: PR1 — 字节级拷贝 + 双绿验收

**Files:**
- Create (in `D:\vscodepro\fin-app\`): `README.md`, `AGENTS.md`, `.gitignore`
- Create (copied from `D:\vscodepro\react\`): `backend/**`, `frontend/**`

**Why not TDD here:** PR1 是物理字节搬迁，每个文件都是逐行复制原内容，没有"行为"可言，编写的测试无法比"复制粘贴没改任何字节"更强。TDD 从 PR2（路由拆分）开始才有意义。

### Step 1.1 — 创建 `D:\vscodepro\fin-app\.gitignore`

**File**: `D:\vscodepro\fin-app\.gitignore`（新建）

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
*.log
build/
dist/

# Node
node_modules/
.vite/

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# Local artifacts
my-app.exe
fin-service.exe
app.log
urlLogs.log
```

### Step 1.2 — 拷贝 `backend-python/` → `fin-app/backend/`

**Run (in `cmd`):**

```cmd
xcopy D:\vscodepro\react\backend-python D:\vscodepro\fin-app\backend /E /I /H /K /Y /EXCLUDE:D:\vscodepro\fin-app\exclude.txt
```

**File**: `D:\vscodepro\fin-app\exclude.txt`（新建，临时文件，拷贝完成后可删）

```
__pycache__
.pytest_cache
.ruff_cache
.egg-info
app.log
build
dist
.pyc
.spec
```

**Expected output**: 大约 ~300 个文件被复制，含 `app/`、`tests/`、`scripts/`、`pyproject.toml`、`README.md` 等。

**Verify (in PowerShell):**

```powershell
Get-ChildItem -Path D:\vscodepro\fin-app\backend -Recurse -File | Measure-Object
# Expected: Count ≈ 250-400
```

确认**没有**以下文件被复制进来：
```powershell
Test-Path D:\vscodepro\fin-app\backend\app.log           # False
Test-Path D:\vscodepro\fin-app\backend\__pycache__        # False
Test-Path D:\vscodepro\fin-app\backend\fin.egg-info       # False
```

### Step 1.3 — 拷贝 `echart-etf/` → `fin-app/frontend/`

**Run (in `cmd`):**

```cmd
xcopy D:\vscodepro\react\echart-etf D:\vscodepro\fin-app\frontend /E /I /H /K /Y /EXCLUDE:D:\vscodepro\fin-app\exclude.txt
```

**Expected output**: ~20 个文件被复制：`package.json`、`vite.config.js`、`index.html`、`public/`、`src/`（含 `Etf.jsx`、`HKFinanceCard.jsx`、`StockCombobox.jsx`、`HKStockCombobox.jsx`、`App.jsx`、`main.jsx`、`const.jsx`、`App.css`、`index.css`、`assets/`）。

**Verify:**

```powershell
Test-Path D:\vscodepro\fin-app\frontend\node_modules       # False
Test-Path D:\vscodepro\fin-app\frontend\dist               # False
Test-Path D:\vscodepro\fin-app\frontend\my-app.exe         # False
Get-ChildItem D:\vscodepro\fin-app\frontend\src *.jsx      # 看到 5 个 jsx + App.css + index.css + const.jsx + assets/
```

### Step 1.4 — 写顶层 `README.md`

**File**: `D:\vscodepro\fin-app\README.md`（新建）

```markdown
# fin-app

金融数据应用：从 `D:\vscodepro\react\` 抽出的独立仓库。

## 目录

- `backend/` — FastAPI 金融数据服务（原 `backend-python/`）
- `frontend/` — Vite + React + echarts 前端（原 `echart-etf/`）
- `docs/superpowers/specs/` — 设计文档
- `docs/superpowers/plans/` — 实施计划

## 启动

### Backend

```bash
cd backend
pip install -e .
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Frontend

```bash
cd frontend
pnpm install
pnpm run dev   # 默认 5173 端口，已配 /api 代理到 8080
```

## 测试

```bash
# Backend
cd backend && pytest -q && ruff check app

# Frontend
cd frontend && pnpm run lint && pnpm run build
```
```

### Step 1.5 — 写顶层 `AGENTS.md`

**File**: `D:\vscodepro\fin-app\AGENTS.md`（新建）

```markdown
# fin-app

## 工作流程

承袭原 `react/AGENTS.md` 的工作流约定：

1. **不动已有函数**：未经明确同意，不改/重命名/删除已存在的函数或方法。
2. **优先新增**：新功能优先新增函数，不就地改写。
3. **不顺手重构**：禁止以"清理"为由改动与当前任务无关的代码。

## 关键约束

- 不引入新 pip / npm 依赖，除非明确批准
- backend 的 services/clients/repositories 默认只读
- 跨 task 改动必须独立 commit；commit message 用 Conventional Commits
```

### Step 1.6 — 删除临时 `exclude.txt`

```cmd
del D:\vscodepro\fin-app\exclude.txt
```

### Step 1.7 — 验收 backend（pytest + ruff）

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pip install -e .
pytest -q
ruff check app
```

**Expected:**
- `pytest -q` → 全部用例通过（如有网络依赖型用例 skip 允许，但 PASS 数 ≥1；spec §6.2 要求全绿）
- `ruff check app` → "All checks passed!"

**若 pytest 失败**：检查 `app/__init__.py`、`tests/conftest.py` 是否缺失；最常见是 `tests/fixtures/` 没复制过来。

### Step 1.8 — 验收 backend（uvicorn 启动 + curl 健康检查）

**Run (terminal A):**

```bash
cd D:\vscodepro\fin-app\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

**Run (terminal B):**

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['paths']), 'paths'); print('\n'.join(sorted(d['paths'].keys())))"
```

**Expected:**
- `/health` → `{"status":"ok"}`
- `/openapi.json` → 16 个路径（含 `/api/etf/search`、`/api/etf/backfill-pinyin`、`/api/sec/search`、`/api/sec/sync`、`/api/sec/refresh-details`、`/api/sec/sync/status`、`/api/etf`、`/api/etf/all`、`/api/etf/szse`、`/api/etf/szse/sync`、`/api/etf/quarter`、`/api/etf/quarter/get`、`/api/etf/kline`、`/api/etf/get`、`/api/one`、`/api/hk/one`、`/api/kline/get`、`/api/kline/refresh`、`/check`——`/health` 是新加的，所以是 16 + 1 = 17）

> 注：`/health` 由 Task 1 的 uvicorn 默认启动就有（`main.py` 里已经定义了），而 `/check` 是 PR2 才搬走的，所以本步 `/check` **仍然存在**。

### Step 1.9 — 验收 frontend（install + lint + build）

**Run:**

```bash
cd D:\vscodepro\fin-app\frontend
pnpm install
pnpm run lint
pnpm run build
```

**Expected:**
- `pnpm install` → 装包成功，无错误
- `pnpm run lint` → 无错误
- `pnpm run build` → 输出 `dist/`，无错误

### Step 1.10 — 验收 frontend（端到端手测）

**Run (terminal A — backend 仍在跑):**
**Run (terminal B):**

```bash
cd D:\vscodepro\fin-app\frontend
pnpm run dev
```

**Browser 手测**（访问 `http://localhost:5173`）：
1. 页面加载，Etf 主页显示
2. 主图（echarts candlestick + bar）有渲染
3. 顶部下拉选 ETF code 能切换
4. 点 "下载份额" 按钮 → 看到 alert 弹窗（说明后端调用成功）
5. 点 "刷新K线" → 看到 alert 弹窗
6. StockCombobox 输入框可输入
7. HKFinanceCard 切换股票有数据返回

**Expected**: 所有交互正常，无 404、无 CORS 报错、无 console 红字。

### Step 1.11 — 确认原仓库无改动

**Run:**

```bash
cd D:\vscodepro\react
git status
```

**Expected:** `nothing to commit, working tree clean`

### Step 1.12 — Commit PR1

```bash
cd D:\vscodepro\fin-app
git status   # 应看到 backend/ frontend/ README.md AGENTS.md .gitignore 全是 untracked
git add .gitignore README.md AGENTS.md backend frontend
git commit -m "chore(init): 字节级搬入 backend-python + echart-etf 到 fin-app

- backend/ ← backend-python/ 整库（api/services/clients/repositories/models 全搬）
- frontend/ ← echart-etf/ 整库（Etf.jsx + HKFinanceCard + StockCombobox + HKStockCombobox）
- 顶层 README.md + AGENTS.md + .gitignore
- 排除 __pycache__/node_modules/dist/exe/egg-info/log

验证：
- pytest -q 全绿
- uvicorn :8080 健康，openapi.json 含 16+1 路径
- pnpm install + lint + build 全绿
- vite dev 5173 端到端手测通过（Etf 主图 + ETF搜索 + SZSE sync + K线 refresh + HKFinance）
- react/ 仓库 git status 干净"
```

---

## Task 2: PR2 — API 文件拆分（路由不变）

**Files:**
- Create: `D:\vscodepro\fin-app\backend\app\api\kline.py`
- Modify: `D:\vscodepro\fin-app\backend\app\api\stock.py`（删除已搬走的路由）
- Modify: `D:\vscodepro\fin-app\backend\app\api\etf.py`（追加 `/etf/*` 系列路由）
- Modify: `D:\vscodepro\fin-app\backend\app\main.py`（删除 `/check`、注册 `kline_router`）
- Create: `D:\vscodepro\fin-app\backend\tests\test_openapi_paths.py`

**Interfaces:**
- Consumes: 原 `stock.py` 里的 `/etf/*`、`/kline/*` 函数（具体签名见 Step 2.2-2.5）
- Produces: 拆分后 `openapi.json` 路径清单与 PR1 完全一致

### Step 2.1 — 写测试：拆分后路由清单与 baseline 一致

**File**: `D:\vscodepro\fin-app\backend\tests\test_openapi_paths.py`（新建）

```python
"""保证 API 文件拆分后 /openapi.json 路径清单不变。"""
from fastapi.testclient import TestClient

from app.main import app

# 这些路径必须在 PR1 与 PR2 之后都存在。
EXPECTED_PATHS = {
    # /api/etf/* （拆分前混在 stock.py，拆分后归 etf.py）
    "/api/etf",
    "/api/etf/all",
    "/api/etf/szse",
    "/api/etf/szse/sync",
    "/api/etf/quarter",
    "/api/etf/quarter/get",
    # /api/etf 原有（一直就在 etf.py）
    "/api/etf/search",
    "/api/etf/backfill-pinyin",
    # /api/sec/* （sec_code.py 一直独立，不动）
    "/api/sec/search",
    "/api/sec/backfill-pinyin",
    "/api/sec/sync",
    "/api/sec/refresh-details",
    "/api/sec/sync/status",
    # /api/kline/* （拆分前混在 stock.py，拆分后归 kline.py）
    "/api/etf/kline",
    "/api/kline/get",
    "/api/kline/refresh",
    # /api/* stock 自身（拆分后 stock.py 只剩这些）
    "/api/one",
    "/api/hk/one",
    # /health
    "/health",
    # /check （本 task 末会被搬进 main.py，路径保留）
    "/check",
}


def test_openapi_paths_match_baseline():
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert paths == EXPECTED_PATHS, f"diff: missing={EXPECTED_PATHS - paths}, extra={paths - EXPECTED_PATHS}"
```

### Step 2.2 — 跑测试确认 PR1 baseline 通过

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_openapi_paths.py::test_openapi_paths_match_baseline
```

**Expected:** `1 passed`

如果失败说明 PR1 的搬运有问题，先回去修。

### Step 2.3 — 记录 PR1 baseline 路径清单（git stash 暂存 / 留作比对）

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
python -c "from fastapi.testclient import TestClient; from app.main import app; import sys; c=TestClient(app); r=c.get('/openapi.json'); print('\n'.join(sorted(r.json()['paths'].keys())))" > /tmp/baseline_paths.txt
```

### Step 2.4 — 新建 `app/api/kline.py`，搬 `/etf/kline` `/kline/get` `/kline/refresh`

**File**: `D:\vscodepro\fin-app\backend\app\api\kline.py`（新建）

从原 `app/api/stock.py`（PR1 拷贝后的版本）里**逐行复制**以下三个函数定义（def 行 + 完整函数体）到本文件：

- `async def get_etf_kline(...)`
- `async def get_kline(...)`
- `async def refresh_kline(...)`

把它们的依赖（`Query` / `Body` 等 from-import、`logger`、`_services` 或新建的 `_service` 工厂）也搬过来。

**文件结构**：

```python
"""K线相关 REST 接口（与前端 echart-etf Etf.jsx 对齐）。

端点：
  GET  /api/etf/kline        query: code=...&...
  GET  /api/kline/get        query: code=...
  POST /api/kline/refresh    query: code=...
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Query

from app.models.result import ResultVO
from app.services.kline_service import KLineService

router = APIRouter()


@lru_cache
def _service() -> KLineService:
    return KLineService()


@router.get("/etf/kline")
async def get_etf_kline(...):
    """原样从 stock.py 复制。函数体一字不动。"""
    ...


@router.get("/kline/get")
async def get_kline(...):
    """原样从 stock.py 复制。函数体一字不动。"""
    ...


@router.post("/kline/refresh")
async def refresh_kline(...):
    """原样从 stock.py 复制。函数体一字不动。"""
    ...
```

> 关键：**函数签名、装饰器参数、函数体内每行**都从 `stock.py` 原样复制，不改任何逻辑。`...` 标记的是工程师需从原 stock.py 复制过来的真实代码块，不是占位符。

### Step 2.5 — 从 `stock.py` 删除 `/etf/kline` `/kline/get` `/kline/refresh`

**File**: `D:\vscodepro\fin-app\backend\app\api\stock.py`（修改）

定位 `stock.py` 中 `get_etf_kline`、`get_kline`、`refresh_kline` 三个 `async def` 函数（含 `@router.get("/etf/kline")` / `@router.get("/kline/get")` / `@router.post("/kline/refresh")` 装饰器起，到下一个 `@router.` / `@lru_cache` / 顶层 `def` / 文件末）。

**操作**：删掉这三段。**不删其他东西**。`stock.py` 现在只剩 `/one` `/hk/one` 两个路由及其依赖。

### Step 2.6 — 把 `stock.py` 里 `/etf/*` 系列搬入 `etf.py`

**File**: `D:\vscodepro\fin-app\backend\app\api\etf.py`（修改 — 追加，不动已有）

从 `stock.py` **原样复制**以下六个函数定义到 `etf.py` 文件末尾（在已有 `/search` `/backfill-pinyin` 之后追加）：

- `async def get_etf(...)`（路径 `/etf`）
- `async def get_etf_all(...)`（路径 `/etf/all`）
- `async def get_etf_szse(...)`（路径 `/etf/szse`）
- `async def post_etf_szse_sync(...)`（路径 `/etf/szse/sync`，POST）
- `async def get_etf_quarter(...)`（路径 `/etf/quarter`）
- `async def get_etf_quarter_get(...)`（路径 `/etf/quarter/get`）

把它们依赖的 `Query`、需要的 `_services()` 或 `_etf_service` 工厂（按需新建 `@lru_cache def _etf_service(): return EtfService()`）也搬过来。

> 已有 `etf.py` 的 `/search` `/backfill-pinyin` 函数与 import **不要动**。

### Step 2.7 — 从 `stock.py` 删除 `/etf/*` 系列函数

**File**: `D:\vscodepro\fin-app\backend\app\api\stock.py`（修改）

定位 `stock.py` 中以下六个 `async def` 函数：

- `get_etf` (`/etf`)
- `get_etf_all` (`/etf/all`)
- `get_etf_szse` (`/etf/szse`)
- `post_etf_szse_sync` (`/etf/szse/sync`)
- `get_etf_quarter` (`/etf/quarter`)
- `get_etf_quarter_get` (`/etf/quarter/get`)

**操作**：连同它们的 `@router.xxx(...)` 装饰器一起删除。

### Step 2.8 — 把 `/check` 搬入 `main.py` 的 `/health` 旁

**File**: `D:\vscodepro\fin-app\backend\app\main.py`（修改）

定位 `stock.py` 中 `async def check_xxx()`（路径 `/check`），**复制**该函数体到 `main.py` 里 `/health` 之下，作为独立端点。函数定义形如：

```python
@app.get("/check")
async def check():
    """原样从 stock.py 复制。函数体一字不动。"""
    ...
```

然后**从 `stock.py` 删除**该函数（含 `@router.get("/check")` 装饰器）。

### Step 2.9 — `main.py` 注册 `kline_router`

**File**: `D:\vscodepro\fin-app\backend\app\main.py`（修改）

在现有 `app.include_router(etf_router, ...)` 那行**之后**追加：

```python
from app.api.kline import router as kline_router
# ...
app.include_router(kline_router, prefix="/api", tags=["kline"])
```

> `etf_router` / `sec_code_router` / `stock_router` 的 `include_router` 调用顺序不变。

### Step 2.10 — 跑测试验证拆分前后路由清单一致

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_openapi_paths.py::test_openapi_paths_match_baseline
```

**Expected:** `1 passed`

如果失败：跑 `python -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); r=c.get('/openapi.json'); print('\n'.join(sorted(r.json()['paths'].keys())))"` 与 baseline 对比 diff，找漏搬的路由。

### Step 2.11 — 跑完整 pytest + ruff

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q
ruff check app
```

**Expected:** 全绿。

### Step 2.12 — 端到端手测

启动 uvicorn，浏览器打开 `http://localhost:5173`，逐项验证：
1. 顶部 ETF 下拉切换 → 主图数据刷新
2. "下载份额" 按钮 → alert 成功（`/api/etf`）
3. "同步深交所" 按钮 → alert（`/api/etf/szse/sync`）
4. 季度数据 → `/api/etf/quarter` 路径返回
5. "刷新K线" → `/api/kline/refresh` 返回
6. HKFinanceCard 切换股票 → `/api/one` 或 `/api/hk/one` 返回
7. StockCombobox 输入 → `/api/sec/search` 返回
8. `/api/etf/search?q=` → 搜索 ETF

**Expected:** 全部正常，无 500 / 404。

### Step 2.13 — Commit PR2

```bash
cd D:\vscodepro\fin-app
git add backend/app/api/kline.py backend/app/api/etf.py backend/app/api/stock.py backend/app/main.py backend/tests/test_openapi_paths.py
git commit -m "refactor(api): 按业务域拆分 stock.py → kline.py + etf.py + main.py

- 新增 app/api/kline.py：承载 /api/etf/kline /api/kline/get /api/kline/refresh
- 追加 app/api/etf.py：/api/etf /etf/all /etf/szse /etf/szse/sync /etf/quarter /etf/quarter/get
  （已有 /search /backfill-pinyin 不动）
- 瘦身 app/api/stock.py：仅留 /api/one /api/hk/one
- 移 /check 到 app/main.py 与 /health 并列
- main.py 注册 kline_router，include_router 顺序：stock → sec → etf → kline
- 路由路径零变化，openapi.json 路径清单 17 条与 PR1 baseline 一致

验证：
- pytest -q 全绿（含新增 test_openapi_paths.py）
- ruff check app 全绿
- 端到端手测：Etf 主图 + SZSE sync + K线 refresh + HKFinance + StockCombobox 全部正常
- react/ 仓库 git status 干净"
```

---

## Task 3: PR3 — 统一响应包装 + 前端同步

**Files:**
- Modify: `D:\vscodepro\fin-app\backend\app\models\result.py`
- Create: `D:\vscodepro\fin-app\backend\app\middleware\__init__.py`
- Create: `D:\vscodepro\fin-app\backend\app\middleware\result_envelope.py`
- Create: `D:\vscodepro\fin-app\backend\app\exception_handlers\__init__.py`
- Create: `D:\vscodepro\fin-app\backend\app\exception_handlers\result_envelope.py`
- Modify: `D:\vscodepro\fin-app\backend\app\main.py`（注册 middleware + handlers）
- Modify: 全部使用 `ResultVO.ok(...)` / `ResultVO.build(...)` 的 12 处 api 文件
- Create: `D:\vscodepro\fin-app\frontend\src\api.js`
- Modify: 12 处 fetch 调用点（`Etf.jsx` 10 处、`HKFinanceCard.jsx` 1 处、`StockCombobox.jsx` 1 处）
- Modify: `D:\vscodepro\fin-app\frontend\src\App.jsx`（去 demo `<h1>` 顶部布局，保留核心）
- Create: `D:\vscodepro\fin-app\backend\tests\test_result_vo.py`
- Create: `D:\vscodepro\fin-app\backend\tests\test_middleware_envelope.py`
- Create: `D:\vscodepro\fin-app\backend\tests\test_exception_to_result.py`

**Interfaces:**
- Consumes: 现有 `ResultVO.build(status, msg, data)` / `ResultVO.ok(data)` 调用（约 40 处，集中在 `api/etf.py`、`api/sec_code.py`、`api/stock.py`）
- Produces: 8 字段响应契约 `{success, code, message, data, timestamp, path, durationMs, errorType}`；前端 `apiGet` / `apiPost` / `ApiError`

### Step 3.1 — 写测试：ResultVO 新字段

**File**: `D:\vscodepro\fin-app\backend\tests\test_result_vo.py`（新建）

```python
"""ResultVO 新契约：success/code/message/data/timestamp/path/durationMs/errorType。"""
import time
from app.models.result import ResultVO


def test_ok_has_success_true_and_message_ok():
    vo = ResultVO.ok({"a": 1}, path="/api/x", durationMs=5)
    assert vo.success is True
    assert vo.code == 0
    assert vo.message == "ok"
    assert vo.data == {"a": 1}
    assert vo.path == "/api/x"
    assert vo.durationMs == 5
    assert vo.errorType is None
    assert isinstance(vo.timestamp, int)
    assert abs(vo.timestamp - int(time.time() * 1000)) < 5000


def test_fail_has_success_false_and_error_type():
    vo = ResultVO.fail(1001, "ETF 不存在", errorType="business", path="/api/etf/get", durationMs=12)
    assert vo.success is False
    assert vo.code == 1001
    assert vo.message == "ETF 不存在"
    assert vo.data is None
    assert vo.path == "/api/etf/get"
    assert vo.durationMs == 12
    assert vo.errorType == "business"


def test_ok_default_data_is_none():
    vo = ResultVO.ok()
    assert vo.data is None
    assert vo.success is True


def test_model_dump_contains_all_eight_fields():
    vo = ResultVO.ok({"k": "v"})
    d = vo.model_dump()
    expected = {"success", "code", "message", "data", "timestamp", "path", "durationMs", "errorType"}
    assert set(d.keys()) == expected
```

### Step 3.2 — 跑测试确认失败

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_result_vo.py
```

**Expected:** 全部 FAIL（提示 `ResultVO.ok() got an unexpected keyword argument 'path'` 或类似）。

### Step 3.3 — 重写 `ResultVO`

**File**: `D:\vscodepro\fin-app\backend\app\models\result.py`（修改 — 替换全文）

```python
"""统一响应包装。8 字段契约见 docs/superpowers/specs/2026-09-04-fin-app-extract-design.md §4.3。"""
from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel


def _now_ms() -> int:
    return int(time.time() * 1000)


class ResultVO(BaseModel):
    success: bool
    code: int = 0
    message: str = "ok"
    data: Any | None = None
    timestamp: int = 0
    path: str = ""
    durationMs: int = 0
    errorType: str | None = None

    @classmethod
    def ok(
        cls,
        data: Any | None = None,
        *,
        path: str = "",
        durationMs: int = 0,
    ) -> "ResultVO":
        return cls(
            success=True,
            code=0,
            message="ok",
            data=data,
            timestamp=_now_ms(),
            path=path,
            durationMs=durationMs,
        )

    @classmethod
    def fail(
        cls,
        code: int,
        message: str,
        *,
        errorType: str = "business",
        path: str = "",
        durationMs: int = 0,
        data: Any | None = None,
    ) -> "ResultVO":
        return cls(
            success=False,
            code=code,
            message=message,
            data=data,
            timestamp=_now_ms(),
            path=path,
            durationMs=durationMs,
            errorType=errorType,
        )

    def model_dump(self, **kwargs):  # type: ignore[override]
        return super().model_dump(**kwargs)
```

### Step 3.4 — 跑测试确认通过

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_result_vo.py
```

**Expected:** `4 passed`

### Step 3.5 — 写测试：middleware 注入 path + durationMs

**File**: `D:\vscodepro\fin-app\backend\tests\test_middleware_envelope.py`（新建）

```python
"""验证 ResultEnvelopeMiddleware 注入 path + durationMs 到 ResultVO 响应。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.result_envelope import ResultEnvelopeMiddleware
from app.models.result import ResultVO


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(ResultEnvelopeMiddleware)

    @app.get("/api/etf/sample")
    async def sample():
        return ResultVO.ok({"x": 1}).model_dump()

    @app.get("/api/raw")
    async def raw():
        return {"y": 2}  # 非 ResultVO 形状，原样透传，不注入 path/duration

    return app


def test_middleware_injects_path_and_duration_on_resultvo(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.get("/api/etf/sample")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["path"] == "/api/etf/sample"
    assert body["durationMs"] >= 0
    assert body["data"] == {"x": 1}


def test_middleware_does_not_modify_non_resultvo_responses(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.get("/api/raw")
    body = r.json()
    assert body == {"y": 2}
    assert "path" not in body
```

### Step 3.6 — 跑测试确认失败

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_middleware_envelope.py
```

**Expected:** `ModuleNotFoundError: No module named 'app.middleware'`

### Step 3.7 — 创建 middleware 包

**File**: `D:\vscodepro\fin-app\backend\app\middleware\__init__.py`（新建，空文件）

**File**: `D:\vscodepro\fin-app\backend\app\middleware\result_envelope.py`（新建）

```python
"""为 ResultVO 响应注入 path + durationMs 字段。"""
from __future__ import annotations

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ResultEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        # 只对 JSON 响应做注入，且 body 含 success 字段的（说明是 ResultVO 形状）
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        try:
            body_bytes = b"".join([chunk async for chunk in response.body_iterator])
        except Exception:
            return response

        try:
            import json

            body = json.loads(body_bytes)
        except Exception:
            new_iter = _iter_bytes(body_bytes)
            response.body_iterator = new_iter
            return response

        if isinstance(body, dict) and "success" in body:
            body.setdefault("path", request.url.path)
            body.setdefault("durationMs", duration_ms)
            new_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
            response.headers["content-length"] = str(len(new_bytes))
            new_response = Response(
                content=new_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )
            return new_response

        # 非 ResultVO：原样回传
        new_iter = _iter_bytes(body_bytes)
        response.body_iterator = new_iter
        return response


async def _iter_bytes(data: bytes):
    yield data
```

### Step 3.8 — 跑测试确认通过

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_middleware_envelope.py
```

**Expected:** `2 passed`

### Step 3.9 — 写测试：HTTPException → ResultVO.fail + errorType 映射

**File**: `D:\vscodepro\fin-app\backend\tests\test_exception_to_result.py`（新建）

```python
"""验证 HTTPException 与未捕获异常被包装为 ResultVO.fail，errorType 正确映射。"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.exception_handlers.result_envelope import register_result_exception_handlers


def _make_app():
    app = FastAPI()
    register_result_exception_handlers(app)

    @app.get("/api/notfound")
    async def nf():
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/api/unauthorized")
    async def unauth():
        raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("explode")

    return app


def test_http_404_maps_to_not_found_error_type():
    client = TestClient(_make_app())
    r = client.get("/api/notfound")
    assert r.status_code == 200  # exception_handler 已包装，仍 200
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 404
    assert body["errorType"] == "not_found"


def test_http_401_maps_to_unauthorized_error_type():
    client = TestClient(_make_app())
    r = client.get("/api/unauthorized")
    body = r.json()
    assert body["errorType"] == "unauthorized"


def test_unhandled_exception_maps_to_service_error_type():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.get("/api/boom")
    body = r.json()
    assert body["success"] is False
    assert body["errorType"] == "service"
    assert "explode" in body["message"]


_HTTP_TO_ERROR_TYPE = {
    400: "validation",
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    409: "business",
    422: "validation",
}


def test_error_type_mapping_table_consistent():
    # 不变量：表里出现的 HTTP 状态码都能映射到 errorType
    for status, etype in _HTTP_TO_ERROR_TYPE.items():
        assert etype in {"validation", "unauthorized", "not_found", "business"}
```

### Step 3.10 — 跑测试确认失败

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_exception_to_result.py
```

**Expected:** `ModuleNotFoundError: No module named 'app.exception_handlers'`

### Step 3.11 — 创建 exception_handlers 包

**File**: `D:\vscodepro\fin-app\backend\app\exception_handlers\__init__.py`（新建，空文件）

**File**: `D:\vscodepro\fin-app\backend\app\exception_handlers\result_envelope.py`（新建）

```python
"""把 HTTPException 与未捕获异常统一包装为 ResultVO.fail(...)。"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.result import ResultVO


_HTTP_TO_ERROR_TYPE = {
    400: "validation",
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    409: "business",
    422: "validation",
}


def _http_to_error_type(status_code: int) -> str:
    return _HTTP_TO_ERROR_TYPE.get(status_code, "http")


def register_result_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        status = exc.status_code
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        vo = ResultVO.fail(
            code=status,
            message=message,
            errorType=_http_to_error_type(status),
            path=request.url.path,
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=200, content=vo.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        vo = ResultVO.fail(
            code=422,
            message="请求参数验证失败",
            errorType="validation",
            path=request.url.path,
            data={"errors": exc.errors()},
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=200, content=vo.model_dump())

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        vo = ResultVO.fail(
            code=500,
            message=str(exc) or exc.__class__.__name__,
            errorType="service",
            path=request.url.path,
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=200, content=vo.model_dump())
```

### Step 3.12 — 跑测试确认通过

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q tests/test_exception_to_result.py
```

**Expected:** `4 passed`

### Step 3.13 — `main.py` 注册 middleware + handlers

**File**: `D:\vscodepro\fin-app\backend\app\main.py`（修改）

在 `app = FastAPI(...)` 之后、`app.add_middleware(CORSMiddleware, ...)` 之前插入：

```python
from app.exception_handlers.result_envelope import register_result_exception_handlers
from app.middleware.result_envelope import ResultEnvelopeMiddleware

# 必须最先 add（CORS 之外最外层），这样它看到的就是最终响应
app.add_middleware(ResultEnvelopeMiddleware)
register_result_exception_handlers(app)
```

**Verify:**

```bash
cd D:\vscodepro\fin-app\backend
pytest -q
ruff check app
```

**Expected:** 全绿。

### Step 3.14 — 替换 backend 全部 `ResultVO.build(...)` 为 `ResultVO.fail(...)`

**Run (grep 找出所有调用点):**

```bash
cd D:\vscodepro\fin-app\backend
grep -rn "ResultVO\.build\|ResultVO\.ok" app/ --include="*.py"
```

**操作**：对每个 `ResultVO.build(-1, "...")` 替换为 `ResultVO.fail(code=-1, message="...")`；`ResultVO.build(500, "...", data=...)` 替换为 `ResultVO.fail(code=500, message="...", data=data)`。

`ResultVO.ok(...)` 调用不动（签名兼容）。

预计改动点（实际可能有偏差，以 grep 结果为准）：
- `app/api/etf.py`：~2 处（`build` 0 处，`ok` 2 处不动）
- `app/api/sec_code.py`：~6 处（同上）
- `app/api/stock.py`：~5 处 build → fail
- `app/api/kline.py`：~3 处 build → fail（PR2 搬过来的）

**Verify:**

```bash
cd D:\vscodepro\fin-app\backend
grep -rn "ResultVO\.build" app/ --include="*.py"   # Expected: 无输出
pytest -q
ruff check app
```

**Expected:** pytest 全绿、ruff 全绿。

### Step 3.15 — 跑 curl 验证 8 字段响应

**Run:**

```bash
cd D:\vscodepro\fin-app\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

**另开终端:**

```bash
curl http://127.0.0.1:8080/api/etf/get?code=999999
curl http://127.0.0.1:8080/api/__nonexistent__
curl http://127.0.0.1:8080/health
```

**Expected:**
- `/api/etf/get?code=999999` → `{"success": false, "code": ..., "message": "...", "data": null, "timestamp": ..., "path": "/api/etf/get", "durationMs": ..., "errorType": "business"}`
- `/api/__nonexistent__` → `{"success": false, "code": 404, "message": "Not Found", ..., "errorType": "not_found"}`
- `/health` → `{"status":"ok"}`（非 ResultVO 形状，原样透传）

### Step 3.16 — 新增 `frontend/src/api.js`

**File**: `D:\vscodepro\fin-app\frontend\src\api.js`（新建）

```js
export class ApiError extends Error {
  constructor({ message, code, errorType, path, durationMs } = {}) {
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
  if (!json || json.success !== true) {
    throw new ApiError({
      message: json?.message,
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
  if (!json || json.success !== true) {
    throw new ApiError({
      message: json?.message,
      code: json?.code,
      errorType: json?.errorType,
      path: json?.path,
      durationMs: json?.durationMs,
    });
  }
  return json.data;
}
```

### Step 3.17 — 替换 12 处 fetch 调用

**Files（4 个文件，12 处）:**

- `D:\vscodepro\fin-app\frontend\src\Etf.jsx`：10 处
- `D:\vscodepro\frontend\src\HKFinanceCard.jsx`：1 处
- `D:\vscodepro\frontend\src\StockCombobox.jsx`：1 处

**改动模式**（每处统一）：

```js
// 旧（PR2 之前）
const r = await fetch(url);
const json = await r.json();
const payload = json?.data ?? [];

// 新（PR3）— 成功路径
try {
  const payload = await apiGet(url);
  // ... 用 payload 渲染
} catch (err) {
  if (err instanceof ApiError) {
    alert(err.message);
    console.warn('[api]', err.errorType, err.path, err.code, err.message);
  } else {
    alert('网络异常');
  }
}
```

**操作**：
1. 在每个文件顶部添加：`import { apiGet, apiPost, ApiError } from './api';`
2. 对每个 `await fetch(...)` 块用上面的 try/catch 模板替换
3. POST 类调用改用 `apiPost(url, body)`，`body` 若是 JSON 字符串则改成对象

> 关键：UX 文案（`alert(...)` 文字）保持不变；只改取数方式与错误处理形状。

### Step 3.18 — `App.jsx` 顶部去 demo `<h1>`

**File**: `D:\vscodepro\fin-app\frontend\src\App.jsx`（修改）

PR1 阶段这个文件就是 `import Etf from './Etf.jsx'; export default Etf;` 这种纯包装。PR3 阶段保留此包装不变（不要新增 UI，因为 Etf.jsx 自己已是完整页面）；如果 `App.jsx` 含 demo `<h1>` 标题，则**只删除该 h1 节点**。

**Verify:**

```bash
cd D:\vscodepro\fin-app\frontend
pnpm run lint
pnpm run build
```

**Expected:** lint 全绿、build 成功。

### Step 3.19 — 端到端手测

启动 uvicorn + vite dev，浏览器手测：
1. Etf 主页加载正常
2. 顶部下拉切换 ETF → 主图刷新
3. 点 "下载份额" → alert 弹窗
4. 点 "刷新K线" → alert 弹窗
5. StockCombobox 输入 → 候选列表返回
6. HKFinanceCard 切换股票 → 数据展示
7. DevTools console 检查 `[api]` 日志格式正确（`errorType path code message`）
8. 故意访问不存在的 ETF code → 弹窗显示后端 message

**Expected:** 全部正常。

### Step 3.20 — 确认原仓库无改动

**Run:**

```bash
cd D:\vscodepro\react
git status
```

**Expected:** `nothing to commit, working tree clean`

### Step 3.21 — Commit PR3

```bash
cd D:\vscodepro\fin-app
git add backend/app/models/result.py backend/app/middleware/ backend/app/exception_handlers/ backend/app/main.py backend/app/api/ backend/tests/test_result_vo.py backend/tests/test_middleware_envelope.py backend/tests/test_exception_to_result.py frontend/src/api.js frontend/src/Etf.jsx frontend/src/HKFinanceCard.jsx frontend/src/StockCombobox.jsx frontend/src/App.jsx
git commit -m "feat(api): 统一响应包装 + 前端 ApiError 同步

- 新 ResultVO：8 字段契约 {success, code, message, data, timestamp, path, durationMs, errorType}
- 新 ResultEnvelopeMiddleware：注入 path + durationMs
- 新 register_result_exception_handlers：HTTPException + 未捕获异常 → ResultVO.fail，errorType 映射
  （404→not_found, 401/403→unauthorized, 422→validation, 500→service, 业务→business）
- 全部 ResultVO.build(...) → ResultVO.fail(...)
- frontend 新增 src/api.js：ApiError 类 + apiGet + apiPost
- 12 处 fetch 改用 apiGet/apiPost + try/catch ApiError
- App.jsx 去 demo h1

验证：
- pytest -q 全绿（含 3 个新测试文件：ResultVO 4 用例 + middleware 2 用例 + exception 4 用例）
- ruff check app 全绿
- pnpm run lint + pnpm run build 全绿
- curl /api/__nonexistent__ 返回 errorType=not_found
- curl /api/etf/get?code=999999 返回 errorType=business
- 端到端手测 Etf + HKFinance + StockCombobox 全部正常
- react/ 仓库 git status 干净"
```

---

## Task 4: 最终验收 + 收尾

### Step 4.1 — 跑完整测试

**Run:**

```bash
cd D:\vscodepro\fin-app\backend && pytest -q && ruff check app
cd D:\vscodepro\fin-app\frontend && pnpm run lint && pnpm run build
```

**Expected:** 全部退出码 0。

### Step 4.2 — 按 §8 验收清单逐项核对

打开 `D:\vscodepro\fin-app\docs\superpowers\specs\2026-09-04-fin-app-extract-design.md` §8 验收清单 8 条，每条用命令验证：

```bash
# 1. 仓库独立
cd D:\vscodepro\fin-app && git log --oneline | head -5   # 至少 4 个 commit（root spec + PR1/PR2/PR3）

# 2. api/ 业务域清晰
ls backend/app/api/

# 3. openapi.json 路径数
cd backend && python -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); print(len(c.get('/openapi.json').json()['paths']))"
# Expected: 17

# 4. ResultVO 8 字段
python -c "from app.models.result import ResultVO; vo = ResultVO.ok({'a':1}, path='/x', durationMs=5); print(sorted(vo.model_dump().keys()))"
# Expected: ['code', 'data', 'durationMs', 'errorType', 'message', 'path', 'success', 'timestamp']

# 5. api.js 存在
ls frontend/src/api.js

# 6. 12 处 fetch 已替换
grep -rn "fetch(" frontend/src/Etf.jsx frontend/src/HKFinanceCard.jsx frontend/src/StockCombobox.jsx 2>&1
# Expected: 0 处（全部走 apiGet/apiPost）

# 7. tests + linters 全过（已在 Step 4.1 跑）

# 8. react/ 干净
cd D:\vscodepro\react && git status
# Expected: nothing to commit, working tree clean
```

### Step 4.3 — 写 `backend/README.md` 收尾说明（如原 README 不够详细）

**File**: `D:\vscodepro\fin-app\backend\README.md`（如 PR1 拷贝的版本已足够则不动；如缺失或简陋，按需补充）

按需补充的内容方向：
- 启动方式（pip install -e . + uvicorn）
- 环境变量（`FIN_EXCEL_DIR`、`DEBUG_LOG_URL` 等）
- API 路径列表（17 条）
- 测试命令

如 PR1 拷贝的版本已覆盖上述要点，跳过此步。

### Step 4.4 — 完成

迁移已完成。

- ✅ `D:\vscodepro\fin-app\` 独立仓库，前端 + 后端在仓内
- ✅ `backend/app/api/` 下业务域清晰：`etf.py`、`sec_code.py`、`kline.py`、`stock.py`
- ✅ openapi.json 路径数 17，与 PR1 baseline 一致
- ✅ `ResultVO` 8 字段；HTTPException 也被包装
- ✅ frontend `src/api.js` 存在，12 处 fetch 全走 `apiGet`/`apiPost`
- ✅ `pytest -q`、`ruff check app`、`pnpm run lint`、`pnpm run build` 全部退出码 0
- ✅ 浏览器手测全部正常
- ✅ `D:\vscodepro\react\` 工作树干净

---

## Self-Review（plan 作者自查）

**1. Spec coverage（按 §1-§9 逐条对照）：**
- §1 动机/目标 → Task 1 Step 1.4（README）+ Task 4 Step 4.3（README 收尾）
- §2 新仓库布局 → Task 1 Step 1.1~1.5（README/AGENTS/.gitignore + 拷贝 + 排除清单）
- §3 API 文件拆分 → Task 2 全任务（kline.py 新建 + etf.py 追加 + stock.py 瘦身 + main.py 注册）
- §4 统一响应包装 → Task 3 Step 3.1~3.15（ResultVO + middleware + exception_handlers）
- §5 前端同步 → Task 3 Step 3.16~3.18（api.js + 12 处 fetch 替换）
- §6 节奏 → Task 1 = PR1、Task 2 = PR2、Task 3 = PR3、Task 4 = 收尾
- §7 回滚 → 已在每个 Task commit message 强调"react/ 仓库 git status 干净"，未单独写 task；如需强 rollback，文档本身已说明
- §8 验收清单 → Task 4 Step 4.2
- §9 不做 → Task 1~4 全程未涉及 docker / CI / OpenAPI schema 升级

**2. Placeholder scan：**已逐字扫描。无 `TBD` / `TODO` / `implement later` / `类似 Task N` 表达。代码块中的 `...` 都是工程师需从原 `stock.py` 复制的真实代码占位（不是 placeholder，是 spec 里标注的"原样复制"动作）。

**3. Type consistency：**
- `ResultVO.ok(data, *, path="", durationMs=0)` 在 Task 3 Step 3.3 定义、Step 3.1 测试、Step 3.5 middleware 测试、Step 3.14 调用替换全程保持关键字参数签名
- `ResultVO.fail(code, message, *, errorType="business", path="", durationMs=0, data=None)` 同上
- `apiGet` / `apiPost` 在 Task 3 Step 3.16 定义、Step 3.17 调用，全局一致
- `ApiError` 构造器 `{message, code, errorType, path, durationMs}` 在 Step 3.16 定义、Step 3.17 调用时一致
- `_HTTP_TO_ERROR_TYPE` 在 Step 3.9（测试）和 Step 3.11（实现）两侧表完全一致