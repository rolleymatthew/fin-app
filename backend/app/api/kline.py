"""K线相关 REST 接口（与前端 echart-etf Etf.jsx 对齐）。

端点：
  GET  /api/etf/kline        query: code=...&...
  GET  /api/kline/get        query: code=...
  POST /api/kline/refresh    query: code=...
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Query

from app.constants import spider
from app.models.result import ResultVO
from app.services.etf_service import EtfService
from app.services.finance_service import FinanceService
from app.services.kline_service import KLineService
from app.services.seccode_service import SecCodeService

router = APIRouter()


@lru_cache
def _services():
    return (
        EtfService(),
        KLineService(),
        SecCodeService(),
        FinanceService(),
    )


def _normalize_codes(code: list[str] | None) -> list[str]:
    codes: list[str] = []
    for c in (code or []):
        if not c:
            continue
        if "," in c:
            codes.extend([x.strip() for x in c.split(",") if x.strip()])
        else:
            codes.append(c.strip())
    return codes


@router.get("/etf/kline")
async def get_etf_kline(code: list[str] | None = Query(default=None)):
    etf_service, _, _, _ = _services()
    codes = _normalize_codes(code)
    name_map = {}
    for c in codes:
        etf_list = await etf_service.repo.find_all_by_sec_code(int(c)) if c.isdigit() else []
        if etf_list:
            name_map[c] = etf_list[0].secName
    await etf_service.spider_kline(codes, name_map=name_map)
    return ResultVO.ok().model_dump()


@router.get("/kline/get")
async def get_kline_by_code(
    code: int = Query(...),
    days: int | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    _, kline_service, _, _ = _services()
    entity = await kline_service.kline_by_sec_code(str(code), start=start, end=end, days=days)
    return ResultVO.ok(entity).model_dump()


@router.post("/kline/refresh")
async def refresh_kline(code: int = Query(...)):
    """强制全量重抓 K 线：删除旧 doc 后从 Eastmoney 全量拉取并落库。

    用于修复历史区间内的坏数据（如某日 open/vol/amount 全为 0）。
    普通 /api/etf/kline 走 spider_kline_data，已有数据时只做增量（last_date
    之后），不会覆盖历史坏条目；本端点专门用来清空后重新全量抓。
    """
    _, kline_service, _, _ = _services()
    market = spider.market_code(code)
    entity = await kline_service.refresh_kline_data(str(code), market, name=None)
    if entity is None:
        return ResultVO.fail(code=1, message="全量重抓失败或返回为空，请检查 code / 网络")
    return ResultVO.ok(
        {
            "code": entity.code,
            "count": len(entity.klines) if entity.klines else 0,
        }
    )
