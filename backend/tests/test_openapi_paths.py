"""保证 API 文件拆分后 /openapi.json 路径清单不变。

PR2 把 stock.py 中混入的 ETF / K-line / /check 路由搬到独立模块；
此测试断言拆分前后路径集合完全一致。
"""
from fastapi.testclient import TestClient

from app.main import app

EXPECTED_PATHS = {
    # /api/etf/* （拆分前混在 stock.py，拆分后归 etf.py）
    "/api/etf",
    "/api/etf/all",
    "/api/etf/szse",
    "/api/etf/szse/sync",
    "/api/etf/quarter",
    "/api/etf/quarter/get",
    "/api/etf/get",
    # /api/etf 原有（一直就在 etf.py）
    "/api/etf/search",
    "/api/etf/backfill-pinyin",
    "/api/etf/szse/import-csv",
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
    # /api/bank/pb/history（银行股 PB 时序，feat/bank-pb-chart 新增）
    "/api/bank/pb/history",
    # /health
    "/health",
    # /api/check （搬到 main.py 后路径前缀不变，保持与 baseline 一致）
    "/api/check",
}


def test_openapi_paths_match_baseline():
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert paths == EXPECTED_PATHS, (
        f"diff: missing={EXPECTED_PATHS - paths}, extra={paths - EXPECTED_PATHS}"
    )
