import asyncio
import logging
from functools import lru_cache

from fastapi import APIRouter, Query

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
                try:
                    kline = await kline_service.spider_kline_data(
                        entity.securityCode,
                        kline_service.market_code(entity.secucode),
                        name=getattr(entity, "securityNameAbbr", "") or None,
                    )
                    await kline_service.save_mongodb(kline)
                except Exception:
                    pass
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
    return ResultVO.fail(code=500, message=msg, data={"code": code, "name": name}).model_dump()


@router.get("/etf/get")
async def get_etf_by_code(code: int = Query(...)):
    """返回单只 ETF 的日度 + 季度数据

    深交所 ETF（1xxxxx）才含季度数据，上交所返回空列表。
    响应: {"data": [...日度], "quarterly": [...季度]}
    """
    etf_service, _, _, _ = _services()
    return await etf_service.get_etf_with_quarterly(code)
