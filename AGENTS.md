# fin-app

金融数据全栈应用，从 `D:\vscodepro\react\` 抽出的独立仓库。

## 布局

- `backend/` — FastAPI 服务（端口 8080，MongoDB 持久化，Excel 输出到 `D:\stock\pyallinone`）
- `frontend/` — Vite + React + ECharts 单页（dev 端口 5173，`/api` 代理到 8080）
- `docker/` — 多阶段构建 + docker-compose（MongoDB + backend 一体化）
- `docs/superpowers/{specs,plans}/` — 设计文档与实施计划
- `.superpowers/` — 工作树本地元数据（gitignored；含 sdd 报告与 review diff）

## 开发命令

```bash
# Backend
cd backend && pip install -e . && pytest -q && ruff check app

# Frontend
cd frontend && pnpm install && pnpm run dev   # 5173
cd frontend && pnpm run lint && pnpm run build
```

后端入口 `app.main:app`；前端入口 `src/main.jsx` → `Etf.jsx`。

## 工作流（继承自原 react 仓，不变）

1. **不动已有函数**：未经明确同意，不改/重命名/删除。
2. **优先新增**：新功能优先新增函数，不就地改写。
3. **不顺手重构**：禁止以"清理"为由改动与当前任务无关的代码。

## 关键约束

- 不引入新 pip / pnpm 依赖，除非明确批准。
- backend `app/services/`、`app/clients/`、`app/repositories/` 默认只读。
- 跨 task 改动必须独立 commit；commit message 用 Conventional Commits。
- 无 CI / pre-commit / PR 模板：合并前靠人 review。

## 架构速记

- **后端分层** `api/` → `services/` → `repositories/` + `clients/`（外部 HTTP/数据源）。其它：`mappers/`（字段映射）、`models/`（DTO + entities + result）、`middleware/`、`exception_handlers/`、`utils/`、`constants/`。
- **响应包装**：所有 API 经 `ResultEnvelopeMiddleware` 输出 8 字段 `ResultVO`：`success / code / message / data / path / durationMs / errorType / timestamp`。新增 endpoint 必须保证 `success` 字段。
- **前端 API 约定**：`src/api.js` 的 `_request` 假设后端返回 `{ success: true, data: ... }` 形态，否则抛 `ApiError` 并把 `code / errorType / path / durationMs` 一并抛出。
- **配置**：`backend/app/config.py` 用 pydantic-settings，所有 env 带 `FIN_` 前缀（个别历史字段兼容 `USE_FINANCE_EASTMONEY_V2`、`KLINE_*` 大写别名）。完整 env 见 `backend/README.md`。
- **静态前端托管**：当 `WEB_DIR` 指向已构建的 `frontend/dist` 时，后端 `mount("/")` 直接 serve。Docker 模式用此方式；本地 dev 不走此路。
- **KLine 多源**：`kline_primary` 默认 `eastmoney`，`kline_fallbacks` 默认 `ths,sina,tencent`。可用 `FIN_KLINE_PRIMARY` / `FIN_KLINE_FALLBACKS` 覆盖。
- **Cookie 来源**：`FIN_COOKIE_DIR`（目录模式，多 `.txt` 文件按名拼接，热加载）> `EASTMONEY_COOKIE_*` 旧别名 > `.eastmoney_cookies/`。失效时会打印 `【COOKIE_INVALID】reason=...`。

## Docker 启动

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

- MongoDB 镜像固定为 `mongodb/mongodb-community-server:8.3.4-ubi9-slim-20260717T064811Z`（与已有 `etf-mongodb` 容器对齐，不换 tag、不换路径）。
- bind mount 复用宿主 `C:\MongoData\data`、`D:\stock`、`D:\stock\cookies`；端口 `80:8080` + `27017:27017`。
- 首次构建 5-10 分钟；UI 验证需 user 手测（subagent 不点浏览器）。
- 详见 `docker/README.md`。

## 文档与计划

- 设计：`docs/superpowers/specs/YYYY-MM-DD-<name>-design.md`
- 实施计划：`docs/superpowers/plans/YYYY-MM-DD-<name>.md`
- 历史 sdd 报告：`.superpowers/sdd/`（本地，不进 git）

启动新 spec / plan 前先看这里有没有可继承的 baseline。
