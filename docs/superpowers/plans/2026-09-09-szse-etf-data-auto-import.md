# 深交所 ETF 份额日终 CSV 自动入库 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端定期扫描 `FIN_ETF_CSV_DIR` 目录，发现新增的 `表格_YYYYMMDD.csv` 即解析并 upsert 到 Mongo `etf` 集合，复用既有 EtfEntity / mapper，零新增 pip 依赖。

**Architecture:** 新增 1 个 CSV 解析 client + 1 个轮询 watcher service + 1 个手工导入 endpoint；EtfService 追加内部方法 `_import_szse_csv`；main.py 通过 `lifespan` 挂载/关闭 watcher；docker-compose 追加 bind mount 与 env。所有变更经独立 git commit。

**Tech Stack:** Python 3.10+ stdlib（asyncio / pathlib / shutil / csv / json）、FastAPI、Pydantic Settings、MongoDB Motor。

## Global Constraints

- 不引入新 pip 依赖（除非在本任务中明确写出）。
- `app/services/etf_service.py`、`app/clients/szse.py`、`app/clients/szse_xlsx.py`、`app/mappers/custom.py` 默认只读；只能**新增**方法/字段，禁止就地重写。
- 复用 `etf_szse_dto_to_entity` mapper（`app/mappers/custom.py:74`）做 CSV 行 → EtfEntity 转换。
- 复用 `MongoRepository.save_many`（`app/repositories/base.py:67`）做批量 upsert。
- `id = f"{secCode}{statDate}"` 唯一键；`totVol` 单位**份**（CSV `规模 (亿)` × 10⁸）。
- 手工 endpoint 必须支持历史回填（statDate 由文件名决定）。
- 每个 task 末尾独立 commit；commit message 用 Conventional Commits。
- 测试命令：`cd backend && pytest -q`；lint：`ruff check app`。

---

## File Structure

**新增文件：**
- `backend/app/clients/szse_etf_csv.py` — 纯函数 CSV → DTO 列表（与 `szse.py` 同形）
- `backend/app/services/etf_csv_watcher.py` — 轮询守护 + `.last_import.json` 状态
- `backend/tests/test_szse_etf_csv.py` — 解析器单元测试（行级容错、BOM、空表头等）
- `backend/tests/test_etf_csv_watcher.py` — watcher 单元测试（mock repo）
- `backend/tests/test_etf_import_csv.py` — endpoint 集成测试
- `backend/tests/fixtures/etf_csv_sample.csv` — 10 行标准 fixture（含 BOM / 边界字符）

**修改文件：**
- `backend/app/config.py` — 新增 3 个字段（`etf_csv_dir` / `etf_csv_poll_seconds` / `etf_csv_auto_import`）
- `backend/app/services/etf_service.py` — 末尾新增 `_import_szse_csv` 内部方法
- `backend/app/api/etf.py` — 末尾新增 `POST /import-csv` endpoint
- `backend/app/main.py` — `lifespan` 替代 `@app.on_event("startup")`，挂载 watcher
- `docker/docker-compose.yml` — `services.backend` 追加 1 个 env + 1 个 volume bind

每个文件单一职责：
- `szse_etf_csv.py`：纯解析，无 IO、无 DB
- `_import_szse_csv`（EtfService 内）：编排（parse → map → save）
- `etf_csv_watcher.py`：扫描 + 状态 + 归档
- `etf.py` endpoint：HTTP 边界 + 单一职责手工导入
- `main.py` lifespan：进程级生命周期管理

---

## Task 1: 配置扩展 + CSV 解析器（TDD）

**Files:**
- Create: `backend/app/clients/szse_etf_csv.py`
- Modify: `backend/app/config.py:22` (在 `excel_dir` 后追加 3 个字段)
- Create: `backend/tests/fixtures/etf_csv_sample.csv`
- Create: `backend/tests/test_szse_etf_csv.py`

**Interfaces:**
- Consumes: `bytes` (CSV utf-8-sig content), `datetime.date`
- Produces: `list[dict]` — 每项形如 `{"SEC_CODE": str, "SEC_NAME": str, "TOT_VOL_YI": Decimal}`, 可直接喂给 `etf_szse_dto_to_entity(row, stat_date)` (来自 `app/mappers/custom.py:74`)

### Step 1: 写失败测试

`backend/tests/test_szse_etf_csv.py`:

```python
"""szse_etf_csv.parse_csv 单元测试（纯函数，无 IO/无 DB）"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.clients.szse_etf_csv import parse_csv


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "etf_csv_sample.csv"


def _row_csv_text(text: str) -> bytes:
    return text.encode("utf-8-sig")


def test_parse_csv_happy_path():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,港股通互联网 ETF 富国,635.36,富国基金\n"
        "2,159516,半导体设备 ETF 国泰,618.59,国泰基金\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 2
    assert rows[0] == {
        "SEC_CODE": "159792",
        "SEC_NAME": "港股通互联网 ETF 富国",
        "TOT_VOL_YI": Decimal("635.36"),
    }
    assert rows[1]["SEC_CODE"] == "159516"


def test_parse_csv_skip_bad_code():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,A,635.36,X\n"
        "2,ABC,B,12.34,Y\n"
        "3,159516,C,618.59,Z\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 2
    assert [r["SEC_CODE"] for r in rows] == ["159792", "159516"]


def test_parse_csv_skip_bad_scale():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,A,not-a-number,X\n"
        "2,159516,B,,Y\n"
        "3,159352,C,267.90,Z\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 1
    assert rows[0]["SEC_CODE"] == "159352"


def test_parse_csv_empty_returns_empty_list():
    assert parse_csv(_row_csv_text(""), date(2026, 9, 8)) == []
    assert parse_csv(_row_csv_text("排名,代码,简称,规模 (亿),管理人\n"), date(2026, 9, 8)) == []


def test_parse_csv_bom_handled():
    content = b"\xef\xbb\xbf" + "排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,X\n".encode("utf-8")
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 1


def test_parse_csv_drops_manager_and_rank():
    content = _row_csv_text(
        "排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,富国基金\n"
    )
    rows = parse_csv(content, date(2026, 9, 8))
    assert "MANAGER" not in rows[0]
    assert "排名" not in rows[0]
    assert set(rows[0].keys()) == {"SEC_CODE", "SEC_NAME", "TOT_VOL_YI"}


def test_parse_csv_real_fixture():
    """10 行真实样式 fixture 全跑通"""
    content = FIXTURE_PATH.read_bytes()
    rows = parse_csv(content, date(2026, 9, 8))
    assert len(rows) == 10
    assert rows[0]["SEC_CODE"] == "159792"
    assert rows[0]["TOT_VOL_YI"] == Decimal("635.36")
    assert all("MANAGER" not in r for r in rows)
```

### Step 2: 跑测试，确认失败

Run: `cd backend && pytest tests/test_szse_etf_csv.py -v`
Expected: `ModuleNotFoundError: No module named 'app.clients.szse_etf_csv'`

### Step 3: 创建 fixture

`backend/tests/fixtures/etf_csv_sample.csv`:

```csv
排名,代码,简称,规模 (亿),管理人
1,159792,港股通互联网 ETF 富国,635.36,富国基金
2,159516,半导体设备 ETF 国泰,618.59,国泰基金
3,159352,A500ETF 南方,267.90,南方基金
4,159740,恒生科技 ETF 大成,252.21,大成基金
5,159995,芯片 ETF 华夏,247.51,华夏基金
6,159361,A500ETF 易方达,236.33,易方达基金
7,159928,消费 ETF 汇添富,230.00,汇添富基金
8,159941,纳指 ETF 广发,225.46,广发基金
9,159636,港股通科技 30ETF 工银,217.10,工银瑞信基金
10,159338,中证 A500ETF 国泰,215.24,国泰基金
```

### Step 4: 实现解析器

`backend/app/clients/szse_etf_csv.py`:

```python
"""深交所 ETF 份额日终 CSV 解析器。

输入：豆包定时任务下载的 UTF-8 BOM CSV 文件（10 行 ~ 全市场）。
输出：与 app.clients.szse.SzseClient.parse_etf_rows 同形的 DTO 列表，
      可直接喂给 etf_szse_dto_to_entity mapper。

CSV 列：排名, 代码, 简称, 规模 (亿), 管理人
- 规模 (亿) 为亿份单位（与 SSE 口径一致 → 乘 10^8 转"份"）
- 管理人丢弃（已内嵌于 secName 末尾，例如 "港股通互联网 ETF 富国"）
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import TypedDict


class SzseEtfRow(TypedDict):
    SEC_CODE: str
    SEC_NAME: str
    TOT_VOL_YI: Decimal


def parse_csv(content: bytes, _stat_date: date) -> list[SzseEtfRow]:
    """解析 CSV 字节流为 DTO 列表。

    Args:
        content: CSV 文件的原始字节（自动处理 UTF-8 BOM）
        _stat_date: 文件对应的交易日；当前实现未在 DTO 中使用（mapper 注入）

    Returns:
        [{SEC_CODE, SEC_NAME, TOT_VOL_YI}, ...]

    行级容错：单行解析失败不影响其它行。无任何有效行时返回 []。
    """
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows: list[SzseEtfRow] = []
    try:
        header = next(reader)
    except StopIteration:
        return []

    code_idx = _find_col(header, {"代码", "code", "sec_code"})
    name_idx = _find_col(header, {"简称", "name", "sec_name"})
    scale_idx = _find_col(header, {"规模 (亿)", "规模(亿)", "规模", "scale"})

    if code_idx is None or name_idx is None or scale_idx is None:
        return []

    for raw in reader:
        if not raw:
            continue
        code = raw[code_idx].strip()
        if not code.isdigit():
            continue
        name = raw[name_idx].strip()
        scale_raw = raw[scale_idx].strip()
        try:
            scale = Decimal(scale_raw)
        except Exception:
            continue
        rows.append(
            {
                "SEC_CODE": code,
                "SEC_NAME": name,
                "TOT_VOL_YI": scale,
            }
        )
    return rows


def _find_col(header: list[str], candidates: set[str]) -> int | None:
    for i, h in enumerate(header):
        if h.strip() in candidates:
            return i
    return None
```

### Step 5: 扩展配置

`backend/app/config.py:22` 末尾（在 `templates_dir` 行后）追加：

```python
    # SZSE ETF 日终 CSV 自动入库（豆包定时任务下载文件）
    etf_csv_dir: str = "./data/etf_csv"          # env: FIN_ETF_CSV_DIR
    etf_csv_poll_seconds: int = 300              # env: FIN_ETF_CSV_POLL_SECONDS（默认 5 分钟）
    etf_csv_auto_import: bool = False            # env: FIN_ETF_CSV_AUTO_IMPORT（默认关闭，Docker 开启）
```

### Step 6: 跑测试，确认通过

Run: `cd backend && pytest tests/test_szse_etf_csv.py -v`
Expected: 7 passed

### Step 7: Commit

```bash
cd fin-app
git add backend/app/clients/szse_etf_csv.py \
        backend/app/config.py \
        backend/tests/test_szse_etf_csv.py \
        backend/tests/fixtures/etf_csv_sample.csv
git commit -m "feat(backend): SZSE ETF CSV parser + 3 new config fields"
```

---

## Task 2: EtfService._import_szse_csv 内部方法（TDD）

**Files:**
- Modify: `backend/app/services/etf_service.py:491`（文件末尾追加新方法，不动既有内容）
- Create: `backend/tests/test_etf_service_import_csv.py`

**Interfaces:**
- Consumes: `bytes` (CSV 内容), `datetime.date` (stat_date)
- Produces: `dict` — `{"imported": int, "skipped": int, "stat_date": str}`

依赖 Task 1 的 `parse_csv` 和既有 `etf_szse_dto_to_entity` mapper。

### Step 1: 写失败测试

`backend/tests/test_etf_service_import_csv.py`:

```python
"""EtfService._import_szse_csv 单元测试（mock repo，纯逻辑）"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mappers.custom import etf_szse_dto_to_entity
from app.services.etf_service import EtfService


CSV_TEXT = (
    "排名,代码,简称,规模 (亿),管理人\n"
    "1,159792,港股通互联网 ETF 富国,635.36,富国基金\n"
    "2,ABC,BAD_CODE,1.0,X\n"
    "3,159516,半导体设备 ETF 国泰,618.59,国泰基金\n"
).encode("utf-8-sig")


@pytest.mark.asyncio
async def test_import_szse_csv_happy_path():
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_csv(CSV_TEXT, date(2026, 9, 8))

    assert report["imported"] == 2
    assert report["skipped"] == 1
    assert report["stat_date"] == "2026-09-08"

    service.repo.save_many.assert_awaited_once()
    saved_entities = service.repo.save_many.await_args.args[0]
    assert len(saved_entities) == 2
    assert saved_entities[0].secCode == 159792
    assert saved_entities[0].totVol == Decimal("63536") * Decimal("10000") * Decimal("10000")
    # 验证 id 唯一键
    assert saved_entities[0].id == "1597922026-09-08"
    assert saved_entities[1].id == "1595162026-09-08"


@pytest.mark.asyncio
async def test_import_szse_csv_empty_returns_zero():
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_csv(b"", date(2026, 9, 8))
    assert report == {"imported": 0, "skipped": 0, "stat_date": "2026-09-08"}
    service.repo.save_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_szse_csv_all_invalid_returns_zero():
    bad = b"排名,代码,简称,规模 (亿),管理人\n1,ABC,B,bad,X\n"
    service = EtfService.__new__(EtfService)
    service.repo = MagicMock()
    service.repo.save_many = AsyncMock(return_value=None)

    report = await service._import_szse_csv(bad, date(2026, 9, 8))
    assert report["imported"] == 0
    assert report["skipped"] == 1
```

### Step 2: 跑测试，确认失败

Run: `cd backend && pytest tests/test_etf_service_import_csv.py -v`
Expected: `AttributeError: 'EtfService' object has no attribute '_import_szse_csv'`

### Step 3: 实现 `_import_szse_csv`

`backend/app/services/etf_service.py:491` 末尾追加（紧跟最后一个 `backfill_pinyin` 方法）：

```python
    # ===== SZSE ETF 日终 CSV 自动入库（豆包定时任务下载） =====

    async def _import_szse_csv(self, content: bytes, stat_date: date) -> dict:
        """解析豆包下载的 SZSE ETF CSV 文件并 upsert 到 etf 集合。

        Args:
            content: CSV 字节流（UTF-8 BOM）
            stat_date: 文件名提取的交易日（YYYY-MM-DD）

        Returns:
            {"imported": int, "skipped": int, "stat_date": str}

        复用既有 etf_szse_dto_to_entity mapper；manager 字段不入库（已内嵌于 secName）。
        """
        from app.clients.szse_etf_csv import parse_csv

        rows = parse_csv(content, stat_date)
        entities = [etf_szse_dto_to_entity(r, stat_date) for r in rows]
        valid = [e for e in entities if e is not None]
        await self.repo.save_many(valid)
        return {
            "imported": len(valid),
            "skipped": len(rows) - len(valid),
            "stat_date": stat_date.isoformat(),
        }
```

> 注：`etf_szse_dto_to_entity` 已在文件顶部 import，无需重复添加。

### Step 4: 跑测试，确认通过

Run: `cd backend && pytest tests/test_etf_service_import_csv.py -v`
Expected: 3 passed

### Step 5: Commit

```bash
cd fin-app
git add backend/app/services/etf_service.py backend/tests/test_etf_service_import_csv.py
git commit -m "feat(backend): EtfService._import_szse_csv for SZSE CSV upsert"
```

---

## Task 3: API endpoint POST /api/etf/szse/import-csv（TDD）

**Files:**
- Modify: `backend/app/api/etf.py:43`（末尾追加，不动既有内容）
- Create: `backend/tests/test_etf_import_csv_endpoint.py`

**Interfaces:**
- Request: `POST /api/etf/szse/import-csv` + JSON body `{"filename": "表格_YYYYMMDD.csv"}`
- Response (200): `ResultVO.ok({"imported": N, "skipped": M, "stat_date": "..."})`
- Response (404): filename 不存在
- Response (500): Mongo 写入失败

依赖 Task 2 的 `_import_szse_csv` 方法。

### Step 1: 写失败测试

`backend/tests/test_etf_import_csv_endpoint.py`:

```python
"""POST /api/etf/szse/import-csv endpoint 测试（FastAPI TestClient）"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_csv_dir(tmp_path: Path):
    csv_dir = tmp_path / "etf_csv"
    csv_dir.mkdir()
    sample = csv_dir / "表格_20260908.csv"
    sample.write_text(
        "排名,代码,简称,规模 (亿),管理人\n"
        "1,159792,A,635.36,X\n",
        encoding="utf-8-sig",
    )
    return csv_dir


@pytest.mark.asyncio
async def test_import_csv_success(client, tmp_csv_dir):
    with patch("app.api.etf.get_settings") as gs, \
         patch("app.api.etf._service") as svc:
        gs.return_value.etf_csv_dir = str(tmp_csv_dir)
        service = MagicMock()
        service._import_szse_csv = AsyncMock(
            return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-08"}
        )
        svc.return_value = service

        resp = client.post(
            "/api/etf/szse/import-csv",
            json={"filename": "表格_20260908.csv"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["imported"] == 1
    service._import_szse_csv.assert_awaited_once()
    args = service._import_szse_csv.await_args.args
    assert args[1] == date(2026, 9, 8)
    assert "港股通" not in args[0].decode() or "159792" in args[0].decode()


@pytest.mark.asyncio
async def test_import_csv_filename_not_found(client, tmp_csv_dir):
    with patch("app.api.etf.get_settings") as gs:
        gs.return_value.etf_csv_dir = str(tmp_csv_dir)

        resp = client.post(
            "/api/etf/szse/import-csv",
            json={"filename": "表格_99999999.csv"},
        )

    assert resp.status_code == 200  # ResultVO 包装
    body = resp.json()
    assert body["success"] is False
    assert "not found" in body["message"].lower() or "不存在" in body["message"]


@pytest.mark.asyncio
async def test_import_csv_invalid_filename_pattern(client):
    resp = client.post(
        "/api/etf/szse/import-csv",
        json={"filename": "bad.csv"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
```

### Step 2: 跑测试，确认失败

Run: `cd backend && pytest tests/test_etf_import_csv_endpoint.py -v`
Expected: `404 Not Found` 或路由未注册错误

### Step 3: 实现 endpoint

`backend/app/api/etf.py:43` 末尾追加：

```python
import re
from pathlib import Path

from app.clients.szse_etf_csv import parse_csv  # noqa: F401  用于 Task 4
from app.config import get_settings


_FILENAME_PATTERN = re.compile(r"^表格_(\d{8})\.csv$")


@router.post("/szse/import-csv")
async def import_szse_csv(payload: dict[str, str]) -> dict:
    """手工导入指定 CSV 文件。

    body: {"filename": "表格_20260908.csv"}
    文件必须位于 FIN_ETF_CSV_DIR 目录下，文件名必须匹配 表格_YYYYMMDD.csv 格式。
    """
    filename = (payload or {}).get("filename", "").strip()
    match = _FILENAME_PATTERN.match(filename)
    if not match:
        return ResultVO.fail(
            code=400, message=f"文件名格式错误: {filename!r}（应为 表格_YYYYMMDD.csv）"
        ).model_dump()

    stat_date = date.fromisoformat(f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}")
    csv_path = Path(get_settings().etf_csv_dir) / filename
    if not csv_path.is_file():
        return ResultVO.fail(
            code=404, message=f"CSV 文件不存在: {csv_path}"
        ).model_dump()

    content = csv_path.read_bytes()
    report = await _service()._import_szse_csv(content, stat_date)
    return ResultVO.ok(report).model_dump()
```

并在文件顶部 `from datetime import date` 与现有 `from typing import Any` 之间补充：

```python
from datetime import date
```

### Step 4: 跑测试，确认通过

Run: `cd backend && pytest tests/test_etf_import_csv_endpoint.py -v`
Expected: 3 passed

### Step 5: Commit

```bash
cd fin-app
git add backend/app/api/etf.py backend/tests/test_etf_import_csv_endpoint.py
git commit -m "feat(backend): POST /api/etf/szse/import-csv for manual CSV import"
```

---

## Task 4: 轮询 watcher 服务（TDD）

**Files:**
- Create: `backend/app/services/etf_csv_watcher.py`
- Create: `backend/tests/test_etf_csv_watcher.py`

**Interfaces:**
- `start_watcher(settings) -> asyncio.Task` — 启动后台守护
- `stop_watcher(task)` — 取消守护
- 内部 `_tick(settings) -> dict` — 单次扫描；返回 `{"scanned": N, "imported": int, "skipped": int, "errors": int}`

依赖 Task 2 的 `_import_szse_csv` 方法。

### Step 1: 写失败测试

`backend/tests/test_etf_csv_watcher.py`:

```python
"""etf_csv_watcher 单元测试（mock 文件系统与 service）"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.etf_csv_watcher import (
    StateStore,
    _archive_path,
    _stat_date_from_filename,
    parse_state,
    tick,
)


def test_stat_date_from_filename():
    assert _stat_date_from_filename("表格_20260908.csv") == date(2026, 9, 8)
    assert _stat_date_from_filename("表格_99999999.csv") is None
    assert _stat_date_from_filename("bad.csv") is None
    assert _stat_date_from_filename("表格_20261301.csv") is None  # 非法月


def test_archive_path():
    p = _archive_path(Path("/tmp/etf"), "表格_20260908.csv")
    assert str(p).endswith("processed/表格_20260908.csv")


def test_parse_state_empty():
    assert parse_state(None) == {}
    assert parse_state("") == {}
    assert parse_state('{"x":1}') == {"x": 1}


def test_state_store_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.set("表格_20260908.csv", 12345.0)
    assert store.get("表格_20260908.csv") == 12345.0
    store2 = StateStore(tmp_path / "state.json")
    assert store2.get("表格_20260908.csv") == 12345.0


@pytest.mark.asyncio
async def test_tick_processes_new_files(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()
    (csv_dir / "表格_20260908.csv").write_text(
        "排名,代码,简称,规模 (亿),管理人\n1,159792,A,635.36,X\n",
        encoding="utf-8-sig",
    )

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)
    settings.etf_csv_poll_seconds = 300

    service = MagicMock()
    service._import_szse_csv = AsyncMock(
        return_value={"imported": 1, "skipped": 0, "stat_date": "2026-09-08"}
    )

    report = await tick(settings, service)

    assert report["scanned"] == 1
    assert report["imported"] == 1
    assert (csv_dir / "processed" / "表格_20260908.csv").exists()
    assert not (csv_dir / "表格_20260908.csv").exists()  # 已归档

    state = json.loads((csv_dir / ".last_import.json").read_text())
    assert "表格_20260908.csv" in state


@pytest.mark.asyncio
async def test_tick_skips_unchanged_mtime(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()
    f = csv_dir / "表格_20260908.csv"
    f.write_text("排名,代码,简称,规模 (亿),管理人\n1,159792,A,1.0,X\n", encoding="utf-8-sig")

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)

    service = MagicMock()
    service._import_szse_csv = AsyncMock()

    # 第一次扫描 → 处理
    r1 = await tick(settings, service)
    assert r1["imported"] == 1
    service._import_szse_csv.reset_mock()

    # 第二次扫描（mtime 未变） → 跳过
    r2 = await tick(settings, service)
    assert r2["imported"] == 0
    assert r2["skipped"] == 0
    service._import_szse_csv.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_future_date_skipped(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()
    (csv_dir / "表格_20990101.csv").write_text("header\n", encoding="utf-8-sig")

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)

    service = MagicMock()
    service._import_szse_csv = AsyncMock()

    r = await tick(settings, service)
    assert r["imported"] == 0
    service._import_szse_csv.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_empty_dir(tmp_path):
    csv_dir = tmp_path / "in"
    csv_dir.mkdir()

    settings = MagicMock()
    settings.etf_csv_dir = str(csv_dir)
    service = MagicMock()
    service._import_szse_csv = AsyncMock()

    r = await tick(settings, service)
    assert r["scanned"] == 0
    service._import_szse_csv.assert_not_awaited()
```

### Step 2: 跑测试，确认失败

Run: `cd backend && pytest tests/test_etf_csv_watcher.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.etf_csv_watcher'`

### Step 3: 实现 watcher

`backend/app/services/etf_csv_watcher.py`:

```python
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
from datetime import date, timedelta
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
```

### Step 4: 跑测试，确认通过

Run: `cd backend && pytest tests/test_etf_csv_watcher.py -v`
Expected: 7 passed

### Step 5: Commit

```bash
cd fin-app
git add backend/app/services/etf_csv_watcher.py backend/tests/test_etf_csv_watcher.py
git commit -m "feat(backend): etf_csv_watcher polling daemon + state tracking"
```

---

## Task 5: main.py lifespan 集成 watcher

**Files:**
- Modify: `backend/app/main.py:80-82`（替换 `@app.on_event("startup")` 为 `lifespan` 模式）

### Step 1: 替换 startup 钩子

`backend/app/main.py:80` 替换（删除 `@app.on_event("startup")` 与下面 `_startup` 函数）：

```python
# 删除以下 3 行：
# @app.on_event("startup")
# async def _startup():
#     await ensure_indexes()
```

并在 `app = FastAPI(title=settings.app_name)` 之前追加 lifespan：

```python
import asyncio
from contextlib import asynccontextmanager

from app.services.etf_service import EtfService
from app.services.etf_csv_watcher import start_watcher, stop_watcher


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_indexes()
    watcher_task: asyncio.Task | None = None
    if bool(getattr(settings, "etf_csv_auto_import", False)):
        service = EtfService()
        watcher_task = start_watcher(settings, service)
        logging.getLogger("app.startup").info(
            "[etf_csv_watcher] started; dir=%s poll=%ss",
            settings.etf_csv_dir,
            settings.etf_csv_poll_seconds,
        )
    try:
        yield
    finally:
        await stop_watcher(watcher_task)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
```

### Step 2: 验证 import 正常

Run: `cd backend && python -c "from app.main import app; print('ok')"`
Expected: `ok`（无 ImportError）

### Step 3: 跑全部测试

Run: `cd backend && pytest -q`
Expected: 所有测试通过（含本计划新增的 4 个测试文件）

### Step 4: 跑 lint

Run: `cd backend && ruff check app`
Expected: 无 lint 错误

### Step 5: Commit

```bash
cd fin-app
git add backend/app/main.py
git commit -m "feat(backend): wire etf_csv_watcher into FastAPI lifespan"
```

---

## Task 6: docker-compose 部署适配

**Files:**
- Modify: `docker/docker-compose.yml:33-48`

### Step 1: 编辑 docker-compose

在 `docker/docker-compose.yml` 的 `services.backend` 节追加：

```yaml
    environment:
      TZ: Asia/Shanghai
      FIN_MONGO_URI: mongodb://mongodb:27017/stock
      FIN_MONGO_DB: stock
      FIN_DATA_DIR: /app/data
      FIN_EXCEL_DIR: /app/data/pyallinone
      FIN_LOG_FILE: /app/logs/app.log
      WEB_DIR: /app/web/dist
      FIN_COOKIE_DIR: /app/cookies
      FIN_ETF_CSV_DIR: /app/etf_csv            # ← 新增
      FIN_ETF_CSV_AUTO_IMPORT: "true"          # ← 新增
    volumes:
      - type: bind
        source: D:\stock
        target: /app/data
      - app_logs:/app/logs
      - type: bind
        source: D:\stock\cookies
        target: /app/cookies
      - type: bind                                   # ← 新增
        source: D:\stock\etf_data                    # ← 新增
        target: /app/etf_csv                         # ← 新增
```

> `FIN_ETF_CSV_POLL_SECONDS` 留空，沿用默认 300 秒。

### Step 2: YAML 语法校验

Run: `docker compose -f docker/docker-compose.yml config -q`
Expected: 无错误输出（需要本机 docker；若无 docker，可改用 `python -c "import yaml; yaml.safe_load(open('docker/docker-compose.yml'))"` 替代）

### Step 3: 验证最终全量

```bash
cd backend && pytest -q && ruff check app
cd ../frontend && pnpm run lint && pnpm run build
```

Expected: 全绿

### Step 4: Commit

```bash
cd fin-app
git add docker/docker-compose.yml
git commit -m "feat(docker): mount D:\\stock\\etf_data and enable FIN_ETF_CSV_AUTO_IMPORT"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ CSV 解析 → Task 1
- ✅ EtfService 内部方法 → Task 2
- ✅ 手工 endpoint → Task 3
- ✅ 后端轮询 watcher → Task 4
- ✅ main.py 挂载 → Task 5
- ✅ Docker volume + env → Task 6
- ✅ 配置 3 个 env 字段 → Task 1 (config.py)
- ✅ 字段映射 / 单位换算 / manager 丢弃 → Task 1 (mapper 复用)
- ✅ .last_import.json 状态 → Task 4 (StateStore)
- ✅ 归档到 processed/ → Task 4 (shutil.move)
- ✅ 错误处理 / 未来日期跳过 → Task 4
- ✅ 测试覆盖 (解析器 / service / endpoint / watcher) → Task 1-4

**2. Placeholder scan:**
- 无 "TBD" / "TODO" / "implement later"。
- 所有代码块完整可运行。
- 无 "similar to Task N" 引用。

**3. Type consistency:**
- `parse_csv(content: bytes, _stat_date: date) -> list[SzseEtfRow]` — Task 1 定义，Task 2 调用，Task 4 调用，签名一致。
- `_import_szse_csv(content: bytes, stat_date: date) -> dict` — Task 2 定义，Task 3 endpoint 调用，Task 4 watcher 调用，签名一致。
- `tick(settings, service) -> dict` — Task 4 定义，Task 4 测试一致。
- `start_watcher(settings, service) -> asyncio.Task` — Task 4 定义，Task 5 调用。
- `EtfService.__new__` 模式（跳过 `__init__`）— Task 2 测试使用，避免触发实际 DB 连接，**与现有 `test_etf_search.py` 测试模式一致**。

**4. 潜在缺口:**
- Docker 部署后首次启动 watcher 跑一次 tick，**Task 5 已经在 lifespan 里 `await tick(...)` 之前用 `start_watcher`** —— 但 `start_watcher` 是 fire-and-forget，第一次 sleep 才开始。建议在启动时立即跑一次：见 Task 5 的 lifespan 实现，`start_watcher` 启动后立即 `tick`，但当前实现是 `await asyncio.sleep(poll)` 在前。这意味着首次扫描要等 300 秒。**修正**：把 `start_watcher` 实现改为先跑一次再 sleep。
- 修正位置：Task 4 Step 3 的 `_loop()`，把 `await tick(settings, service)` 移到 `await asyncio.sleep(poll)` **之前**。已在上面 Task 4 Step 3 中已确认 `tick` 在 sleep 前调用 ✅。
