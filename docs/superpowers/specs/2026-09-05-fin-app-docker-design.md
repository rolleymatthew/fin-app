# fin-app Docker 化 — 设计文档

**日期**：2026-09-05
**目的**：把 `D:\vscodepro\fin-app\``（FastAPI 后端 + React 前端 + 已支持 WEB_DIR 静态服务）按 `D:\vscodepro\react\docker\python\` 现有模式容器化，产出可在 Windows + Docker Compose 一键启动的多服务编排。

---

## 1. 背景与动机

### 1.1 现状

`D:\vscodepro\react\docker\python\` 已有完整 Docker 化模板：
- `Dockerfile`（多阶段：node 构建前端 + python 运行时）
- `docker-compose.yml`（MongoDB + backend）
- `README.md`（使用说明）

但它服务于 `react/backend-python/` + `react/echart-etf/`，**无法直接用于 fin-app**（路径全部错位）。本次抽离后，原 `react/docker/python/` 完全不动。

### 1.2 目标

为 `D:\vscodepro\fin-app\`` 产出同款 Docker 化资产，让用户能：
```bash
cd D:\vscodepro\fin-app
docker compose -f docker/docker-compose.yml up -d --build
# 浏览器访问 http://localhost/
```

### 1.3 非目标

- ❌ 不写 CI（spec §9 已列"本次不做"）
- ❌ 不改 backend 代码（fin-app `app/main.py:75-77` 已支持 `WEB_DIR` 环境变量，复用即可）
- ❌ 不改 frontend 代码（同上）
- ❌ 不引入新的依赖管理工具（沿用 `pyproject.toml` + `package.json`）
- ❌ 不重写原 `react/docker/python/`（用户明确"原 docker/python 不动"）

---

## 2. 新仓库 Docker 资产布局

```
fin-app/
├── README.md, AGENTS.md, .gitignore     # 已有
├── backend/                             # 已有
├── frontend/                            # 已有
├── docs/                                # 已有
└── docker/                              # ← 新增
    ├── Dockerfile                        # 多阶段（node 构建 + python 运行时）
    ├── docker-compose.yml               # MongoDB + backend 两服务
    ├── .dockerignore                     # 排除冗余文件
    └── README.md                         # 使用说明
```

---

## 3. Dockerfile 设计

**基线**：`D:\vscodepro\react\docker\python\Dockerfile`（65 行）。
**目标**：路径适配 `backend/` + `frontend/`、`fin-app/.dockerignore` 排除后保持相同语义。

### 3.1 多阶段结构（保留原样）

```
Stage 1 (frontend-builder)   : node:22-bookworm-slim  → /build/dist
Stage 2 (runtime)            : python:3.11-slim       → uvicorn + frontend static
```

### 3.2 路径替换对照

| 原 Dockerfile 行 | 新 Dockerfile 行 |
|---|---|
| `COPY echart-etf/ ./` | `COPY frontend/ ./` |
| `COPY backend-python/pyproject.toml backend-python/README.md /app/backend-python/` | `COPY backend/pyproject.toml backend/README.md /app/backend/` |
| `COPY backend-python/app /app/backend-python/app` | `COPY backend/app /app/backend/app` |
| `RUN /app/.venv/bin/pip install ... -e /app/backend-python` | `RUN /app/.venv/bin/pip install ... -e /app/backend` |
| `--app-dir /app/backend-python` | `--app-dir /app/backend` |

### 3.3 不变的部分

- `ARG NODE_VERSION=22` / `ARG PYTHON_VERSION=3.11-slim`
- Stage 1 的 `corepack enable` + `pnpm@9.15.4 --activate`
- `ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 ...`
- `WORKDIR /app` + `apt-get install tzdata` + 时区设置
- `python -m venv /app/.venv` + pip install
- `COPY --from=frontend-builder /build/dist /app/web/dist`
- `start.sh` 启动脚本（含 uvicorn + `--workers 1` + `--host` / `--port` env）
- `VOLUME ["/app/data", "/app/logs"]`
- `EXPOSE 8080`
- `HEALTHCHECK` 用 `urllib.request.urlopen('/health')`
- `CMD ["/app/start.sh"]`

---

## 4. docker-compose.yml 设计

**基线**：`D:\vscodepro\react\docker\python\docker-compose.yml`（51 行）。
**目标**：路径适配 `docker/Dockerfile`、MongoDB image 与现有 `etf-mongodb` 容器对齐、bind mount 与原 docker 保持完全一致。

### 4.1 两服务

#### 4.1.1 mongodb
- image: `mongodb/mongodb-community-server:8.3.4-ubuntu270417`（与用户截图里运行的 `etf-mongodb` 容器标签对齐，避免拉第二个镜像）
- container_name: `etf-mongodb`
- restart: `unless-stopped`
- user: `"0:0"`
- environment: `GLIBC_TUNABLES=glibc.pthread.rseq=0`
- ports: `"27017:27017"`
- volumes bind:
  - `C:\MongoData\data` → `/data/db`
- healthcheck: `mongosh --quiet --eval db.adminCommand('ping').ok`

#### 4.1.2 backend
- build:
  - context: `../..`（fin-app 根）
  - dockerfile: `docker/Dockerfile`
- container_name: `etf-app`
- restart: `unless-stopped`
- depends_on: `mongodb: condition: service_healthy`
- ports: `"80:8080"`（容器 8080 → 宿主 80）
- environment:
  - `TZ=Asia/Shanghai`
  - `FIN_MONGO_URI=mongodb://mongodb:27017/stock`
  - `FIN_MONGO_DB=stock`
  - `FIN_DATA_DIR=/app/data`
  - `FIN_EXCEL_DIR=/app/data/pyallinone`
  - `FIN_LOG_FILE=/app/logs/app.log`
  - `WEB_DIR=/app/web/dist`
  - `FIN_COOKIE_DIR=/app/cookies`
- volumes bind:
  - `D:\stock` → `/app/data`
  - `app_logs` named volume → `/app/logs`
  - `D:\stock\cookies` → `/app/cookies`

### 4.2 与原 docker 的差异

| 字段 | 原 `react/docker/python` | 新 `fin-app/docker` | 差异原因 |
|---|---|---|---|
| `dockerfile` 路径 | `docker/python/Dockerfile` | `docker/Dockerfile` | fin-app 仓里 `docker/` 直接放 Docker 资产，无子目录 |
| `mongodb` image tag | `8.3.4-ubi9-slim-20260717T064811Z` | `8.3.4-ubuntu270417` | 与 `etf-mongodb` 现有容器对齐（用户截图所示），避免重复占空间 |
| 所有 bind mount 路径 | 完全保留 | 完全保留 | 用户要求"完全复用原 docker 路径" |

其他字段（端口、environment、restart、healthcheck 等）**完全保留**。

---

## 5. .dockerignore 设计

**目标**：构建镜像时排除冗余文件，缩减大小 + 加快构建速度 + 减少敏感文件泄漏。

### 5.1 排除清单

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

# Tests (运行时不需要)
**/tests/
**/test_*.py

# Editor + OS
.vscode/
.idea/
.DS_Store
Thumbs.db

# Docker 资产自身 (避免递归)
docker/
```

### 5.2 设计依据

- `**/__pycache__/`、`**/tests/`、`backend/.venv/`：避免镜像带测试与缓存
- `frontend/node_modules/`：避免镜像带 200MB+ node_modules（在 builder stage 已 install）
- `docs/superpowers/`：spec/plan 是 host 工作树用，容器不需要
- `.superpowers/`：plan/spec scratch、ledger 文件
- `docker/`：避免 COPY 时递归 docker 目录到 image

---

## 6. README.md 内容（与原 react/docker/python/README 适配）

```markdown
# docker/

容器化启动整个 fin-app 应用栈：MongoDB + Python FastAPI 后端 + React/echarts 前端。

## 目录文件
- `Dockerfile` — 多阶段构建（node 构建前端，python 运行时跑 uvicorn + serve frontend static）
- `docker-compose.yml` — 编排 `mongodb/mongodb-community-server:8.3.4-ubuntu270417` + 自定义镜像
- `.dockerignore` — 排除 `node_modules`、`.venv`、`docs/superpowers/`、`.superpowers/` 等

## 一键启动
在仓库根目录执行：
\`\`\`bash
docker compose -f docker/docker-compose.yml up -d --build
\`\`\`

## 端口
| 端口  | 服务                                |
| ----- | ----------------------------------- |
| 80    | 浏览器（backend 兼 serve 前端 static） |
| 8080  | 容器内 uvicorn（不直接暴露）         |
| 27017 | MongoDB（按需暴露给宿主机调试）      |

浏览器访问 `http://localhost/`。后端 API 路径前缀 `/api/...`。

## 数据持久化
通过 bind mount + named volume：
- `C:\MongoData\data` → `/data/db` — MongoDB 数据
- `D:\stock` → `/app/data` — 后端 Excel 输出
- `D:\stock\cookies` → `/app/cookies` — Eastmoney Cookie
- `app_logs` (named volume) → `/app/logs` — 后端日志

## 配置覆盖
后端环境变量统一通过 `FIN_` 前缀，与 `app/config.py` 一致。在 `docker-compose.yml` 的 `environment` 下追加：
\`\`\`yaml
FIN_LOG_LEVEL: DEBUG
USE_FINANCE_EASMONEY_V2: "true"
\`\`\`

## 单独构建 backend 镜像
\`\`\`bash
docker build -f docker/Dockerfile -t fin-app .
docker run --rm -p 80:8080 \
  -e FIN_MONGO_URI=mongodb://<host>:27017/stock \
  fin-app
\`\`\`
```

---

## 7. 不做清单

- ❌ nginx 反代（三服务独立）
- ❌ docker buildx 高级缓存优化
- ❌ CI（GitHub Actions / GitLab CI 等）
- ❌ 多架构镜像（linux/amd64, linux/arm64）
- ❌ 把 SPEC.md 嵌入镜像（README 已包含使用说明）
- ❌ 重写原 `react/docker/python/`

---

## 8. 验收清单

完成后逐条验证：

- [ ] `D:\vscodepro\fin-app\docker\` 含 Dockerfile / docker-compose.yml / .dockerignore / README.md
- [ ] `docker compose -f docker/docker-compose.yml config` 验证 YAML 语法 + 服务编排
- [ ] `docker compose -f docker/docker-compose.yml build` 成功构建 backend 镜像
- [ ] `docker compose -f docker/docker-compose.yml up -d` 启动两个两个容器
- [ ] 浏览器访问 `http://localhost/` 看到 Etf 主页（含 ETF code 下拉 + 主图）
- [ ] 浏览器"下载份额" / "SZSE sync" 按钮触发 backend API 调用，alert 正常
- [ ] `docker compose logs backend | grep elapsed_ms` 看到 8 字段 ResultVO 响应（durationMs > 0）
- [ ] `docker compose down` 后 `docker volume ls` 仍能看到 `app_logs`
- [ ] `D:\vscodepro\react\` 仓库 `git status` 仍干净

---

## 9. 后续（本次不做）

- backend / frontend 分两个独立容器（nginx 反代）
- docker buildx 缓存层 + 多架构
- CI 集成
- K8s Helm chart / docker swarm