"""为 ResultVO 响应注入 path + durationMs 字段。"""
from __future__ import annotations

import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


async def _iter_bytes(data: bytes):
    yield data


class ResultEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        try:
            body_bytes = b"".join([chunk async for chunk in response.body_iterator])
        except Exception:
            return response

        try:
            body = json.loads(body_bytes)
        except Exception:
            response.body_iterator = _iter_bytes(body_bytes)
            return response

        if isinstance(body, dict) and "success" in body:
            body["path"] = request.url.path
            body["durationMs"] = duration_ms
            new_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
            new_response = Response(
                content=new_bytes,
                status_code=response.status_code,
                media_type="application/json",
            )
            return new_response

        response.body_iterator = _iter_bytes(body_bytes)
        return response