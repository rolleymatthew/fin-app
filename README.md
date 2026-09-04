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