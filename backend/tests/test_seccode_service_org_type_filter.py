"""search_stocks 的 org_type_code 过滤测试（不依赖真实 MongoDB）。

验证：新增的 org_type_code 参数：
- 不传（None）→ 行为等价于旧版，返回所有上市股票
- 传 "3" → 仅返回银行股（orgTypeCode == "3"）
- 传其它类型码 → 仅返回对应公司类型
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
    org_type_code: str | None = None,
    listing_state: str = "0",
) -> dict:
    return {
        "_id": code,
        "securityCode": code,
        "securityNameAbbr": name,
        "securityPinyin": pinyin,
        "secucode": secucode or f"{code}.SZ",
        "tradeMarket": "深交所" if code.startswith(("0", "3")) else "上交所",
        "securityType": "A股",
        "listingDate": None,
        "listingState": listing_state,
        "orgTypeCode": org_type_code,
    }


DOCS = [
    _doc("000001", "平安银行", "PAYH", org_type_code="3"),       # 银行
    _doc("600036", "招商银行", "ZSYH", secucode="600036.SH", org_type_code="3"),
    _doc("601398", "工商银行", "GSYH", secucode="601398.SH", org_type_code="3"),
    _doc("600000", "浦发银行", "PFYH", secucode="600000.SH", org_type_code="3"),
    _doc("601628", "中国人寿", "ZRSH", secucode="601628.SH", org_type_code="2"),  # 保险
    _doc("600030", "中信证券", "ZXZQ", secucode="600030.SH", org_type_code="1"),  # 证券
    _doc("000002", "万　科Ａ", "WKEA", org_type_code="4"),       # 通用
    _doc("300750", "宁德时代", "NDSD", org_type_code="4"),       # 通用
    _doc(
        "900001",
        "退市银行",
        "TSYH",
        secucode="900001.SH",
        org_type_code="3",
        listing_state="1",
    ),  # 退市
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


async def test_default_org_type_code_returns_all():
    """不传 org_type_code 时，行为与旧版一致：返所有上市股票（含 银行/保险/证券/通用）。"""
    svc = _service()
    rows = await svc.search_stocks(q="", limit=100)
    codes = {r["code"] for r in rows}
    assert "900001" not in codes  # 退市排除
    assert {"000001", "600036", "601398", "600000", "601628", "600030", "000002", "300750"} <= codes


async def test_org_type_code_bank_only():
    """传 org_type_code='3' 时，仅返银行股。"""
    svc = _service()
    rows = await svc.search_stocks(q="", limit=100, org_type_code="3")
    codes = {r["code"] for r in rows}
    assert codes == {"000001", "600036", "601398", "600000"}
    assert "900001" not in codes  # 退市银行仍排除


async def test_org_type_code_bank_with_pinyin():
    """银行过滤 + pinyin 搜索联动。"""
    svc = _service()
    rows = await svc.search_stocks(q="zsyh", limit=20, org_type_code="3")
    codes = [r["code"] for r in rows]
    assert "600036" in codes
    assert "601628" not in codes  # 保险不在范围内


async def test_org_type_code_other_type():
    """传非银行类型码，返对应类型。"""
    svc = _service()
    rows = await svc.search_stocks(q="", limit=100, org_type_code="2")
    codes = {r["code"] for r in rows}
    assert codes == {"601628"}


async def test_org_type_code_universal():
    """org_type_code='4' 仅返通用公司。"""
    svc = _service()
    rows = await svc.search_stocks(q="", limit=100, org_type_code="4")
    codes = {r["code"] for r in rows}
    assert codes == {"000002", "300750"}


async def test_org_type_code_no_match():
    """过滤后无匹配返空列表。"""
    svc = _service()
    rows = await svc.search_stocks(q="", limit=100, org_type_code="9")
    assert rows == []