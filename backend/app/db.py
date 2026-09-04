from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings

settings = get_settings()

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_db():
    return get_client()[settings.mongo_db]


async def ensure_indexes() -> None:
    db = get_db()
    # ETF 查询主要走 secCode，创建索引避免全表扫描
    await db["etf"].create_index("secCode")
    # 方便按日期顺序读取（前端常需要按日期展示）
    await db["etf"].create_index([("secCode", 1), ("statDate", -1)])
    # k_line 以 _id 查询，Mongo 默认已建 _id 索引，这里显式声明便于部署一致性
    await db["k_line"].create_index("_id")
    # sec_code 下拉搜索：按上市状态 + 代码 / 拼音首字母 检索
    await db["sec_code"].create_index([("listingState", 1), ("securityCode", 1)])
    await db["sec_code"].create_index([("listingState", 1), ("securityPinyin", 1)])
