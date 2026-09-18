"""通达信 vipdata 全量日线包下载器.

入口 (Task 5 之后可用):
    TdxDailyFetcher(...).run_sync()

子模块 (Task 2+ 起即可单独 import):
    from app.services.tdx_daily_fetcher.meta import parse_meta_info
    from app.services.tdx_daily_fetcher.exceptions import MetaParseError
    from app.services.tdx_daily_fetcher.constants import DOWNLOAD_URL
"""