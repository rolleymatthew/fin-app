from __future__ import annotations

from app.clients.exchange_base import OfficialStock
from app.models.entities import SecCodeEntity


def official_to_entity(stock: OfficialStock) -> SecCodeEntity:
    entity = SecCodeEntity(
        id=stock.code,
        securityCode=stock.code,
        securityNameAbbr=stock.name,
        tradeMarket=stock.market,
        tradeMarketCode=stock.market,
        listingDate=stock.listingDate,
        listingState=stock.listingState,
        securityTypeCode=stock.type,
    )
    return entity
