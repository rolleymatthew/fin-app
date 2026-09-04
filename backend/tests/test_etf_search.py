"""EtfService.search_etfs 的纯逻辑测试（不依赖真实 MongoDB）。

通过内存 FakeCollection 替换 EtfService.collection（异步 motor 风格），
验证：空 q 返回所有 / 拼音首字母前缀 / 代码精确优先 / 代码前缀去重 /
名称包含 / 无匹配 / limit / 上限 / null q。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.etf_service import EtfService


def _doc(
    code: int,
    name: str,
    pinyin: str,
    *,
    etf_type: str = "单市",
    stat_date: str = "2026-08-05",
) -> dict:
    return {
        "_id": f"{code}{stat_date}",
        "secCode": code,
        "secName": name,
        "etfType": etf_type,
        "pinyin": pinyin,
        "statDate": stat_date,
    }


# 真实 ETF 典型样本
FIXTURE = [
    _doc(510050, "50ETF", "ETF", stat_date="2026-08-05"),
    _doc(510050, "50ETF", "ETF", stat_date="2026-08-04"),  # 重复 secCode，更早
    _doc(510300, "沪深300ETF", "HS300ETF"),
    _doc(510500, "500ETF", "500ETF"),
    _doc(511010, "国债ETF", "GZETF"),
    _doc(512100, "1000ETF", "1000ETF"),
    _doc(513100, "纳指ETF", "NZETF"),
    _doc(588000, "科创50ETF", "KC50ETF"),
    _doc(588080, "科创板50ETF", "KCB50ETF"),
    _doc(159915, "创业板ETF", "CYBETF"),
    _doc(159919, "沪深300ETF", "HS300ETF"),  # 与 510300 同名同拼音
    _doc(159995, "芯片ETF", "XPETF"),
]


class _Cursor:
    """模拟 motor 异步 cursor：支持 .sort().limit() 链式 + __aiter__。"""

    def __init__(self, docs: list[dict]):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        if args:
            spec = args[0]
            if isinstance(spec, str):
                direction = args[1] if len(args) > 1 else 1
                sort_spec = {spec: direction}
            else:
                sort_spec = spec
        else:
            sort_spec = kwargs
        self._docs = _apply_sort(self._docs, sort_spec)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d

        return gen()


def _apply_sort(docs: list[dict], sort_spec) -> list[dict]:
    items = list(sort_spec.items()) if isinstance(sort_spec, dict) else list(sort_spec)
    result = list(docs)
    for key, direction in reversed(items):
        reverse = direction == -1
        result = sorted(result, key=lambda d, k=key: _sort_safe(d.get(k)), reverse=reverse)
    return result


def _sort_safe(v):
    if v is None:
        return (1, 0)
    return (0, v)


class FakeCollection:
    """极简内存 mock：解释 motor find / find_one / aggregate / bulk_write 的最小子集。"""

    def __init__(self, docs: list[dict]):
        self._docs = list(docs)

    async def find_one(self, query: dict, projection: dict | None = None):
        for d in self._docs:
            if _match_doc(d, query):
                return dict(d)
        return None

    def find(self, query: dict, projection: dict | None = None):
        matched = [d for d in self._docs if _match_doc(d, query)]
        return _Cursor(matched)

    def aggregate(self, pipeline: list[dict]):
        docs = list(self._docs)
        for stage in pipeline:
            op = next(iter(stage))
            spec = stage[op]
            if op == "$match":
                docs = [d for d in docs if _match_doc(d, spec)]
            elif op == "$sort":
                docs = _apply_sort(docs, spec)
            elif op == "$group":
                # 只实现 _id=$field + doc={$first:"$$ROOT"}（或 name=$first）
                id_spec = spec["_id"]
                if isinstance(id_spec, str) and id_spec.startswith("$"):
                    group_key = id_spec[1:]
                else:
                    group_key = id_spec
                first_field = None
                for k_, f in spec.items():
                    if k_ != "_id" and isinstance(f, dict) and "$first" in f:
                        ff = f["$first"]
                        if ff == "$$ROOT":
                            first_field = "__root__"
                        elif isinstance(ff, str) and ff.startswith("$"):
                            first_field = ff[1:]
                grouped: dict = {}
                for d in docs:
                    key = d.get(group_key)
                    if key not in grouped:
                        if first_field == "__root__":
                            grouped[key] = d
                        elif first_field:
                            grouped[key] = {group_key: key, first_field: d.get(first_field)}
                        else:
                            grouped[key] = d
                if first_field == "__root__":
                    docs = [{"_id": k, "doc": v} for k, v in grouped.items()]
                else:
                    docs = [{"_id": k, **v} for k, v in grouped.items()]
            elif op == "$replaceRoot":
                docs = [d.get("doc", d) for d in docs]
            elif op == "$limit":
                docs = docs[:spec]

        async def gen():
            for d in docs:
                yield d

        return gen()

    async def bulk_write(self, ops, ordered=False):
        return _FakeBulkResult(len(ops))


class _FakeBulkResult:
    def __init__(self, modified_count: int):
        self.modified_count = modified_count


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
            elif op == "$options":
                continue
            elif op == "$ne":
                if field_val == val:
                    return False
            elif op == "$nin":
                if field_val in val:
                    return False
            elif op == "$exists":
                if bool(val) != (field_val is not None):
                    return False
            else:
                return False
        return True
    return field_val == cond


def _eval_expr(doc: dict, expr: Any) -> Any:
    """极简 $expr 求值：支持 $regexMatch / $toString / $ne / $and。"""
    if isinstance(expr, str):
        if expr.startswith("$"):
            return doc.get(expr[1:])
        return expr
    if not isinstance(expr, dict):
        return expr
    if "$regexMatch" in expr:
        rm = expr["$regexMatch"]
        input_val = _eval_expr(doc, rm["input"])
        regex_str = rm["regex"]
        if not isinstance(input_val, str):
            return False
        pattern = regex_str[1:] if regex_str.startswith("^") else regex_str
        if regex_str.startswith("^"):
            return input_val.startswith(pattern)
        return pattern in input_val
    if "$toString" in expr:
        v = _eval_expr(doc, expr["$toString"])
        return "" if v is None else str(v)
    if "$ne" in expr:
        arr = expr["$ne"]
        if not isinstance(arr, list) or len(arr) != 2:
            return False
        return _eval_expr(doc, arr[0]) != _eval_expr(doc, arr[1])
    if "$and" in expr:
        return all(_eval_expr(doc, sub) for sub in expr["$and"])
    return expr


def _match_doc(doc: dict, filt: dict) -> bool:
    for key, cond in filt.items():
        if key == "$and":
            for sub in cond:
                if not _match_doc(doc, sub):
                    return False
        elif key == "$or":
            if not any(_match_doc(doc, sub) for sub in cond):
                return False
        elif key == "$expr":
            if not _eval_expr(doc, cond):
                return False
        else:
            field_val = doc.get(key)
            if not _match_value(field_val, cond):
                return False
    return True


def _service() -> EtfService:
    svc = EtfService.__new__(EtfService)  # 绕过 __init__（避免构造 Sse/Szse/Gmbd client）
    svc.repo = MagicMock()
    svc.repo.collection = FakeCollection(FIXTURE)
    svc.quarter_repo = MagicMock()
    return svc


# ====================== tests ======================


@pytest.mark.asyncio
async def test_empty_q_returns_all_unique_codes():
    svc = _service()
    rows = await svc.search_etfs("", 100)
    codes = [r["code"] for r in rows]
    assert "510050" in codes
    assert "510300" in codes
    assert "159919" in codes
    # 同 code 只出一次（最新日期）
    assert sum(1 for c in codes if c == "510050") == 1
    assert len(rows) == 11  # 12 docs, 11 unique codes


@pytest.mark.asyncio
async def test_exact_code_priority_first():
    svc = _service()
    rows = await svc.search_etfs("510300", 20)
    assert rows[0]["code"] == "510300"
    assert rows[0]["name"] == "沪深300ETF"
    assert rows[0]["lastDate"] == "2026-08-05"


@pytest.mark.asyncio
async def test_pinyin_prefix_search():
    svc = _service()
    rows = await svc.search_etfs("HS", 20)
    codes = {r["code"] for r in rows}
    assert "510300" in codes
    assert "159919" in codes
    for r in rows:
        py = r["pinyin"]
        if py:
            assert py.startswith("HS")


@pytest.mark.asyncio
async def test_code_prefix_no_dup():
    svc = _service()
    rows = await svc.search_etfs("510", 20)
    codes = [r["code"] for r in rows]
    for c in ["510050", "510300", "510500"]:
        assert c in codes
    assert sum(1 for c in codes if c == "510050") == 1


@pytest.mark.asyncio
async def test_name_contains():
    svc = _service()
    rows = await svc.search_etfs("沪深300", 20)
    codes = {r["code"] for r in rows}
    assert "510300" in codes
    assert "159919" in codes


@pytest.mark.asyncio
async def test_no_match_returns_empty():
    svc = _service()
    rows = await svc.search_etfs("zzzz", 20)
    assert rows == []


@pytest.mark.asyncio
async def test_limit_is_respected():
    svc = _service()
    rows = await svc.search_etfs("", 3)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_limit_upper_bound_clamped():
    svc = _service()
    rows = await svc.search_etfs("", 99999)
    assert len(rows) <= 1000
    assert len(rows) == 11


@pytest.mark.asyncio
async def test_null_q_treated_as_empty():
    svc = _service()
    rows = await svc.search_etfs(None, 100)
    assert len(rows) == 11


@pytest.mark.asyncio
async def test_regex_special_chars_in_query_dont_break():
    svc = _service()
    await svc.search_etfs("5..*", 20)
    await svc.search_etfs(".", 20)


@pytest.mark.asyncio
async def test_save_mongo_data_sets_pinyin():
    """save_mongo_data 落库前应从 secName 算好 pinyin。"""
    from app.models.entities import EtfEntity

    svc = EtfService.__new__(EtfService)
    svc.repo = MagicMock()
    svc.repo.save = AsyncMock()
    svc.kline_repo = MagicMock()
    svc.kline_service = MagicMock()

    e1 = EtfEntity(secCode=510300, secName="沪深300ETF", statDate="2026-08-05")
    e2 = EtfEntity(secCode=510050, secName="50ETF", statDate="2026-08-05")

    await svc.save_mongo_data([e1, e2], with_kline=False)

    assert svc.repo.save.await_count == 2
    saved1 = svc.repo.save.await_args_list[0].args[0]
    saved2 = svc.repo.save.await_args_list[1].args[0]
    # pypinyin Style.FIRST_LETTER 对数字串只取首数字："沪深300ETF"->"HS3","科创50ETF"->"KC5"
    assert saved1.pinyin == "HS3"
    assert saved2.pinyin == "5"  # "50ETF" 纯代码简称，只剩数字