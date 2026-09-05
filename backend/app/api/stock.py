import asyncio
import logging
from functools import lru_cache

from fastapi import APIRouter, Query

from app.constants import spider
from app.models.result import ResultVO
from app.services.etf_service import EtfService
from app.services.finance_service import FinanceService
from app.services.hk_finance_service import HKFinanceService
from app.services.kline_service import KLineService
from app.services.seccode_service import SecCodeService
from app.utils import finance_utils

logger = logging.getLogger(__name__)

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


@router.get("/etf")
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


@router.get("/etf/szse")
async def get_szse_etf(code: list[str] | None = Query(default=None)):
    etf_service, _, _, _ = _services()
    data = await etf_service.spider_szse_etf_data()
    codes = _normalize_codes(code)
    if codes:
        code_set = {c for c in codes if c}
        data = [x for x in data if x.secCode and str(x.secCode) in code_set]
    await etf_service.save_mongo_data(data)
    return ResultVO.ok({"count": len(data)}).model_dump()


@router.post("/etf/szse/sync")
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


@router.get("/etf/all")
async def get_all_etf(days: int = Query(default=1), code: list[str] | None = Query(default=None)):
    etf_service, _, _, _ = _services()
    data = await etf_service.spider_all_etf(day_count=days)
    codes = _normalize_codes(code)
    if codes:
        code_set = {c for c in codes if c}
        data = [x for x in data if x.secCode and str(x.secCode) in code_set]
    await etf_service.save_mongo_data(data)
    return ResultVO.ok({"count": len(data)}).model_dump()


@router.get("/etf/quarter")
async def get_etf_quarter(code: list[str] = Query(...)):
    """抓取并保存指定 ETF 列表的季度历史数据到 etf_quarter 集合

    例: GET /etf/quarter?code=510010&code=159001
    """
    etf_service, _, _, _ = _services()
    codes = _normalize_codes(code)
    if not codes:
        return ResultVO.build(-1, "code 参数必填").model_dump()

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


@router.get("/etf/quarter/get")
async def get_etf_quarter_history(code: str = Query(...)):
    """查询某只 ETF 的季度历史数据"""
    etf_service, _, _, _ = _services()
    if not code.isdigit():
        return ResultVO.build(-1, "code 必须是数字").model_dump()
    history = await etf_service.get_quarter_history(int(code))
    return ResultVO.ok(history).model_dump()


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


@router.get("/check")
async def check_finance_data(date: list[str] = Query(...), code: list[str] | None = Query(default=None)):
    _, _, _, finance_service = _services()
    sec_entities = await finance_service.get_sec_code_entities(code)
    missing = []
    for s in sec_entities:
        for d in date:
            if not await finance_service.has_fin_data(s, d):
                missing.append(f"{s.securityCode},{d}")
    return ResultVO.build(1, "缺少财务数据", missing).model_dump()


@router.get("/one")
async def get_one_by_one(
    code: list[str] | None = Query(default=None),
    date: str | None = Query(default=None),
    keepon_code: str | None = Query(default=None),
    crawl: bool | None = Query(default=None),
    parallel: int | None = Query(default=10),
):
    _, kline_service, seccode_service, finance_service = _services()

    sec_codes = _normalize_codes(code)
    if sec_codes:
        logger.info("[api] /one codes=%s", sec_codes)
    if not sec_codes:
        if crawl:
            sec_codes = [x.get("secCode") for x in await seccode_service.spider_all_sec_code()]
        else:
            sec_codes = [x.securityCode for x in await seccode_service.sec_code_list()]
    if not sec_codes:
        logger.info("[api] /one 未获取到任何股票代码，退出")
        return ResultVO.ok({"processed": [], "skipped": [], "failed": []}).model_dump()

    sec_codes = sorted([x for x in sec_codes if x])
    if keepon_code:
        sec_codes = [x for x in sec_codes if x > keepon_code]

    processed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    total = len(sec_codes)
    counter = [0]
    sem = asyncio.Semaphore(max(parallel or 5, 1))

    async def _process_one(code):
        async with sem:
            code_str = code or "?"

            if crawl:
                await seccode_service.sec_code_entity_by_one(code)
            entity = await seccode_service.sec_code_entity_by_id(code)

            if not entity or not finance_utils.null_st(entity):
                reason = "实体为空"
                if entity:
                    ls = getattr(entity, "listingState", None)
                    name = getattr(entity, "securityNameAbbr", "") or ""
                    if ls != "0":
                        reason = f"listingState={ls}"
                    elif "ST" in name or "*ST" in name or "退" in name:
                        reason = f"名称={name}"
                counter[0] += 1
                logger.info("[api] /one [%s/%s] %s 无效(%s)", counter[0], total, code_str, reason)
                skipped.append(code_str)
                return

            if crawl:
                # K 线: 完全不存在时用东财接口先抓一遍全量
                # (refresh_kline_data 在无 existing 时走 spider_kline_data 全量分支)
                existing_kline = await kline_service.kline_by_sec_code(entity.securityCode)
                if not existing_kline or not existing_kline.klines:
                    await kline_service.refresh_kline_data(
                        entity.securityCode,
                        kline_service.market_code(entity.secucode),
                        name=getattr(entity, "securityNameAbbr", "") or None,
                    )
                # 后续 K 线窗口缺口检测交给 export_fin_to_excel → _ensure_kline_complete
                # (Tasks 1-4 智能判断：4 季度窗口 < 5 条触发补抓；>120 走 EM 全量, ≤120 走定向)
                err = await finance_service.save_fin_data_to_mongodb(entity, date, crawl)
                if err:
                    counter[0] += 1
                    logger.info("[api] /one [%s/%s] %s 失败", counter[0], total, code_str)
                    failed.append(code_str)
                    return
            else:
                exists = await (
                    finance_service.has_fin_data(entity, date)
                    if date
                    else finance_service.has_fin_data_any(entity)
                )
                if not exists:
                    counter[0] += 1
                    logger.info("[api] /one [%s/%s] %s 跳过(无数据)", counter[0], total, code_str)
                    skipped.append(code_str)
                    return

            await finance_service.export_fin_to_excel(entity, 2)
            counter[0] += 1
            logger.info("[api] /one [%s/%s] %s 完成", counter[0], total, code_str)
            processed.append(code_str)

    batch = 100
    for i in range(0, total, batch):
        tasks = [_process_one(c) for c in sec_codes[i : i + batch]]
        await asyncio.gather(*tasks, return_exceptions=True)

    return ResultVO.ok({"processed": processed, "skipped": skipped, "failed": failed}).model_dump()


@router.get("/hk/one")
async def get_hk_one(
    code: str = Query(...),
    name: str = Query(...),
):
    logger.info("[api] /hk/one code=%s name=%s", code, name)
    hk_service = HKFinanceService()
    await hk_service.save_hk_fin_data_to_mongodb(code, name)
    ok, msg = await hk_service.export_hk_fin_2_excle(code, name)
    if ok:
        return ResultVO.ok({"code": code, "name": name, "path": msg}).model_dump()
    return ResultVO.build(status=500, msg=msg, data={"code": code, "name": name}).model_dump()


@router.get("/etf/get")
async def get_etf_by_code(code: int = Query(...)):
    """返回单只 ETF 的日度 + 季度数据

    深交所 ETF（1xxxxx）才含季度数据，上交所返回空列表。
    响应: {"data": [...日度], "quarterly": [...季度]}
    """
    etf_service, _, _, _ = _services()
    payload = await etf_service.get_etf_with_quarterly(code)
    return ResultVO.ok(payload).model_dump()


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
        return ResultVO.build(1, "全量重抓失败或返回为空，请检查 code / 网络", None)
    return ResultVO.ok(
        {
            "code": entity.code,
            "count": len(entity.klines) if entity.klines else 0,
        }
    )
