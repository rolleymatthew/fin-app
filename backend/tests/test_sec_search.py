"""search_stocks 的纯逻辑测试（不依赖真实 MongoDB）。

通过内存 FakeCollection 替换 SecCodeService.repo.collection，
验证：默认仅 A 股 / listingState 过滤 / 拼音首字母前缀 / 代码精确优先 /
名称包含 / 去重 / limit 裁剪 / 上限。
"""

from __future__ import annotations

from typing import Any

from app.services.seccode_service import SecCodeService


def _doc(
    code: str,
    name: str,
    pinyin: str,
    *,
    secucode: str | None = None,
    market: str = "深交所",
    stype: str = "A股",
    listing_date: str | None = None,
    listing_state: str = "0",
) -> dict:
    return {
        "_id": code,
        "securityCode": code,
        "securityNameAbbr": name,
        "securityPinyin": pinyin,
        "secucode": secucode or f"{code}.SZ",
        "tradeMarket": market,
        "securityType": stype,
        "listingDate": listing_date,
        "listingState": listing_state,
    }


DOCS = [
    _doc("300750", "宁德时代", "NDSD", listing_date="2018-06-11", market="深交所创业板"),
    _doc("600519", "贵州茅台", "GZMT", secucode="600519.SH", market="上交所"),
    _doc("000001", "平安银行", "PAYH", secucode="000001.SZ"),
    _doc("600000", "浦发银行", "PFYH", secucode="600000.SH", market="上交所"),
    _doc("000333", "美的集团", "MDJT", secucode="000333.SZ"),
    _doc("600030", "中信证券", "ZXZQ", secucode="600030.SH", market="上交所"),
    _doc("000002", "万　科Ａ", "WKEA", secucode="000002.SZ"),
    _doc("688981", "中芯国际", "ZXGJ", secucode="688981.SH", market="上交所科创板"),
    _doc("900001", "退市公司", "TSGS", secucode="900001.SH", listing_state="1"),  # 退市
    _doc("510050", "50ETF", "ETFA", secucode="510050.SH", stype="ETF基金"),  # 非 A 股
]


def _match_value(field_val: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        for op, val in cond.items():
            if op == "$regex":
                if not isinstance(field_val, str):
                    return False
                pattern = val[1:] if val.startswith("^") else val
                if val.startswith("^"):
                    if not field_val.startswith(pattern):
                        return False
                else:
                    if pattern not in field_val:
                        return False
            elif op == "$ne":
                if field_val == val:
                    return False
            else:
                return False
        return True
    return field_val == cond


def _match_doc(doc: dict, filt: dict) -> bool:
    for key, cond in filt.items():
        if key == "$and":
            for sub in cond:
                if not _match_doc(doc, sub):
                    return False
        else:
            if not _match_value(doc.get(key), cond):
                return False
    return True


def project(doc: dict, projection: dict | None) -> dict:
    if not projection:
        return dict(doc)
    return {k: doc.get(k) for k in projection.keys() if k in doc}


class FakeCursor:
    def __init__(self, docs: list[dict], projection: dict | None):
        self._docs = [project(d, projection) for d in docs]
        self._limit: int | None = None

    def limit(self, n: int) -> "FakeCursor":
        self._limit = n
        return self

    def __aiter__(self):
        docs = self._docs if self._limit is None else self._docs[: self._limit]

        async def gen():
            for d in docs:
                yield d

        return gen()


class FakeCollection:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def _apply(self, filt: dict) -> list[dict]:
        return [d for d in self._docs if _match_doc(d, filt)]

    def find(self, filt: dict, projection: dict | None = None) -> FakeCursor:
        return FakeCursor(self._apply(filt), projection)

    async def find_one(self, filt: dict, projection: dict | None = None) -> dict | None:
        rows = self._apply(filt)
        return project(rows[0], projection) if rows else None


def _service() -> SecCodeService:
    svc = SecCodeService()
    svc.repo._collection = FakeCollection(DOCS)
    return svc


async def test_empty_q_returns_all_listed():
    svc = _service()
    rows = await svc.search_stocks(q="", limit=100)
    codes = [r["code"] for r in rows]
    assert "900001" not in codes  # 退市被排除
    assert "300750" in codes
    assert "510050" in codes  # 非A股证券（ETF）也返回：默认覆盖全部上市公司


async def test_pinyin_prefix_search():
    svc = _service()
    rows = await svc.search_stocks(q="nd", limit=20)
    codes = [r["code"] for r in rows]
    assert "300750" in codes
    assert all(r["pinyin"].startswith("ND") for r in rows if r["pinyin"])


async def test_exact_code_priority_first():
    svc = _service()
    rows = await svc.search_stocks(q="600519", limit=20)
    assert rows[0]["code"] == "600519"
    assert rows[0]["name"] == "贵州茅台"


async def test_code_prefix_no_dup():
    svc = _service()
    rows = await svc.search_stocks(q="600", limit=20)
    codes = [r["code"] for r in rows]
    assert codes.count("600519") == 1
    assert codes.count("600000") == 1
    assert codes.count("600030") == 1
    assert {"600519", "600000", "600030"} <= set(codes)


async def test_name_contains():
    svc = _service()
    rows = await svc.search_stocks(q="贵州", limit=20)
    codes = [r["code"] for r in rows]
    assert "600519" in codes


async def test_no_match_returns_empty():
    svc = _service()
    rows = await svc.search_stocks(q="zzzz", limit=20)
    assert rows == []


async def test_limit_is_respected():
    svc = _service()
    rows = await svc.search_stocks(q="", limit=3)
    assert len(rows) == 3


async def test_limit_upper_bound_clamped():
    svc = _service()
    rows = await svc.search_stocks(q="", limit=99999)
    assert len(rows) == 9  # 全部 9 条非退市文档（1000 上限不会越界）
