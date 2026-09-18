"""Fetcher orchestrator: meta → download → extract → last_fetch.

同步执行 (run_sync) 是 v1 实现. 异步包装由上层 (api/admin_tdx.py) 做,
后续如需真正释放事件循环可改 run() 为 async def 并 await asyncio.to_thread
下载/解压 IO, 当前实现已经用阻塞 IO 但调用方会在 asyncio.to_thread 中跑.

状态机:
    pending → checking → (skipped | downloading → extracting) → (done | failed)
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.services.tdx_daily_fetcher.constants import HSJDAY_ZIP_NAME
from app.services.tdx_daily_fetcher.downloader import download_zip, fetch_meta
from app.services.tdx_daily_fetcher.exceptions import (
    DownloadError,
    ExtractError,
    FetchError,
)
from app.services.tdx_daily_fetcher.extract import atomic_extract_zip
from app.services.tdx_daily_fetcher.last_fetch import LastFetch

logger = logging.getLogger(__name__)


StateName = Literal[
    "pending", "checking", "downloading", "extracting",
    "done", "failed", "skipped",
]

ACTIVE_STATES: frozenset[str] = frozenset({
    "pending", "checking", "downloading", "extracting",
})


@dataclass
class TaskStatus:
    task_id: str
    state: StateName = "pending"
    progress: int = 0
    message: str = ""
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    update_time: str | None = None
    file_count: int | None = None
    zip_size: int | None = None

    def mark(self, state: StateName, message: str = "", progress: int | None = None) -> None:
        self.state = state
        if message:
            self.message = message
        if progress is not None:
            self.progress = progress
        if state in ("done", "failed", "skipped"):
            self.finished_at = datetime.now()


class TdxDailyFetcher:
    """单次任务编排器. 每次 POST /fetch 创建新实例."""

    def __init__(
        self,
        *,
        data_dir: Path,
        download_url: str,
        meta_url: str,
    ):
        self.data_dir = Path(data_dir)
        self.download_url = download_url
        self.meta_url = meta_url
        self.zip_path = self.data_dir / HSJDAY_ZIP_NAME
        self.status_ = TaskStatus(task_id=uuid.uuid4().hex[:12])

    # ---- public API ----

    def status(self) -> TaskStatus:
        return self.status_

    def run_sync(self) -> TaskStatus:
        s = self.status_
        s.mark("checking", "查询元信息")
        log_prefix = f"[tdx/fetch] task={s.task_id}"

        try:
            meta = fetch_meta(self.meta_url)
            s.update_time = meta.update_time
        except FetchError as exc:
            return self._fail(s, log_prefix, f"meta 查询失败: {exc}")

        # SKIPPED 路径
        lf = LastFetch(self.data_dir)
        if lf.should_skip(meta.update_time):
            s.mark("skipped", f"已是今日 ({meta.update_time})", progress=100)
            logger.info("%s state=skipped update_time=%s", log_prefix, meta.update_time)
            return s

        # 磁盘空间预检 (zip ≈ meta.file_size, 解压后 ≈ 2× zip)
        if meta.file_size and meta.file_size > 0:
            import shutil
            free = shutil.disk_usage(self.data_dir).free
            need = int(meta.file_size * 2.5)  # zip + 解压 + 余量
            if free < need:
                return self._fail(
                    s, log_prefix,
                    f"磁盘不足: 需 {need // 1024 // 1024}MB, 剩余 {free // 1024 // 1024}MB",
                )

        # DOWNLOADING
        s.mark("downloading", "下载中", progress=0)
        logger.info("%s state=downloading url=%s", log_prefix, self.download_url)

        def _on_progress(downloaded: int, total: int) -> None:
            pct = int(downloaded / total * 100) if total else 0
            mb_d = downloaded // 1024 // 1024
            mb_t = total // 1024 // 1024
            s.mark("downloading", f"下载中 {mb_d}MB/{mb_t}MB", progress=pct)

        try:
            written = download_zip(self.download_url, self.zip_path, progress_cb=_on_progress)
        except DownloadError as exc:
            return self._fail(s, log_prefix, f"下载失败: {exc}")

        s.zip_size = written

        # EXTRACTING
        s.mark("extracting", "解压中", progress=0)
        logger.info("%s state=extracting zip_size=%s", log_prefix, written)
        t0 = time.perf_counter()
        try:
            file_count = atomic_extract_zip(self.zip_path, self.data_dir)
        except ExtractError as exc:
            return self._fail(s, log_prefix, f"解压失败: {exc}")
        elapsed = time.perf_counter() - t0

        # 写 last_fetch.json
        lf.write(meta=meta, file_count=file_count, zip_size=written)

        s.file_count = file_count
        s.mark("done", f"完成,elapsed={elapsed:.1f}s,files={file_count}", progress=100)
        logger.info(
            "%s state=done elapsed=%.1fs files=%s update_time=%s",
            log_prefix, elapsed, file_count, meta.update_time,
        )
        return s

    # ---- helpers ----

    @staticmethod
    def _fail(s: TaskStatus, log_prefix: str, error: str) -> TaskStatus:
        s.error = error
        s.mark("failed", error)
        logger.warning("%s state=failed reason=%s", log_prefix, error)
        return s
