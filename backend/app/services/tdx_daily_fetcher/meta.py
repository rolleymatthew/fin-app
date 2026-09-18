"""解析 _hsjdayinfo.js (TDX CDN 元信息 JS).

文件格式 (实测):
    var HSJDAY_SOFT_SIZE="335,544,320";
    var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";
    (其他变量可忽略)

字段语义:
    HSJDAY_SOFT_TIME: 包更新日期, 与 .last_fetch.json 的 last_update_time 比对
    HSJDAY_SOFT_SIZE : 包字节数 (压缩后), 仅做参考
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.tdx_daily_fetcher.exceptions import MetaParseError


@dataclass(frozen=True)
class MetaInfo:
    update_time: str
    file_size: int | None


_TIME_RE = re.compile(r'HSJDAY_SOFT_TIME\s*=\s*["\']([^"\']+)["\']')
_SIZE_RE = re.compile(r'HSJDAY_SOFT_SIZE\s*=\s*["\']([^"\']+)["\']')


def parse_meta_info(text: str) -> MetaInfo:
    """从 _hsjdayinfo.js 文本提取 update_time 与 file_size.

    Raises:
        MetaParseError: 找不到 HSJDAY_SOFT_TIME 变量 (格式变更)
    """
    if not text or not text.strip():
        raise MetaParseError("_hsjdayinfo.js 内容为空")

    m_time = _TIME_RE.search(text)
    if not m_time:
        raise MetaParseError(
            "_hsjdayinfo.js 格式变更, 无法解析 HSJDAY_SOFT_TIME"
        )

    update_time = m_time.group(1).strip()

    file_size: int | None = None
    m_size = _SIZE_RE.search(text)
    if m_size:
        raw = m_size.group(1).replace(",", "").strip()
        try:
            file_size = int(raw)
        except ValueError:
            file_size = None  # 软失败: size 不影响主流程

    return MetaInfo(update_time=update_time, file_size=file_size)