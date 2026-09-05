# fin-app Docker 化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `D:\vscodepro\fin-app\docker\` 下产出 Dockerfile + docker-compose.yml + .dockerignore + README.md，让用户能 `docker compose -f docker/docker-compose.yml up -d --build` 一键启动 fin-app 全栈。

**Architecture:** 多阶段构建（Node 22 构建前端 → Python 3.11-slim 运行时同时跑 uvicorn + serve frontend static）；docker-compose 编排 MongoDB（与现有 `etf-mongodb` 容器镜像标签对齐）+ backend（绑定宿主机 `D:\stock`、`D:\stock\cookies`、`C:\MongoData\data`，端口 80→容器 8080）。

**Tech Stack:** Docker Compose v2 / Node 22 bookworm-slim / Python 3.11-slim / pnpm 9.15.4 / MongoDB Community Server 8.3.4。

---

## Global Constraints

1. **不动原 `D:\vscodepro\react\docker\python\`**：原 docker 资产完全保留在 react 仓不动。本 plan 产出在 `D:\vscodepro\fin-app\docker\` 下，**不与 react 仓共享文件**。
3. **不动 backend / frontend 代码**：fin-app `backend/app/main.py:75-77` 已支持 `WEB_DIR` 环境变量，复用即可；不改任何 `.py` / `.jsx` / `.ts` / `.tsx`。
4. **不动 fin-app `pyproject.toml` 或 `package.json`**：Dockerfile 沿用现有依赖清单。
5. **MongoDB image tag 必须与现有 `etf-mongodb` 容器一致**：tag `mongodb/mongodb-community-server:8.3.4-ubuntu270417`（用户截图所示）；不要拉新镜像。
6. **bind mount 路径复用原 react docker**：`C:\MongoData\data`、`D:\stock`、`D:\stock\cookies` — 用户要求"完全复用原 docker 路径"，不要改成新路径。
7. **端口映射保持 `"80:8080"`**：容器内 8080 → 宿主 80（与原 react docker 一致）。
8. **不引入 CI / buildx 多架构 / K8s / nginx 反代**：spec §9 明确"本次不做"。
9. **每个 task 结束 git commit**；commit message 风格遵循 Conventional Commits。
11. **subagent 不能点浏览器**：所有 `docker compose up` 后的 UI 验证交给 user；subagent 只跑 `curl` / `docker logs` / `docker compose config` 类可脚本化验证。

---

## File Structure（任务结束时的最终落点）

```
fin-app/
├── docker/                                  # ← 新增
│   ├── Dockerfile                            # 多阶段构建（frontend-builder + python runtime）
│   ├── docker-compose.yml                    # mongodb + backend 两服务
│   ├── .dockerignore                         # 排除冗余
│   └── README.md                             # 使用说明
├── backend/                                  # 不动
├── frontend/                                 # 不动
└── docs/superpowers/                         # 不动
```

---

## Task 1: 写 Dockerfile

**Files:**
- Create: `D:\vscodepro\fin-app\docker\Dockerfile`

**Interfaces:**
- Consumes: 源 `D:\vscodepro\react\docker\python\Dockerfile`（65 行）作为模板基线
- Produces: 多阶段 Docker 镜像 `fin-app`，最终 stage 启动命令 `uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port 8080`

### Step 1.1 — 复制原 Dockerfile 并做路径替换

**Run (PowerShell):**

```powershell
Copy-Item D:\vscodepro\react\docker\python\Dockerfile D:\vscodepro\fin-app\docker\Dockerfile
```

然后用 edit 工具做 5 处路径替换：

| 替换前 | 替换后 |
|---|---|
| `COPY echart-etf/ ./` | `COPY frontend/ ./` |
| `COPY backend-python/pyproject.toml backend-python/README.md /app/backend-python/` | `COPY backend/pyproject.toml backend/README.md /app/backend/` |
| `COPY backend-python/app /app/backend-python/app` | `COPY backend/app /app/backend/app` |
| `/app/backend-python` （在 pip install 行） | `/app/backend` |
| `--app-dir /app/backend-python` | `--app-dir /app/backend` |

**预期最终 Dockerfile 结构**（替换完成后，从头到尾应当是 65 行左右，与原文件行数相同；行 11、42、43、44、54 各改一次）：

```dockerfile
# 多阶段构建：前端构建产物 + 后端运行时（最小化最终镜像）
# 用法（在 fin-app 根目录执行）：
#   docker compose -f docker/docker-compose.yml up -d --build

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.11-slim

# ---------- Stage 1: 前端构建 ----------
FROM node:${NODE_VERSION}-bookworm-slim AS frontend-builder
WORKDIR /build
COPY frontend/ ./
RUN corepack enable \
 && corepack prepare pnpm@9.15.4 --activate \
 && pnpm install --config.confirmModulesPurge=false
RUN pnpm run build

# ---------- Stage 2: 后端运行时 ----------
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    FIN_HOST=0.0.0.0 \
    FIN_PORT=8080 \
    WEB_DIR=/app/web/dist

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
 && echo $TZ > /etc/timezone \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /app/.venv \
 && /app/.venv/bin/pip install --upgrade pip

COPY backend/pyproject.toml backend/README.md /app/backend/
COPY backend/app /app/backend/app
RUN /app/.venv/bin/pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -e /app/backend

COPY --from=frontend-builder /build/dist /app/web/dist

RUN mkdir -p /app/data /app/logs

RUN { \
      echo '#!/bin/sh'; \
      echo 'set -e'; \
      echo ''; \
      echo 'exec /app/.venv/bin/uvicorn app.main:app --app-dir /app/backend \\'; \
      echo '  --host ${FIN_HOST:-0.0.0.0} --port ${FIN_PORT:-8080} --workers 1'; \
    } > /app/start.sh \
 && chmod +x /app/start.sh

VOLUME ["/app/data", "/app/logs"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"

CMD ["/app/start.sh"]
```

### Step 1.2 — 验证路径替换无遗漏

**Run:**

```bash
grep -nE "backend-python|echart-etf" D:/vscodepro/fin-app/docker/Dockerfile
```

**Expected:** 无输出（原路径已全替换为 `backend` / `frontend`）。

如有输出，按行号继续 edit 替换。

### Step 1.3 — 验证 Dockerfile 行数与原文件相近

**Run:**

```bash
wc -l D:/vscodepro/react/docker/python/Dockerfile D:/vscodepro/fin-app/docker/Dockerfile
```

**Expected:** 两个文件行数相差 ≤2 行（替换是等长的）。

### Step 1.4 — Commit Task 1

```bash
cd D:\vscodepro\fin-app
git add docker/Dockerfile
git commit -m "chore(docker): 新增 Dockerfile — 多阶段构建 fin-app 镜像

基线：D:\vscodepro\react\docker\python\Dockerfile（65 行）。
改动：backend-python/ → backend/、echart-etf/ → frontend/、--app-dir
路径同步替换；其余 ENV / VOLUME / EXPOSE / HEALTHCHECK / start.sh
全部保留。Stage 1 (frontend-builder) 与 Stage 2 (python runtime)
多阶段结构不变。

未触发 docker build（下一步 Task 3 + Task 5 才一起验证）。"
```

---

## Task 2: 写 .dockerignore

**Files:**
- Create: `D:\vscodepro\fin-app\docker\.dockerignore`

**Interfaces:**
- Consumes: 无
- Produces: docker build 阶段排除冗余文件（node_modules / .venv / __pycache__ / tests / docs/superpowers / .git / .superpowers 等），降低镜像体积 60%+

### Step 2.1 — 写 .dockerignore

**File**: `D:\vscodepro\fin-app\docker\.dockerignore`（新建）

```gitignore
# Git + 工作树元数据
.git/
.superpowers/
docs/superpowers/

# Backend (Python)
**/__pycache__/
**/*.pyc
**/*.pyo
**/.pytest_cache/
**/.ruff_cache/
**/*.egg-info/
backend/.venv/
backend/app.log
backend/.eastmoney_cookies/
backend/build/
backend/dist/

# Frontend (Node)
frontend/node_modules/
frontend/dist/
frontend/.vite/
frontend/my-app.exe

# Tests + build artifacts
**/tests/
**/test_*.py

# Editor + OS
.vscode/
.idea/
.DS_Store
Thumbs.db

# Docker 资产自身 (避免 COPY 时递归)
docker/
```

### Step 2.2 — 验证 .dockerignore 语法

**Run:**

```bash
docker build --help 2>&1 | grep -i "ignore" | head -3
```

**Expected:** 看到 `--ignore-file` flag 说明 Docker 19.03+ 支持 .dockerignore。

> 注：本步骤只确认 Docker 版本支持 .dockerignore。实际效果验证在 Task 5（`docker compose build` 时观察镜像大小或 build 日志）。

### Step 2.3 — Commit Task 2

```bash
cd D:\vscodepro\fin-app
git add docker/.dockerignore
git commit -m "chore(docker): 新增 .dockerignore — 排除冗余文件

排除项：
- Python 缓存: __pycache__/, *.pyc, .pytest_cache/, .ruff_cache/
- Python venv/build: backend/.venv/, *.egg-info/, backend/build/, backend/dist/
- Node: frontend/node_modules/, frontend/dist/, frontend/.vite/, frontend/my-app.exe
- Backend 日志/Cookie: backend/app.log, backend/.eastmoney_cookies/
- 测试代码: **/tests/, **/test_*.py（运行时不需要）
- 工作树元数据: .git/, .superpowers/, docs/superpowers/
- 编辑器/OS: .vscode/, .idea/, .DS_Store, Thumbs.db
- Docker 自身: docker/（避免 COPY 递归）"
```

---

## Task 3: 写 docker-compose.yml

**Files:**
- Create: `D:\vscodepro\fin-app\docker\docker-compose.yml`

**Interfaces:**
- Consumes: 源 `D:\vscodepro\react\docker\python\docker-compose.yml`（51 行）作为模板；本 Task 1 写好的 Dockerfile
- Produces: 编排两服务（mongodb + backend）的 compose 文件，端口 80:8080，bind mount 复用原 react docker 路径

### Step 3.1 — 复制原 compose 并改 dockerfile 路径 + MongoDB image tag

**Run (PowerShell):**

```powershell
Copy-Item D:\vscodepro\react\docker\python\docker-compose.yml D:\vscodepro\fin-app\docker\docker-compose.yml
```

然后做 2 处修改：

| 字段 | 原值 | 新值 | 替换方式 |
|---|---|---|---|
| mongodb image | `mongodb/mongodb-community-server:8.3.4-ubi9-slim-20260717T064811Z` | `mongodb/mongodb-community-server:8.3.4-ubuntu270417` | edit 工具直接替换整行 |
| backend build dockerfile | `dockerfile: docker/python/Dockerfile` | `dockerfile: docker/Dockerfile` | edit 工具直接替换 |

其他字段（container_name / restart / user / ports / environment / volumes / healthcheck / depends_on / 顶层 volumes）**一字不动**。

**预期最终 docker-compose.yml**：

```yaml
services:
  mongodb:
    image: mongodb/mongodb-community-server:8.3.4-ubuntu270417
    container_name: etf-mongodb
    restart: unless-stopped
    user: "0:0"
    environment:
      GLIBC_TUNABLES: glibc.pthread.rseq=0
    ports:
      - "27017:27017"
    volumes:
      - type: bind
        source: C:\MongoData\data
        target: /data/db
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ../..
      dockerfile: docker/Dockerfile
    container_name: etf-app
    restart: unless-stopped
    depends_on:
      mongodb:
        condition: service_healthy
    ports:
      - "80:8080"
    environment:
      TZ: Asia/Shanghai
      FIN_MONGO_URI: mongodb://mongodb:27017/stock
      FIN_MONGO_DB: stock
      FIN_DATA_DIR: /app/data
      FIN_EXCEL_DIR: /app/data/pyallinone
      FIN_LOG_FILE: /app/logs/app.log
      WEB_DIR: /app/web/dist
      FIN_COOKIE_DIR: /app/cookies
    volumes:
      - type: bind
        source: D:\stock
        target: /app/data
      - app_logs:/app/logs
      - type: bind
        source: D:\stock\cookies
        target: /app/cookies

volumes:
  app_logs:
```

### Step 3.2 — 验证 YAML 语法

**Run:**

```bash
cd D:\vscodepro\fin-app
docker compose -f docker/docker-compose.yml config
```

**Expected:** 输出完整合并后的 YAML（两 service + 顶层 volumes），**无 "ERROR" / "yaml" 关键字**。Exit code 0。

如有错误，按 docker compose 提示修复（常见：缩进错、tab vs spaces、端口写法）。

### Step 3.3 — 验证 MongoDB image 已被复用

**Run:**

```bash
docker images mongodb/mongodb-community-server --format "{{.Repository}}:{{.Tag}} {{.Size}}"
```

**Expected:** 至少看到一行 `mongodb/mongodb-community-server:8.3.4-ubuntu270417`（即用户截图里 `etf-mongodb` 容器使用的镜像），说明 `docker compose build` 不会拉新镜像。

### Step 3.4 — Commit Task 3

```bash
cd D:\vscodepro\fin-app
git add docker/docker-compose.yml
git commit -m "chore(docker): 新增 docker-compose.yml — MongoDB + backend 编排

基线：D:\vscodepro\react\docker\python\docker-compose.yml（51 行）。
两处改动：
- mongodb image: 8.3.4-ubi9-slim-20260717T064811Z → 8.3.4-ubuntu270417
  （与现有 etf-mongodb 容器镜像对齐，避免拉第二个镜像）
- backend build.dockerfile: docker/python/Dockerfile → docker/Dockerfile

其余（端口 80:8080、bind mount C:\\MongoData\\data / D:\\stock /
D:\\stock\\cookies、environment、healthcheck、depends_on、named
volume app_logs）一字不动。"
```

---

## Task 4: 写 README.md

**Files:**
- Create: `D:\vscodepro\fin-app\docker\README.md`

**Interfaces:**
- Consumes: 无
- Produces: 用户向文档，说明一键启动 / 端口 / 数据持久化 / 配置覆盖 / 单独构建

### Step 4.1 — 写 README.md

**File**: `D:\vscodepro\fin-app\docker\README.md`（新建）

```markdown
# docker/

容器化启动整个 fin-app 应用栈：MongoDB + Python FastAPI 后端 + React/echarts 前端。

## 目录文件

- `Dockerfile` — 多阶段构建：node:22-bookworm-slim 构建前端，python:3.11-slim 运行时跑 uvicorn + serve frontend static
- `docker-compose.yml` — 编排 `mongodb/mongodb-community-server:8.3.4-ubuntu270417` + 自定义镜像
- `.dockerignore` — 排除 `node_modules`、`.venv`、`__pycache__`、`tests`、`docs/superpowers/`、`.superpowers/`、`.git/` 等

## 一键启动

在 fin-app 仓库根目录执行：

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

首次构建约 5-10 分钟（前端 `pnpm install` + 后端 `pip install -e`）；之后增量构建 <30 秒。

## 端口

| 端口  | 服务                                      |
| ----- | ----------------------------------------- |
| 80    | 浏览器（backend 兼 serve 前端 static）    |
| 8080  | 容器内 uvicorn（不直接暴露）              |
| 27017 | MongoDB（按需暴露给宿主机调试）           |

浏览器访问 `http://localhost/`。后端 API 路径前缀 `/api/...`。

## 数据持久化

通过 bind mount + named volume：

- `C:\MongoData\data` → `/data/db` — MongoDB 数据
- `D:\stock` → `/app/data` — 后端 Excel 输出目录
- `D:\stock\cookies` → `/app/cookies` — Eastmoney Cookie 多文件目录
- `app_logs` (named volume) → `/app/logs` — 后端日志

## 配置覆盖

后端环境变量统一通过 `FIN_` 前缀，与 `app/config.py` 一致。在 `docker-compose.yml` 的 `environment` 下追加：

```yaml
FIN_LOG_LEVEL: DEBUG
USE_FINANCE_EASMONEY_V2: "true"
FIN_KLINE_PRIMARY: ths
```

## 单独构建 backend 镜像（不带 compose）

```bash
docker build -f docker/Dockerfile -t fin-app .
docker run --rm -p 80:8080 \
  -e FIN_MONGO_URI=mongodb://<host>:27017/stock \
  fin-app
```

## 查看日志

```bash
# 实时跟踪
docker compose -f docker/docker-compose.yml logs -f backend

# 最近 100 行
docker compose -f docker/docker-compose.yml logs --tail=100 backend
```

## 停止与清理

```bash
# 停止 + 删除容器（保留 volumes）
docker compose -f docker/docker-compose.yml down

# 停止 + 删除容器 + 删除 named volume app_logs
docker compose -f docker/docker-compose.yml down --volumes

# 清理已停止容器
docker container prune
```
```

### Step 4.2 — Commit Task 4

```bash
cd D:\vscodepro\fin-app
git add docker/README.md
git commit -m "docs(docker): 新增 README.md — 启动 / 端口 / 数据持久化 / 配置覆盖

覆盖场景：一键启动 / 端口 / 数据持久化 / 配置覆盖 / 单独构建 /
查看日志 / 停止与清理。基于 react/docker/python/README.md 适配
fin-app 路径与 MongoDB image tag。"
```

---

## Task 5: 端到端验证

**Files:**
- Modify: 无（纯验证）

**Interfaces:**
- Consumes: Task 1-4 产出的 4 个文件
- Produces: 在 spec §8 验收清单上每条打钩

### Step 5.1 — 静态校验 docker-compose 语法

**Run:**

```bash
cd D:\vscodepro\fin-app
docker compose -f docker/docker-compose.yml config --quiet
```

**Expected:** 无输出 + exit code 0。如有报错，按提示调整 YAML。

### Step 5.2 — 构建 backend 镜像

**Run:**

```bash
cd D:\vscodepro\fin-app
docker compose -f docker/docker-compose.yml build backend
```

**Expected:** 看到：
1. Stage 1 `frontend-builder` 解析：`pnpm install` + `pnpm run build`（约 2-3 分钟）
2. Stage 2 `runtime` 解析：`apt-get install tzdata` + `pip install -e /app/backend`（约 1 分钟）
3. 最终镜像构建成功（`naming to docker.io/library/fin-app-backend` 类似输出）

**预期总耗时**：5-10 分钟（首次）。如有失败：
- pnpm install 失败：检查 `frontend/package.json` 与 `pnpm-lock.yaml` 是否一致
- pip install 失败：检查 `backend/pyproject.toml` 的 dependencies
- COPY 失败：检查路径是否真的在仓库根（context: `../..`）

### Step 5.3 — 启动两服务

**Run:**

```bash
cd D:\vscodepro\fin-app
docker compose -f docker/docker-compose.yml up -d
```

**Expected:** `Creating etf-mongodb ... done` + `Creating etf-app ... done`。

**如 `etf-mongodb` 已存在**：docker compose 会报 "container name already in use"。先停旧容器：
```bash
docker stop etf-mongodb
docker rm etf-mongodb
```
然后重跑 `up -d`。注意：旧容器使用了相同的 bind mount `C:\MongoData\data` 与 named volume 路径，数据不丢。

### Step 5.4 — 等 backend 启动 + 健康检查通过

**Run:**

```bash
sleep 30   # 等 uvicorn 启动 + MongoDB 连接 + ensure_indexes
docker compose -f docker/docker-compose.yml ps
```

**Expected:** `etf-mongodb` 状态 `healthy`（约 10 秒内），`etf-app` 状态 `healthy`（约 30 秒内）。

如 `etf-app` 长期 unhealthy：
```bash
docker compose -f docker/docker-compose.yml logs --tail=50 backend
```
检查 MongoDB 是否可达（容器内 `mongodb:27017`）。

### Step 5.5 — 验证 backend API 通过容器端口可达

**Run:**

```bash
curl -s http://localhost/api/health
curl -s 'http://localhost/api/etf/get?code=510010' | python -c "import json,sys; d=json.load(sys.stdin); print('success:', d.get('success')); print('path:', d.get('path')); print('has 8 fields:',','.join(sorted(d.keys())))"
```

**Expected:**
- `/api/health` → `{"status":"ok"}`（注意：这里是 `/api/health`，不是 `/health`，因 vite 代理不在容器内生效；要测 `/health` 用 `curl http://localhost:8080/health` —— 但 8080 未暴露给宿主，跳过此步）

实际上 backend 把 frontend static mount 在 `/`，所以 `/api/health` 会被 StaticFiles 当成静态资源查找 → 404。改测 `/health` 但 8080 端口没暴露给宿主。

正确验证方式（直接 curl 容器内端口）：
```bash
docker compose -f docker/docker-compose.yml exec backend curl -s http://127.0.0.1:8080/api/etf/get?code=510010
```

**Expected:** 8 字段 ResultVO 响应（success=True / path=/api/etf/get）。

### Step 5.6 — 验证前端静态资源可达

**Run:**

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost/
curl -s http://localhost/ | grep -oE "<title>[^<]+</title>"
```

**Expected:** `HTTP 200` + `<title>ETF + fetch stock</title>`（来自 `frontend/index.html`）。

### Step 5.7 — 验证 ResultVO 8 字段响应

**Run:**

```bash
docker compose -f docker/docker-compose.yml exec backend curl -s 'http://127.0.0.1:8080/api/etf/get?code=510010' | python -c "import json,sys; d=json.load(sys.stdin); print('keys:', sorted(d.keys())); print('path:', d['path']); print('errorType:', d.get('errorType'))"
```

**Expected:**
```
keys: ['code', 'data', 'durationMs', 'errorType', 'message', 'path', 'success', 'timestamp']
path: /api/etf/get
errorType: None
```

### Step 5.8 — 验证 named volume 持久化

**Run:**

```bash
docker volume ls | grep app_logs
```

**Expected:** 看到一行 `local     fin-app_app_logs`（或类似）。

### Step 5.9 — 验证 react 仓未受影响

**Run:**

```bash
cd D:\vscodepro\react && git status
```

**Expected:** `nothing to commit, working tree clean`。

### Step 5.10 — 写 Task 5 验收报告

新建 `D:\vscodepro\fin-app\docker\VERIFY-REPORT.md`（不进 git，仅交付时给 user 看）：

```markdown
# fin-app Docker 化 — 端到端验证报告

**日期**：2026-09-05
**执行者**：subagent
**commit 链**：T1 / T2 / T3 / T4 各 1 commit

## 静态校验
- `docker compose config --quiet` → exit 0
- `docker images mongodb/mongodb-community-server` → 包含 `:8.3.4-ubuntu270417`

## 镜像构建
- backend 镜像 `fin-app-backend` 构建成功
- Stage 1 (frontend-builder): pnpm install + build 完成
- Stage 2 (runtime): pip install 完成

## 容器启动
- `etf-mongodb`: healthy
- `etf-app`: healthy（uvicorn + MongoDB 连接 + ensure_indexes 完成）

## API 验证（容器内）
- `/api/etf/get?code=510010` → 8 字段 ResultVO 响应：
  - success=True / path=/api/etf/get / errorType=None
  - keys = [code, data, durationMs, errorType, message, path, success, timestamp]

## 前端验证
- `GET http://localhost/` → HTTP 200，`<title>ETF + fetch stock</title>`
- 浏览器手测（user 侧）：Etf 主页加载 / 主图渲染 / 按钮交互 / K线刷新

## 数据持久化
- named volume `app_logs` 存在

## 原 react 仓
- `git status` 干净（无变更）
```

---

## Self-Review（plan 作者自查）

**1. Spec coverage**（按 §1-§9 逐条对照）：
- §1 动机/目标 → Task 5 Step 5.10 验收报告 § "API 验证"
- §2 总体布局 → Task 1 / 2 / 3 / 4 各自产出 4 个文件
- §3 Dockerfile 设计 → Task 1 Step 1.1（含完整 65 行 Dockerfile 内容）
- §4 docker-compose 设计 → Task 3 Step 3.1（含完整 YAML 内容）
- §5 .dockerignore → Task 2 Step 2.1（完整 30+ 行 ignore）
- §6 README.md → Task 4 Step 4.1（含完整 markdown）
- §7 不做清单 → plan 顶部 Global Constraints 已声明
- §8 验收清单 → Task 5 全部 10 个 Step 覆盖
- §9 后续 → Global Constraints 已排除（不写 CI / buildx / K8s / nginx）

**2. Placeholder scan**：grep 全 plan 无 `TBD` / `TODO` / `FIXME` / `implement later` / "Similar to Task N"。所有 Dockerfile / compose / .dockerignore / README 内容都是完整代码块。

**3. Type consistency**：
- Task 1 产出的 Dockerfile 与 Task 3 Step 3.1 引用的 `docker/Dockerfile` 路径一致
- Task 3 Step 3.1 的 MongoDB image tag (`8.3.4-ubuntu270417`) 与 Step 3.3 验证命令一致
- Task 5 Step 5.5-5.7 验证 URL `/api/etf/get?code=510010` 与 spec §4.3 / Task 3 PR 合同契一致（ResultVO 8 字段）