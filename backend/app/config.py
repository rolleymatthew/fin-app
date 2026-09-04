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
    # 默认顺序: eastmoney → ths → sina → tencent
    # 改 eastmoney 为默认主源 (2026-08-21):
    #   - THS 增量抓取偶尔返回日期不在期望窗口的行, 但聚合器"first-non-empty"会误判成功
    #   - 东财 11 字段全、增量窗口精确, 但需要 Cookie
    kline_primary: str = Field(
        default="eastmoney",
        validation_alias=AliasChoices("FIN_KLINE_PRIMARY", "KLINE_PRIMARY"),
    )
    kline_fallbacks: str = Field(
        default="ths,sina,tencent",
        validation_alias=AliasChoices("FIN_KLINE_FALLBACKS", "KLINE_FALLBACKS"),
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.excel_dir).mkdir(parents=True, exist_ok=True)
    return settings
