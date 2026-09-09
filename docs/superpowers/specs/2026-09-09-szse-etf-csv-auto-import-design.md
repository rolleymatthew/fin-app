# 深交所 ETF 份额日终 CSV 自动入库

日期：2026-09-09
范围：`backend/` + `docker/docker-compose.yml`（前端零改动）

## 背景

`EtfService` 当前对深交所 ETF 份额的拉取走 `SzseClient.etf()` JSON 实时接口（`fund.szse.cn/api/report/ShowReport/data?CATALOGID=ssjjcp_1`）。该接口有两个短板：

1. 返回的是**最近一个交易日的快照**，无法做历史重放或单日多次刷新。
2. 数据是深交所服务器侧动态拼装，缺权威"日终文件"作为兜底/审计来源。

外部已有数据源：豆包免费版可按计划任务每日下载深交所公开 ETF 份额 CSV（文件名固定 `表格_YYYYMMDD.csv`），落到本地目录。目标是把这份 CSV **每日自动** upsert 到 Mongo `etf` collection，复用既有 EtfEntity / mapper。

## 目标

1. 后端后台轮询指定目录，发现新增 `表格_*.csv` 即解析入库。
2. 字段映射尽量复用既有 `etf_szse_dto_to_entity` mapper（`mappers/custom.py:74`），零行数据丢失。
3. 本地开发与 Docker 双模式支持；Docker 场景下文件挂到宿主 `D:\stock\etf_data\`。
4. 保留手工导入 endpoint 用于调试与历史回填。

## 设计

### 新增文件

```
backend/app/
├── clients/
│   └── szse_etf_csv.py              ← CSV 解析器（独立模块）
├── services/
│   ├── etf_service.py               ← 不动，新增 1 个内部方法 _import_szse_csv
│   └── etf_csv_watcher.py           ← 轮询守护服务（asyncio）
├── api/
│   └── etf.py                       ← 不动，新增 POST /etf/szse/import-csv
└── config.py                        ← 不动既有字段，新增 1 个 etf_csv_dir
docker/docker-compose.yml            ← 新增 1 个 volume + 1 个 env
```

不动 `szse.py` / `szse_xlsx.py` / 现有 mapper / 任何 collection 索引。

### 字段映射

CSV 实测样例（`data/表格_20260908.csv`）：

| CSV 列 | 类型 | 转换为 | 落库字段 |
|---|---|---|---|
| 代码 | str | `int(row)` | `secCode: int` |
| 简称 | str | 原样 | `secName: str` |
| 规模 (亿) | str | `Decimal × 1e8`（与 SSE 口径一致） | `totVol: Decimal`（份） |
| 管理人 | str | **丢弃**（已内嵌于 secName，如"港股通互联网 ETF 富国"含"富国"） | — |
| 排名 | int | 丢弃 | — |
| 文件名 `_20260908` | str | `dt.date(2026, 9, 8).isoformat()` | `statDate: str` |

`id = f"{secCode}{statDate}"` 沿用 `etf_szse_dto_to_entity` 既有约定，MongoRepository.save 用 `_id` 替换式 upsert，天然支持重复导入幂等。

### CSV 解析器 `szse_etf_csv.py`

```python
# 入口
def parse_csv(content: bytes, stat_date: date) -> list[dict]:
    """返回 [{SEC_CODE, SEC_NAME, TOT_VOL_YI}] 列表，与 SzseClient.parse_etf_rows 同形"""
```

- `csv.reader(utf-8-sig)` 处理 BOM
- 第 1 行为表头，跳过；校验列数 ≥ 4
- 行级容错：单行解析失败累计 `skip_count`，不影响其它行
- 返回 DTO 列表**直接喂给** `etf_szse_dto_to_entity(row, stat_date)`，mapper 复用

### 导入服务（`_import_szse_csv` + `etf_csv_watcher.py`）

```
data/表格_20260908.csv
  ↓ watcher 每 N 秒扫一次
  ↓ glob("表格_*.csv")
  ↓ read_bytes + parse_csv
  ↓ list[EtfEntity] via 复用 mapper
  ↓ MongoRepository.save (upsert)
  ↓ 成功 → shutil.move → <etf_csv_dir>/processed/
  ↓ 记录 <etf_csv_dir>/.last_import.json = {filename: mtime, imported_at}
```

**EtfService 新增方法**：

```python
async def _import_szse_csv(self, file_bytes: bytes, stat_date: date) -> dict:
    """返回 {"imported": int, "skipped": int, "errors": list[str]}"""
    rows = parse_csv(file_bytes, stat_date)
    entities = [etf_szse_dto_to_entity(r, stat_date) for r in rows]
    entities = [e for e in entities if e is not None]
    imported = await self.repo.save_many(entities)
    return {"imported": imported, "skipped": len(rows) - len(entities)}
```

> 注：`MongoRepository.save_many` **已存在**（`repositories/base.py:67`，内部循环调 `save`），直接复用即可。`save` 走 `replace_one(..., upsert=True)`，对 `id = f"{secCode}{statDate}"` 天然幂等。

### 轮询守护 `etf_csv_watcher.py`

```python
async def start_watcher(settings: Settings) -> asyncio.Task:
    """lifespan 启动时调用；app 关闭时 task.cancel()"""
    async def _loop():
        while True:
            await _tick(settings)
            await asyncio.sleep(settings.etf_csv_poll_seconds)
    return asyncio.create_task(_loop(), name="etf-csv-watcher")
```

- `Path(settings.etf_csv_dir).mkdir(parents=True, exist_ok=True)` 启动时自建
- `.last_import.json` 记录 `{filename: mtime_float}`，mtime 未变 → 跳过（即使归档失败也不会二次落库）
- 整文件 0 行有效 → 报错日志 + 不归档

### 配置 `config.py`

```python
etf_csv_dir: str = "./data/etf_csv"          # env: FIN_ETF_CSV_DIR
etf_csv_poll_seconds: int = 300              # env: FIN_ETF_CSV_POLL_SECONDS（默认 5 分钟）
etf_csv_auto_import: bool = False            # env: FIN_ETF_CSV_AUTO_IMPORT（默认关闭，Docker 开启）
```

沿用 `SettingsConfigDict(env_prefix="FIN_")`，命名一致。

### Docker 适配 `docker/docker-compose.yml`

在 `services.backend` 节追加：

```yaml
environment:
  # ... 既有 ...
  FIN_ETF_CSV_DIR: /app/etf_csv
  FIN_ETF_CSV_AUTO_IMPORT: "true"

volumes:
  # ... 既有 ...
  - type: bind
    source: D:\stock\etf_data
    target: /app/etf_csv
```

Dockerfile **不动**（不需要新增包；`csv` / `asyncio` / `pathlib` / `shutil` 都是 stdlib）。

### 手工入口 `POST /api/etf/szse/import-csv`

请求：

```json
POST /api/etf/szse/import-csv
Content-Type: application/json
{ "filename": "表格_20260908.csv" }
```

行为：从 `settings.etf_csv_dir` 读 `filename`，调用 `_import_szse_csv`；不存在则 404。

保留用途：watcher 关闭时手工触发 + 历史回填 + 调试。

### 错误处理

| 场景 | 处理 |
|---|---|
| 文件名不匹配 `表格_YYYYMMDD.csv` | glob 不命中 → 静默跳过 |
| `statDate > 今天` | 跳过 + warn 日志 |
| `代码` 非数字 | 跳过该行 + 累计 skip |
| `规模 (亿)` 非数字 | 跳过该行 + 累计 skip |
| 整文件 0 行有效 | error 日志 + 不归档 + 不写 `.last_import` |
| Mongo 写入抛异常 | error 日志 + 文件**留在原位**（下次轮询重试） |
| 同一文件 mtime 未变 | `.last_import.json` 跳过 |

## 验证

### 单元 / 集成测试

新增 `tests/clients/test_szse_etf_csv.py`：

- 10 行正常 CSV → 10 个 DTO，单位正确 ×1e8
- 空文件 / 仅表头 → 返回 `[]`
- 含"代码非数字"行 → skip 该行，其它正常
- 含"规模 (亿) 非法字符"行 → skip 该行
- BOM (`\ufeff`) → 正常解析

新增 `tests/services/test_etf_csv_watcher.py`：

- 首次扫描 → 解析 + 归档 + 写 `.last_import`
- 二次扫描 mtime 未变 → 跳过
- 二次扫描 mtime 变 → 重新处理（覆盖式 upsert）
- 文件名不匹配 → 跳过

新增 `tests/api/test_etf_import_csv.py`：

- 200：fixture 准备 CSV → POST → 校验 Mongo upsert
- 404：filename 不存在
- 500：模拟 Mongo 写入失败

### 手工验证

```bash
# 本地
cd backend && pip install -e . && pytest -q && ruff check app
cp data/表格_20260908.csv data/etf_csv/
# 启动后端，FIN_ETF_CSV_AUTO_IMPORT=true
# 观察日志：解析 10 行 → 归档 → 写 .last_import

# Docker
docker compose -f docker/docker-compose.yml up -d --build
# 将测试 CSV 拷到 D:\stock\etf_data\
# 观察 backend 容器日志，5 分钟内完成解析
```

### 不变项验证

- `python -c "from app.main import app"` 无 import error
- `pnpm run lint && pnpm run build`（前端零改动，仍需通过）
- `pytest -q` 全绿
- 现有 `SzseClient.etf()` 实时接口链路不变

## 不做（YAGNI）

- 不新增定时调度框架（APScheduler 等），轮询够用且零依赖。
- 不改 EtfEntity 任何字段（manager 不入库）。
- 不做 CSV 历史回溯 UI（手工 endpoint 即可）。
- 不引入 watchdog（polling 已足够 5 分钟精度）。
- 不动现有任何 collection 索引 / mapper。
