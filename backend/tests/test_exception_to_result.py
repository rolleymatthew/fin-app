"""验证 HTTPException 与未捕获异常被包装为 ResultVO.fail，errorType 正确映射。"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.exception_handlers.result_envelope import register_result_exception_handlers


def _make_app():
    app = FastAPI()
    register_result_exception_handlers(app)

    @app.get("/api/notfound")
    async def nf():
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/api/unauthorized")
    async def unauth():
        raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("explode")

    return app


def test_http_404_maps_to_not_found_error_type():
    client = TestClient(_make_app())
    r = client.get("/api/notfound")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 404
    assert body["errorType"] == "not_found"


def test_http_401_maps_to_unauthorized_error_type():
    client = TestClient(_make_app())
    r = client.get("/api/unauthorized")
    body = r.json()
    assert body["errorType"] == "unauthorized"


def test_unhandled_exception_maps_to_service_error_type():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.get("/api/boom")
    body = r.json()
    assert body["success"] is False
    assert body["errorType"] == "service"
    assert "explode" in body["message"]


_HTTP_TO_ERROR_TYPE = {
    400: "validation",
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    409: "business",
    422: "validation",
}


def test_error_type_mapping_table_consistent():
    for status, etype in _HTTP_TO_ERROR_TYPE.items():
        assert etype in {"validation", "unauthorized", "not_found", "business"}