"""轮询守护：扫描 FIN_ETF_CSV_DIR 下的 表格_*.csv 文件并自动 upsert 到 Mongo etf 集合。

触发方式：main.py lifespan 启动 asyncio task，每 N 秒一次。
状态：<etf_csv_dir>/.last_import.json 记录 {filename: mtime_float}，避免重复处理。
归档：成功导入后 shutil.move 到 <etf_csv_dir>/processed/。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_FILENAME_PATTERN = re.compile(r"^表格_(\d{8})\.csv$")


@dataclass
class StateStore:
    """<etf_csv_dir>/.last_import.json 读写封装"""

    path: Path

    def get(self, filename: str) -> float | None:
        data = parse_state(self._read())
        return data.get(filename)

    def set(self, filename: str, mtime: float) -> None:
        data = parse_state(self._read())
        data[filename] = mtime
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _read(self) -> str | None:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return None


def parse_state(raw: str | None) -> dict[str, float]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _stat_date_from_filename(filename: str) -> date | None:
    m = _FILENAME_PATTERN.match(filename)
    if not m:
        return None
    s = m.group(1)
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None


def _archive_path(csv_dir: Path, filename: str) -> Path:
    return csv_dir / "processed" / filename


async def tick(settings: Any, service: Any) -> dict[str, int]:
    """单次扫描。返回 {scanned, imported, skipped, errors}。"""
    csv_dir = Path(settings.etf_csv_dir)
    csv_dir.mkdir(parents=True, exist_ok=True)

    state = StateStore(csv_dir / ".last_import.json")
    processed_dir = csv_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(csv_dir.glob("表格_*.csv"))
    today = date.today()
    imported = 0
    skipped = 0
    errors = 0
    scanned = 0

    for fp in files:
        scanned += 1
        filename = fp.name
        stat_date = _stat_date_from_filename(filename)
        if stat_date is None:
            logger.warning("[etf_csv_watcher] skip bad filename: %s", filename)
            skipped += 1
            continue
        if stat_date > today:
            logger.warning("[etf_csv_watcher] skip future date: %s", filename)
            skipped += 1
            continue
        mtime = fp.stat().st_mtime
        if state.get(filename) == mtime:
            continue  # 未变化，跳过

        try:
            content = fp.read_bytes()
            report = await service._import_szse_csv(content, stat_date)
            imported += report.get("imported", 0)
            skipped += report.get("skipped", 0)
            if report.get("imported", 0) + report.get("skipped", 0) == 0:
                logger.error("[etf_csv_watcher] zero rows for %s; not archiving", filename)
                errors += 1
                continue
            shutil.move(str(fp), str(_archive_path(csv_dir, filename)))
            state.set(filename, mtime)
            logger.info(
                "[etf_csv_watcher] %s: imported=%d skipped=%d → processed/",
                filename,
                report.get("imported", 0),
                report.get("skipped", 0),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[etf_csv_watcher] failed to import %s: %s", filename, exc)
            errors += 1

    return {"scanned": scanned, "imported": imported, "skipped": skipped, "errors": errors}


def start_watcher(settings: Any, service: Any) -> asyncio.Task:
    """lifespan 启动时调用。返回后台 task，便于关闭时 cancel。"""

    async def _loop():
        poll = int(getattr(settings, "etf_csv_poll_seconds", 300))
        while True:
            try:
                await tick(settings, service)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[etf_csv_watcher] tick failed: %s", exc)
            await asyncio.sleep(poll)

    return asyncio.create_task(_loop(), name="etf-csv-watcher")


async def stop_watcher(task: asyncio.Task | None) -> None:
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass