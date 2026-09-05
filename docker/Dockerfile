# 多阶段构建：前端构建产物 + 后端运行时（最小化最终镜像）
# 用法（在仓库根目录执行）：
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