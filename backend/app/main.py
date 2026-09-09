import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.etf import router as etf_router
from app.api.kline import router as kline_router
from app.api.sec_code import router as sec_code_router
from app.api.stock import router as stock_router
from app.config import get_settings
from app.db import ensure_indexes
from app.exception_handlers.result_envelope import register_result_exception_handlers
from app.middleware.result_envelope import ResultEnvelopeMiddleware
from app.models.result import ResultVO
from app.services.etf_csv_watcher import start_watcher, stop_watcher
from app.services.etf_service import EtfService
from app.services.finance_service import FinanceService

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

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_indexes()
    watcher_task: asyncio.Task | None = None
    if bool(getattr(settings, "etf_csv_auto_import", False)):
        service = EtfService()
        watcher_task = start_watcher(settings, service)
        logging.getLogger("app.startup").info(
            "[etf_csv_watcher] started; dir=%s poll=%ss",
            settings.etf_csv_dir,
            settings.etf_csv_poll_seconds,
        )
    try:
        yield
    finally:
        await stop_watcher(watcher_task)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(ResultEnvelopeMiddleware)
register_result_exception_handlers(app)

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
app.include_router(kline_router, prefix="/api", tags=["kline"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/check")
async def check_finance_data(
    date: list[str] = Query(...),
    code: list[str] | None = Query(default=None),
):
    finance_service = FinanceService()
    sec_entities = await finance_service.get_sec_code_entities(code)
    missing = []
    for s in sec_entities:
        for d in date:
            if not await finance_service.has_fin_data(s, d):
                missing.append(f"{s.securityCode},{d}")
    return ResultVO.fail(code=1, message="缺少财务数据", data=missing).model_dump()


WEB_DIR = os.environ.get("WEB_DIR", "/app/web/dist")
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


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
