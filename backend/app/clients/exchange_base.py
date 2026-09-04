from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from app.clients.user_agents import USER_AGENTS


@dataclass
class OfficialStock:
    code: str
    name: str
    market: str
    listingDate: str | None
    listingState: str
    type: str | None
    raw: dict[str, Any] = field(default_factory=dict)


class ExchangeFetchError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def random_headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS) if USER_AGENTS else "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer,
    }
