"""K线相关 REST 接口（与前端 echart-etf Etf.jsx 对齐）。

端点：
  GET  /api/etf/kline        query: code=...&...
  GET  /api/kline/get        query: code=...
  POST /api/kline/refresh    query: code=...
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.constants import spider
from app.models.result import ResultVO
from app.services.etf_service import EtfService
from app.services.finance_service import FinanceService
from app.services.kline_service import KLineService
from app.services.seccode_service import SecCodeService

router = APIRouter()


# 全市场同步并发度 (避免一次性 5000+ 同时打 TDX 本地 IO)
_BATCH_SYNC_CONCURRENCY = 20


@lru_cache
def _services():
    return (
        EtfService(),
        KLineService(),
        SecCodeService(),
        FinanceService(),
    )


class SyncFromTdxRequest(BaseModel):
    code: str = Field(
        default="",
        description="6 位股票代码 (如 '000049'), 空字符串 = 全市场批量同步",
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
async def get_etf_kline(
    code: list[str] | None = Query(default=None),
    source: str = Query(
        default="online",
        description="K线数据源. 'online' (默认, 网络抓) | 'offline' (本地通达信)",
    ),
):
    etf_service, _, _, _ = _services()
    if source not in ("online", "offline"):
        return ResultVO.fail(
            code=400,
            message=f"非法 source={source!r}, 期望 'online' 或 'offline'",
        ).model_dump()
    codes = _normalize_codes(code)
    print(
        f"[kline/api] GET /api/etf/kline codes={codes} source={source}",
        flush=True,
    )
    name_map = {}
    for c in codes:
        etf_list = await etf_service.repo.find_all_by_sec_code(int(c)) if c.isdigit() else []
        if etf_list:
            name_map[c] = etf_list[0].secName
    await etf_service.spider_kline(codes, name_map=name_map, data_source=source)
    return ResultVO.ok().model_dump()


@router.get("/kline/get")
async def get_kline_by_code(
    code: int = Query(...),
    days: int | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    source: str = Query(
        default="online",
        description="数据源. 'online' (默认, Mongo 落库) | 'offline' (本地通达信 vipdoc+gbbq)",
    ),
):
    _, kline_service, _, _ = _services()
    if source not in ("online", "offline"):
        return ResultVO.fail(
            code=400,
            message=f"非法 source={source!r}, 期望 'online' 或 'offline'",
        ).model_dump()
    print(
        f"[kline/api] GET /api/kline/get code={code} source={source} "
        f"start={start} end={end} days={days}",
        flush=True,
    )
    entity = await kline_service.kline_by_sec_code(
        str(code), start=start, end=end, days=days, data_source=source,
    )
    return ResultVO.ok(entity).model_dump()


@router.post("/kline/refresh")
async def refresh_kline(
    code: int = Query(...),
    source: str = Query(
        default="online",
        description="数据源. 'online' (默认, 清空后从 Eastmoney 全量重抓) | "
                    "'offline' (清空后从本地通达信 vipdoc+gbbq 重写)",
    ),
):
    """强制全量重抓 K 线：删除旧 doc 后从指定数据源全量拉取并落库。

    用于修复历史区间内的坏数据（如某日 open/vol/amount 全为 0）。
    普通 /api/etf/kline 走 spider_kline_data，已有数据时只做增量（last_date
    之后），不会覆盖历史坏条目；本端点专门用来清空后重新全量抓。

    source:
        'online'  — 删除旧 doc 后从 Eastmoney 全量拉取
        'offline' — 删除旧 doc 后从本地通达信 vipdoc+gbbq 重写
                    (无网络/无 DB 依赖, 适合离线环境)
    """
    if source not in ("online", "offline"):
        return ResultVO.fail(
            code=400,
            message=f"非法 source={source!r}, 期望 'online' 或 'offline'",
        ).model_dump()
    _, kline_service, _, _ = _services()
    market = spider.market_code(code) if source != "offline" else None
    print(
        f"[kline/api] POST /api/kline/refresh code={code} source={source}",
        flush=True,
    )
    entity = await kline_service.refresh_kline_data(
        str(code), market, name=None, data_source=source,
    )
    if entity is None:
        return ResultVO.fail(code=1, message="全量重抓失败或返回为空，请检查 code / 网络")
    return ResultVO.ok(
        {
            "code": entity.code,
            "count": len(entity.klines) if entity.klines else 0,
        }
    )


@router.post("/kline/sync-from-tdx")
async def sync_from_tdx(payload: SyncFromTdxRequest):
    """把通达信本地 K 线按日期合并覆盖到 MongoDB k_line.

    流程:
      1. 读 TDX 本地 (.day, 含 qfq 复权)
      2. 读 Mongo k_line 现有
      3. 比最新日期, TDX 更新则合并覆盖 (TDX 胜出, 保留 Mongo 独有字段)
      4. 返 Mongo (现在保证新鲜, 含 TDX 最新日期)

    调用方按需触发 (例如 /one 跑前批量调一次). 不修改任何已有读路径.

    Request body: {"code": "000049"} 或 {"code": ""} (后者=全市场)
    Response ok (单只): {code, latest_date, record_count}
    Response ok (批量): {batch: true, total, synced, up_to_date, failed: [...]}
    """
    _, kline_service, sec_code_service, _ = _services()

    code = (payload.code or "").strip()

    # 空 code → 全市场批量同步
    if not code:
        all_entities = await sec_code_service.repo.find_all()
        targets = [e for e in all_entities if e.securityCode]
        print(
            f"[kline/api] POST /api/kline/sync-from-tdx batch "
            f"total_targets={len(targets)} concurrency={_BATCH_SYNC_CONCURRENCY}",
            flush=True,
        )

        synced_count = 0
        failed: list[dict] = []

        async def _one(entity) -> None:
            nonlocal synced_count
            try:
                result = await kline_service.sync_mongo_with_tdx(
                    entity.securityCode, entity,
                )
                if result is not None:
                    synced_count += 1
            except Exception as exc:
                failed.append(
                    {"code": entity.securityCode, "error": f"{type(exc).__name__}: {exc}"}
                )

        sem = asyncio.Semaphore(_BATCH_SYNC_CONCURRENCY)

        async def _bounded(entity) -> None:
            async with sem:
                await _one(entity)

        await asyncio.gather(*[_bounded(e) for e in targets])

        print(
            f"[kline/api] /kline/sync-from-tdx batch done "
            f"total={len(targets)} synced={synced_count} failed={len(failed)}",
            flush=True,
        )
        return ResultVO.ok(
            {
                "batch": True,
                "total": len(targets),
                "synced": synced_count,
                "failed": failed,
            }
        ).model_dump()

    # 单只同步
    sec_code_entity = await sec_code_service.sec_code_entity_by_id(code)
    if sec_code_entity is None:
        return ResultVO.fail(
            code=404, message=f"sec_code 未找到: {code}"
        ).model_dump()

    print(
        f"[kline/api] POST /api/kline/sync-from-tdx code={code}",
        flush=True,
    )
    synced = await kline_service.sync_mongo_with_tdx(code, sec_code_entity)
    if synced is None:
        return ResultVO.fail(
            code=1,
            message=f"TDX 本地无 {code} 数据 (检查通达信 .day 文件)",
        ).model_dump()

    latest_date = max(
        (k.date for k in synced.klines if k.date), default=None
    )
    return ResultVO.ok(
        {
            "code": code,
            "latest_date": latest_date,
            "record_count": len(synced.klines),
        }
    ).model_dump()
