"""ETF 下拉搜索 REST 接口（与前端 echart-etf EtfCombobox  对齐）。

端点：
  GET  /api/etf/search              query: q=...&limit=200
  POST /api/etf/backfill-pinyin     body: {"only_missing": true}

数据源：MongoDB `etf` 集合（secCode + secName），需先调 backfill-pinyin
从 secName 算首字母写入 pinyin 字段（一次性）。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query

from app.models.result import ResultVO
from app.services.etf_service import EtfService
from app.services.finance_service import FinanceService
from app.services.kline_service import KLineService
from app.services.seccode_service import SecCodeService

router = APIRouter()


@lru_cache
def _service() -> EtfService:
    return EtfService()


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


@router.get("/search")
async def search(
    q: str | None = None,
    limit: int = 200,
) -> dict:
    """按 代码 / 拼音首字母 / 中文名 模糊搜索 ETF，返回每只 ETF 最新条目。"""
    rows = await _service().search_etfs(q=q, limit=limit)
    return ResultVO.ok(rows).model_dump()


@router.post("/backfill-pinyin")
async def backfill_pinyin(payload: dict[str, Any] | None = None) -> dict:
    """一次性维护：从 secName 计算首字母写入 pinyin 字段。"""
    only_missing = bool((payload or {}).get("only_missing", True))
    report = await _service().backfill_pinyin(only_missing=only_missing)
    return ResultVO.ok(report).model_dump()


@router.get("")
async def get_etf(
    days: int = Query(default=1),
    code: list[str] | None = Query(default=None),
    with_kline: bool = Query(default=False),
    with_quarter: bool = Query(default=False),
):
    """抓取 ETF 日度份额数据，按 code 前缀自动分发到 SSE / SZSE。

    - 不传 code：上交所抓全量，下交所全量
    - 传 code：按前缀（5/6=SSE，1=SZSE）分别抓取并过滤
    - with_kline=true：同时抓取 K 线
    - with_quarter=true：同时抓取 SZSE 季度数据（写入 etf_quarter）
    """
    etf_service, _, _, _ = _services()
    codes = _normalize_codes(code)

    if codes:
        data = await etf_service.spider_etf_by_codes(codes, day_count=days)
    else:
        data = await etf_service.spider_all_etf(day_count=days)

    await etf_service.save_mongo_data(data, with_kline=with_kline)

    quarter_count = 0
    if with_quarter:
        szse_codes = [c for c in codes if c.isdigit() and len(c) == 6 and c.startswith("1")]
        if not codes:
            # 无 code 时只对 SZSE 全量做季度（之前 spider_szse_etf_data 已抓了全量快照）
            szse_entities = await etf_service.spider_szse_etf_data(days=days)
            szse_codes = [str(e.secCode) for e in szse_entities if e.secCode]
        if szse_codes:
            name_map = {
                str(e.secCode): e.secName
                for e in data
                if e.secCode
            }
            quarter_entities = await etf_service.spider_quarter_history_batch(
                szse_codes, name_map=name_map
            )
            await etf_service.save_quarter_data(quarter_entities)
            quarter_count = len(quarter_entities)

    return ResultVO.ok(
        {"daily": len(data), "quarter": quarter_count}
    ).model_dump()


@router.get("/szse")
async def get_szse_etf(code: list[str] | None = Query(default=None)):
    etf_service, _, _, _ = _services()
    data = await etf_service.spider_szse_etf_data()
    codes = _normalize_codes(code)
    if codes:
        code_set = {c for c in codes if c}
        data = [x for x in data if x.secCode and str(x.secCode) in code_set]
    await etf_service.save_mongo_data(data)
    return ResultVO.ok({"count": len(data)}).model_dump()


@router.post("/szse/sync")
async def sync_szse_etf(
    threshold: int | None = Query(default=None),
    force: bool = Query(default=False),
):
    """下载深交所 ETF 份额快照。

    先查 DB 在深交所原始日期上是否已有近完整快照；记录数达到 threshold
    且不强制时跳过，否则全量下载并按原始日期 upsert。

    - threshold：判定已有快照的最低记录数，默认 500
    - force=true：跳过检查直接下载
    """
    etf_service, _, _, _ = _services()
    target_date = await etf_service.latest_szse_etf_date()
    target_date_str = target_date.isoformat()
    threshold = threshold if threshold is not None else etf_service.SZSE_SYNC_THRESHOLD
    existing = await etf_service.count_szse_records_at(target_date_str)

    if not force and existing >= threshold:
        return ResultVO.ok(
            {
                "targetDate": target_date_str,
                "existingCount": existing,
                "threshold": threshold,
                "skipped": True,
                "savedCount": 0,
                "message": (
                    f"已经有最新数据 ({target_date_str}: {existing} 条 ≥ {threshold} 阈值)，"
                    "无需重复下载"
                ),
            }
        ).model_dump()

    data = await etf_service.spider_szse_etf_data(stat_date=target_date)
    await etf_service.save_mongo_data(data)
    return ResultVO.ok(
        {
            "targetDate": target_date_str,
            "existingCount": existing,
            "threshold": threshold,
            "skipped": False,
            "savedCount": len(data),
            "message": f"已下载并保存 {len(data)} 条 (statDate={target_date_str})",
        }
    ).model_dump()


@router.get("/all")
async def get_all_etf(days: int = Query(default=1), code: list[str] | None = Query(default=None)):
    etf_service, _, _, _ = _services()
    data = await etf_service.spider_all_etf(day_count=days)
    codes = _normalize_codes(code)
    if codes:
        code_set = {c for c in codes if c}
        data = [x for x in data if x.secCode and str(x.secCode) in code_set]
    await etf_service.save_mongo_data(data)
    return ResultVO.ok({"count": len(data)}).model_dump()


@router.get("/quarter")
async def get_etf_quarter(code: list[str] = Query(...)):
    """抓取并保存指定 ETF 列表的季度历史数据到 etf_quarter 集合

    例: GET /etf/quarter?code=510010&code=159001
    """
    etf_service, _, _, _ = _services()
    codes = _normalize_codes(code)
    if not codes:
        return ResultVO.fail(code=-1, message="code 参数必填").model_dump()

    # 优先使用 etf collection 中的 secName
    name_map = {}
    for c in codes:
        if c.isdigit():
            for e in await etf_service.get_etf_date(int(c)):
                if e.secName:
                    name_map[c] = e.secName
                    break

    entities = await etf_service.spider_quarter_history_batch(codes, name_map=name_map)
    await etf_service.save_quarter_data(entities)
    return ResultVO.ok({"codes": codes, "count": len(entities)}).model_dump()


@router.get("/quarter/get")
async def get_etf_quarter_history(code: str = Query(...)):
    """查询某只 ETF 的季度历史数据"""
    etf_service, _, _, _ = _services()
    if not code.isdigit():
        return ResultVO.fail(code=-1, message="code 必须是数字").model_dump()
    history = await etf_service.get_quarter_history(int(code))
    return ResultVO.ok(history).model_dump()