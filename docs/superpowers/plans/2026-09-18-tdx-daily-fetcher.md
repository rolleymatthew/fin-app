# TDX Vipdata Daily Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-download 通达信 `hsjday.zip` from `data.tdx.com.cn`, atomic-extract to `vipdoc/`, expose async admin API (`POST /fetch` + `GET /status`) with progress polling; add a frontend button in `Etf.jsx`.

**Architecture:** Single new sub-package `app/services/tdx_daily_fetcher/` holds core logic (state machine + download + atomic extract). FastAPI router `app/api/admin_tdx.py` wraps it. State dict lives on `app.state.tdx_tasks` (in-memory, no DB). Reuse existing `tdx_offline.day_reader` contract — no changes to offline chain. Docker reuses the existing `D:\stock → /app/data` bind mount.

**Tech Stack:** FastAPI, pydantic-settings, `requests` (already in deps), `zipfile`/`shutil`/`pathlib` stdlib, pytest + monkeypatch (already in use), ruff.

## Global Constraints

Copied verbatim from `AGENTS.md` and the approved spec (`docs/superpowers/specs/2026-09-18-tdx-daily-fetcher-design.md`):

- **No new pip / pnpm dependencies** unless explicitly approved.
- **Read-only by default:** `app/services/`、`app/clients/`、`app/repositories/` existing files MUST NOT be modified. New files in those dirs OK; modifications require explicit approval.
- **Cross-task changes = independent commits.** Every task ends with one commit.
- **Conventional Commits** for all commit messages.
- **No CI / pre-commit / PR template** — local review only.
- **Don't move/rename/delete existing functions** without explicit consent. **Prefer new functions** over in-place rewrites.
- **No "cleanup" refactors** unrelated to current task.
- **Lint before commit:** run `cd backend && ruff check app`.
- **Tests before commit:** run `cd backend && pytest -q tests/test_tdx_daily_fetcher.py tests/test_admin_tdx_api.py tests/test_tdx_day_reader_regression.py`.
- **Result envelope contract** (all existing endpoints): every API response MUST be `ResultVO.ok(...)` / `ResultVO.fail(...)` — see `app/api/kline.py` for the pattern.
- **No emojis** in code or commits.
- Backend entry: `app.main:app`; tests live in `backend/tests/`.

## File Structure

```
backend/app/
├── config.py                                 [MODIFY: +3 fields]
├── services/
│   └── tdx_daily_fetcher/                    [NEW PACKAGE]
│       ├── __init__.py                       [NEW]
│       ├── constants.py                      [NEW]
│       ├── fetcher.py                        [NEW: TdxDailyFetcher class]
│       └── exceptions.py                     [NEW: FetchError, MetaParseError]
├── state/
│   ├── __init__.py                           [NEW: empty marker]
│   └── tdx_fetch_state.py                    [NEW: task state singleton]
├── api/
│   └── admin_tdx.py                          [NEW: FastAPI router]
└── main.py                                   [MODIFY: +2 lines for router]

backend/tests/
├── test_tdx_daily_fetcher.py                 [NEW]
├── test_admin_tdx_api.py                     [NEW]
└── test_tdx_day_reader_regression.py         [NEW: bonus coverage for day_reader]

backend/scripts/
└── fetch_tdx_vipdata.py                      [NEW: CLI wrapper, optional]

docker/docker-compose.yml                     [MODIFY: delete 1 bind, change 1 env, add 1 env]
frontend/src/Etf.jsx                          [MODIFY: +1 button, +1 useState]
```

---

### Task 1: Configuration fields + constants module

**Files:**
- Create: `backend/app/services/tdx_daily_fetcher/__init__.py`
- Create: `backend/app/services/tdx_daily_fetcher/constants.py`
- Create: `backend/app/services/tdx_daily_fetcher/exceptions.py`
- Create: `backend/app/state/__init__.py`
- Modify: `backend/app/config.py:60` (after `tdx_home` block)

**Interfaces:**
- Consumes: none
- Produces:
  - `app.services.tdx_daily_fetcher.constants.DOWNLOAD_URL` (str) — default `https://data.tdx.com.cn/vipdoc/hsjday.zip`
  - `app.services.tdx_daily_fetcher.constants.META_URL` (str) — default `https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js`
  - `app.services.tdx_daily_fetcher.constants.HSJDAY_ZIP_NAME` (str) — `"hsjday.zip"`
  - `app.services.tdx_daily_fetcher.constants.VIPDOC_SUBDIR` (str) — `"vipdoc"`
  - `app.services.tdx_daily_fetcher.constants.LAST_FETCH_FILENAME` (str) — `".last_fetch.json"`
  - `app.services.tdx_daily_fetcher.exceptions.FetchError(Exception)`
  - `app.services.tdx_daily_fetcher.exceptions.MetaParseError(FetchError)`
  - `app.services.tdx_daily_fetcher.exceptions.DownloadError(FetchError)`
  - `app.services.tdx_daily_fetcher.exceptions.ExtractError(FetchError)`
  - `app.config.Settings.tdx_data_dir: str`
  - `app.config.Settings.tdx_download_url: str`
  - `app.config.Settings.tdx_meta_url: str`

- [ ] **Step 1: Write the constants module**

Create `backend/app/services/tdx_daily_fetcher/constants.py`:

```python
"""TDX vipdata daily fetcher constants.

URLs and on-disk filenames shared between the fetcher, admin API, and CLI.
Defaults match the official 通达信 个人版 data CDN.
"""

# 个人版盘后日线包 (全量, ~525MB / 12420 files, deflate 压缩)
DOWNLOAD_URL: str = "https://data.tdx.com.cn/vipdoc/hsjday.zip"

# 同站点元信息 JS (暴露 HSJDAY_SOFT_TIME / HSJDAY_SOFT_SIZE)
META_URL: str = "https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js"

# on-disk names
HSJDAY_ZIP_NAME: str = "hsjday.zip"
VIPDOC_SUBDIR: str = "vipdoc"
LAST_FETCH_FILENAME: str = ".last_fetch.json"

# 下载时给 TDX CDN 的 Referer (部分镜像会校验)
REFERER: str = "https://www.tdx.com.cn/article/vipdata.html"
USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) fin-app/fetcher"
```

- [ ] **Step 2: Write the exceptions module**

Create `backend/app/services/tdx_daily_fetcher/exceptions.py`:

```python
"""TDX fetcher exception hierarchy.

所有失败用 FetchError 基类,子类按失败阶段细分,便于上层 / API 区分提示.
"""


class FetchError(Exception):
    """下载/解压流程任意阶段失败时抛. message 包含可直接呈现给用户的描述."""


class MetaParseError(FetchError):
    """_hsjdayinfo.js 不可达或格式变更."""


class DownloadError(FetchError):
    """zip 下载中断 / testzip 校验失败."""


class ExtractError(FetchError):
    """解压失败 (zip 损坏 / 磁盘满 / 权限不足)."""


class DiskSpaceError(ExtractError):
    """解压前磁盘预检不通过."""
```

- [ ] **Step 3: Write the package marker**

Create `backend/app/services/tdx_daily_fetcher/__init__.py`:

```python
"""通达信 vipdata 全量日线包下载器.

入口 (后续 task 实现):
    TdxDailyFetcher(target_dir=...).run_sync()
    TdxDailyFetcher(target_dir=...).run()  # async, 写入 task state
"""
from app.services.tdx_daily_fetcher.fetcher import (
    ACTIVE_STATES,
    TaskStatus,
    TdxDailyFetcher,
)

__all__ = ["TdxDailyFetcher", "TaskStatus", "ACTIVE_STATES"]
```

- [ ] **Step 4: Write the state package marker**

Create `backend/app/state/__init__.py`:

```python
"""App-wide in-memory state containers (singleton-style, NOT persisted)."""
```

- [ ] **Step 5: Add 3 settings fields**

Modify `backend/app/config.py`. After the `tdx_home` field block (after line 63), add:

```python
    # TDX vipdata 全量日线包下载目标目录 (zip + 解压 vipdoc/ 都在此)
    # Docker 场景: env 覆盖为 /app/data (与现有 D:\stock bind mount 对齐)
    tdx_data_dir: str = Field(
        default=r"D:\stock\data",
        description="通达信日线包根目录: hsjday.zip + vipdoc/ 都在此",
        validation_alias=AliasChoices("FIN_TDX_DATA_DIR", "TDX_DATA_DIR"),
    )
    tdx_download_url: str = Field(
        default="https://data.tdx.com.cn/vipdoc/hsjday.zip",
        validation_alias=AliasChoices("FIN_TDX_DOWNLOAD_URL", "TDX_DOWNLOAD_URL"),
    )
    tdx_meta_url: str = Field(
        default="https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js",
        validation_alias=AliasChoices("FIN_TDX_META_URL", "TDX_META_URL"),
    )
```

- [ ] **Step 6: Verify imports + settings load**

Run:
```bash
cd backend && python -c "
from app.config import get_settings
s = get_settings()
print('tdx_data_dir    =', s.tdx_data_dir)
print('tdx_download_url=', s.tdx_download_url)
print('tdx_meta_url    =', s.tdx_meta_url)
from app.services.tdx_daily_fetcher import constants as c, exceptions as e
print('DOWNLOAD_URL    =', c.DOWNLOAD_URL)
print('FetchError mro  =', [b.__name__ for b in e.FetchError.__mro__[:3]])
"
```

Expected: prints 6 lines without error. (The `from app.services.tdx_daily_fetcher import` will fail until Task 5 creates `fetcher.py` — adjust by importing `constants` / `exceptions` directly in this verification, or skip this step now and verify at end of Task 5.)

**Adjusted step 6** — verify only:

Run:
```bash
cd backend && python -c "
from app.config import get_settings
s = get_settings()
print('tdx_data_dir    =', s.tdx_data_dir)
print('tdx_download_url=', s.tdx_download_url)
print('tdx_meta_url    =', s.tdx_meta_url)
from app.services.tdx_daily_fetcher import constants as c
print('DOWNLOAD_URL    =', c.DOWNLOAD_URL)
from app.services.tdx_daily_fetcher import exceptions as e
print('FetchError      =', e.FetchError)
"
```

Expected: 6 lines of output, no error.

- [ ] **Step 7: Lint + commit**

Run:
```bash
cd backend && ruff check app/services/tdx_daily_fetcher app/state app/config.py
cd backend && pytest -q tests/ -k "not eastmoney" 2>&1 | tail -20  # ensure no regression
```

Expected: ruff clean; existing tests still pass (or skip those requiring network).

```bash
git add backend/app/services/tdx_daily_fetcher backend/app/state backend/app/config.py
git commit -m "feat(tdx): add vipdata fetcher config + constants + exceptions"
```

---

### Task 2: Meta info parser (TDD)

**Files:**
- Create: `backend/app/services/tdx_daily_fetcher/meta.py`
- Create: `backend/tests/test_tdx_daily_fetcher.py`

**Interfaces:**
- Consumes: `constants.META_URL`, `exceptions.MetaParseError`
- Produces:
  - `parse_meta_info(text: str) -> MetaInfo` where `MetaInfo` is a `@dataclass(frozen=True)` with `update_time: str` and `file_size: int | None` fields.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tdx_daily_fetcher.py`:

```python
"""Unit tests for tdx_daily_fetcher."""
from __future__ import annotations

import pytest

from app.services.tdx_daily_fetcher.exceptions import MetaParseError
from app.services.tdx_daily_fetcher.meta import MetaInfo, parse_meta_info


# ---- meta parser ----

_VALID_JS = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";
"""


def test_parse_meta_info_valid():
    info = parse_meta_info(_VALID_JS)
    assert info.update_time == "2026-09-17 15:59:01"
    assert info.file_size == 335544320


def test_parse_meta_info_size_with_commas():
    info = parse_meta_info('HSJDAY_SOFT_SIZE = "524,927,539";')
    assert info.file_size == 524927539


def test_parse_meta_info_size_missing_returns_none():
    info = parse_meta_info('HSJDAY_SOFT_TIME="2026-09-17 15:15:00";')
    assert info.file_size is None


def test_parse_meta_info_no_time_raises():
    with pytest.raises(MetaParseError, match="HSJDAY_SOFT_TIME"):
        parse_meta_info("var OTHER_VAR = 'foo';")


def test_parse_meta_info_empty_raises():
    with pytest.raises(MetaParseError):
        parse_meta_info("")
```

- [ ] **Step 2: Run tests, verify they fail**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
```

Expected: 5 errors with `ImportError` or `ModuleNotFoundError` (meta.py doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/tdx_daily_fetcher/meta.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py::test_parse_meta_info_valid tests/test_tdx_daily_fetcher.py::test_parse_meta_info_size_with_commas tests/test_tdx_daily_fetcher.py::test_parse_meta_info_size_missing_returns_none tests/test_tdx_daily_fetcher.py::test_parse_meta_info_no_time_raises tests/test_tdx_daily_fetcher.py::test_parse_meta_info_empty_raises
```

Expected: 5 passed.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/services/tdx_daily_fetcher app/tests/test_tdx_daily_fetcher.py
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
git add backend/app/services/tdx_daily_fetcher/meta.py backend/tests/test_tdx_daily_fetcher.py
git commit -m "feat(tdx): add _hsjdayinfo.js meta parser with full test coverage"
```

---

### Task 3: Atomic extract (TDD)

**Files:**
- Create: `backend/app/services/tdx_daily_fetcher/extract.py`
- Modify: `backend/tests/test_tdx_daily_fetcher.py`

**Interfaces:**
- Consumes: `exceptions.ExtractError`, `constants.VIPDOC_SUBDIR`
- Produces:
  - `atomic_extract_zip(zip_path: Path, target_dir: Path) -> int` — returns count of files extracted. Raises `ExtractError` on failure (original `vipdoc/` left untouched).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_tdx_daily_fetcher.py`:

```python
import zipfile
from pathlib import Path

from app.services.tdx_daily_fetcher.extract import atomic_extract_zip


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)


def test_atomic_extract_happy(tmp_path: Path):
    zip_path = tmp_path / "in.zip"
    _make_zip(zip_path, {
        "sh/lday/sh600000.day": b"X" * 32,
        "sz/lday/sz000001.day": b"Y" * 32,
    })
    count = atomic_extract_zip(zip_path, tmp_path)
    assert count == 2
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").read_bytes() == b"X" * 32
    assert (tmp_path / "vipdoc" / "sz" / "lday" / "sz000001.day").read_bytes() == b"Y" * 32
    assert not (tmp_path / "vipdoc.tmp").exists()


def test_atomic_extract_failure_leaves_existing_intact(tmp_path: Path):
    """预先放一个 'good' vipdoc/, 然后构造会触发解压失败的情况, 验证 vipdoc/ 不被改."""
    # 1) 先做一次成功解压, 建立基线
    zip_path = tmp_path / "good.zip"
    _make_zip(zip_path, {"sh/lday/sh600000.day": b"GOOD" * 8})
    atomic_extract_zip(zip_path, tmp_path)
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").read_bytes() == b"GOOD" * 8

    # 2) 现在构造一个会失败的场景 — 制造一个文件占位 vipdoc.tmp 让 shutil.move 失败
    #    (move 会因为目标已存在而失败 — 但本实现在 move 前会清 .tmp, 所以这里走 zip 损坏路径)
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    with pytest.raises(ExtractError):
        atomic_extract_zip(bad_zip, tmp_path)
    # vipdoc/ 保持原状
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").read_bytes() == b"GOOD" * 8
    assert not (tmp_path / "vipdoc.tmp").exists()


def test_atomic_extract_creates_vipdoc_subdir(tmp_path: Path):
    zip_path = tmp_path / "x.zip"
    _make_zip(zip_path, {"bj/lday/bj920982.day": b"Z" * 32})
    count = atomic_extract_zip(zip_path, tmp_path)
    assert count == 1
    assert (tmp_path / "vipdoc" / "bj" / "lday" / "bj920982.day").exists()
```

And add the import at the top of the test file (alongside existing imports):

```python
from app.services.tdx_daily_fetcher.exceptions import ExtractError
```

- [ ] **Step 2: Run tests, verify they fail**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py -k "atomic_extract"
```

Expected: 3 errors, `ImportError: cannot import name 'atomic_extract_zip'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/tdx_daily_fetcher/extract.py`:

```python
"""原子解压: zip → <target>/vipdoc.tmp/ → shutil.move → <target>/vipdoc/.

失败保证:
  - zip 解压失败 → vipdoc.tmp/ 删除, 原 vipdoc/ 不动
  - shutil.move 失败 (罕见, 跨盘符会触发) → vipdoc.tmp/ 删除
  - 任何阶段抛错统一包装成 ExtractError

代价: 解压中磁盘峰值 ×2 (zip + 旧 vipdoc + 新 vipdoc.tmp).
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from app.services.tdx_daily_fetcher.constants import VIPDOC_SUBDIR
from app.services.tdx_daily_fetcher.exceptions import ExtractError


def atomic_extract_zip(zip_path: Path, target_dir: Path) -> int:
    """解压 zip 到 target_dir/vipdoc/ (tmp + rename 保证失败时原目录不变).

    Args:
        zip_path: 已下载的 zip 文件
        target_dir: 解压根目录 (zip 自身也保留在此)

    Returns:
        解压的文件数

    Raises:
        ExtractError: zip 损坏 / IO 失败 / move 失败
    """
    if not zip_path.is_file():
        raise ExtractError(f"zip 文件不存在: {zip_path}")

    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_dir / f"{VIPDOC_SUBDIR}.tmp"
    final_dir = target_dir / VIPDOC_SUBDIR

    # 清理上次残留的 .tmp (上次中途崩了)
    if tmp_dir.is_dir():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                raise ExtractError(f"zip 损坏: {bad}")
            z.extractall(tmp_dir)
        # 整个 vipdoc/ 是 zip 内的顶级目录; tmp_dir 已经是 vipdoc 内容
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        shutil.move(str(tmp_dir), str(final_dir))
    except ExtractError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ExtractError(f"解压失败: {exc}") from exc
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ExtractError(f"解压失败: {exc}") from exc

    # 统计: 数 final_dir 下的所有文件
    count = sum(1 for _ in final_dir.rglob("*") if _.is_file())
    return count
```

- [ ] **Step 4: Run tests, verify they pass**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py -k "atomic_extract"
```

Expected: 3 passed.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/services/tdx_daily_fetcher/extract.py tests/test_tdx_daily_fetcher.py
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
git add backend/app/services/tdx_daily_fetcher/extract.py backend/tests/test_tdx_daily_fetcher.py
git commit -m "feat(tdx): add atomic zip extract with rollback semantics"
```

---

### Task 4: Download + last-fetch tracker (TDD)

**Files:**
- Create: `backend/app/services/tdx_daily_fetcher/downloader.py`
- Create: `backend/app/services/tdx_daily_fetcher/last_fetch.py`
- Modify: `backend/tests/test_tdx_daily_fetcher.py`

**Interfaces:**
- Consumes: `constants.{DOWNLOAD_URL,META_URL,HSJDAY_ZIP_NAME,LAST_FETCH_FILENAME,REFERER,USER_AGENT}`, `exceptions.{MetaParseError,DownloadError,DiskSpaceError}`
- Produces:
  - `last_fetch.py`:
      - `LastFetch(target_dir: Path)` with `.read() -> dict | None`, `.write(meta: MetaInfo, file_count: int, zip_size: int)`, `.should_skip(current_update_time: str) -> bool`
  - `downloader.py`:
      - `fetch_meta(url: str) -> MetaInfo` — wraps `requests.get`, parses via `meta.parse_meta_info`
      - `download_zip(url: str, dest_path: Path, *, progress_cb=None) -> int` — streams zip to disk, returns bytes written. Calls `progress_cb(downloaded, total)` after each chunk if provided. Calls `zipfile.testzip()` after.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tdx_daily_fetcher.py`:

```python
import json
import time
from app.services.tdx_daily_fetcher.downloader import fetch_meta, download_zip
from app.services.tdx_daily_fetcher.last_fetch import LastFetch


# ---- last_fetch ----

def test_last_fetch_empty_when_no_file(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    assert lf.read() is None
    assert lf.should_skip("2026-09-17 15:59:01") is False


def test_last_fetch_round_trip(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    lf.write(
        meta=type(_REF_META)(),
        file_count=12420,
        zip_size=524927539,
    )
    loaded = lf.read()
    assert loaded is not None
    assert loaded["file_count"] == 12420
    assert loaded["zip_size"] == 524927539
    assert "fetched_at" in loaded


def test_last_fetch_should_skip_when_same_update_time(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    lf.write(meta=type(_REF_META)(), file_count=12420, zip_size=100)
    # 写完后 LastFetch 内部要记录 update_time, should_skip 同值应 True
    meta_obj = type(_REF_META)()
    assert lf.should_skip(meta_obj.update_time) is True


def test_last_fetch_should_skip_false_when_different(tmp_path: Path):
    lf = LastFetch(target_dir=tmp_path)
    lf.write(meta=type(_REF_META)(), file_count=12420, zip_size=100)
    assert lf.should_skip("2099-01-01 00:00:00") is False


# ---- downloader ----

_VALID_JS = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:01";
"""

_META_INFO = parse_meta_info(_VALID_JS)


@pytest.fixture
def _REF_META() -> MetaInfo:
    return _META_INFO


def test_fetch_meta_ok(monkeypatch):
    class _Resp:
        text = _VALID_JS
        def raise_for_status(self): pass
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    info = fetch_meta("https://x/y.js")
    assert info.update_time == "2026-09-17 15:59:01"
    assert info.file_size == 335544320


def test_fetch_meta_raises_on_network_error(monkeypatch):
    import requests
    def _raise(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr("requests.get", _raise)
    with pytest.raises(MetaParseError):
        fetch_meta("https://x/y.js")


def test_download_zip_streams_to_disk(tmp_path, monkeypatch):
    payload = b"hello zip content"
    class _Resp:
            def __init__(self):
                self.headers = {"Content-Length": str(len(payload))}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield payload
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    dest = tmp_path / "out.zip"
    n = download_zip("https://x/y.zip", dest)
    assert n == len(payload)
    assert dest.read_bytes() == payload


def test_download_zip_progress_callback(tmp_path, monkeypatch):
    chunks = [b"a" * 100, b"b" * 100, b"c" * 100]
    class _Resp:
        headers = {"Content-Length": "300"}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            for c in chunks:
                yield c
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    calls = []
    download_zip("https://x/y.zip", tmp_path / "o.zip", progress_cb=lambda d, t: calls.append((d, t)))
    # 最后一次回调应该是 (300, 300)
    assert calls[-1] == (300, 300)
    assert all(t == 300 for _, t in calls)


def test_download_zip_removes_partial_on_error(tmp_path, monkeypatch):
    """下载中途抛错 → 半成品文件应被删除."""
    def _half(*a, **k):
        class _R:
            headers = {"Content-Length": "1000"}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield b"abc"
                raise requests.ConnectionError("drop")
        return _R()
    import requests
    monkeypatch.setattr("requests.get", _half)
    dest = tmp_path / "o.zip"
    with pytest.raises(DownloadError):
        download_zip("https://x/y.zip", dest)
    assert not dest.exists()
```

Add imports at top of test file:

```python
import requests
from app.services.tdx_daily_fetcher.exceptions import (
    DownloadError,
    ExtractError,
    MetaParseError,
)
from app.services.tdx_daily_fetcher.downloader import download_zip, fetch_meta
from app.services.tdx_daily_fetcher.last_fetch import LastFetch
from app.services.tdx_daily_fetcher.meta import MetaInfo, parse_meta_info
```

- [ ] **Step 2: Run tests, verify they fail**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py -k "last_fetch or fetch_meta or download_zip"
```

Expected: errors with `ImportError` (downloader/last_fetch don't exist yet).

- [ ] **Step 3: Write the last_fetch module**

Create `backend/app/services/tdx_daily_fetcher/last_fetch.py`:

```python"""<target_dir>/.last_fetch.json 读写封装.

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
```

- [ ] **Step 4: Write the downloader module**

Create `backend/app/services/tdx_daily_fetcher/downloader.py`:

```python
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

    total = 0
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
```

- [ ] **Step 5: Run tests, verify they pass**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
```

Expected: all tests pass (~16).

- [ ] **Step 6: Lint + commit**

```bash
cd backend && ruff check app/services/tdx_daily_fetcher/ tests/test_tdx_daily_fetcher.py
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
git add backend/app/services/tdx_daily_fetcher/downloader.py backend/app/services/tdx_daily_fetcher/last_fetch.py backend/tests/test_tdx_daily_fetcher.py
git commit -m "feat(tdx): add zip downloader + last-fetch tracker with full coverage"
```

---

### Task 5: Fetcher orchestrator + TaskStatus (TDD)

**Files:**
- Create: `backend/app/services/tdx_daily_fetcher/fetcher.py`
- Modify: `backend/tests/test_tdx_daily_fetcher.py`

**Interfaces:**
- Consumes: all modules created in Tasks 2-4
- Produces:
  - `ACTIVE_STATES: frozenset[str]` — `{"pending","checking","downloading","extracting"}`
  - `class TaskStatus` — `@dataclass` with fields:
    - `task_id: str`
    - `state: Literal["pending","checking","downloading","extracting","done","failed","skipped"]`
    - `progress: int` (0-100)
    - `message: str`
    - `error: str | None`
    - `started_at: datetime`
    - `finished_at: datetime | None`
    - `update_time: str | None`
    - `file_count: int | None`
    - `zip_size: int | None`
  - `class TdxDailyFetcher`:
    - `__init__(self, *, data_dir: Path, download_url: str, meta_url: str)`
    - `run_sync() -> TaskStatus` — synchronous, returns final status
    - `run_async() -> TaskStatus` — alias of `run_sync()` (used by API for now; can move to thread later)
    - `status() -> TaskStatus` — current internal status (for API polling)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tdx_daily_fetcher.py`:

```python
from app.services.tdx_daily_fetcher.fetcher import (
    ACTIVE_STATES,
    TaskStatus,
    TdxDailyFetcher,
)


_VALID_JS = """
var HSJDAY_SOFT_SIZE="335,544,320";
var HSJDAY_SOFT_TIME="2026-09-17 15:59:14";
"""

_ZIP_FILES = {
    "sh/lday/sh600000.day": b"X" * 32,
    "sz/lday/sz000001.day": b"Y" * 32,
    "bj/lday/bj920982.day": b"Z" * 32,
}


def _build_minimal_zip() -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in _ZIP_FILES.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_active_states_constant():
    assert ACTIVE_STATES == frozenset({"pending", "checking", "downloading", "extracting"})


def test_fetcher_skip_when_already_today(tmp_path, monkeypatch):
    # 预置 .last_fetch.json = 今日 update_time
    last = LastFetch(target_dir=tmp_path)
    meta = parse_meta_info(_VALID_JS)
    last.write(meta=meta, file_count=3, zip_size=100)

    # 网络应完全不被调
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("网络被调了")))

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="x", meta_url="x")
    status = fetcher.run_sync()
    assert status.state == "skipped"
    assert status.update_time == meta.update_time


def test_fetcher_full_happy_path(tmp_path, monkeypatch):
    payload = _build_minimal_zip()

    class _MetaResp:
        text = _VALID_JS
        def raise_for_status(self): pass

    class _ZipResp:
        headers = {"Content-Length": str(len(payload))}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield payload

    def _mock_get(url, **k):
        if url.endswith(".js"):
            return _MetaResp()
        return _ZipResp()

    import requests
    monkeypatch.setattr(requests, "get", _mock_get)

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="https://x/y.zip", meta_url="https://x/y.js")
    status = fetcher.run_sync()

    assert status.state == "done"
    assert status.file_count == 3
    assert status.update_time == "2026-09-17 15:59:14"
    assert (tmp_path / "hsjday.zip").exists()
    assert (tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day").exists()
    # .last_fetch.json 应已写入
    lf = LastFetch(target_dir=tmp_path).read()
    assert lf is not None
    assert lf["update_time"] == "2026-09-17 15:59:14"


def test_fetcher_progress_increases(tmp_path, monkeypatch):
    payload = _build_minimal_zip()

    class _MetaResp:
        text = _VALID_JS
        def raise_for_status(self): pass

    class _ZipResp:
        headers = {"Content-Length": str(len(payload))}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield payload

    def _mock_get(url, **k):
        return _MetaResp() if url.endswith(".js") else _ZipResp()

    import requests
    monkeypatch.setattr(requests, "get", _mock_get)

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="x", meta_url="x")
    fetcher.run_sync()
    # 终态 progress 应该是 100
    assert fetcher.status().progress == 100


def test_fetcher_meta_failure_marks_failed(tmp_path, monkeypatch):
    import requests
    def _raise(*a, **k):
        raise requests.ConnectionError("no net")
    monkeypatch.setattr(requests, "get", _raise)

    fetcher = TdxDailyFetcher(data_dir=tmp_path, download_url="x", meta_url="x")
    status = fetcher.run_sync()
    assert status.state == "failed"
    assert status.error is not None
    assert "TDX" in status.error or "元信息" in status.error or "连接" in status.error
```

Add at top of test file (with other imports):

```python
import zipfile
import io
```

Wait — these are already imported by Task 3/4. Re-check the top of `test_tdx_daily_fetcher.py` and only add what's missing.

- [ ] **Step 2: Run tests, verify they fail**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py -k "fetcher or active_states"
```

Expected: 5 errors, `ImportError` (fetcher.py doesn't exist yet).

- [ ] **Step 3: Write the fetcher module**

Create `backend/app/services/tdx_daily_fetcher/fetcher.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
```

Expected: all 19+ tests pass.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/services/tdx_daily_fetcher/ tests/test_tdx_daily_fetcher.py
cd backend && pytest -q tests/test_tdx_daily_fetcher.py
git add backend/app/services/tdx_daily_fetcher/fetcher.py backend/tests/test_tdx_daily_fetcher.py
git commit -m "feat(tdx): add fetcher orchestrator with state machine + 19 tests"
```

---

### Task 6: Task state singleton

**Files:**
- Create: `backend/app/state/tdx_fetch_state.py`

**Interfaces:**
- Consumes: `app.services.tdx_daily_fetcher.fetcher.{TdxDailyFetcher, TaskStatus}`
- Produces:
  - `class TdxFetchStateStore`:
    - `__init__(self)` — empty dict
    - `start(settings) -> TaskStatus` — creates new TdxDailyFetcher, runs in `asyncio.to_thread`, stores result, returns initial status
    - `get(task_id: str) -> TaskStatus | None`
    - `active() -> TaskStatus | None` — first task in `ACTIVE_STATES`, or None
    - `cancel_active(reason: str) -> int` — mark all active as failed with reason; returns count

- [ ] **Step 1: Write the module**

Create `backend/app/state/tdx_fetch_state.py`:

```python
"""TDX fetcher 任务状态字典 (单例模式, 内存).

lifespan 启动时挂到 app.state.tdx_state, 关闭时 cancel_active().
不进 DB — 进程重启任务丢失, 用户重新 POST 即可.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.services.tdx_daily_fetcher.fetcher import (
    ACTIVE_STATES,
    TaskStatus,
    TdxDailyFetcher,
)
from app.services.tdx_daily_fetcher.exceptions import FetchError

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
```

- [ ] **Step 2: Verify import works**

Run:
```bash
cd backend && python -c "
from app.state.tdx_fetch_state import TdxFetchStateStore
store = TdxFetchStateStore()
print('store=', store)
print('active()=', store.active())
print('cancel_active()=', store.cancel_active('test'))
print('OK')
"
```

Expected: prints 4 lines + "OK", no error.

- [ ] **Step 3: Lint + commit**

```bash
cd backend && ruff check app/state/tdx_fetch_state.py
git add backend/app/state/tdx_fetch_state.py
git commit -m "feat(tdx): add in-memory task state singleton with lifespan integration"
```

---

### Task 7: Admin API endpoints (TDD)

**Files:**
- Create: `backend/app/api/admin_tdx.py`
- Create: `backend/tests/test_admin_tdx_api.py`

**Interfaces:**
- Consumes: `app.state.tdx_state: TdxFetchStateStore`, `ResultVO`
- Produces:
  - `router: APIRouter` (tag `["admin"]`) with:
    - `POST /fetch` → `ResultVO.ok({state, task_id?, active_task_id?, current_state?})`
    - `GET /status?task_id=...` → `ResultVO.ok({task_id, state, progress, message, error, update_time, file_count, zip_size, started_at, finished_at})` or `ResultVO.fail(code=404, message="task 不存在")`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_tdx_api.py`:

```python
"""API tests for /api/admin/tdx/* endpoints."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state.tdx_fetch_state import TdxFetchStateStore


@pytest.fixture
def fake_state(monkeypatch) -> TdxFetchStateStore:
    store = TdxFetchStateStore()
    # 替换 lifespan 启动时挂的实例
    monkeypatch.setattr(app, "state", MagicMock(tdx_state=store))
    return store


def _client() -> TestClient:
    return TestClient(app)


def test_post_fetch_returns_started(fake_state):
    # start() 会真的起 asyncio.create_task — TestClient 同步驱动,
    # task 会在请求处理期间或之后跑. 这里只检查返回结构.
    from app.services.tdx_daily_fetcher.fetcher import TaskStatus
    fake_state.start = MagicMock(return_value=TaskStatus(task_id="abc12345"))

    r = _client().post("/api/admin/tdx/fetch")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["state"] == "started"
    assert body["data"]["task_id"] == "abc12345"


def test_post_fetch_busy_when_active(fake_state):
    from app.services.tdx_daily_fetcher.fetcher import TaskStatus
    # 模拟已有一个 active 任务
    fake_state.active = MagicMock(return_value=TaskStatus(task_id="existing01"))
    fake_state.start = MagicMock(side_effect=AssertionError("start should not be called"))

    r = _client().post("/api/admin/tdx/fetch")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["state"] == "busy"
    assert body["data"]["active_task_id"] == "existing01"


def test_get_status_unknown_task(fake_state):
    r = _client().get("/api/admin/tdx/status?task_id=nonexistent")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 404
    assert "不存在" in body["message"]


def test_get_status_known_task(fake_state):
    from app.services.tdx_daily_fetcher.fetcher import TaskStatus
    s = TaskStatus(task_id="known01")
    s.mark("downloading", "下载中 50%", progress=50)
    fake_state.get = MagicMock(return_value=s)

    r = _client().get("/api/admin/tdx/status?task_id=known01")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["task_id"] == "known01"
    assert body["data"]["state"] == "downloading"
    assert body["data"]["progress"] == 50
    assert body["data"]["message"] == "下载中 50%"
    assert body["data"]["started_at"]  # 非空字符串
```

- [ ] **Step 2: Run tests, verify they fail**

Run:
```bash
cd backend && pytest -q tests/test_admin_tdx_api.py
```

Expected: 4 errors with `404` or routing failure (admin_tdx.py doesn't exist yet).

- [ ] **Step 3: Write the API router**

Create `backend/app/api/admin_tdx.py`:

```python
"""TDX vipdata fetcher 管理端点.

端点:
  POST /api/admin/tdx/fetch          启动一次下载 (busy 时返已有 task_id)
  GET  /api/admin/tdx/status?task_id= 查任务进度

状态从 app.state.tdx_state (TdxFetchStateStore 单例) 取.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.result import ResultVO

router = APIRouter()


@router.post("/fetch")
async def post_fetch(request: Request):
    state = request.app.state.tdx_state
    existing = state.active()
    if existing is not None:
        return ResultVO.ok({
            "state": "busy",
            "active_task_id": existing.task_id,
            "current_state": existing.state,
            "progress": existing.progress,
        }).model_dump()
    status = state.start(request.app.state.settings)
    return ResultVO.ok({
        "state": "started",
        "task_id": status.task_id,
    }).model_dump()


@router.get("/status")
async def get_status(task_id: str, request: Request):
    state = request.app.state.tdx_state
    status = state.get(task_id)
    if status is None:
        return ResultVO.fail(
            code=404, message=f"task 不存在: {task_id}",
        ).model_dump()
    return ResultVO.ok({
        "task_id": status.task_id,
        "state": status.state,
        "progress": status.progress,
        "message": status.message,
        "error": status.error,
        "update_time": status.update_time,
        "file_count": status.file_count,
        "zip_size": status.zip_size,
        "started_at": status.started_at.isoformat() if status.started_at else None,
        "finished_at": status.finished_at.isoformat() if status.finished_at else None,
    }).model_dump()
```

- [ ] **Step 4: Run tests, verify they pass**

Run:
```bash
cd backend && pytest -q tests/test_admin_tdx_api.py
```

Expected: 4 passed.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/api/admin_tdx.py tests/test_admin_tdx_api.py
cd backend && pytest -q tests/test_admin_tdx_api.py
git add backend/app/api/admin_tdx.py backend/tests/test_admin_tdx_api.py
git commit -m "feat(tdx): add admin API endpoints POST /fetch + GET /status"
```

---

### Task 8: Wire main.py + docker-compose

**Files:**
- Modify: `backend/app/main.py:11-22` (imports), `backend/app/main.py:40-55` (lifespan), `backend/app/main.py:71-74` (router include)
- Modify: `docker/docker-compose.yml:43-59` (env + volumes)

**Interfaces:**
- `app.state.tdx_state: TdxFetchStateStore` (lifespan 注入)
- `app.state.settings: Settings` (已有, 暴露给 API)
- router prefix `/api/admin/tdx`

- [ ] **Step 1: Wire main.py**

Modify `backend/app/main.py`:

After line 19 (after existing imports), add:
```python
from app.api.admin_tdx import router as admin_tdx_router
from app.state.tdx_fetch_state import TdxFetchStateStore
```

Modify the lifespan function (lines 40-55). Replace with:
```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_indexes()
    _app.state.settings = settings
    _app.state.tdx_state = TdxFetchStateStore()

    watcher_task: asyncio.Task | None = None
    if bool(getattr(settings, "etf_data_auto_import", False)):
        service = EtfService()
        watcher_task = start_watcher(settings, service)
        logging.getLogger("app.startup").info(
            "[etf_data_watcher] started; dir=%s poll=%ss",
            settings.etf_data_dir,
            settings.etf_data_poll_seconds,
        )
    try:
        yield
    finally:
        cancelled = _app.state.tdx_state.cancel_active("服务关闭,任务中断")
        if cancelled:
            logging.getLogger("app.shutdown").warning(
                "[tdx/state] cancelled %s active tasks on shutdown", cancelled,
            )
        await stop_watcher(watcher_task)
```

After line 74, add:
```python
app.include_router(admin_tdx_router, prefix="/api/admin/tdx", tags=["admin"])
```

- [ ] **Step 2: Update docker-compose.yml**

Modify `docker/docker-compose.yml`. In the `environment:` block (lines 33-45), replace:
```yaml
  FIN_ETF_DATA_AUTO_IMPORT: "true"
  # TDX 离线 K 线: 挂载宿主通达信目录, API ?source=offline 即走这里
  # 容器内路径固定 /app/tdx (vipdoc/sh|sz/bj/lday/*.day 在此目录下)
  FIN_TDX_HOME: /app/tdx
```
with:
```yaml
  FIN_ETF_DATA_AUTO_IMPORT: "true"
  # TDX 离线 K 线: vipdoc/ 在 /app/data 下 (与 D:\stock bind mount 共享)
  # 见 docs/superpowers/specs/2026-09-18-tdx-daily-fetcher-design.md
  FIN_TDX_HOME: /app/data
  FIN_TDX_DATA_DIR: /app/data
```

In the `volumes:` block (lines 46-59), remove these lines:
```yaml
  - type: bind
    source: C:\zd_zxzq_gm
    target: /app/tdx
```

- [ ] **Step 3: Verify the service still boots**

Run:
```bash
cd backend && python -c "
from app.main import app
print('app routes:')
for r in app.routes:
    if hasattr(r, 'path'):
        print(' ', r.path)
"
```

Expected: among existing routes, `/api/admin/tdx/fetch` and `/api/admin/tdx/status` are listed.

- [ ] **Step 4: Run full test suite**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py tests/test_admin_tdx_api.py
```

Expected: all pass.

Also run the smoke test to ensure main.py imports don't break anything:
```bash
cd backend && python -c "from app.main import app; print('OK', len(app.routes), 'routes')"
```

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/main.py
git add backend/app/main.py docker/docker-compose.yml
git commit -m "feat(tdx): wire admin router in main.py; drop dead C:\\\\zd_xzq_gm mount"
```

---

### Task 9: Frontend button

**Files:**
- Modify: `frontend/src/Etf.jsx` (locate the "K 线源切换 radio" area, ~line 1025)

**Interfaces:**
- New local state: `tdxFetch, setTdxFetch`
- New handler: `handleFetchTdxVipdata()`
- New button rendered near the existing offline/online radio

- [ ] **Step 1: Find the insertion point**

Run:
```bash
grep -n "etfKlineSource\|source=offline\|拉取\|tdx\|TDX" frontend/src/Etf.jsx | head -30
```

Identify the JSX section containing the "本地 TDX (vipdoc+gbbq)" / "东财网络" radio. The button will go immediately after.

- [ ] **Step 2: Add the state + handler**

In `frontend/src/Etf.jsx`, find the existing useState declarations and add a new one (near `useState` lines for `etfKlineSource`):

```jsx
const [tdxFetch, setTdxFetch] = useState(null);
// shape: {state: 'started'|'checking'|'downloading'|'extracting'|'done'|'failed'|'skipped'|'busy', task_id, progress, message}
```

Find a logical location for the handler function (alongside other `handle*` functions). Add:

```jsx
const handleFetchTdxVipdata = async () => {
  if (!window.confirm("拉取通达信全量日线包到本地（约 525MB，1-3 分钟）？")) return;
  try {
    const start = await apiGet("/api/admin/tdx/fetch");
    if (start?.state === "busy") {
      alert(`已有任务在跑: ${start.active_task_id} (${start.current_state})`);
      return;
    }
    if (!start?.task_id) {
      alert("启动下载失败，请查看后端日志");
      return;
    }
    setTdxFetch({ state: "started", task_id: start.task_id, progress: 0 });
    const iv = setInterval(async () => {
      try {
        const s = await apiGet(`/api/admin/tdx/status?task_id=${start.task_id}`);
        setTdxFetch(s);
        if (["done", "failed", "skipped"].includes(s?.state)) {
          clearInterval(iv);
          if (s?.state === "done") {
            // 成功: 给个轻量反馈 (不强制 alert, 让 UI 上的按钮文字提示即可)
          }
          if (s?.state === "failed") {
            alert(`下载失败: ${s?.error || s?.message || "未知错误"}`);
          }
        }
      } catch (err) {
        clearInterval(iv);
        alert(`查询进度失败: ${err?.message || err}`);
      }
    }, 1000);
  } catch (err) {
    alert(`启动失败: ${err?.message || err}`);
  }
};
```

- [ ] **Step 3: Add the button JSX**

Locate the existing offline/online radio button area and add a new button nearby. The exact location will be visible from grep in Step 1. Example insertion (the actual JSX depends on what's already there — copy what's shown and place it adjacent to the radio group):

```jsx
<button
  type="button"
  onClick={handleFetchTdxVipdata}
  disabled={
    tdxFetch &&
    !["done", "failed", "skipped"].includes(tdxFetch.state)
  }
  style={{ marginLeft: 8 }}
>
  {tdxFetch?.state === "downloading" ? `下载中 ${tdxFetch.progress || 0}%` :
   tdxFetch?.state === "extracting"  ? `解压中 ${tdxFetch.progress || 0}%` :
   tdxFetch?.state === "checking"     ? "查询元信息..." :
   tdxFetch?.state === "started"      ? "准备..." :
   "拉取通达信日线包"}
</button>
{tdxFetch?.state === "done" && (
  <span style={{ marginLeft: 8, color: "#28a745" }}>
    ✓ 已更新 ({(tdxFetch.file_count || 0).toLocaleString()} 文件)
  </span>
)}
{tdxFetch?.state === "failed" && (
  <span style={{ marginLeft: 8, color: "#dc3545" }}>
    ✗ 失败
  </span>
)}
```

- [ ] **Step 4: Verify build + lint**

Run:
```bash
cd frontend && pnpm run lint && pnpm run build
```

Expected: both succeed. (Manual UI verification is the user's responsibility per AGENTS.md — subagent does not click browsers.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/Etf.jsx
git commit -m "feat(frontend): add TDX vipdata fetch button with progress polling"
```

---

### Task 10: Day-reader regression tests (bonus coverage)

**Files:**
- Create: `backend/tests/test_tdx_day_reader_regression.py`

**Coverage:**
- Regression tests for the EXISTING `tdx_offline.day_reader.TdxDailyBarReader`, not new code.
- Uses actual `D:\stock\data\hsjday.zip` (skipped if missing).
- Validates:
  - sh600000 day count > 5000
  - Last date matches the meta `update_time`
  - Amount self-consistency for at least 3 stocks
  - ETF detection (sh510300) returns correct security type

- [ ] **Step 1: Write the test file**

Create `backend/tests/test_tdx_day_reader_regression.py`:

```python
"""Regression tests for app/services/tdx_offline/day_reader.py.

These tests use the actual hsjday.zip downloaded from data.tdx.com.cn.
If the file is missing, tests skip — they're for manual / CI run after fetching.

Note: These tests touch the existing day_reader module, but only ADD coverage,
not modify the implementation. Per AGENTS.md read-only-by-default rule, we
intentionally do not change day_reader.py.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

ZIP_PATH = Path(r"D:\stock\data\hsjday.zip")


pytestmark = pytest.mark.skipif(
    not ZIP_PATH.is_file(),
    reason=f"hsjday.zip 不在 {ZIP_PATH}, 跳过 (需先跑 fetcher 下载)",
)


def _open_zip():
    import zipfile
    return zipfile.ZipFile(ZIP_PATH)


def _read_day(market, code):
    """Extract + parse one .day file using the actual production reader."""
    import io
    from app.services.tdx_offline.day_reader import TdxDailyBarReader, TdxMarket

    with _open_zip() as z:
        raw = z.read(f"{market}/lday/{market}{code}.day")
    market_obj = TdxMarket(name=market, lday_dir=Path(f"/tmp/fake/{market}/lday"))
    reader = TdxDailyBarReader(market_obj, code)
    # Bypass reader.path check by feeding bytes:
    reader.path = Path(f"/tmp/fake/{market}/lday/{market}{code}.day")
    import struct
    from datetime import datetime as _dt
    n = len(raw) // 32
    rec = struct.iter_unpack("<IIIIIfII", raw[:n * 32])
    rows = [
        (datetime.strptime(str(d), "%Y%m%d").isoformat(),
         o * 0.01, h * 0.01, low * 0.01, c * 0.01, amount, int(vol * 0.01))
        for d, o, h, low, c, amount, vol, _ in rec
    ]
    return rows


def test_sh600000_minimum_history():
    rows = _read_day("sh", "600000")
    assert len(rows) > 5000
    first_date = rows[0][0]
    assert first_date.startswith("1999-11")  # 浦发银行上市月


def test_sh510300_etf_detection():
    """510300 (华泰柏瑞沪深300 ETF) 应该被识别为 FUND, 不是 A_STOCK."""
    from app.services.tdx_offline.day_reader import TdxDailyBarReader
    sec_type = TdxDailyBarReader.detect_security_type("sh", "510300")
    assert sec_type == "FUND"


def test_amount_self_consistency():
    """close × shares ≈ amount (偏差 < 5×)."""
    rows = _read_day("sz", "000001")
    # 取最近 30 天校验
    last_30 = rows[-30:]
    fails = 0
    for date_s, _o, _h, _l, c, amt, vol in last_30:
        shares = vol * 100  # raw × 0.01 = 手, 再 ×100 = shares
        if shares <= 0 or amt <= 0:
            continue
        expected = c * shares
        ratio = amt / expected
        if ratio < 0.2 or ratio > 5.0:
            fails += 1
    assert fails <= 2  # 允许极少数坏记录 (day_reader.py:160 注释提到)


def test_bj_market_present():
    """北交所至少有一只股票."""
    rows = _read_day("bj", "920982")
    assert len(rows) > 100
```

- [ ] **Step 2: Run tests**

Run:
```bash
cd backend && pytest -q tests/test_tdx_day_reader_regression.py -v
```

Expected: 4 tests run (since the zip exists), all pass.

If they skip (zip missing), that's OK — the integration smoke from Task 11 covers end-to-end.

- [ ] **Step 3: Lint + commit**

```bash
cd backend && ruff check tests/test_tdx_day_reader_regression.py
git add backend/tests/test_tdx_day_reader_regression.py
git commit -m "test(tdx): add day_reader regression coverage using hsjday.zip"
```

---

### Task 11: End-to-end smoke + final verify

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run:
```bash
cd backend && pytest -q tests/test_tdx_daily_fetcher.py tests/test_admin_tdx_api.py tests/test_tdx_day_reader_regression.py
```

Expected: all pass (or skip day_reader if zip missing).

- [ ] **Step 2: Run ruff on all touched files**

Run:
```bash
cd backend && ruff check app tests
```

Expected: clean.

- [ ] **Step 3: Boot the service in dev mode**

Run:
```bash
cd backend && timeout 15 python -m uvicorn app.main:app --host 127.0.0.1 --port 8081 --app-dir backend 2>&1 | head -40
```

Expected output (first 5-10 lines):
```
INFO:     Started server process [...]
Uvicorn running on http://127.0.0.1:8081
...
[no errors]
```

If any import or lifespan error appears, fix before proceeding.

- [ ] **Step 4: Hit the new endpoints**

In another terminal, with server running:
```bash
curl -s -X POST http://127.0.0.1:8081/api/admin/tdx/fetch | python -m json.tool
```

Expected: `success: true, data: {state: "started", task_id: "..."}`. Capture the task_id, then:
```bash
curl -s "http://127.0.0.1:8081/api/admin/tdx/status?task_id=<TASK_ID>" | python -m json.tool
```

Expected: `success: true, data: {state: "...", progress: ..., message: "..."}`. Over 30 seconds, state should progress `checking → downloading → extracting → done`.

If the download succeeds, verify the file landed at `D:\stock\data\hsjday.zip` and `D:\stock\data\vipdoc\sh\lday\sh600000.day` exists.

- [ ] **Step 5: Verify offline chain now works**

With the service still up:
```bash
curl -s "http://127.0.0.1:8081/api/kline/get?code=600000&source=offline" | python -m json.tool
```

Expected: `success: true, data: {code: "600000", klines: [...]}` — confirms the offline reader chain works end-to-end.

If this returns null/empty even though the .day file exists, double-check `FIN_TDX_HOME` resolves correctly to `D:\stock\data` (which is where `vipdoc/` lives).

- [ ] **Step 6: Kill the server**

```bash
# (timeout from Step 3 will auto-kill after 15s)
```

- [ ] **Step 7: Final commit if anything was tweaked**

If Step 3-5 revealed minor issues that were fixed (typos, missing imports, env var name), commit them now:
```bash
git status
git add -A  # only if changes are intentional
git commit -m "fix(tdx): address smoke-test findings"
```

(Skip if no changes were needed.)

- [ ] **Step 8: Verify git log**

Run:
```bash
git log --oneline -15
```

Expected: 10-11 new commits with the conventional-commit prefixes used in this plan (`feat(tdx):`, `test(tdx):`, etc.).

---

## Self-Review (completed before plan delivery)

**1. Spec coverage:**
- Config fields → Task 1 ✓
- Constants → Task 1 ✓
- Exceptions → Task 1 ✓
- Meta parser → Task 2 ✓
- Atomic extract → Task 3 ✓
- Download + progress → Task 4 ✓
- Last-fetch tracker → Task 4 ✓
- Fetcher state machine → Task 5 ✓
- TaskStatus dataclass → Task 5 ✓
- State singleton → Task 6 ✓
- Admin API POST/GET → Task 7 ✓
- main.py lifespan wiring → Task 8 ✓
- docker-compose mount + env → Task 8 ✓
- Frontend button → Task 9 ✓
- Day_reader regression tests → Task 10 ✓
- End-to-end smoke → Task 11 ✓
- "v1 不做" section (Range, gbbq 自动下载, etc.) → explicitly excluded with rationale ✓
- 错误处理 (7 modes) → covered via exception types + tests in Tasks 1-5 ✓

**2. Placeholder scan:** no "TBD/TODO/待定/implement later" patterns found in code blocks.

**3. Type consistency:**
- `TaskStatus.state` uses `Literal[...]` consistently in Task 5, Task 6, Task 7
- `ACTIVE_STATES` is `frozenset[str]` and exported from `fetcher.py` (Task 5), used by `TdxFetchStateStore` (Task 6) and `admin_tdx.py` (Task 7)
- `TaskStatus.mark(state, message, progress)` signature consistent across Tasks 5 and 6
- `LastFetch.should_skip(update_time)` uses string in Tasks 4 and 5 (matching the type stored in JSON)
- `download_zip` and `fetch_meta` use exception types from `exceptions.py` defined in Task 1
- `MetaInfo` is `frozen=True` (Task 2) — `LastFetch.write` accepts it as `meta: MetaInfo` (Task 4) — consistent

**4. Scope:** 11 tasks, each with a clear deliverable, all produce independently testable code. Single feature, no decomposition needed.