"""FreshQuant 实战手记 — 本地通达信离线 K 线 (FreshQuant 链路).

入口:
    fetch_local_day(code, fq='qfq') -> pd.DataFrame
    list_codes() -> list[str]
    invalidate_gbbq_cache()       跨交易日主动清缓存

设计契约 (见 fetcher.py 顶部):
- 复权失败硬报错, 不静默降级 (回测污染源).
- tdx_home 三级 fallback: 入参 > FIN_TDX_HOME > TDX_HOME > C:\\zd_zxzq_gm.
- gbbq 私有格式需 pytdx / GbbqXdxrReader; 调用方 qfq/hfq 模式前需先确认.

未完成项 (2026-09-17):
- gbbq 事件精确解析 (需集成第三方解析器, 当前 .map 索引已通).
- 复权公式实现依赖 gbbq 事件, 当前在 fetcher 层硬报错.
"""
from app.services.tdx_offline.fetcher import (
    fetch_local_day,
    invalidate_gbbq_cache,
    list_codes,
)

__all__ = ["fetch_local_day", "list_codes", "invalidate_gbbq_cache"]