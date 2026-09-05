from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class CookieHealth:
    invalid: bool
    reason: str | None = None


class CookieHealthChecker:
    ACCEPTABLE_RC = {0, -1, -2, -100, -101, -102}
    INVALID_KEYWORDS = (
        "访问频次",
        "验证码",
        "请输入验证码",
        "Access Denied",
        "Forbidden",
    )

    def __init__(self):
        pass

    def check(self, text: str) -> CookieHealth:
        if not text:
            return CookieHealth(invalid=False)
        stripped = text.strip()
        try:
            data = json.loads(stripped)
        except (ValueError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            rc = data.get("rc")
            if isinstance(rc, int) and rc not in self.ACCEPTABLE_RC:
                return CookieHealth(invalid=True, reason=f"rc={rc}")
        for kw in self.INVALID_KEYWORDS:
            if kw in text:
                return CookieHealth(invalid=True, reason=f"keyword={kw}")
        return CookieHealth(invalid=False)

    async def refresh_once(self, client) -> bool:
        """两层兜底: HTTP 流 → 切次新 cookie 文件.

        任一方式拿到新 cookie 都返回 True. 全失败返回 False.
        """
        if await client._refresh_cookie_from_server():
            return True

        if client.try_next_cookie_file():
            print("[cookie/file] switched to next-newest cookie file", flush=True)
            return True

        return False


class CookieStore:
    """从单一目录加载 *.txt 文件并按文件名顺序拼接为 Cookie 字符串。"""

    def __init__(self, dir_path: Path):
        self.dir_path = Path(dir_path)
        self._last_snapshot: dict[str, tuple[float, int]] = {}
        self._last_string: str = ""

    def _iter_files(self):
        if not self.dir_path.exists() or not self.dir_path.is_dir():
            return []
        files = [
            p for p in self.dir_path.iterdir()
            if p.is_file() and p.suffix == ".txt" and not p.name.startswith(".")
        ]
        files.sort(key=lambda p: p.name)
        return files

    def load_combined_string(self) -> str:
        seen: dict[str, str] = {}
        order: list[str] = []
        for f in self._iter_files():
            try:
                text = f.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not text:
                continue
            for piece in text.split(";"):
                piece = piece.strip()
                if "=" not in piece:
                    continue
                key, _, _ = piece.partition("=")
                key = key.strip()
                if not key:
                    continue
                if key not in seen:
                    order.append(key)
                seen[key] = piece
        return "; ".join(seen[k] for k in order)

    def file_snapshot(self) -> dict[str, tuple[float, int]]:
        snap: dict[str, tuple[float, int]] = {}
        for f in self._iter_files():
            try:
                stat = f.stat()
            except OSError:
                continue
            snap[f.name] = (stat.st_mtime, stat.st_size)
        return snap

    def load_if_changed(self, client: httpx.AsyncClient) -> bool:
        new_snap = self.file_snapshot()
        if new_snap == self._last_snapshot and self._last_string:
            return False
        is_initial = not self._last_string
        snapshot_changed = new_snap != self._last_snapshot
        combined = self.load_combined_string()
        self._write_to_jar(client, combined)
        self._last_snapshot = new_snap
        self._last_string = combined
        return snapshot_changed and not is_initial

    def latest_file(self) -> Path | None:
        """返回 mtime 最新的 *.txt 文件路径. 目录为空返回 None."""
        files = self._iter_files()
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def files_by_mtime_desc(self) -> list[Path]:
        """按 mtime 倒序返回所有文件."""
        files = self._iter_files()
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def load_file(self, path: Path) -> str:
        """读取单个 *.txt 文件内容 (strip). 读失败返回空字符串."""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def mark_loaded(self, cookie_str: str) -> None:
        """登记外部已加载的 cookie 字符串.

        单文件模式 (``latest_file()`` + ``load_file()``) 绕过了
        ``load_if_changed()``, 需要显式同步快照与当前字符串, 否则
        ``current_string()`` 为空 (诊断日志 fields=0), 且下一次
        ``load_if_changed()`` 会被误判为"文件变化"。
        """
        self._last_snapshot = self.file_snapshot()
        self._last_string = cookie_str

    def _write_to_jar(self, client: httpx.AsyncClient, cookie_str: str) -> None:
        if not cookie_str:
            return
        for piece in cookie_str.split(";"):
            piece = piece.strip()
            if "=" not in piece:
                continue
            key, _, value = piece.partition("=")
            client.cookies.set(key.strip(), value.strip(), domain=".eastmoney.com")

    def current_string(self) -> str:
        return self._last_string
