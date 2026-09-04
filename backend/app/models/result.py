"""统一响应包装。8 字段契约见 docs/superpowers/specs/2026-09-04-fin-app-extract-design.md §4.3。"""
from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel


def _now_ms() -> int:
    return int(time.time() * 1000)


class ResultVO(BaseModel):
    success: bool
    code: int = 0
    message: str = "ok"
    data: Any | None = None
    timestamp: int = 0
    path: str = ""
    durationMs: int = 0
    errorType: str | None = None

    @classmethod
    def ok(
        cls,
        data: Any | None = None,
        *,
        path: str = "",
        durationMs: int = 0,
    ) -> "ResultVO":
        return cls(
            success=True,
            code=0,
            message="ok",
            data=data,
            timestamp=_now_ms(),
            path=path,
            durationMs=durationMs,
        )

    @classmethod
    def fail(
        cls,
        code: int,
        message: str,
        *,
        errorType: str = "business",
        path: str = "",
        durationMs: int = 0,
        data: Any | None = None,
    ) -> "ResultVO":
        return cls(
            success=False,
            code=code,
            message=message,
            data=data,
            timestamp=_now_ms(),
            path=path,
            durationMs=durationMs,
            errorType=errorType,
        )

    def model_dump(self, **kwargs):
        return super().model_dump(**kwargs)