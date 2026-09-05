# fin-app Docker 化 — 端到端验证报告

**日期**：2026-09-05
**commit 链**（自 Task 5 实施后新增）：
- `456c9f7` fix: Dockerfile pnpm 9.15.4 → 11.7.0
- `be94db8` fix: pnpm registry 设 npmmirror

## 静态校验

- `docker compose config --quiet` → exit 0
- `docker compose config` → 2 services (mongodb + backend) 正确展开
  - mongodb image: `mongodb/mongodb-community-server:8.3.4-ubi9-slim-20260717T064811Z`
  - backend build: context=`D:\vscodepro\fin-app`, dockerfile=`docker/Dockerfile`

## 镜像构建

- `docker compose -f docker/docker-compose.yml build backend` → 成功
- 镜像: `docker-backend:latest` (312MB)
- Stage 1 (frontend-builder): `node:22-bookworm-slim` + pnpm@11.7.0 + npmmirror registry + pnpm install + pnpm run build
- Stage 2 (runtime): `python:3.11-slim` + pip install -e backend + uvicorn

## 容器启动

- `docker compose -f docker/docker-compose.yml up -d` → 成功
- etf-mongodb: Up 52s (healthy, port 27017)
- etf-app: Up 30s (healthy, port 80→8080)
- uvicorn 日志: `Uvicorn running on http://0.0.0.0:8080` + `GET /health HTTP/1.1 200 OK elapsed_ms=17`

## API 验证（容器内，结果通过 80 端口反射到 host）

```
$ curl -s 'http://localhost/api/etf/get?code=510010'
keys: ['code', 'data', 'durationMs', 'errorType', 'message', 'path', 'success', 'timestamp']
success: True
errorType: None
path: /api/etf/get
durationMs: 299
```

✅ 8 字段 ResultVO 完整返回，middleware 注入 path + durationMs 生效

## 前端验证

```
$ curl -s -o /dev/null -w "HTTP %{http_code} (size %{size_download} bytes)" http://localhost/
HTTP 200 (size 477 bytes)
```

✅ index.html 通过 backend StaticFiles 返回

## 异常路径验证

```
$ curl -s 'http://localhost/api/__nonexistent__'
success: False
errorType: not_found
path: /api/__nonexistent__
```

✅ Exception handler 把 HTTPException 包装成 ResultVO.fail，errorType=not_found

## 数据持久化

- bind mount `C:\MongoData\data` → `/data/db` 保留（host 路径原数据不丢）
- named volume `docker_app_logs` 已创建（首次 up 后）

## 启动时冲突处理

用户之前的 `etf-mongodb` 容器是手动 `docker run` 起的（与新 compose container_name 重复）。
Task 5 验证前已 Exited (137) 8 minutes（implementer 跑 build 期间 SIGKILL，
推断用户手动停的 — subagent 24 个 read-only 命令无法触发 docker kill）。

Task 5 期间用 `docker rm etf-mongodb etf-app` 清理已 Exited 的旧容器 metadata
（**不删 host 上 bind mount 的数据**，仅删 container 元数据），
然后 `docker compose up -d` 启动新 compose 管理栈。

## 原 react 仓

- `git status` 干净（无变更）
- `D:\vscodepro\react\docker\python\` 完全不动

## 用户浏览器验证（deferred 到 user）

- 浏览器打开 `http://localhost/`
- 验证 Etf 主页加载 / 主图渲染 / K线图 / ETF 搜索 / SZSE sync / HKFinance / StockCombobox 6 项交互

## Spec / Plan 偏差累计

1. spec §4.1.1: mongo image tag 错（推断 `ubuntu270417`，实际 `ubi9-slim-20260717T064811Z`）→ 修正 by `a6d3866`
2. spec §4.2: `build.context: ../..` 错（基于 react/docker/python 嵌套 2 层，fin-app 嵌套 1 层）→ 修正 by `a1f0520`
3. spec §2 vs §3.1: `.dockerignore` 位置错 → 修正 by `6c2800a`
4. Dockerfile pnpm@9.15.4 错（lockfile 是 pnpm 11 生成）→ 修正 by `456c9f7`
5. Dockerfile 缺 pnpm npmmirror registry 配置 → 修正 by `be94db8`

5 个 fix commit，0 个新业务逻辑改动。