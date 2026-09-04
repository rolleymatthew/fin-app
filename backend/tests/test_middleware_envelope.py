"""验证 ResultEnvelopeMiddleware 注入 path + durationMs 到 ResultVO 响应。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.result_envelope import ResultEnvelopeMiddleware
from app.models.result import ResultVO


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(ResultEnvelopeMiddleware)

    @app.get("/api/etf/sample")
    async def sample():
        return ResultVO.ok({"x": 1}).model_dump()

    @app.get("/api/raw")
    async def raw():
        return {"y": 2}

    return app


def test_middleware_injects_path_and_duration_on_resultvo(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.get("/api/etf/sample")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["path"] == "/api/etf/sample"
    assert body["durationMs"] >= 0
    assert body["data"] == {"x": 1}


def test_middleware_does_not_modify_non_resultvo_responses(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.get("/api/raw")
    body = r.json()
    assert body == {"y": 2}
    assert "path" not in body