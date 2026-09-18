"""网络层: meta 元信息 + zip 流式下载.

设计要点:
  - 用 stdlib requests.get, 不复用 app.clients.* (那里都是业务专属 client)
  - 进度通过 progress_cb(downloaded, total) 回调, 上层 (fetcher) 写 task state
  - 下载失败时清理半成品 dest 文件
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import requests

from app.services.tdx_daily_fetcher.constants import (
    META_URL,
    REFERER,
    USER_AGENT,
)
from app.services.tdx_daily_fetcher.exceptions import (
    DownloadError,
    MetaParseError,
)
from app.services.tdx_daily_fetcher.meta import MetaInfo, parse_meta_info

ProgressCb = Callable[[int, int], None]


_DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
}


def fetch_meta(url: str = META_URL, *, timeout: float = 15.0) -> MetaInfo:
    """GET 元信息 → 解析 → MetaInfo.

    Raises:
        MetaParseError: 网络错 / 格式变更
    """
    try:
        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise MetaParseError(f"无法连接 TDX 元信息接口: {exc}") from exc
    return parse_meta_info(resp.text)


def download_zip(
    url: str,
    dest_path: Path,
    *,
    progress_cb: ProgressCb | None = None,
    timeout: float = 60.0,
    chunk_size: int = 256 * 1024,
) -> int:
    """流式下载到磁盘. 路径经过 Return: 写入字节数.

    Raises:
        DownloadError: 网络中断 / HTTP 非 200 / dest_path 无法写入
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(
            url, headers=_DEFAULT_HEADERS, timeout=timeout, stream=True,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DownloadError(f"下载失败: {exc}") from exc

    try:
        total_header = resp.headers.get("Content-Length")
        total_size = int(total_header) if total_header else 0
    except ValueError:
        total_size = 0

    downloaded = 0
    try:
        with dest_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb is not None and total_size:
                    progress_cb(downloaded, total_size)
    except requests.RequestException as exc:
        # 中途断网 — 清理半成品
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise DownloadError(f"下载中断 (已下载 {downloaded} bytes): {exc}") from exc
    except OSError as exc:
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise DownloadError(f"写盘失败: {exc}") from exc

    if progress_cb is not None and total_size:
        progress_cb(downloaded, total_size)
    return downloaded
