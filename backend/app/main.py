import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.etf import router as etf_router
from app.api.sec_code import router as sec_code_router
from app.api.stock import router as stock_router
from app.config import get_settings
from app.db import ensure_indexes

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(settings.log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

_debug_url = os.getenv("DEBUG_LOG_URL", "").strip().lower()
if _debug_url not in {"1", "true", "yes", "y", "on"}:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

app.include_router(stock_router, prefix="/api", tags=["stock"])
app.include_router(sec_code_router, prefix="/api/sec", tags=["sec"])
app.include_router(etf_router, prefix="/api/etf", tags=["etf"])


@app.get("/health")
async def health():
    return {"status": "ok"}


WEB_DIR = os.environ.get("WEB_DIR", "/app/web/dist")
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.on_event("startup")
async def _startup():
    await ensure_indexes()


@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    client_host = request.client.host if request.client else "-"
    client_port = request.client.port if request.client else 0
    path = request.url.path
    query = request.url.query
    target = f"{path}?{query}" if query else path
    logger = logging.getLogger("app.request")
    logger.info(
        "%s:%s - \"%s %s HTTP/1.1\" %s elapsed_ms=%s",
        client_host, client_port, request.method, target, response.status_code, elapsed_ms,
    )
    return response
