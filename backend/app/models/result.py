from typing import Any, ClassVar, Generic, TypeVar
from pydantic import BaseModel


T = TypeVar("T")


class ResultVO(BaseModel, Generic[T]):
    RESULT_CODE_SUCCESS: ClassVar[int] = 200
    RESULT_CODE_FAILURE: ClassVar[int] = -1

    code: int | None = None
    msg: str | None = None
    data: Any | None = None
    count: int | None = None
    ids: list[int] | None = None

    @classmethod
    def build(cls, status: int, msg: str, data: Any | None = None):
        return cls(code=status, msg=msg, data=data)

    @classmethod
    def ok(cls, data: Any | None = None):
        return cls(code=cls.RESULT_CODE_SUCCESS, msg="成功", data=data)

    def success(self) -> bool:
        return self.code == self.RESULT_CODE_SUCCESS
