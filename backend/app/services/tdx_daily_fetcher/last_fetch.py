"""<target_dir>/.last_fetch.json 读写封装.

记录上次成功 fetch 的元信息, 用于 SKIPPED 路径判断:
  - 文件缺失 → 必下载
  - update_time 一致 → 跳过
  - update_time 不一致 → 下载
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.tdx_daily_fetcher.constants import LAST_FETCH_FILENAME

if TYPE_CHECKING:
    from app.services.tdx_daily_fetcher.meta import MetaInfo


class LastFetch:
    def __init__(self, target_dir: Path):
        self.path = Path(target_dir) / LAST_FETCH_FILENAME

    def read(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write(self, meta: "MetaInfo", file_count: int, zip_size: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "update_time": meta.update_time,
            "file_size": meta.file_size,
            "file_count": file_count,
            "zip_size": zip_size,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def should_skip(self, current_update_time: str) -> bool:
        data = self.read()
        if data is None:
            return False
        return data.get("update_time") == current_update_time
