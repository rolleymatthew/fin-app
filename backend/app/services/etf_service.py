from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, List

from pypinyin import Style, lazy_pinyin

from app.clients.eastmoney_gmbd import EastMoneyGmbdClient
from app.clients.sse import SseClient
from app.clients.szse import SzseClient
from app.constants import spider
from app.mappers.custom import (
    etf_dto_to_entity,
    etf_quarter_dto_to_entity,
    etf_szse_dto_to_entity,
)
from app.models.entities import EtfEntity, EtfQuarterEntity, KLineEntity
from app.repositories.base import MongoRepository
from app.services.kline_service import KLineService
from app.utils import date_utils


class EtfService:
    SZSE_SYNC_THRESHOLD = 500  # SZSE ETF 总数 ~706，认为"近完整快照"的最低记录数

    def __init__(self):
        self.sse = SseClient()
        self.szse = SzseClient()
        self.gmbd = EastMoneyGmbdClient()
        self.repo = MongoRepository(EtfEntity)
        self.quarter_repo = MongoRepository(EtfQuarterEntity)
        self.kline_repo = MongoRepository(KLineEntity)
        self.kline_service = KLineService()

    async def spider_etf_data(self, day_count: int) -> List[EtfEntity]:
        result: List[EtfEntity] = []
        days = 0
        i = 0
        while i < day_count:
            local_date = date_utils.previous_days(days)
            if date_utils.is_working_day(local_date):
                etf_dto = await self.sse.etf(local_date.isoformat())
                if etf_dto and etf_dto.get("result"):
                    yesterday_num = days + 1
                    yesterday_dto = None
                    while not (yesterday_dto and yesterday_dto.get("result")):
                        yesterday = date_utils.previous_days(yesterday_num)
                        if date_utils.is_working_day(yesterday):
                            yesterday_dto = await self.sse.etf(yesterday.isoformat())
                        yesterday_num += 1
                    yesterday_list = yesterday_dto.get("result", [])
                    for etf in etf_dto.get("result", []):
                        y = next(
                            (x for x in yesterday_list if x.get("SEC_CODE") == etf.get("SEC_CODE")),
                            None,
                        )
                        result.append(etf_dto_to_entity(etf, y))
                else:
                    i -= 1
            else:
                i -= 1
            days += 1
            i += 1
        return result

    async def spider_szse_etf_data(
        self,
        days: int = 1,
        codes: list[str] | None = None,
        stat_date: date | None = None,
    ) -> List[EtfEntity]:
        """抓取深交所 ETF 份额数据（当前快照，无历史数据）

        SZSE 接口无日期参数，返回的是最近一个交易日的快照。
        即便上层传入 days>1，statDate 默认仍固定为最近一个工作日。
        需要按下载日期标记时可传入 stat_date。
        codes: 可选代码过滤；为 None 时返回全量。
        """
        raw = await self.szse.etf()
        rows = self.szse.parse_etf_rows(raw)
        stat_date = stat_date or self._latest_working_day()
        entities = [etf_szse_dto_to_entity(r, stat_date) for r in rows]
        result = [e for e in entities if e is not None]
        if codes:
            target_set = {c for c in codes}
            result = [e for e in result if e.secCode and str(e.secCode) in target_set]
        return result

    async def latest_szse_etf_date(self) -> date:
        source_date = await self.szse.etf_date()
        if source_date:
            try:
                return date.fromisoformat(source_date)
            except ValueError:
                pass
        return self._latest_working_day()

    @staticmethod
    def _previous_working_day(days: int = 1):
        """从今天开始查找第 N 个工作日（今天作为第 1 个工作日）"""
        offset = 0
        found = 0
        while found < days:
            d = date_utils.previous_days(offset)
            if date_utils.is_working_day(d):
                found += 1
                if found == days:
                    return d
            offset += 1
        return date_utils.previous_days(offset - 1)

    @staticmethod
    def _latest_working_day():
        """最近一个工作日：今天若是工作日则返回今天，否则返回上一个工作日"""
        today = date_utils.today()
        if date_utils.is_working_day(today):
            return today
        return EtfService._previous_working_day(1)

    async def spider_all_etf(self, day_count: int = 1) -> List[EtfEntity]:
        """合并抓取上交所 + 深交所 ETF 数据"""
        sse_entities, szse_entities = await asyncio.gather(
            self.spider_etf_data(day_count),
            self.spider_szse_etf_data(day_count),
        )
        return list(sse_entities) + list(szse_entities)

    async def spider_etf_by_codes(
        self, codes: list[str], day_count: int = 1
    ) -> List[EtfEntity]:
        """根据 code 前缀自动分发到 SSE / SZSE 客户端

        - 5/6 开头 → 上交所 (SSE)
        - 1 开头 → 深交所 (SZSE)
        其他前缀直接跳过。
        """
        sse_codes: list[int] = []
        szse_codes: list[str] = []
        for code in codes:
            if not code or not code.isdigit() or len(code) != 6:
                continue
            head = code[0]
            if head in ("5", "6"):
                sse_codes.append(int(code))
            elif head == "1":
                szse_codes.append(code)

        tasks = []
        if sse_codes:
            tasks.append(self._spider_sse_filtered(sse_codes, day_count))
        if szse_codes:
            tasks.append(self.spider_szse_etf_data(days=day_count, codes=szse_codes))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: List[EtfEntity] = []
        for r in results:
            if isinstance(r, list):
                out.extend(r)
        return out

    async def _spider_sse_filtered(
        self, target_codes: list[int], day_count: int
    ) -> List[EtfEntity]:
        """抓取 SSE 日度数据，并按 target_codes 过滤"""
        all_data = await self.spider_etf_data(day_count)
        target_set = {c for c in target_codes}
        return [e for e in all_data if e.secCode in target_set]

    async def save_mongo_data(self, etf_list: List[EtfEntity], with_kline: bool = False) -> None:
        for e in etf_list:
            e.pinyin = self._etf_pinyin_first_letters(e.secName)
            await self.repo.save(e)

        if not with_kline:
            return

        codes = sorted({e.secCode for e in etf_list if e.secCode})
        name_map = {e.secCode: e.secName for e in etf_list if e.secCode}
        kline_map = {}
        sem = asyncio.Semaphore(5)

        async def _fetch_one(code):
            async with sem:
                market_code = spider.market_code(code)
                kline = await self.kline_service.spider_kline_data(
                    str(code), market_code, name=name_map.get(code),
                )
                if kline and kline.klines:
                    kline_map[code] = kline
                    await self.kline_repo.save(kline)

        await asyncio.gather(*(_fetch_one(c) for c in codes), return_exceptions=True)
        for e in etf_list:
            kline = kline_map.get(e.secCode)
            if kline and kline.klines:
                amount = next((k.amountOfAverage for k in kline.klines if k.date == e.statDate), None)
                if amount is not None and e.addVol is not None:
                    e.addAmount = int(float(amount) * e.addVol)
            e.pinyin = self._etf_pinyin_first_letters(e.secName)
            await self.repo.save(e)

    async def spider_kline(self, etf_codes: List[str], name_map: dict | None = None):
        name_map = name_map or {}

        async def _fetch_one(code):
            market_code = spider.market_code(code)
            kline = await self.kline_service.spider_kline_data(
                code, market_code, name=name_map.get(code),
            )
            if kline and kline.klines:
                await self.kline_repo.save(kline)

        codes = [c for c in etf_codes if c]
        sem = asyncio.Semaphore(5)

        async def _fetch_with_sem(code):
            async with sem:
                await _fetch_one(code)

        await asyncio.gather(*(_fetch_with_sem(c) for c in codes), return_exceptions=True)

    async def report_etf_data(self) -> int | None:
        return None

    async def get_etf_date(self, sec_code: int):
        return await self.repo.find_all_by_sec_code(sec_code)

    async def get_etf_with_quarterly(self, sec_code: int) -> dict:
        """返回单只 ETF 的日度 + 季度数据

        深交所 ETF（1xxxxx）才有季度数据，上交所返回空列表。
        """
        daily = await self.get_etf_date(sec_code)
        quarterly: List[EtfQuarterEntity] = []
        if 100000 <= sec_code < 200000:
            quarterly = await self.get_quarter_history(sec_code)
        return {"data": daily, "quarterly": quarterly}

    async def spider_quarter_history(
        self, code: str, sec_name: str | None = None
    ) -> List[EtfQuarterEntity]:
        """抓取单只 ETF 的季度历史数据（东方财富 gmbd）

        数据存储到 etf_quarter 集合，独立于日度的 etf 集合。
        """
        raw = await self.gmbd.gmbd(code)
        rows = self.gmbd.parse_gmbd(raw)
        entities: List[EtfQuarterEntity] = []
        try:
            sec_code_int = int(code)
        except ValueError:
            return []
        for row in rows:
            entity = etf_quarter_dto_to_entity(row, sec_name=sec_name)
            if entity is None:
                continue
            entity.secCode = sec_code_int
            entity.id = f"{sec_code_int}{entity.statDate}"
            entities.append(entity)
        return entities

    async def spider_quarter_history_batch(
        self, codes: list[str], name_map: dict | None = None
    ) -> List[EtfQuarterEntity]:
        """批量抓取多只 ETF 季度历史"""
        name_map = name_map or {}
        sem = asyncio.Semaphore(5)

        async def _fetch_one(code):
            async with sem:
                try:
                    return await self.spider_quarter_history(code, sec_name=name_map.get(code))
                except Exception:
                    return []

        results = await asyncio.gather(*(_fetch_one(c) for c in codes), return_exceptions=True)
        flat: List[EtfQuarterEntity] = []
        for r in results:
            if isinstance(r, list):
                flat.extend(r)
        return flat

    async def save_quarter_data(self, entities: List[EtfQuarterEntity]) -> None:
        """保存季度数据到 etf_quarter 集合"""
        for e in entities:
            await self.quarter_repo.save(e)

    async def count_szse_records_at(self, stat_date: str) -> int:
        """统计 etf 集合里 stat_date 当天深市（1xxxxx）的记录数"""
        return await self.repo.collection.count_documents(
            {
                "secCode": {"$gte": 100000, "$lt": 200000},
                "statDate": stat_date,
            }
        )

    async def get_quarter_history(self, sec_code: int) -> List[EtfQuarterEntity]:
        """查询某只 ETF 的全部季度历史"""
        cursor = self.quarter_repo.collection.find({"secCode": sec_code}).sort("statDate", -1)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(EtfQuarterEntity.model_validate(self.quarter_repo._from_bson(doc)))
        return results

    # ===== ETF 下拉搜索 + 拼音回填（与 /api/sec/search 对齐） =====

    @staticmethod
    def _etf_pinyin_first_letters(name: str | None) -> str | None:
        """中文名 -> 大写首字母串（"沪深300ETF" -> "HS300ETF"）。"""
        if not name:
            return None
        letters = [p[0] for p in lazy_pinyin(name, style=Style.FIRST_LETTER) if p]
        py = "".join(letters).upper()
        return py or None

    async def search_etfs(
        self, q: str | None, limit: int = 200
    ) -> List[dict[str, Any]]:
        """在 etf 集合中按 代码 / 拼音首字母 / 中文名 模糊搜索，返回每只 ETF 最新条目。

        命中优先级：代码精确 > 代码前缀 > 拼音首字母前缀 > 名称包含。
        返回字段：code / name / pinyin / type / lastDate。
        """
        collection = self.repo.collection
        capped = max(1, min(int(limit or 200), 1000))
        query = (q or "").strip()

        base = {"secCode": {"$exists": True}, "secName": {"$exists": True, "$nin": [None, ""]}}
        projection = {
            "_id": 0,
            "secCode": 1,
            "secName": 1,
            "etfType": 1,
            "pinyin": 1,
            "statDate": 1,
        }

        def to_row(doc: dict) -> dict:
            return {
                "code": str(doc.get("secCode", "")),
                "name": doc.get("secName"),
                "pinyin": doc.get("pinyin"),
                "type": doc.get("etfType"),
                "lastDate": doc.get("statDate"),
            }

        async def latest_per_code(extra_q: dict, cap: int) -> List[dict]:
            pipeline = [
                {"$match": {**base, **extra_q}},
                {"$sort": {"secCode": 1, "statDate": -1}},
                {"$group": {"_id": "$secCode", "doc": {"$first": "$$ROOT"}}},
                {"$replaceRoot": {"newRoot": "$doc"}},
                {"$limit": cap},
            ]
            out: List[dict] = []
            async for d in collection.aggregate(pipeline):
                out.append(to_row(d))
            return out

        if not query:
            return await latest_per_code({}, capped)

        results: List[dict] = []
        seen: set[str] = set()

        # 1) 代码精确
        if query.isdigit():
            exact_doc = await collection.find_one(
                {**base, "secCode": int(query)}, projection
            )
            if exact_doc:
                code = str(exact_doc.get("secCode", ""))
                seen.add(code)
                results.append(to_row(exact_doc))

        # 2) 代码前缀（$expr 处理 int 字段，排除精确命中）
        prefix_re = f"^{query}"
        if query.isdigit():
            prefix_expr = {
                "$and": [
                    {"$regexMatch": {"input": {"$toString": "$secCode"}, "regex": prefix_re}},
                    {"$ne": [{"$toString": "$secCode"}, query]},
                ]
            }
        else:
            prefix_expr = {
                "$regexMatch": {"input": {"$toString": "$secCode"}, "regex": prefix_re}
            }
        async for d in (
            collection.find({**base, "$expr": prefix_expr}, projection)
            .sort([("secCode", 1), ("statDate", -1)])
        ):
            code = str(d.get("secCode", ""))
            if not code or code in seen:
                continue
            seen.add(code)
            results.append(to_row(d))
            if len(results) >= capped:
                return results

        # 3) 拼音首字母前缀
        if len(results) < capped:
            py = query.upper()
            py_q = {**base, "pinyin": {"$regex": f"^{py}"}}
            async for d in (
                collection.find(py_q, projection).sort([("secCode", 1), ("statDate", -1)])
            ):
                code = str(d.get("secCode", ""))
                if not code or code in seen:
                    continue
                seen.add(code)
                results.append(to_row(d))
                if len(results) >= capped:
                    return results

        # 4) 名称包含
        if len(results) < capped:
            name_q = {**base, "secName": {"$regex": query, "$options": "i"}}
            async for d in (
                collection.find(name_q, projection).sort([("secCode", 1), ("statDate", -1)])
            ):
                code = str(d.get("secCode", ""))
                if not code or code in seen:
                    continue
                seen.add(code)
                results.append(to_row(d))
                if len(results) >= capped:
                    return results

        return results

    async def backfill_pinyin(self, only_missing: bool = True) -> dict[str, Any]:
        """从 secName 算首字母写入 pinyin 字段（一次性维护，幂等）。

        - only_missing=True（默认）：仅更新 pinyin 缺失/为空的文档
        - only_missing=False：全量重算并覆盖
        """
        collection = self.repo.collection
        match_q: dict = {"secName": {"$exists": True, "$nin": [None, ""]}}
        if only_missing:
            match_q["$or"] = [
                {"pinyin": {"$exists": False}},
                {"pinyin": None},
                {"pinyin": ""},
            ]

        # 按 secCode 去重，用最新一天的 secName 算拼音
        pipeline = [
            {"$match": match_q},
            {"$sort": {"statDate": -1}},
            {"$group": {"_id": "$secCode", "name": {"$first": "$secName"}}},
        ]
        from pymongo import UpdateMany

        bulk_ops: list[UpdateMany] = []
        skipped = 0
        async for d in collection.aggregate(pipeline):
            code = d.get("_id")
            name = d.get("name")
            py = self._etf_pinyin_first_letters(name)
            if not py or not code:
                skipped += 1
                continue
            bulk_ops.append(
                UpdateMany(
                    {
                        "secCode": code,
                        "$or": [
                            {"pinyin": {"$exists": False}},
                            {"pinyin": None},
                            {"pinyin": ""},
                        ],
                    },
                    {"$set": {"pinyin": py}},
                )
            )
        updated = 0
        if bulk_ops:
            res = await collection.bulk_write(bulk_ops, ordered=False)
            updated = res.modified_count
        print(
            f"[backfill_pinyin/etf] updated={updated} skipped={skipped} "
            f"only_missing={only_missing}",
            flush=True,
        )
        return {"updated": updated, "skipped": skipped, "only_missing": only_missing}