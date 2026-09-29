"""本地通达信 (TDX) K 线适配器.

职责:
    - resolve_tdx_home(): 三级 fallback 解析 TDX_HOME 路径
    - TdxAdapter: 实现 KLineAdapter 协议, 包 fetch_local_day (Task 3 扩展)

设计: 本模块迁出自 tdx_offline/fetcher.py 的 _resolve_tdx_home, 让 KLinePipeline
能在不依赖 tdx_offline 子包的情况下使用同一路径解析逻辑. tdx_offline 改为
import shim, 保持向后兼容.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings


def resolve_tdx_home(tdx_home: str | os.PathLike | None) -> Path:
    """解析 TDX 主目录. 三级 fallback: 入参 > settings.tdx_home > TDX_HOME 环境变量 > 默认.

    默认值 C:\\zd_zxzq_gm 与 tdx_offline 既有契约一致.
    """
    if tdx_home:
        return Path(tdx_home)
    settings = get_settings()
    home = settings.tdx_home or os.environ.get("TDX_HOME") or r"C:\zd_zxzq_gm"
    return Path(home)
