"""kline_network_chain 配置字段测试."""
from __future__ import annotations

import os
from unittest.mock import patch

from app.config import Settings


def test_kline_network_chain_default():
    s = Settings()
    assert s.kline_network_chain == "sina,tencent,eastmoney"


def test_kline_network_chain_env_override():
    with patch.dict(os.environ, {"FIN_KLINE_NETWORK_CHAIN": "tencent,sina,eastmoney"}):
        s = Settings()
        assert s.kline_network_chain == "tencent,sina,eastmoney"