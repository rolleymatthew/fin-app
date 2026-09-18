"""通达信 vipdata 全量日线包下载器.

入口 (后续 task 实现):
    TdxDailyFetcher(target_dir=...).run_sync()
    TdxDailyFetcher(target_dir=...).run()  # async, 写入 task state
"""
from app.services.tdx_daily_fetcher.fetcher import (
    ACTIVE_STATES,
    TaskStatus,
    TdxDailyFetcher,
)

__all__ = ["TdxDailyFetcher", "TaskStatus", "ACTIVE_STATES"]