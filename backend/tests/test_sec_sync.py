import pytest

from app.clients.eastmoney_cookie import CookieHealthChecker
from app.clients.exchange_base import OfficialStock
from app.models.entities import SecCodeEntity
from app.services.seccode_service import SecCodeService


def _entity(code: str, **kw):
    return SecCodeEntity(
        id=code,
        securityCode=code,
        securityNameAbbr=kw.get("name", "x"),
        tradeMarket=kw.get("market", "SH"),
        orgName=kw.get("orgName", "x"),
        regCapital=kw.get("regCapital", 1.0),
        orgTypeCode=kw.get("orgTypeCode", "1"),
        tradeMarketCode=kw.get("market", "SH"),
        listingState=kw.get("listingState", "0"),
    )


def _company_dto(code: str) -> dict:
    return {
        "code": 0,
        "result": {
            "data": [
                {
                    "SECURITY_CODE": code,
                    "SECURITY_NAME_ABBR": "测试",
                    "ORG_NAME": "测试公司",
                    "REG_CAPITAL": 1.0,
                    "ORG_TYPE_CODE": "1",
                    "TRADE_MARKET_CODE": "SH",
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_compute_diff_returns_new_state_changed_and_missing():
    official = [
        OfficialStock(
            code="600000", name="浦发", market="SH",
            listingDate=None, listingState="0", type="stock",
        ),
        OfficialStock(
            code="000001", name="平安", market="SZ",
            listingDate=None, listingState="0", type="stock",
        ),
        OfficialStock(
            code="000099", name="已退市", market="SZ",
            listingDate=None, listingState="2", type="stock",
        ),
    ]
    existing = [
        _entity("600000", listingState="2"),
        _entity("000001", orgName=None),
        _entity("999999"),
    ]
    svc = SecCodeService.__new__(SecCodeService)
    diff = await svc.compute_diff(official, existing, force=False)
    assert "000001" in diff.new_codes or "000001" in diff.missing_details
    assert "600000" in diff.state_changed or "600000" in diff.new_codes
    assert "000099" in diff.new_codes
    assert "999999" not in (diff.new_codes + diff.state_changed + diff.missing_details)
    assert diff.by_exchange == {"SH": 1, "SZ": 2}


class _FakeRepo:
    def __init__(self, entities: list[SecCodeEntity] | None = None):
        self.entities = list(entities or [])
        self.saved: list[SecCodeEntity] = []

    async def find_all(self):
        return self.entities

    async def save(self, entity):
        self.saved.append(entity)
        return entity

    async def save_many(self, entities):
        for e in entities:
            await self.save(e)


@pytest.mark.asyncio
async def test_refill_details_success_path(monkeypatch):
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = _FakeRepo()

    async def fake_get_company_dto(self, code):
        return {
            "code": 0,
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": code,
                        "SECURITY_NAME_ABBR": "测试",
                        "ORG_NAME": "测试公司",
                        "REG_CAPITAL": 1.0,
                        "ORG_TYPE_CODE": "1",
                        "TRADE_MARKET_CODE": "SH",
                    }
                ]
            },
        }

    monkeypatch.setattr(SecCodeService, "get_company_dto", fake_get_company_dto)

    result = await svc.refill_details(["600000"], rate=20.0, retries=1)

    assert result.refilled == 1
    assert result.failed == []
    assert any(e.securityCode == "600000" for e in svc.repo.saved)


@pytest.mark.asyncio
async def test_refill_details_mapper_empty_path(monkeypatch):
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = _FakeRepo()

    async def fake_get_company_dto(self, code):
        return {"code": 0, "result": {"data": []}}

    monkeypatch.setattr(SecCodeService, "get_company_dto", fake_get_company_dto)

    result = await svc.refill_details(["600000"], rate=20.0, retries=1)

    assert result.refilled == 0
    assert len(result.failed) == 1
    assert result.failed[0] == {"code": "600000", "reason": "mapper_empty"}
    assert svc.repo.saved == []


@pytest.mark.asyncio
async def test_refresh_all_details_includes_delisted_by_default(monkeypatch):
    repo = _FakeRepo(
        [
            _entity("600000", listingState="0"),
            _entity("000001", market="SZ", listingState="2"),
        ]
    )
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = repo

    async def fake_get_company_dto(self, code):
        return _company_dto(code)

    monkeypatch.setattr(SecCodeService, "get_company_dto", fake_get_company_dto)

    report = await svc.refresh_all_details()

    assert report.details_refilled == 2
    assert {entity.securityCode for entity in repo.saved} == {"600000", "000001"}


@pytest.mark.asyncio
async def test_refresh_all_details_excludes_delisted_when_requested(monkeypatch):
    repo = _FakeRepo(
        [
            _entity("600000", listingState="0"),
            _entity("000001", market="SZ", listingState="2"),
        ]
    )
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = repo

    async def fake_get_company_dto(self, code):
        return _company_dto(code)

    monkeypatch.setattr(SecCodeService, "get_company_dto", fake_get_company_dto)

    report = await svc.refresh_all_details(include_delisted=False)

    assert report.details_refilled == 1
    assert {entity.securityCode for entity in repo.saved} == {"600000"}


@pytest.mark.asyncio
async def test_refresh_all_details_only_missing_filters_correctly(monkeypatch):
    repo = _FakeRepo(
        [
            _entity("600000"),
            _entity("000001", market="SZ", orgName=None),
        ]
    )
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = repo

    async def fake_get_company_dto(self, code):
        return _company_dto(code)

    monkeypatch.setattr(SecCodeService, "get_company_dto", fake_get_company_dto)

    report = await svc.refresh_all_details(only_missing=True)

    assert report.details_refilled == 1
    assert {entity.securityCode for entity in repo.saved} == {"000001"}


@pytest.mark.asyncio
async def test_refill_details_refreshes_invalid_cookie_and_retries():
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = _FakeRepo()

    company = {
        "code": 0,
        "result": {
            "data": [
                {
                    "SECURITY_CODE": "600000",
                    "SECURITY_NAME_ABBR": "测试",
                    "ORG_NAME": "测试公司",
                    "REG_CAPITAL": 1.0,
                    "ORG_TYPE_CODE": "1",
                    "TRADE_MARKET_CODE": "SH",
                }
            ]
        },
    }

    class FakeDataCenter:
        def __init__(self):
            self.responses = [(None, '{"rc": 100}'), (company, '{"code": 0}')]
            self.calls = 0

        async def company_with_raw(self, *args, **kwargs):
            self.calls += 1
            return self.responses.pop(0)

    class FakeClient:
        def __init__(self):
            self._cookie_health = CookieHealthChecker()
            self.refresh_calls = 0

        async def _refresh_cookie_from_server(self):
            self.refresh_calls += 1
            return True

    svc.data_center = FakeDataCenter()
    svc.client = FakeClient()

    result = await svc.refill_details(["600000"], rate=1000.0, retries=1)

    assert result.refilled == 1
    assert result.failed == []
    assert svc.data_center.calls == 2
    assert svc.client.refresh_calls == 1
    assert any(e.securityCode == "600000" for e in svc.repo.saved)


@pytest.mark.asyncio
async def test_refill_details_classifies_cookie_invalid_after_retry():
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = _FakeRepo()

    class FakeDataCenter:
        def __init__(self):
            self.responses = [(None, '{"rc": 100}'), (None, '{"rc": 100}')]
            self.calls = 0

        async def company_with_raw(self, *args, **kwargs):
            self.calls += 1
            return self.responses.pop(0)

    class FakeClient:
        def __init__(self):
            self._cookie_health = CookieHealthChecker()
            self.refresh_calls = 0

        async def _refresh_cookie_from_server(self):
            self.refresh_calls += 1
            return True

    svc.data_center = FakeDataCenter()
    svc.client = FakeClient()

    result = await svc.refill_details(["600000"], rate=1000.0, retries=3)

    assert result.refilled == 0
    assert result.failed == [{"code": "600000", "reason": "cookie_invalid"}]
    assert svc.data_center.calls == 2
    assert svc.client.refresh_calls == 1
    assert svc.repo.saved == []


@pytest.mark.asyncio
async def test_sync_from_exchanges_upserts_official_rows(monkeypatch):
    from app.services import seccode_service as mod

    repo = _FakeRepo()
    svc = SecCodeService.__new__(SecCodeService)
    svc.repo = repo
    svc.data_center = type("DC", (), {"company": staticmethod(lambda *a, **k: None)})()

    async def fake_fetch_official(self):
        return [
            OfficialStock(
                code="600000", name="浦发", market="SH",
                listingDate="1999-11-10", listingState="0", type="stock",
            )
        ]

    monkeypatch.setattr(mod.SecCodeService, "_fetch_official", fake_fetch_official)

    report = await svc.sync_from_exchanges(force=False)

    assert report.total_in_official == 1
    assert any(e.securityCode == "600000" for e in repo.saved)
    assert svc.last_sync_report is report
    assert report.cookie_warmed is False


def _reset_singleton():
    from app.api.sec_code import _service
    _service.cache_clear()


@pytest.mark.asyncio
async def test_post_sec_sync_returns_report(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.api import sec_code as api_mod
    from app.main import app

    _reset_singleton()
    fake_report = {
        "total_in_official": 1, "existing_in_db": 0, "new_added": 1,
        "state_changed": 0, "details_refilled": 0, "failed": [],
        "by_exchange": {"SH": 1, "SZ": 0}, "elapsed_ms": 10,
    }

    async def fake_sync(self, force=False):
        self.last_sync_report = fake_report
        return fake_report

    monkeypatch.setattr(api_mod.SecCodeService, "sync_from_exchanges", fake_sync)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/sec/sync", json={"force": False})
    assert r.status_code == 200
    assert r.json()["data"]["total_in_official"] == 1


@pytest.mark.asyncio
async def test_post_refresh_details_returns_report(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.api import sec_code as api_mod
    from app.main import app

    _reset_singleton()
    fake_report = {
        "total_in_official": 0, "existing_in_db": 5, "new_added": 0,
        "state_changed": 0, "details_refilled": 3, "failed": [],
        "by_exchange": {}, "elapsed_ms": 20,
    }

    async def fake_refresh(self, include_delisted=True, only_missing=False):
        self.last_sync_report = fake_report
        return fake_report

    monkeypatch.setattr(api_mod.SecCodeService, "refresh_all_details", fake_refresh)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/sec/refresh-details",
            json={"include_delisted": False, "only_missing": True},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["details_refilled"] == 3
    assert body["data"]["existing_in_db"] == 5


@pytest.mark.asyncio
async def test_sync_status_returns_none_when_no_sync(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    _reset_singleton()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/sec/sync/status")
    assert r.status_code == 200
    assert r.json()["data"] is None


@pytest.mark.asyncio
async def test_sync_status_returns_last_report(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.api import sec_code as api_mod
    from app.main import app

    _reset_singleton()
    fake_report = {
        "total_in_official": 7, "existing_in_db": 2, "new_added": 5,
        "state_changed": 1, "details_refilled": 4, "failed": [],
        "by_exchange": {"SH": 4, "SZ": 3}, "elapsed_ms": 42,
    }

    async def fake_sync(self, force=False):
        self.last_sync_report = fake_report
        return fake_report

    monkeypatch.setattr(api_mod.SecCodeService, "sync_from_exchanges", fake_sync)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/api/sec/sync", json={"force": True})
        assert r1.status_code == 200
        r2 = await client.get("/api/sec/sync/status")
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert data["total_in_official"] == 7
    assert data["new_added"] == 5
    assert data["elapsed_ms"] == 42
