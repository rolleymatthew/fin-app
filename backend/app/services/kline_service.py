from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List

import httpx

from app.clients.eastmoney import get_eastmoney_client
from app.clients.kline import FQT, PERIOD, KLineRow, build_aggregator
from app.config import get_settings
from app.constants import spider
from app.mappers.kline_data import quarter_of_kline
from app.models.entities import KLineDataEntity, KLineEntity
from app.repositories.base import MongoRepository
from app.utils import date_utils, num_utils, transform


class KLineService:
    fields1 = "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
    fields2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    beg = 0
    end = 20500101
    klt = 101
    fqt = 1
    infqt = 0

    # 全量拉取: 覆盖上市至今所有历史数据
    DEFAULT_LIMIT = 99999

    # 增量窗口阈值: 超过此天数走东财全量补齐 (避免腾讯/新浪单次数据上限)
    INC_FULL_REFILL_DAYS = 90

    def __init__(self):
        self.client = get_eastmoney_client()
        self.repo = MongoRepository(KLineEntity)
        settings = get_settings()
        # 增量主源 + 回退链: tencent → eastmoney → sina (env 驱动)
        self._aggregator = build_aggregator(
            primary=settings.kline_primary,
            fallbacks=settings.kline_fallbacks.split(","),
        )
        # 全量主源 + 回退链: eastmoney → sina → tencent
        # 全量抓取覆盖历史最全, 东财字段最完整
        self._full_aggregator = build_aggregator(
            primary="eastmoney",
            fallbacks=["sina", "tencent"],
        )

    def market_code(self, secucode: str) -> int | None:
        return spider.market(secucode)

    def _secid_to_symbol(self, market: int, code: str) -> str:
        """1.510500 -> 'sh510500'; 0.159915 -> 'sz159915'."""
        prefix = {1: "sh", 0: "sz", 2: "bj"}.get(market, "")
        return f"{prefix}{code}" if prefix else code

    async def spider_kline_data(
        self,
        code: str,
        market: int | None,
        name: str | None = None,
    ) -> KLineEntity | None:
        if market is None:
            return None
        # 反爬随机延时 1~2 秒
        await asyncio.sleep(random.uniform(1.0, 2.0))

        # HK 市场 (market=116) 仅有东财支持, 不走聚合链
        if market == 116:
            entity = await self._fetch_eastmoney_direct(code, market)
            if entity and name and not entity.name:
                entity.name = name
            return entity

        # 1) 检查数据库中是否已有历史数据
        existing = await self.repo.find_by_id(code)
        existing_klines = existing.klines if existing else None
        last_date = self._last_kline_date(existing_klines)
        symbol = self._secid_to_symbol(market, code)

        if last_date:
            # 2) 已有历史 → 增量拉取 last_date 之后的 K 线
            #    计算从 last_date 到今天的日历天数
            limit = self._incremental_limit(last_date)
            # 增量窗口 > 90 天 → 走东财全量补齐
            # (腾讯/新浪接口单次上限 ~640/3248, 超过会返回空)
            if limit > self.INC_FULL_REFILL_DAYS:
                result = await self._full_aggregator.fetch(
                    symbol, PERIOD.DAY, FQT.QFQ, limit=self.DEFAULT_LIMIT,
                )
                if not result.rows:
                    self._log_incremental_no_data(code, last_date, limit, result)
                    return existing
                new_entities = self._rows_to_entities(result.rows)
                merged = self._merge_klines(existing_klines, new_entities)
                final_name = name or (existing.name if existing else None)
                entity = KLineEntity(code=code, name=final_name, klines=merged)
                # 路径标签: 区分东财直接 / 链式 fallback
                full_path = (
                    "incremental-full-EM" if not result.fell_back
                    else "incremental-full-chain"
                )
                new_count = len([r for r in result.rows if r.date > last_date])
                print(
                    f"[kline] {full_path} code={code} +{new_count} rows "
                    f"(last={last_date} → {merged[0].date if merged else '?'}) "
                    f"source={result.source.value if result.source else 'none'}",
                    flush=True,
                )
                return entity
            # 增量窗口 <= 90 天 → 走主链聚合器 (默认腾讯主源)
            result = await self._aggregator.fetch(
                symbol, PERIOD.DAY, FQT.QFQ, limit,
            )
            if not result.rows:
                if limit <= 0:
                    pass  # 数据已是最新，无需拉取
                else:
                    self._log_incremental_no_data(code, last_date, limit, result)
                return existing
            new_rows = [r for r in result.rows if r.date > last_date]
            if not new_rows:
                # 抓到了 rows 但都在 last_date 之前 — 增量窗口错位, 详细诊断
                self._log_incremental_window_mismatch(
                    code, last_date, limit, result,
                )
                return existing
            new_entities = self._rows_to_entities(new_rows)
            # 增量路径: 防止腾讯 6 字段覆盖已有的 11 字段
            merged = self._merge_klines(existing_klines, new_entities, prefer="existing")
            # name: 调用方传入 > DB 旧记录
            final_name = name or (existing.name if existing else None)
            entity = KLineEntity(code=code, name=final_name, klines=merged)
            # 路径标签: 区分主源成功 / 链式 fallback
            incr_path = (
                "incremental-primary" if not result.fell_back
                else "incremental-chain-fallback"
            )
            print(
                f"[kline] {incr_path} code={code} +{len(new_entities)} rows "
                f"(last={last_date} → {merged[0].date if merged else '?'}) "
                f"source={result.source.value if result.source else 'none'}",
                flush=True,
            )
            return entity

        # 3) 无历史 → 全量拉取 (东财优先, 覆盖历史最全)
        result = await self._full_aggregator.fetch(
            symbol=symbol, period=PERIOD.DAY, fqt=FQT.QFQ, limit=self.DEFAULT_LIMIT,
        )
        if not result.rows:
            print(f"[kline] full no data code={code} source={result.source} "
                  f"error={result.error}", flush=True)
            return None
        # 路径标签 (2026-08-26 改造): 区分东财直接 / 主链 fallback
        full_path = (
            "full-EM-direct"
            if result.source and result.source.value == "eastmoney" and not result.fell_back
            else "full-chain-fallback"
        )
        print(
            f"[kline] {full_path} code={code} "
            f"source={result.source.value if result.source else 'none'} "
            f"rows={len(result.rows)} first={result.rows[0].date} "
            f"last={result.rows[-1].date}",
            flush=True,
        )
        klines = self._rows_to_entities(result.rows)
        return KLineEntity(code=code, name=name, klines=klines)

    async def refresh_kline_data(
        self,
        code: str,
        market: int | None,
        name: str | None = None,
    ) -> KLineEntity | None:
        """强制全量重抓：删除 k_line 中该 code 的旧数据后从 Eastmoney 全量拉取并落库。

        用于修复历史区间内的坏数据（如 open/vol/amount 全为 0 的条目），
        普通 spider_kline_data 在已有数据时只做增量（last_date 之后），
        不会覆盖已存在的历史条目。
        """
        if not code:
            return None
        if market is None:
            return None
        # 1) 记录旧 name (删除后 spider_kline_data 无 existing, 避免 name 丢失)
        existing = await self.repo.find_by_id(code)
        if name is None and existing and existing.name:
            name = existing.name
        # 2) 删旧 doc
        try:
            await self.repo.delete_by_id(code)
        except Exception as exc:
            print(f"[kline/refresh] delete existing failed code={code}: {exc}", flush=True)
        # 3) 调 spider_kline_data，无 existing → 走全量分支（_full_aggregator Eastmoney）
        entity = await self.spider_kline_data(code, market, name)
        if entity is None or not entity.klines:
            print(f"[kline/refresh] full fetch returned empty code={code}", flush=True)
            return None
        # 3) 落库
        await self.save_mongodb(entity)
        print(
            f"[kline/refresh] done code={code} count={len(entity.klines)} "
            f"first={entity.klines[0].date} last={entity.klines[-1].date}",
            flush=True,
        )
        return entity

    def _last_kline_date(self, klines: List[KLineDataEntity] | None) -> str | None:
        """获取已有 K 线的最大日期 (YYYY-MM-DD)."""
        if not klines:
            return None
        dates = [k.date for k in klines if k.date]
        if not dates:
            return None
        return max(dates)

    def _incremental_limit(self, last_date: str) -> int:
        """从 last_date 到今天的日历天数."""
        try:
            dt = datetime.strptime(last_date[:10], "%Y-%m-%d").date()
            return (date.today() - dt).days
        except (ValueError, TypeError):
            return 120

    # ------------------------------------------------------------------ #
    # 增量抓取诊断日志 (新增 2026-08-21)
    # ------------------------------------------------------------------ #
    def _log_incremental_no_data(self, code, last_date, limit, result) -> None:
        """增量抓取返回 0 行 — 详细诊断: 哪个源失败, 为什么失败."""
        source_info = (
            f"source={result.source.value if result.source else 'NONE'} "
            f"error={result.error}"
        )
        chain_summary = self._format_chain_results(result.chain_results)
        print(
            f"[kline] incremental no-data code={code} last_db_date={last_date} "
            f"limit={limit} {source_info}\n"
            f"  → chain: {chain_summary}",
            flush=True,
        )

    def _log_incremental_window_mismatch(self, code, last_date, limit, result) -> None:
        """增量抓取有 rows 但都 <= last_date — 窗口错位诊断."""
        resp_first = result.rows[0].date if result.rows else "?"
        resp_last = result.rows[-1].date if result.rows else "?"
        source_info = (
            f"source={result.source.value if result.source else 'NONE'}"
        )
        print(
            f"[kline] incremental window-mismatch code={code} "
            f"db_last={last_date} resp_range=[{resp_first}..{resp_last}] "
            f"limit={limit} {source_info}\n"
            f"  → 增量返回的日期全部 <= DB 最后日期, 数据未实际推进\n"
            f"  → 可能原因: 1)源端数据延迟 2)limit 不够 3)fallback 链全空但被首个非空源拦截",
            flush=True,
        )

    @staticmethod
    def _format_chain_results(chain_results) -> str:
        """格式化每个源的尝试结果, 例: 'eastmoney=ok:0;ths=error:Timeout;...'."""
        if not chain_results:
            return "<no chain info>"
        parts = []
        for source_name, status, row_count, err in chain_results:
            if status == "ok":
                parts.append(f"{source_name}=ok:{row_count}")
            elif status == "empty":
                parts.append(f"{source_name}=empty")
            else:  # error
                # err 截短到 80 字符避免日志过长
                short_err = (err or "")[:80]
                parts.append(f"{source_name}=error:{short_err}")
        return "; ".join(parts)

    def _merge_klines(
        self,
        existing: List[KLineDataEntity] | None,
        new_rows: List[KLineDataEntity],
        prefer: str = "new",
    ) -> List[KLineDataEntity]:
        """按日期去重合并.

        prefer="new" (默认): 新数据覆盖同日期旧数据 — 全量补齐时用 (东财 11 字段优先).
        prefer="existing": 旧数据保留, 新数据仅填补缺失日期 — 增量抓取时用
                          (防止腾讯 6 字段覆盖已有的 11 字段).
        按日期降序排列.
        """
        by_date: dict[str, KLineDataEntity] = {}
        if prefer == "existing":
            # existing 优先: 先填 new_rows, 再用 existing 覆盖同名 key
            for k in new_rows:
                if k.date:
                    by_date[k.date] = k
            for k in existing or []:
                if k.date:
                    by_date[k.date] = k
        else:
            # new 优先 (默认): 先填 existing, 再用 new_rows 覆盖
            for k in existing or []:
                if k.date:
                    by_date[k.date] = k
            for k in new_rows:
                if k.date:
                    by_date[k.date] = k
        merged = list(by_date.values())
        merged.sort(key=lambda x: x.date or "", reverse=True)
        return merged

    async def _fetch_eastmoney_direct(self, code: str, market: int) -> KLineEntity | None:
        """HK 等特殊市场: 直接走东财 (其他源不支持)."""
        secid = f"{market}.{code}"
        try:
            text = await self.client.kline(
                self.fields1, self.fields2, self.beg, self.end, secid, self.klt, self.fqt,
            )
        except httpx.HTTPError as exc:
            print(f"[kline] eastmoney HK request failed secid={secid} err={exc}", flush=True)
            return None
        if not text:
            print(f"[kline] eastmoney HK empty secid={secid}", flush=True)
            return None
        text = self._extract_json(text)
        try:
            data = transform.normalize_keys(__import__("json").loads(text))
        except Exception as exc:
            print(f"[kline] eastmoney HK json error secid={secid} err={exc}", flush=True)
            return None
        d = data.get("data") if isinstance(data, dict) else None
        if not d or not d.get("klines"):
            print(f"[kline] eastmoney HK no klines secid={secid}", flush=True)
            return None
        klines = self._convert_kline(d.get("klines"))
        return KLineEntity(code=code, name=d.get("name"), klines=klines)

    def _rows_to_entities(self, rows: list[KLineRow]) -> List[KLineDataEntity]:
        result: List[KLineDataEntity] = []
        for r in rows:
            entity = KLineDataEntity(
                date=r.date,
                open=self._fmt(r.open),
                close=self._fmt(r.close),
                higher=self._fmt(r.high),
                lower=self._fmt(r.low),
                # KLineRow.volume 统一为"股"; entity.vol 与东财路径一致用"手" (1手=100股)
                vol=str(r.volume // 100) if r.volume else "0",
            )
            if r.amount is not None:
                entity.amount = self._fmt(r.amount)
            if r.amplitude is not None:
                entity.amplitude = self._fmt(r.amplitude)
            if r.amount_of_increase is not None:
                entity.amountOfIncrease = self._fmt(r.amount_of_increase)
            if r.up_down_amount is not None:
                entity.UpDownAmount = self._fmt(r.up_down_amount)
            if r.turnover is not None:
                entity.turnOver = self._fmt(r.turnover)
            # amountOfAverage: amount / vol (与原 _convert_kline 逻辑一致)
            try:
                amt = float(entity.amount or 0)
                vol = float(entity.vol or 0)
                if vol:
                    avg = Decimal(str(amt / vol))
                    entity.amountOfAverage = str(
                        (avg / Decimal(100)).quantize(Decimal("0.000"), rounding=ROUND_HALF_UP)
                    )
                else:
                    entity.amountOfAverage = "0.000"
            except Exception:
                entity.amountOfAverage = "0.000"
            result.append(entity)
        result.sort(key=lambda x: x.date or "", reverse=True)
        return result

    @staticmethod
    def _fmt(v: float) -> str:
        if v is None:
            return ""
        return f"{v:g}"

    def _extract_json(self, text: str) -> str:
        """防御性剥离 JSONP callback 包装"""
        if not text:
            return ""
        text = text.strip()
        if text.startswith(("jQuery", "(")):
            match = re.search(r"\((\{.*\})\)$", text, re.DOTALL)
            if match:
                return match.group(1)
        return text

    async def save_mongodb(self, kline_entity: KLineEntity | None) -> None:
        if kline_entity is None:
            return
        kline_entity.updatedAt = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        await self.repo.save(kline_entity)

    async def kline_by_sec_code(
        self,
        sec_code: str,
        start: str | None = None,
        end: str | None = None,
        days: int | None = None,
    ) -> KLineEntity | None:
        return await self.kline_by_sec_code_with_range(sec_code, start=start, end=end, days=days)

    async def kline_by_sec_code_with_range(
        self,
        sec_code: str,
        start: str | None = None,
        end: str | None = None,
        days: int | None = None,
    ) -> KLineEntity | None:
        entity = await self.repo.find_by_id(sec_code)
        if not entity or not entity.klines:
            return entity

        start_date, end_date = self._resolve_date_range(start, end, days)
        if not start_date and not end_date:
            return entity

        filtered: List[KLineDataEntity] = []
        for k in entity.klines:
            if not k.date:
                continue
            k_date = self._parse_date(k.date)
            if not k_date:
                continue
            if start_date and k_date < start_date:
                continue
            if end_date and k_date > end_date:
                continue
            filtered.append(k)

        entity.klines = filtered
        return entity

    def _resolve_date_range(
        self, start: str | None, end: str | None, days: int | None
    ) -> tuple[date | None, date | None]:
        start_date = self._parse_date(start) if start else None
        end_date = self._parse_date(end) if end else None
        if days and days > 0 and not (start_date or end_date):
            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)
        return start_date, end_date

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        val = value.strip()
        if not val:
            return None
        val = val[:10]
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
        return None

    def _convert_kline(self, klines: List[str]) -> List[KLineDataEntity]:
        title_map = spider.convert_dic_map(spider.KLINE_TITLE)
        result: List[KLineDataEntity] = []
        for line in klines:
            parts = line.split(",")
            entity = KLineDataEntity()
            for i, s in enumerate(parts):
                field_name = title_map.get(str(i + 1))
                if field_name:
                    setattr(entity, field_name, s)
            avg = num_utils.devide(getattr(entity, "amount", "0"), getattr(entity, "vol", "0"))
            entity.amountOfAverage = str((avg / Decimal(100)).quantize(Decimal("0.000"), rounding=ROUND_HALF_UP))
            result.append(entity)
        result.sort(key=lambda x: x.date, reverse=True)
        return result

    @dataclass(frozen=True)
    class GapInfo:
        """K 线窗口断层信息.

        Attributes:
            start: 窗口左边界 = previous_years(mapper_window_end, 1)
            end: 窗口右边界 = mapper_window_end
            span_days: 窗口跨度 (日历天数) = (end - start).days
        """
        start: date
        end: date
        span_days: int

    @staticmethod
    def detect_gap_in_window(
        klines: list, mapper_window_end: date,
    ) -> "KLineService.GapInfo | None":
        """检测 mapper 关心的季度窗口是否断层.

        复用 quarter_of_kline 的窗口生成 (左边界=previous_years(end, 1)),
        确保与 mapper.creat 内部窗口严格一致.
        窗口内 K 线 < 5 条 → 视为断层, 返 GapInfo; 否则返 None.

        Args:
            klines: 当前 K 线数组
            mapper_window_end: quarter_of_kline 的 start_date (季度末日期)

        Returns:
            GapInfo(start, end, span_days) 或 None
        """
        in_window = quarter_of_kline(klines, mapper_window_end)
        if len(in_window) >= 5:
            return None
        window_start = date_utils.previous_years(mapper_window_end, 1)
        return KLineService.GapInfo(
            start=window_start,
            end=mapper_window_end,
            span_days=(mapper_window_end - window_start).days,
        )

    async def backfill_kline_window(
        self,
        code: str,
        market: int | None,
        start_date: date,
        end_date: date,
        name: str | None = None,
    ) -> KLineEntity | None:
        """定向补抓指定区间 K 线, 合并入 DB.

        用于 ROE 估值时检测到窗口内 K 线缺失的兜底补抓.
        复用主链聚合器 (THS→EM/sina/tencent 回退), 用 limit 反推天数, 再切片到目标区间.

        Args:
            code: 股票代码 (如 "300122")
            market: 市场代码 (0=深, 1=沪, 2=北, 116=港)
            start_date: 补抓起点 (含)
            end_date: 补抓终点 (含)
            name: 股票名称 (缺省从 DB 现有记录取)

        Returns:
            更新后的 KLineEntity (含合并后的 klines), 或 None (拉取失败/切片为空)
        """
        if market is None or end_date < start_date:
            return None

        # 1) 用主链聚合器拉"近期"足够多
        days_back = (date.today() - start_date).days + 30
        symbol = self._secid_to_symbol(market, code)
        result = await self._aggregator.fetch(
            symbol, PERIOD.DAY, FQT.QFQ, limit=days_back,
        )
        if not result.rows:
            return None

        # 2) 切片到 [start_date, end_date]
        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()
        target_rows = [
            r for r in result.rows
            if start_iso <= r.date <= end_iso
        ]
        if not target_rows:
            return None

        # 3) 与现有 klines 合并去重 (同日期新覆盖旧)
        existing = await self.repo.find_by_id(code)
        if name is None and existing and existing.name:
            name = existing.name
        existing_klines = existing.klines if existing else []
        new_entities = self._rows_to_entities(target_rows)
        merged = self._merge_klines(existing_klines, new_entities)

        # 4) 落库
        entity = KLineEntity(code=code, name=name, klines=merged)
        await self.save_mongodb(entity)

        print(
            f"[kline/backfill-ths] code={code} window=[{start_date},{end_date}] "
            f"new={len(target_rows)} merged_total={len(merged)} "
            f"source={result.source.value if result.source else 'none'}",
            flush=True,
        )
        return entity
