"""KLine adapter package: unified multi-source K-line fetcher."""
from app.clients.kline.aggregator import KLineAggregator
from app.clients.kline.eastmoney_adapter import EastmoneyAdapter
from app.clients.kline.factory import build_aggregator
from app.clients.kline.sina_adapter import SinaAdapter
from app.clients.kline.tencent_adapter import TencentAdapter
from app.clients.kline.types import FQT, PERIOD, SOURCE, FetchResult, KLineRow

__all__ = [
    "EastmoneyAdapter",
    "FQT",
    "FetchResult",
    "KLineAggregator",
    "KLineRow",
    "PERIOD",
    "SOURCE",
    "SinaAdapter",
    "TencentAdapter",
    "build_aggregator",
]