from __future__ import annotations

from typing import Any
import os
from pathlib import Path
import sys
from datetime import datetime
import asyncio

import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed

from app.clients.user_agents import random_user_agent
from app.config import get_settings


class BaseHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        http2: bool = False,
        trust_env: bool = False,
        allow_http2_fallback: bool = True,
    ):
        self.base_url = base_url
        self.settings = get_settings()
        self._http2 = http2
        self._trust_env = trust_env
        self._allow_http2_fallback = allow_http2_fallback
        # Disable env proxies to avoid http proxy disconnects
        self._client = self._build_client()

    async def close(self):
        await self._client.aclose()

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.settings.http_timeout,
            trust_env=self._trust_env,
            http2=self._http2,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def _reset_client(self) -> None:
        old_cookies = self._client.cookies
        try:
            await self._client.aclose()
        finally:
            self._client = self._build_client()
            self._client.cookies = old_cookies

    async def _fallback_http2_off(self) -> None:
        if not self._http2 or not self._allow_http2_fallback:
            return
        self._http2 = False
        await self._reset_client()

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        base_url_override: str | None = None,
        *,
        retry: bool = True,
    ) -> httpx.Response:
        headers = headers or {}
        headers.setdefault("User-Agent", random_user_agent())
        # 不再全局注入 Accept-Encoding: identity / Connection: close
        # 避免触发反爬特征，由各 client 自行控制
        url = (base_url_override or self.base_url) + path
        self._log_url_if_enabled(url, params)

        if not retry:
            try:
                resp = await self._client.get(url, params=params, headers=headers)
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
                await self._fallback_http2_off()
                if not self._http2:
                    await self._reset_client()
                self._log_error_if_enabled(url, params, exc)
                raise exc
            if resp.status_code >= 400:
                resp.raise_for_status()
            self._log_response_if_enabled(url, params, resp)
            return resp

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.http_retries),
            wait=wait_fixed(self.settings.http_retry_wait),
            reraise=True,
        ):
            with attempt:
                try:
                    resp = await self._client.get(url, params=params, headers=headers)
                except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
                    # Recreate client on transport-level disconnects before retry.
                    await self._fallback_http2_off()
                    if not self._http2:
                        await self._reset_client()
                    self._log_error_if_enabled(url, params, exc)
                    await asyncio.sleep(0.2)
                    raise exc
                if resp.status_code >= 400:
                    resp.raise_for_status()
                self._log_response_if_enabled(url, params, resp)
                return resp
        raise RuntimeError("unreachable")

    def _log_url_if_enabled(self, url: str, params: dict[str, Any] | None) -> None:
        if not self._is_debug_log_url_enabled():
            return
        try:
            req = httpx.Request("GET", url, params=params)
            full_url = str(req.url)
            log_path = self._get_url_log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", errors="ignore") as f:
                f.write(full_url + "\n")
        except Exception:
            # URL logging must never break the request flow.
            return

    def _log_response_if_enabled(self, url: str, params: dict[str, Any] | None, resp: httpx.Response) -> None:
        if not self._is_debug_log_url_enabled():
            return
        if "eastmoney.com" not in self.base_url:
            return
        try:
            req = httpx.Request("GET", url, params=params)
            full_url = str(req.url)
            log_path = self._get_url_log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with log_path.open("a", encoding="utf-8", errors="ignore") as f:
                f.write(f"[{timestamp}] {full_url}\n")
                f.write(resp.text + "\n")
                f.write("-" * 80 + "\n")
        except Exception:
            # Response logging must never break the request flow.
            return

    def _log_error_if_enabled(self, url: str, params: dict[str, Any] | None, exc: Exception) -> None:
        if not self._is_debug_log_url_enabled():
            return
        try:
            req = httpx.Request("GET", url, params=params)
            full_url = str(req.url)
            log_path = self._get_url_log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with log_path.open("a", encoding="utf-8", errors="ignore") as f:
                f.write(f"[{timestamp}] ERROR {full_url}\n")
                f.write(f"{type(exc).__name__}: {exc}\n")
                f.write("-" * 80 + "\n")
        except Exception:
            # Error logging must never break the request flow.
            return

    def _is_debug_log_url_enabled(self) -> bool:
        value = os.getenv("DEBUG_LOG_URL", "")
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _get_url_log_path(self) -> Path:
        override = os.getenv("DEBUG_LOG_URL_PATH", "").strip()
        if override:
            try:
                return Path(override)
            except Exception:
                pass
        return Path.cwd() / "urlLogs.log"

    async def get_text(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        base_url_override: str | None = None,
        *,
        retry: bool = True,
    ) -> str:
        resp = await self.get(path, params=params, headers=headers, base_url_override=base_url_override, retry=retry)
        return resp.text

    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        base_url_override: str | None = None,
        *,
        retry: bool = True,
    ) -> Any:
        resp = await self.get(path, params=params, headers=headers, base_url_override=base_url_override, retry=retry)
        return resp.json()
