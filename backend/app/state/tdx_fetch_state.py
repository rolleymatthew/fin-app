"""TDX fetcher 任务状态字典 (单例模式, 内存).

lifespan 启动时挂到 app.state.tdx_state, 关闭时 cancel_active().
不进 DB — 进程重启任务丢失, 用户重新 POST 即可.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.services.tdx_daily_fetcher.exceptions import FetchError
from app.services.tdx_daily_fetcher.fetcher import (
    ACTIVE_STATES,
    TaskStatus,
    TdxDailyFetcher,
)

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class TdxFetchStateStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskStatus] = {}

    def start(self, settings: "Settings") -> TaskStatus:
        """新建任务, 在 asyncio.to_thread 里跑 fetcher.run_sync()."""
        from app.services.tdx_daily_fetcher.constants import (
            DOWNLOAD_URL as DEFAULT_URL,
        )
        from app.services.tdx_daily_fetcher.constants import (
            META_URL as DEFAULT_META,
        )
        download_url = settings.tdx_download_url or DEFAULT_URL
        meta_url = settings.tdx_meta_url or DEFAULT_META

        fetcher = TdxDailyFetcher(
            data_dir=settings.tdx_data_dir,
            download_url=download_url,
            meta_url=meta_url,
        )
        status = fetcher.status()
        self._tasks[status.task_id] = status
        # 在后台线程跑 — 同步阻塞 IO 不阻塞 asyncio 事件循环
        asyncio.get_event_loop().create_task(self._run(fetcher))
        return status

    async def _run(self, fetcher: TdxDailyFetcher) -> None:
        try:
            await asyncio.to_thread(fetcher.run_sync)
        except FetchError as exc:
            fetcher.status().mark("failed", f"unexpected: {exc}")
            logger.exception("[tdx/state] task %s unexpected error", fetcher.status().task_id)
        except Exception as exc:  # noqa: BLE001  永远兜底, 不让 task 静默死掉
            fetcher.status().mark("failed", f"unexpected: {exc}")
            logger.exception("[tdx/state] task %s crashed", fetcher.status().task_id)

    def get(self, task_id: str) -> TaskStatus | None:
        return self._tasks.get(task_id)

    def active(self) -> TaskStatus | None:
        for s in self._tasks.values():
            if s.state in ACTIVE_STATES:
                return s
        return None

    def cancel_active(self, reason: str) -> int:
        n = 0
        for s in self._tasks.values():
            if s.state in ACTIVE_STATES:
                s.mark("failed", reason)
                n += 1
        return n
