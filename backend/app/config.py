from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIN_", env_file=".env", extra="ignore")

    app_name: str = "prod"
    env: str = "prod"
    host: str = "0.0.0.0"
    port: int = 8080

    mongo_uri: str = "mongodb://127.0.0.1:27017/stock"
    mongo_db: str = "stock"

    log_level: str = "INFO"
    log_file: str = "./app.log"

    data_dir: str = "./data"
    excel_dir: str = "D:\\stock\\pyallinone"
    templates_dir: str = "./src/main/resources/templates"

    http_timeout: float = 30.0
    http_retries: int = 3
    http_retry_wait: float = 1.0

    use_finance_eastmoney_v2: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "USE_FINANCE_EASTMONEY_V2",
            "FIN_USE_FINANCE_EASTMONEY_V2",
        ),
    )

    # KLine 多源配置: 主源 + 回退链 (env: FIN_KLINE_PRIMARY / FIN_KLINE_FALLBACKS)
    # 增量场景默认顺序: tencent → eastmoney → sina (2026-09-02 改造: 移除 THS)
    #   - 腾讯 主源: 无需 Cookie, 反爬宽松, 字段 6 个 (缺 amount/turnover/振幅/涨跌幅/涨跌额)
    #   - 东财 兜底: 11 字段全, 增量窗口精确, 但需要 Cookie, 有反爬延时
    # 全量场景 (DB 无历史 或 last_date 距今 > 90 天) 仍硬编码走东财, 保证首次入库字段完整
    kline_primary: str = Field(
        default="tencent",
        validation_alias=AliasChoices("FIN_KLINE_PRIMARY", "KLINE_PRIMARY"),
    )
    kline_fallbacks: str = Field(
        default="eastmoney,sina",
        validation_alias=AliasChoices("FIN_KLINE_FALLBACKS", "KLINE_FALLBACKS"),
    )

    # SZSE ETF 日终 JSON 自动入库（豆包定时任务下载文件）
    etf_data_dir: str = "./data/etf_data"  # env: FIN_ETF_DATA_DIR
    etf_data_poll_seconds: int = 300      # env: FIN_ETF_DATA_POLL_SECONDS 默认 5 分钟
    etf_data_auto_import: bool = False    # env: FIN_ETF_DATA_AUTO_IMPORT 默认关闭

    # 本地通达信离线 K 线（FreshQuant 链路：vipdoc + gbbq，无需网络/数据库）
    # 解析顺序: FIN_TDX_HOME > TDX_HOME > 默认 D:\stock\data
    # (2026-09 改造: 接入 tdx_offline 服务, 离线复权日线)
    # Docker 场景: env 覆盖为 /app/data
    tdx_home: str = Field(
        default=r"D:\stock\data",
        validation_alias=AliasChoices("FIN_TDX_HOME", "TDX_HOME"),
    )

    # TDX vipdata 全量日线包下载目标目录 (zip + 解压 vipdoc/ 都在此)
    # Docker 场景: env 覆盖为 /app/data (与现有 D:\stock bind mount 对齐)
    tdx_data_dir: str = Field(
        default=r"D:\stock\data",
        description="通达信日线包根目录: hsjday.zip + vipdoc/ 都在此",
        validation_alias=AliasChoices("FIN_TDX_DATA_DIR", "TDX_DATA_DIR"),
    )
    tdx_download_url: str = Field(
        default="https://data.tdx.com.cn/vipdoc/hsjday.zip",
        validation_alias=AliasChoices("FIN_TDX_DOWNLOAD_URL", "TDX_DOWNLOAD_URL"),
    )
    tdx_meta_url: str = Field(
        default="https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js",
        validation_alias=AliasChoices("FIN_TDX_META_URL", "TDX_META_URL"),
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.excel_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.etf_data_dir).mkdir(parents=True, exist_ok=True)
    return settings
