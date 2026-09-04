"""把 HTTPException 与未捕获异常统一包装为 ResultVO.fail(...)。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.result import ResultVO

_HTTP_TO_ERROR_TYPE = {
    400: "validation",
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    409: "business",
    422: "validation",
}


def _http_to_error_type(status_code: int) -> str:
    return _HTTP_TO_ERROR_TYPE.get(status_code, "http")


def register_result_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        status = exc.status_code
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        vo = ResultVO.fail(
            code=status,
            message=message,
            errorType=_http_to_error_type(status),
            path=request.url.path,
        )
        return JSONResponse(status_code=200, content=vo.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        vo = ResultVO.fail(
            code=422,
            message="请求参数验证失败",
            errorType="validation",
            path=request.url.path,
            data={"errors": exc.errors()},
        )
        return JSONResponse(status_code=200, content=vo.model_dump())

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        vo = ResultVO.fail(
            code=500,
            message=str(exc) or exc.__class__.__name__,
            errorType="service",
            path=request.url.path,
        )
        return JSONResponse(status_code=200, content=vo.model_dump())