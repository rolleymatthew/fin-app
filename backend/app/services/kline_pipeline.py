"""K 线 Hybrid 编排器: TDX 优先 + 网络补 gap + 纯网络兜底.

设计契约 (见 docs/superpowers/specs/2026-09-29-kline-hybrid-pipeline-design.md):
    Phase 1: TdxAdapter.fetch() — 读本地 .day, 失败降级
    Phase 2: 网络链 (默认 sina,tencent,eastmoney) 补 gap
    Phase 3: 纯网络链 (kline_primary + kline_fallbacks) — TDX 不可用时兜底
    Phase 4: 合并 + 切片 [:limit]
"""
import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime

from app.clients.kline.factory import build_aggregator
from app.clients.kline.tdx_adapter import TdxAdapter
from app.clients.kline.types import FQT, PERIOD, KLineRow


@dataclass
class HybridFetchResult:
    """Hybrid 编排器顶层返回. 不复用 FetchResult (后者是单源链设计)."""
    rows: list[KLineRow] = field(default_factory=list)            # 合并后, 降序
    sources_used: list[str] = field(default_factory=list)
    tdx_rows_count: int = 0
    network_rows_count: int = 0
    gap_days: int | None = None
    network_attempted: bool = False
    network_error: str | None = None
    tdx_available: bool = True


class KLinePipeline:
    """TDX-first + 网络补 gap 编排器."""

    def __init__(self, network_chain_cfg: list[str], fallback_chain_cfg: list[str]):
        # 网络补 gap 链 — 默认 sina,tencent,eastmoney
        self._gap_chain = build_aggregator(
            primary=network_chain_cfg[0],
            fallbacks=network_chain_cfg[1:],
        )
        # TDX 不可用时的纯网络兜底链 — 默认 tencent,eastmoney,sina
        self._pure_chain = build_aggregator(
            primary=fallback_chain_cfg[0],
            fallbacks=fallback_chain_cfg[1:],
        )
        self._tdx_adapter = TdxAdapter()

    async def fetch_hybrid(
        self,
        code: str,
        market: int | None,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> HybridFetchResult:
        # ---- Phase 1: TDX 探测 ----
        tdx_rows, tdx_available, tdx_err = await self._phase1_tdx(symbol, period, fqt, limit)
        if tdx_err:
            print(f"[kline/pipeline] phase1=tdx error={tdx_err}", flush=True)
        print(
            f"[kline/pipeline] phase1=tdx rows={len(tdx_rows)} "
            f"status={'ok' if tdx_available else 'unavailable'}",
            flush=True,
        )

        # ---- Phase 3 (TDX 不可用时) ----
        if not tdx_available:
            return await self._run_pure_network(symbol, period, fqt, limit)

        # ---- Phase 2 (TDX 有数据) ----
        if not tdx_rows:
            # TDX 存在但全空 — 退回 Phase 3
            print(
                "[kline/pipeline] phase1=tdx rows=0 status=empty → phase3=pure-network",
                flush=True,
            )
            return await self._run_pure_network(symbol, period, fqt, limit)

        tdx_max_date = tdx_rows[0].date  # 降序
        try:
            tdx_last = datetime.strptime(tdx_max_date[:10], "%Y-%m-%d").date()
            gap_days = (date.today() - tdx_last).days
        except ValueError as exc:
            print(
                f"[kline/pipeline] phase2 gap 解析失败 tdx_max={tdx_max_date!r}: {exc}",
                flush=True,
            )
            gap_days = 0

        network_rows: list[KLineRow] = []
        network_error: str | None = None
        network_attempted = gap_days > 0
        network_source_name: str | None = None

        if gap_days > 0:
            chain_names = ",".join(
                [
                    self._gap_chain.primary.source.value,
                    *(a.source.value for a in self._gap_chain.fallbacks),
                ],
            )
            print(
                f"[kline/pipeline] phase2 chain={chain_names} attempt=yes",
                flush=True,
            )
            gap_result = await self._gap_chain.fetch(symbol, period, fqt,
                                                            gap_days + 5)
            if gap_result.rows:
                network_rows = gap_result.rows
                network_source_name = (gap_result.source.value
                                       if gap_result.source else "unknown")
            else:
                network_error = gap_result.error or "all sources empty"
                print(
                    f"[kline/pipeline] phase2 all empty, fallback to tdx rows={len(tdx_rows)}",
                    flush=True,
                )
        else:
            print("[kline/pipeline] phase2 skipped (gap=0)", flush=True)

        # ---- Phase 4: 合并 + 切片 ----
        sources_used: list[str] = ["tdx"]
        if network_source_name:
            sources_used.append(network_source_name)
        by_date: dict[str, KLineRow] = {r.date: r for r in tdx_rows}
        for r in network_rows:
            by_date[r.date] = r  # 网络覆盖同日 TDX (EM11 字段 > TDX 6 字段)
        merged = sorted(by_date.values(), key=lambda r: r.date, reverse=True)[:limit]
        print(
            f"[kline/pipeline] merged total={len(merged)} sources={sources_used} limit={limit}",
            flush=True,
        )

        return HybridFetchResult(
            rows=merged,
            sources_used=sources_used,
            tdx_rows_count=len(tdx_rows),
            network_rows_count=len(network_rows),
            gap_days=gap_days,
            network_attempted=network_attempted,
            network_error=network_error,
            tdx_available=True,
        )

    async def fetch_pure_network(
        self,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> HybridFetchResult:
        """跳过 TDX, 直接走纯网络链 (供 kline_service 增量窗口错位时使用)."""
        return await self._run_pure_network(symbol, period, fqt, limit)

    async def _run_pure_network(
        self,
        symbol: str,
        period: PERIOD,
        fqt: FQT,
        limit: int,
    ) -> HybridFetchResult:
        result = await self._pure_chain.fetch(symbol, period, fqt, limit)
        sources_used: list[str] = []
        if result.source:
            sources_used.append(result.source.value)
        return HybridFetchResult(
            rows=result.rows[:limit],
            sources_used=sources_used,
            tdx_rows_count=0,
            network_rows_count=len(result.rows),
            gap_days=None,
            network_attempted=True,
            network_error=result.error,
            tdx_available=False,
        )

    async def _phase1_tdx(
        self, symbol: str, period: PERIOD, fqt: FQT, limit: int,
    ) -> tuple[list[KLineRow], bool, str | None]:
        try:
            rows = await self._tdx_adapter.fetch(symbol, period, fqt, limit)
        except FileNotFoundError:
            return [], False, None
        except Exception as exc:
            return [], False, f"{type(exc).__name__}: {exc}"
        return rows, True, None

    async def aclose(self) -> None:
        await asyncio.gather(
            self._gap_chain.aclose(),
            self._pure_chain.aclose(),
            self._tdx_adapter.aclose(),
            return_exceptions=True,
        )
