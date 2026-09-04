from __future__ import annotations

import os
import random
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.clients.base import BaseHttpClient
from app.clients.eastmoney_cookie import CookieHealthChecker, CookieStore
from app.clients.user_agents import random_user_agent


def _cookie_file_path() -> Path:
    """Cookie 持久化路径：优先环境变量 EASTMONEY_COOKIE_FILE，否则当前工作目录。"""
    env_path = os.getenv("EASTMONEY_COOKIE_FILE", "").strip()
    if env_path:
        return Path(env_path)
    return Path.cwd() / ".eastmoney_cookie"


def _cookie_dir_path() -> Path:
    """多文件 Cookie 目录：FIN_COOKIE_DIR > EASTMONEY_COOKIE_DIR > ./.eastmoney_cookies"""
    env = os.getenv("FIN_COOKIE_DIR", "").strip() or os.getenv("EASTMONEY_COOKIE_DIR", "").strip()
    if env:
        return Path(env)
    return Path.cwd() / ".eastmoney_cookies"


@lru_cache
def get_eastmoney_client() -> "EastmoneyClient":
    return EastmoneyClient()


class EastmoneyClient(BaseHttpClient):
    def __init__(self):
        super().__init__("https://push2his.eastmoney.com", http2=False)
        self._kline_hosts = [
            "https://push2his.eastmoney.com",
            "https://push2.eastmoney.com",
        ]
        self._cookie_last_refreshed_at: float | None = None
        self._cookie_cooldown_seconds = 300  # 5 分钟冷却期
        self._cookie_health = CookieHealthChecker()
        self._cookie_store: CookieStore | None = None
        self._seeded = self._seed_cookie_jar()
        # 启动后立即打印 Cookie 状态, 让用户能直观看到当前 Cookie 是否需要更换
        self._log_cookie_status(tag="启动")

    # ------------------------------------------------------------------ #
    # Cookie 持久化
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_persisted_cookie() -> str:
        fpath = _cookie_file_path()
        if not fpath.exists():
            return ""
        try:
            return fpath.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _persist_cookie(self, cookie_str: str) -> None:
        try:
            fpath = _cookie_file_path()
            fpath.write_text(cookie_str, encoding="utf-8")
            print(f"Cookie 已持久化到 {fpath}", flush=True)
        except Exception as exc:
            print(f"Cookie 持久化失败: {exc}", flush=True)

    # ------------------------------------------------------------------ #
    # Cookie jar 种子初始化
    # ------------------------------------------------------------------ #
    def _seed_cookie_jar(self) -> bool:
        # 目录配置优先（多文件 Cookie 模式），单文件/字符串模式作为兜底
        dir_env = (
            os.getenv("FIN_COOKIE_DIR", "").strip()
            or os.getenv("EASTMONEY_COOKIE_DIR", "").strip()
        )
        has_cookie_source = any(
            os.getenv(name, "").strip()
            for name in (
                "FIN_COOKIE_DIR",
                "EASTMONEY_COOKIE_DIR",
                "EASTMONEY_COOKIE_FILE",
                "EASTMONEY_COOKIE",
            )
        )
        if dir_env:
            dir_path = Path(dir_env)
        elif not has_cookie_source:
            dir_path = _cookie_dir_path()
        else:
            dir_path = None
        if dir_path is not None:
            store = CookieStore(dir_path)
            store.load_if_changed(self._client)
            loaded = store.current_string()
            if loaded:
                print(
                    f"Cookie 已从目录种子化: {store.dir_path} "
                    f"({len(loaded.split(';'))} 个字段)",
                    flush=True,
                )
            else:
                print(
                    f"【COOKIE_EMPTY】目录 {store.dir_path} 不存在或无 *.txt 文件",
                    flush=True,
                )
            self._cookie_store = store
            return True  # 目录模式下不抛硬错误，让 health check 驱动更新

        cookie_str = os.getenv("EASTMONEY_COOKIE", "").strip()
        source = "环境变量 EASTMONEY_COOKIE"
        if not cookie_str:
            cookie_str = self._load_persisted_cookie()
            source = "持久化文件"
        if not cookie_str:
            return False
        self._seed_from_string(cookie_str)
        print(f"Cookie 已种子化 (来源: {source}): {self._mask_cookie(cookie_str)}", flush=True)
        return True

    def _seed_from_string(self, cookie_str: str) -> None:
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                self._client.cookies.set(key, value, domain=".eastmoney.com")

    @staticmethod
    def _mask_cookie(cookie_str: str) -> str:
        if len(cookie_str) <= 40:
            return cookie_str
        return cookie_str[:40] + "..."

    def _get_cookie_string(self) -> str:
        parts = []
        for c in self._client.cookies.jar:
            if c.value:
                parts.append(f"{c.name}={c.value}")
        return "; ".join(parts)

    # ------------------------------------------------------------------ #
    # Cookie 诊断日志 (新增 2026-08-21: 让用户能直观看到 Cookie 状态)
    # ------------------------------------------------------------------ #
    def _log_cookie_status(self, tag: str = "状态") -> None:
        """打印 Cookie 当前状态. 启动时 tag="启动", 文件变化时 tag="热加载"."""
        if self._cookie_store is None:
            cookie_str = self._get_cookie_string()
            if not cookie_str:
                print(
                    f"【COOKIE_{tag}】未配置 Cookie → kline 请求会被服务端静默拒绝\n"
                    "  → 请设置环境变量 EASTMONEY_COOKIE 或 FIN_COOKIE_DIR 指向 *.txt 目录",
                    flush=True,
                )
            else:
                field_count = len([p for p in cookie_str.split(";") if "=" in p])
                print(
                    f"【COOKIE_{tag}】fields={field_count} (单文件模式)",
                    flush=True,
                )
            return

        dir_path = self._cookie_store.dir_path
        if not dir_path.exists() or not dir_path.is_dir():
            print(
                    f"【COOKIE_{tag}】目录 {dir_path} 不存在 → kline 请求会被服务端静默拒绝\n"
                    "  → 请创建该目录并放入浏览器复制的 Cookie (*.txt 文件)",
                    flush=True,
                )
            return

        files = [p for p in dir_path.glob("*.txt") if p.is_file()]
        if not files:
            print(
                    f"【COOKIE_{tag}】目录 {dir_path} 下无 *.txt 文件 → 会被服务端静默拒绝\n"
                    "  → 请放入浏览器 F12 → push2his.eastmoney.com 请求头里的 Cookie",
                    flush=True,
                )
            return

        oldest = min(files, key=lambda p: p.stat().st_mtime)
        age_days = (time.time() - oldest.stat().st_mtime) / 86400
        cookie_str = self._cookie_store.current_string()
        field_count = (
            len([p for p in cookie_str.split(";") if "=" in p]) if cookie_str else 0
        )

        age_hint = ""
        if age_days > 14:
            age_hint = " ⚠️ 较旧 (超过 14 天), 建议从浏览器 F12 复制新 Cookie"
        elif age_days > 7:
            age_hint = " (7 天以上, 接近过期, 可考虑更换)"

        print(
            f"【COOKIE_{tag}】file={oldest.name} age={age_days:.1f}d "
            f"fields={field_count}{age_hint}",
            flush=True,
        )

    def _log_cookie_invalid(self, reason: str) -> None:
        """打印可执行的 Cookie 失效处理步骤."""
        if self._cookie_store is not None:
            path = self._cookie_store.dir_path
            mode = "目录模式"
        else:
            path = _cookie_file_path()
            mode = "单文件模式"
        print(
            f"【COOKIE_INVALID】{reason}\n"
            f"  → 当前 Cookie 已失效, kline 数据将无法从东财获取\n"
            f"  → 处理步骤:\n"
            f"     1. 浏览器打开任意 ETF 详情页 (如 https://quote.eastmoney.com/sh510500.html)\n"
            f"     2. F12 → Network → 找到 push2his.eastmoney.com 请求 → 复制完整 Cookie\n"
            f"     3. 粘贴到 {path} ({mode})\n"
            f"     4. 替换后无需重启, 下次抓取会自动读取新 Cookie",
            flush=True,
        )

    # ------------------------------------------------------------------ #
    # Cookie 冷却期控制
    # ------------------------------------------------------------------ #
    def _can_refresh_cookie(self) -> bool:
        if self._cookie_last_refreshed_at is None:
            return True
        return (time.time() - self._cookie_last_refreshed_at) >= self._cookie_cooldown_seconds

    def _reset_refresh_cooldown(self) -> None:
        self._cookie_last_refreshed_at = None

    async def _refresh_cookie_from_server(self) -> bool:
        """尝试通过请求东财接口触发 Set-Cookie。

        注意：东财的 ``qgqp_b_id`` 等关键 cookie 通常只在浏览器首次访问时由
        前端 JS 写入，这套 HTTP 流程通常**拿不到新 cookie**。因此函数只有在
        cookie jar 真的发生变化时才返回 ``True``，否则返回 ``False`` 让调用方
        走指数退避重试，而不是把"看似 200"当成"刷新成功"白白浪费冷却预算。
        """
        before = self._get_cookie_string()
        ua = random_user_agent()
        # 浏览器首页用 HTML Accept 即可
        html_headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        # push2his kline 是 JSON API，仿照 Java Feign 客户端的 headers，
        # 关键是要带 Referer，否则东财会直接断连
        kline_headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Host": "push2his.eastmoney.com",
            "Referer": "https://quote.eastmoney.com/sh510500.html",
            "sec-fetch-dest": "script",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "same-site",
            "pragma": "no-cache",
        }
        # 候选 URL：依次尝试，谁先下发新 Set-Cookie 就用谁
        # 第二个为 push2his kline 接口，可以拿到最贴合 kline 数据请求的 cookie
        candidates = [
            ("https://www.eastmoney.com/", html_headers),
            (
                "https://push2his.eastmoney.com/api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6%2Cf7%2Cf8%2Cf9%2Cf10%2Cf11%2Cf12%2Cf13&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&beg=0&end=20500101&secid=1.510500&klt=101&fqt=0&ut=fa5fd1943c7b386f172d6893dbfba10b&smplmt=1000000&lmt=1000000&_=1779428378597",
                kline_headers,
            ),
            ("https://quote.eastmoney.com/sh510050.html", html_headers),
        ]
        for url, headers in candidates:
            try:
                resp = await self._client.get(
                    url, headers=headers, follow_redirects=True, timeout=30
                )
                resp.raise_for_status()
            except Exception as exc:
                print(f"Cookie 刷新请求失败 ({url}): {exc}", flush=True)
                continue
            after = self._get_cookie_string()
            if after != before:
                self._cookie_last_refreshed_at = time.time()
                print(
                    f"Cookie 刷新生效 ({url}) 字段变化: "
                    f"{len(before)} -> {len(after)} chars",
                    flush=True,
                )
                return True

        print(
            "Cookie 刷新无效：所有候选 URL 都未下发新的 Set-Cookie。"
            "东财关键 cookie 需浏览器手动复制后再注入 EASTMONEY_COOKIE。",
            flush=True,
        )
        return False

    # ------------------------------------------------------------------ #
    # K 线抓取（自定义重试 + 指数退避 + Cookie 刷新）
    # ------------------------------------------------------------------ #
    async def kline(
        self, fields1: str, fields2: str, beg: int, end: int, secid: str, klt: int, fqt: int
    ) -> str:
        if not self._seeded:
            raise RuntimeError("请先设置环境变量 EASTMONEY_COOKIE（从浏览器复制请求 Cookie）")

        if self._cookie_store is not None:
            # load_if_changed 返回 True 表示文件自上次加载后发生变化
            if self._cookie_store.load_if_changed(self._client):
                self._log_cookie_status(tag="热加载")
        cookie_str = self._get_cookie_string()
        if not cookie_str:
            print("【COOKIE_EMPTY】未发现任何 Cookie，跳过请求", flush=True)
            return ""

        market, code = secid.split(".", 1)
        prefix = "sz" if market == "0" else "sh"
        referer = f"https://quote.eastmoney.com/{prefix}{code}.html"

        xhr_headers = {
            "User-Agent": random_user_agent(),
            "Accept": "*/*",
            "Host": "push2his.eastmoney.com",
            "Referer": referer,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "pragma": "no-cache",
            "accept-language": "zh-CN,zh;q=0.9",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-dest": "script",
        }
        xhr_headers["Cookie"] = cookie_str
        params = {
            "fields1": fields1,
            "fields2": fields2,
            "beg": beg,
            "end": end,
            "secid": secid,
            "klt": klt,
            "fqt": fqt,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "smplmt": 1000000,
            "lmt": 1000000,
            "_": int(time.time() * 1000),
        }

        max_retry = 3
        max_refresh = 2
        cookie_refresh_count = 0
        last_exc: Exception | None = None

        for attempt in range(1, max_retry + 1):
            for host in self._kline_hosts:
                headers = dict(xhr_headers)
                try:
                    text = await self.get_text(
                        "/api/qt/stock/kline/get",
                        params=params,
                        headers=headers,
                        base_url_override=host,
                        retry=False,
                    )
                    if text:
                        health = self._cookie_health.check(text)
                        if health.invalid:
                            self._log_cookie_invalid(health.reason or "unknown")
                            if await self._cookie_health.refresh_once(self):
                                self._cookie_last_refreshed_at = time.time()
                                cookie_refresh_count += 1
                                new_cookie = self._get_cookie_string()
                                masked_cookie = self._mask_cookie(new_cookie)
                                print(
                                    f"【COOKIE_REFRESHED #{cookie_refresh_count}】{masked_cookie}",
                                    flush=True,
                                )
                                if self._cookie_store is None:
                                    self._persist_cookie(new_cookie)
                                xhr_headers["Cookie"] = new_cookie
                                try:
                                    text = await self.get_text(

                                        "/api/qt/stock/kline/get",
                                        params=params,
                                        headers=dict(xhr_headers),
                                        base_url_override=host,
                                        retry=False,
                                    )
                                    if text:
                                        return text
                                except (
                                    httpx.RemoteProtocolError,
                                    httpx.ReadError,
                                    httpx.ConnectError,
                                    httpx.TimeoutException,
                                ):
                                    pass
                            continue
                        return text
                    raise httpx.ReadError("empty kline response body")
                except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    if cookie_refresh_count < max_refresh and self._can_refresh_cookie():
                        if await self._refresh_cookie_from_server():
                            cookie_refresh_count += 1
                            new_cookie = self._get_cookie_string()
                            print(f"【COOKIE_REFRESHED #{cookie_refresh_count}】{self._mask_cookie(new_cookie)}", flush=True)
                            if self._cookie_store is None:
                                self._persist_cookie(new_cookie)
                            if new_cookie:
                                xhr_headers["Cookie"] = new_cookie
                            headers = dict(xhr_headers)
                            try:
                                text = await self.get_text(
                                    "/api/qt/stock/kline/get",
                                    params=params,
                                    headers=headers,
                                    base_url_override=host,
                                    retry=False,
                                )
                                if text:
                                    return text
                            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.TimeoutException):
                                pass
                            # refresh 真正拿到了新 cookie，重置冷却期让后续 host/attempt 还能再用一次
                            self._reset_refresh_cooldown()
                        else:
                            # refresh 失败时不计入计数、不重置冷却，避免空转
                            print("Cookie 刷新失败（无新 Set-Cookie），走指数退避重试", flush=True)
                    elif cookie_refresh_count >= max_refresh:
                        print(f"Cookie 已刷新 {cookie_refresh_count} 次，不再刷新", flush=True)
                    elif not self._can_refresh_cookie():
                        remaining = self._cookie_cooldown_seconds - (time.time() - (self._cookie_last_refreshed_at or 0))
                        print(f"Cookie刷新冷却中，距离下次可刷新还有 {int(remaining)} 秒", flush=True)
                    continue
                except Exception as exc:
                    last_exc = exc
                    continue

            if attempt >= max_retry:
                break
            backoff = (2 ** attempt) + random.random()
            time.sleep(backoff)

        if last_exc:
            raise last_exc
        return ""

    # ------------------------------------------------------------------ #
    # 代码列表
    # ------------------------------------------------------------------ #
    async def code_list(self, pn: int, pz: int, np: int, fs: str, fields: str) -> Any:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Cache-Control": "no-cache",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        if self._cookie_store is not None:
            self._cookie_store.load_if_changed(self._client)
            cookie = self._cookie_store.current_string()
        else:
            cookie = self._load_persisted_cookie()
            if not cookie:
                cookie = os.getenv("EASTMONEY_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie
        params = {"pn": pn, "pz": pz, "np": np, "fs": fs, "fields": fields}
        return await self.get_json("/api/qt/clist/get", params=params, headers=headers)
