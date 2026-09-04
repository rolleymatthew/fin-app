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
        """委托 EastmoneyClient 的现有刷新逻辑。仅当 jar 真正变化时返回 True。"""
        return await client._refresh_cookie_from_server()


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
