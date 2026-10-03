# docker/

容器化启动整个 fin-app 应用栈：MongoDB + Python FastAPI 后端 + React/echarts 前端。

## 目录文件

- `Dockerfile` — 多阶段构建：node:22-bookworm-slim 构建前端，python:3.11-slim 运行时跑 uvicorn + serve frontend static
- `docker-compose.yml` — 编排 `mongodb/mongodb-community-server:8.3.4-ubi9-slim-20260717T064811Z` + 自定义镜像
- `../.dockerignore` — 排除 `node_modules`、`.venv`、`__pycache__`、`tests`、`docs/superpowers/`、`.superpowers/`、`.git/` 等

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
- `D:\stock\etf_data` → `/app/etf_data` — SZSE ETF JSON 自动导入目录
- `C:\zd_zxzq_gm` → `/app/tdx` — 本地通达信目录（TDX 离线 K 线，见下文）
- `app_logs` (named volume) → `/app/logs` — 后端日志

## TDX 离线 K 线（2026-09 新增）

容器内 `/api/kline/get?source=offline`、`/api/etf/kline?source=offline`、`/api/kline/refresh?source=offline`、`/api/one?source=offline` 等接口可走本地通达信 vipdoc + gbbq，无需网络。

- 宿主需安装通达信客户端并完成至少一次**盘后数据下载**（包含目标股票的 `.day` 文件）
- 默认挂载宿主 `C:\zd_zxzq_gm` 到容器 `/app/tdx`，并设置 `FIN_TDX_HOME=/app/tdx`
- 容器内的 `vipdoc/sh/lday/*.day`、`vipdoc/sz/lday/*.day` 来自此挂载
- **显式选择**：`source=offline`，不会被当作 online 失败后的 fallback
- 数据流：本地 `.day` 解析 → `_offline_df_to_entities` → 写入 Mongo `k_line` 集合

如果宿主通达信目录不在 `C:\zd_zxzq_gm`，修改 `docker-compose.yml` 的 `FIN_TDX_HOME` 与绑定卷 `source`：

```yaml
- type: bind
  source: D:\zd_zxzq_gm      # 宿主路径
  target: /app/tdx
environment:
  FIN_TDX_HOME: /app/tdx     # 容器内路径 (与 target 一致)
```

如果不需要离线 K 线，只想跑纯 online，可注释掉该绑定卷和 `FIN_TDX_HOME`。

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
