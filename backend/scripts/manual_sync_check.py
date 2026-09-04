from __future__ import annotations

import asyncio

from app.clients.exchange_base import ExchangeFetchError
from app.clients.sse import SSEClient
from app.clients.szse import SZSEClient
from app.models.entities import SecCodeEntity
from app.repositories.base import MongoRepository


async def main() -> None:
    sse, szse = SSEClient(), SZSEClient()
    results = await asyncio.gather(sse.fetch_list(), szse.fetch_list(), return_exceptions=True)
    official: list = []
    for r in results:
        if isinstance(r, ExchangeFetchError):
            print(f"[!] fetch failed: {r}")
            continue
        if isinstance(r, Exception):
            print(f"[!] fetch error: {r}")
            continue
        official.extend(r)
    await sse.aclose()
    await szse.aclose()

    repo = MongoRepository(SecCodeEntity)
    existing = await repo.find_all()
    existing_codes = {e.securityCode for e in existing}

    official_codes = {s.code for s in official}
    new_codes = sorted(official_codes - existing_codes)
    stale_codes = sorted(existing_codes - official_codes)
    missing_details = sorted(e.securityCode for e in existing if not (e.orgName and e.regCapital))

    print(f"official={len(official_codes)} db={len(existing_codes)}")
    print(f"new_in_official_not_in_db={len(new_codes)}")
    print(f"in_db_not_in_official={len(stale_codes)}")
    print(f"missing_details={len(missing_details)}")
    for c in new_codes[:20]:
        print("  +", c)
    for c in stale_codes[:20]:
        print("  -", c)
    for c in missing_details[:20]:
        print("  ?", c)


if __name__ == "__main__":
    asyncio.run(main())
