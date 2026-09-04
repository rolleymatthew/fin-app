from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Iterable, List

from pypinyin import Style, lazy_pinyin

from app.clients.eastmoney import get_eastmoney_client
from app.clients.eastmoney_datacenter import EastmoneyDataCenterClient
from app.clients.exchange_base import OfficialStock
from app.constants import spider
from app.mappers.custom import seccode_from_company
from app.mappers.official_stock import official_to_entity
from app.models.entities import SecCodeEntity
from app.repositories.base import MongoRepository


def _pinyin_first_letters(name: str | None) -> str | None:
    """从中文名计算大写首字母串，如 宁德时代 -> NDSD。"""
    if not name:
        return None
    letters = [p[0] for p in lazy_pinyin(name, style=Style.FIRST_LETTER) if p]
    py = "".join(letters).upper()
    return py or None


@dataclass
class SyncDiff:
    new_codes: list[str] = field(default_factory=list)
    state_changed: list[str] = field(default_factory=list)
    missing_details: list[str] = field(default_factory=list)
    by_exchange: dict[str, int] = field(default_factory=dict)


@dataclass
class RefillResult:
    refilled: int = 0
    failed: list[dict] = field(default_factory=list)


@dataclass
class SyncReport:
    total_in_official: int = 0
    existing_in_db: int = 0
    new_added: int = 0
    state_changed: int = 0
    details_refilled: int = 0
    failed: list[dict] = field(default_factory=list)
    by_exchange: dict[str, int] = field(default_factory=dict)
    elapsed_ms: int = 0
    cookie_warmed: bool = False
    partial: bool = False


_MISSING_FIELDS = ("orgName", "regCapital", "orgTypeCode", "tradeMarketCode")


class SecCodeService:
    pn = 1
    pz = 3000
    np = 1

    def __init__(self):
        self.client = get_eastmoney_client()
        self.data_center = EastmoneyDataCenterClient()
        self.repo = MongoRepository(SecCodeEntity)

    def _infer_secucode(self, security_code: str | None) -> str | None:
        if not security_code:
            return None
        code = security_code.strip()
        if code.startswith("6"):
            return f"{code}.SH"
        if code.startswith("0") or code.startswith("3"):
            return f"{code}.SZ"
        if code.startswith("8") or code.startswith("4"):
            return f"{code}.BJ"
        return None

    async def _ensure_secucode(self, entity: SecCodeEntity | None) -> SecCodeEntity | None:
        if entity is None:
            return None
        if entity.secucode:
            return entity
        inferred = self._infer_secucode(entity.securityCode)
        if not inferred:
            return entity
        entity.secucode = inferred
        await self.repo.save(entity)
        return entity

    async def spider_sec_code(self, sec_code: str | None = None) -> List[dict]:
        diff = []
        if not sec_code:
            diff = await self.spider_all_sec_code()
        else:
            diff = [{"secCode": sec_code}]
        companies = []
        for d in diff:
            company = await self.get_company_dto(d.get("secCode"))
            if company:
                companies.append(company)
        return companies

    async def get_company_dto(self, sec_code: str) -> dict | None:
        try:
            return await self.data_center.company(
                "RPT_F10_ORG_BASICINFO", "ALL", f"(SECURITY_CODE=\"{sec_code}\")"
            )
        except Exception:
            return None

    async def get_company_dto_with_raw(self, sec_code: str) -> tuple[dict | None, str]:

        data_center = getattr(self, "data_center", None)
        company_with_raw = getattr(data_center, "company_with_raw", None)
        if company_with_raw is None:
            return await self.get_company_dto(sec_code), ""
        try:
            company, raw = await company_with_raw(
                "RPT_F10_ORG_BASICINFO", "ALL", f"(SECURITY_CODE=\"{sec_code}\")"
            )
        except Exception:
            return None, ""
        if not isinstance(company, dict):
            company = None
        return company, raw or ""

    async def spider_all_sec_code(self) -> List[dict]:
        existing = await self.repo.find_all()
        if existing:
            return [
                {"secCode": e.securityCode, "secName": e.securityNameAbbr}
                for e in existing
                if e.securityCode and (e.listingState or "0") == "0"
            ]
        # DB 为空：回退到东财列表（向后兼容老调用方）
        try:
            sh = await self.client.code_list(
                self.pn, self.pz, self.np, spider.SH_CODE_FS, spider.CODE_FIELDS
            )
        except Exception as exc:
            print(f"[spider_all_sec_code] 沪市股票列表请求失败: {exc}", flush=True)
            sh = None
        try:
            sz = await self.client.code_list(
                self.pn, self.pz, self.np, spider.SZ_CODE_FS, spider.CODE_FIELDS
            )
        except Exception as exc:
            print(f"[spider_all_sec_code] 深市股票列表请求失败: {exc}", flush=True)
            sz = None
        diff: List[dict] = []
        if sh and sh.get("data"):
            diff.extend(sh["data"].get("diff", []))
        if sz and sz.get("data"):
            diff.extend(sz["data"].get("diff", []))
        result = [
            {"secCode": d.get("f12"), "secName": d.get("f14")}
            for d in diff
            if d.get("f12")
        ]
        print(
            f"[spider_all_sec_code] 降级路径：东财返回 {len(diff)} 条，有效 {len(result)} 条",
            flush=True,
        )
        return result

    async def save(self, companies: List[dict]) -> None:
        for c in companies:
            await self.sec_code_by_company(c)

    async def sec_code_by_company(self, company: dict) -> SecCodeEntity | None:
        if not company or company.get("code") != 0:
            return None
        data = company.get("result", {}).get("data", [])
        if not data:
            return None
        entity = seccode_from_company(data[0])
        await self.repo.save(entity)
        return entity

    async def sec_code_list(self) -> List[SecCodeEntity]:
        return await self.repo.find_all()

    async def search_stocks(
        self,
        q: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """在 sec_code 集合中按 代码 / 拼音首字母 / 名称 模糊搜索。

        - listingState == "0" 仅返回正常上市（约 5200+ 家）
        - 命中优先级：代码精确 > 代码前缀 > 拼音首字母前缀 > 名称包含
        """
        max_limit = 1000
        limit = max(1, min(int(limit or 200), max_limit))
        query = (q or "").strip()

        base_filter: dict = {"listingState": "0"}

        projection = {
            "_id": 1,
            "securityCode": 1,
            "securityNameAbbr": 1,
            "securityPinyin": 1,
            "secucode": 1,
            "tradeMarket": 1,
            "securityType": 1,
            "listingDate": 1,
        }

        def _row(doc: dict) -> dict:
            return {
                "code": doc.get("securityCode") or doc.get("_id"),
                "name": doc.get("securityNameAbbr"),
                "pinyin": doc.get("securityPinyin"),
                "secucode": doc.get("secucode"),
                "market": doc.get("tradeMarket"),
                "type": doc.get("securityType"),
                "listingDate": doc.get("listingDate"),
            }

        collection = self.repo.collection

        if not query:
            cursor = collection.find(base_filter, projection).limit(limit)
            return [_row(doc) async for doc in cursor]

        qu = query.upper()
        exact_filter = {**base_filter, "securityCode": query}
        exact_doc = await collection.find_one(exact_filter, projection)
        exact_list = [exact_doc] if exact_doc else []

        prefix_filter = {
            **base_filter,
            "$and": [
                {"securityCode": {"$regex": f"^{query}"}},
                {"securityCode": {"$ne": query}},
            ],
        }
        pinyin_filter = {**base_filter, "securityPinyin": {"$regex": f"^{qu}"}}
        name_filter = {**base_filter, "securityNameAbbr": {"$regex": query}}

        remaining = limit - len(exact_list)
        results: list[dict] = []
        seen: set[str] = set()
        if exact_list:
            code = exact_list[0].get("securityCode")
            if code:
                seen.add(code)
            results.append(_row(exact_list[0]))

        if remaining > 0:
            cursor = collection.find(prefix_filter, projection).limit(remaining)
            async for doc in cursor:
                code = doc.get("securityCode")
                if code and code in seen:
                    continue
                if code:
                    seen.add(code)
                results.append(_row(doc))
                if len(results) >= limit:
                    break

        if len(results) < limit:
            remaining = limit - len(results)
            cursor = collection.find(pinyin_filter, projection).limit(remaining)
            async for doc in cursor:
                code = doc.get("securityCode")
                if code and code in seen:
                    continue
                if code:
                    seen.add(code)
                results.append(_row(doc))
                if len(results) >= limit:
                    break

        if len(results) < limit:
            remaining = limit - len(results)
            cursor = collection.find(name_filter, projection).limit(remaining)
            async for doc in cursor:
                code = doc.get("securityCode")
                if code and code in seen:
                    continue
                if code:
                    seen.add(code)
                results.append(_row(doc))
                if len(results) >= limit:
                    break

        return results

    async def backfill_pinyin(self, only_missing: bool = True) -> dict:
        """从中文名 securityNameAbbr 计算首字母，回填 securityPinyin 字段。

        - only_missing=True（默认）：仅更新 securityPinyin 缺失/为空的文档（幂等、可重跑）
        - only_missing=False：全量重算并覆盖
        """
        collection = self.repo.collection
        query: dict = {
            "securityNameAbbr": {"$exists": True, "$nin": [None, ""]},
        }
        if only_missing:
            query["$or"] = [
                {"securityPinyin": {"$exists": False}},
                {"securityPinyin": {"$in": [None, ""]}},
            ]

        updated = 0
        skipped = 0
        async for doc in collection.find(query, {"_id": 1, "securityNameAbbr": 1}):
            name = doc.get("securityNameAbbr")
            py = _pinyin_first_letters(name)
            _id = doc.get("_id")
            if not py or not _id:
                skipped += 1
                continue
            await collection.update_one({"_id": _id}, {"$set": {"securityPinyin": py}})
            updated += 1
        print(
            f"[backfill_pinyin] updated={updated} skipped={skipped} "
            f"only_missing={only_missing}",
            flush=True,
        )
        return {"updated": updated, "skipped": skipped, "only_missing": only_missing}

    async def sec_code_entity_by_id(self, sec_code: str) -> SecCodeEntity | None:
        entity = await self.repo.find_by_id(sec_code.strip())
        return await self._ensure_secucode(entity)

    async def sec_code_entity_by_one(self, sec_code: str) -> SecCodeEntity | None:
        companies = await self.spider_sec_code(sec_code)
        for c in companies:
            entity = await self.sec_code_by_company(c)
            if entity:
                return await self._ensure_secucode(entity)
        entity = await self.repo.find_by_id(sec_code.strip())
        return await self._ensure_secucode(entity)

    @staticmethod
    def _is_missing_details(entity: SecCodeEntity) -> bool:
        return any(getattr(entity, k, None) in (None, "") for k in _MISSING_FIELDS)

    async def compute_diff(
        self,
        official: list[OfficialStock],
        existing: list[SecCodeEntity],
        force: bool = False,
    ) -> SyncDiff:
        existing_by_code: dict[str, SecCodeEntity] = {
            (e.securityCode or e.id or ""): e for e in existing
        }
        diff = SyncDiff()
        for stock in official:
            entity = existing_by_code.get(stock.code)
            if entity is None:
                diff.new_codes.append(stock.code)
                continue
            if entity.listingState != stock.listingState:
                diff.state_changed.append(stock.code)
                continue
            if force or self._is_missing_details(entity):
                diff.missing_details.append(stock.code)
        diff.by_exchange = {"SH": 0, "SZ": 0}
        for s in official:
            diff.by_exchange[s.market] = diff.by_exchange.get(s.market, 0) + 1
        return diff

    async def refill_details(
        self,
        codes: Iterable[str],
        rate: float = 5.0,
        retries: int = 3,
    ) -> RefillResult:
        sem = asyncio.Semaphore(max(int(rate), 1))
        interval = 1.0 / max(rate, 0.1)
        result = RefillResult()
        cookie_health = getattr(getattr(self, "client", None), "_cookie_health", None)

        async def _one(code: str) -> None:
            async with sem:
                await asyncio.sleep(interval)
                cookie_retry_used = False
                for attempt in range(1, retries + 1):
                    try:
                        company, raw = await self.get_company_dto_with_raw(code)
                    except Exception as exc:
                        if attempt >= retries:
                            reason = f"exception:{type(exc).__name__}"
                            result.failed.append({"code": code, "reason": reason})
                            return
                        await asyncio.sleep(2 ** attempt)
                        continue

                    invalid_cookie = False
                    if raw and cookie_health is not None:
                        try:
                            invalid_cookie = cookie_health.check(raw).invalid
                        except Exception:
                            invalid_cookie = False
                    if invalid_cookie:
                        if cookie_retry_used:
                            result.failed.append({"code": code, "reason": "cookie_invalid"})
                            return
                        cookie_retry_used = True
                        try:
                            refreshed = await cookie_health.refresh_once(self.client)
                        except Exception:
                            refreshed = False
                        if not refreshed:
                            result.failed.append({"code": code, "reason": "cookie_invalid"})
                            return
                        try:
                            company, raw = await self.get_company_dto_with_raw(code)
                        except Exception:
                            result.failed.append({"code": code, "reason": "cookie_invalid"})
                            return
                        try:
                            retry_invalid = bool(raw and cookie_health.check(raw).invalid)
                        except Exception:
                            retry_invalid = False
                        if retry_invalid or not (company and company.get("code") == 0):
                            result.failed.append({"code": code, "reason": "cookie_invalid"})
                            return
                        entity = await self.sec_code_by_company(company)
                        if entity is None:
                            result.failed.append({"code": code, "reason": "cookie_invalid"})
                            return
                        result.refilled += 1
                        return

                    if company and company.get("code") == 0:
                        entity = await self.sec_code_by_company(company)
                        if entity is None:
                            result.failed.append({"code": code, "reason": "mapper_empty"})
                            return
                        result.refilled += 1
                        return
                    if attempt >= retries:
                        result.failed.append({"code": code, "reason": "datacenter_empty"})
                        return
                    await asyncio.sleep(2 ** attempt)

        await asyncio.gather(*[_one(c) for c in codes])
        return result

    last_sync_report: SyncReport | None = None

    @staticmethod
    def _merge_unique(stocks: list[OfficialStock]) -> list[OfficialStock]:
        seen: dict[str, OfficialStock] = {}
        for s in stocks:
            seen.setdefault(s.code, s)
        return list(seen.values())

    async def _fetch_sse_equity(self) -> list[OfficialStock]:
        from app.clients.sse_equity import SseEquityClient

        client = SseEquityClient()
        try:
            return await client.fetch_list()
        finally:
            await client.close()

    async def _fetch_szse_xlsx(self) -> list[OfficialStock]:
        from app.clients.szse_xlsx import SzseXlsxClient

        client = SzseXlsxClient()
        try:
            return await client.fetch_list()
        finally:
            await client.close()

    async def _fetch_official(self) -> list[OfficialStock]:
        self._last_fetch_failed_segments = []
        official: list[OfficialStock] = []
        failed: list[str] = []
        for source, fetcher in (
            ("SSE_EQUITY", self._fetch_sse_equity),
            ("SZSE_XLSX", self._fetch_szse_xlsx),
        ):
            try:
                official.extend(await fetcher())
            except Exception as exc:
                failed.append(source)
                print(f"[sec_sync] {source} fetch failed: {exc}", flush=True)
        self._last_fetch_failed_segments = failed
        return self._merge_unique(official)

    async def sync_from_exchanges(self, force: bool = False) -> SyncReport:
        started = time.time()
        self._last_fetch_failed_segments = []
        official = await self._fetch_official()
        existing = await self.repo.find_all()
        diff = await self.compute_diff(official, existing, force=force)

        official_by_code = {s.code: s for s in official}
        for code in diff.new_codes + diff.state_changed:
            entity = official_to_entity(official_by_code[code])
            await self.repo.save(entity)

        target_codes = diff.new_codes + diff.state_changed + diff.missing_details
        seen: set[str] = set()
        target_codes = [c for c in target_codes if not (c in seen or seen.add(c))]
        refill = await self.refill_details(target_codes)

        partial = bool(self._last_fetch_failed_segments)
        report = SyncReport(
            total_in_official=len(official),
            existing_in_db=len(existing),
            new_added=len(diff.new_codes),
            state_changed=len(diff.state_changed),
            details_refilled=refill.refilled,
            failed=refill.failed,
            by_exchange=diff.by_exchange,
            elapsed_ms=int((time.time() - started) * 1000),
            cookie_warmed=False,
            partial=partial,
        )
        self.last_sync_report = report
        print(
            f"[sec_sync] official={report.total_in_official} "
            f"new={report.new_added} changed={report.state_changed} "
            f"refilled={report.details_refilled} failed={len(report.failed)} "
            f"partial={report.partial} elapsed_ms={report.elapsed_ms}",
            flush=True,
        )
        return report

    async def refresh_all_details(
        self,
        include_delisted: bool = True,
        only_missing: bool = False,
    ) -> SyncReport:
        started = time.time()
        existing = await self.repo.find_all()
        if not include_delisted:
            existing = [e for e in existing if (e.listingState or "0") == "0"]
        if only_missing:
            targets = [e.securityCode for e in existing if self._is_missing_details(e)]
        else:
            targets = [e.securityCode for e in existing if e.securityCode]
        refill = await self.refill_details(targets)
        report = SyncReport(
            total_in_official=0,
            existing_in_db=len(existing),
            new_added=0,
            state_changed=0,
            details_refilled=refill.refilled,
            failed=refill.failed,
            by_exchange={},
            elapsed_ms=int((time.time() - started) * 1000),
        )
        self.last_sync_report = report
        print(
            f"[sec_force] targets={len(targets)} refilled={refill.refilled} "
            f"failed={len(refill.failed)} elapsed_ms={report.elapsed_ms}",
            flush=True,
        )
        return report
