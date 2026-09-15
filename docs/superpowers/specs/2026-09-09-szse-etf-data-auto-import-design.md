# 深交所 ETF 份额日终 JSON 自动入库

日期：2026-09-09（初版 CSV，2026-09-09 切换到 JSON）
范围：`backend/` + `docker/docker-compose.yml`（前端零改动）

## 背景

`EtfService` 当前对深交所 ETF 份额的拉取走 `SzseClient.etf()` JSON 实时接口（`fund.szse.cn/api/report/ShowReport/data?CATALOGID=ssjjcp_1`）。该接口有两个短板：

1. 返回的是**最近一个交易日的快照**，无法做历史重放或单日多次刷新。
2. 数据是深交所服务器侧动态拼装，缺权威"日终文件"作为兜底/审计来源。

外部已有数据源：豆包免费版可按计划任务每日下载深交所公开 ETF 份额 JSON（文件名固定 `sz_etf_YYYY-MM-DD.json`），落到本地目录。目标是把这份 JSON **每日自动** upsert 到 Mongo `etf` collection，复用既有 EtfEntity / mapper。

> 2026-09-09 初版用 `表格_YYYYMMDD.csv` 上线后发现上游实际产出 JSON 格式（`code/name/scale/mgr`），同日内迁移到本 JSON 实现；CSV 路径已下线（parser / watcher / 旧测试 / 旧 fixture 全部删除）。

## 目标

1. 后端后台轮询指定目录，发现新增 `sz_etf_*.json` 即解析入库。
2. 字段映射尽量复用既有 `etf_szse_dto_to_entity` mapper（`mappers/custom.py:74`），零行数据丢失。
3. 本地开发与 Docker 双模式支持；Docker 场景下文件挂到宿主 `D:\stock\etf_data\`。
4. 保留手工导入 endpoint 用于调试与历史回填。

## 设计

### 文件清单

```
backend/app/
├── clients/
│   └── szse_etf_json.py              ← JSON 解析器
├── services/
│   ├── etf_service.py               ← 不动既有逻辑，替换 _import_szse_csv → _import_szse_json
│   └── etf_data_watcher.py          ← 轮询守护（asyncio），替代原 etf_csv_watcher
├── api/
│   └── etf.py                       ← 替换 POST /szse/import-csv → /szse/import-json
└── config.py                        ← 字段名 etf_csv_dir/... → etf_data_dir/...
docker/docker-compose.yml            ← env: FIN_ETF_CSV_DIR/... → FIN_ETF_DATA_DIR/...
```

### 字段映射

JSON 实测样例（`D:\stock\etf_data\sz_etf_2026-09-09.json`）：

| JSON 字段 | 类型 | 转换为 | 落库字段 |
|---|---|---|---|
| code | str | `int(row)` | `secCode: int` |
| name | str | 原样 | `secName: str` |
| scale | str | `Decimal × 1e8`（与 SSE 口径一致） | `totVol: Decimal`（份） |
| mgr | str | **丢弃**（已内嵌于 secName，如"港股通互联网 ETF 富国"含"富国"） | — |
| 文件名 `_2026-09-09` | str | `dt.date(2026, 9, 9).isoformat()` | `statDate: str` |

`id = f"{secCode}{statDate}"` 沿用 `etf_szse_dto_to_entity` 既有约定，MongoRepository.save 用 `_id` 替换式 upsert，天然支持重复导入幂等。

### JSON 解析器 `szse_etf_json.py`

```python
def parse_json(content: bytes, _stat_date: date) -> list[SzseEtfRow]:
    """返回 [{SEC_CODE, SEC_NAME, TOT_VOL_YI}] 列表，与 SzseClient.parse_etf_rows 同形"""
```

- `json.loads(content.decode("utf-8-sig"))` 处理 BOM
- 顶层必须是 list；非 list 或 JSON 解析失败 → 返回 []
- 行级容错：code 非数字 / name 缺失 / scale 解析失败 → 跳过该行
- 返回 DTO 列表**直接喂给** `etf_szse_dto_to_entity(row, stat_date)`，mapper 复用

### 导入服务（`_import_szse_json` + `etf_data_watcher.py`）

```
data/sz_etf_2026-09-09.json
  ↓ watcher 每 N 秒扫一次
  ↓ glob("sz_etf_*.json")
  ↓ read_bytes + parse_json
  ↓ list[EtfEntity] via 复用 mapper
  ↓ MongoRepository.save (upsert)
  ↓ 成功 → shutil.move → <etf_data_dir>/processed/
  ↓ 记录 <etf_data_dir>/.last_import.json = {filename: mtime}
```

**EtfService 新增方法**：

```python
async def _import_szse_json(self, file_bytes: bytes, stat_date: date) -> dict:
    """返回 {"imported": int, "skipped": int, "stat_date": str}"""
    rows = parse_json(file_bytes, stat_date)
    entities = [etf_szse_dto_to_entity(r, stat_date) for r in rows]
    entities = [e for e in entities if e is not None]
    await self.repo.save_many(entities)
    return {"imported": len(entities), "skipped": len(rows) - len(entities)}
```

> `MongoRepository.save_many` **已存在**（`repositories/base.py`，内部循环调 `save`），直接复用即可。`save` 走 `replace_one(..., upsert=True)`，对 `id = f"{secCode}{statDate}"` 天然幂等。

### 轮询守护 `etf_data_watcher.py`

- `Path(settings.etf_data_dir).mkdir(parents=True, exist_ok=True)` 启动时自建
- `.last_import.json` 记录 `{filename: mtime_float}`，mtime 未变 → 跳过（即使归档失败也不会二次落库）
- 整文件 0 行有效 → 报错日志 + 不归档

### 配置 `config.py`

```python
etf_data_dir: str = "./data/etf_data"          # env: FIN_ETF_DATA_DIR
etf_data_poll_seconds: int = 300                # env: FIN_ETF_DATA_POLL_SECONDS（默认 5 分钟）
etf_data_auto_import: bool = False              # env: FIN_ETF_DATA_AUTO_IMPORT（默认关闭，Docker 开启）
```

沿用 `SettingsConfigDict(env_prefix="FIN_")`，命名一致。

### Docker 适配 `docker/docker-compose.yml`

```yaml
environment:
  FIN_ETF_DATA_DIR: /app/etf_data
  FIN_ETF_DATA_AUTO_IMPORT: "true"

volumes:
  - type: bind
    source: D:\stock\etf_data
    target: /app/etf_data
```

### 手工入口 `POST /api/etf/szse/import-json`

请求：

```json
POST /api/etf/szse/import-json
Content-Type: application/json
{ "filename": "sz_etf_2026-09-09.json" }
```

行为：从 `settings.etf_data_dir` 读 `filename`，调用 `_import_szse_json`；不存在则 404。

保留用途：watcher 关闭时手工触发 + 历史回填 + 调试。

### 错误处理

| 场景 | 处理 |
|---|---|
| 文件名不匹配 `sz_etf_YYYY-MM-DD.json` | glob 不命中 → 静默跳过 |
| `statDate > 今天` | 跳过 + warn 日志 |
| `code` 非数字 | 跳过该行 |
| `scale` 非数字 | 跳过该行 |
| 整文件 0 行有效 | error 日志 + 不归档 + 不写 `.last_import` |
| Mongo 写入抛异常 | error 日志 + 文件**留在原位**（下次轮询重试） |
| 同一文件 mtime 未变 | `.last_import.json` 跳过 |

## 验证

### 单元 / 集成测试（全部新写）

`tests/test_szse_etf_json.py`：
- 正常 JSON → DTO 列表，scale 精度保留
- `mgr` 字段不入 DTO
- code 非数字 / scale 非法 → skip
- 缺字段（code/name/scale 任一缺失）→ skip
- 空数组 / 空字节 / 非 JSON / 非 list → 返回 []
- 10 行真实样式 fixture 全跑通

`tests/test_etf_service_import_json.py`：
- happy path：2 行有效 + 1 行 code 非法 → imported=2, id 唯一键
- 空文件 → imported=0 skipped=0
- 全部非法 → imported=0 skipped=0

`tests/test_etf_import_json_endpoint.py`：
- 200 + 成功 body
- 404：filename 不存在
- 400：filename 不匹配 `sz_etf_YYYY-MM-DD.json`
- 拒绝旧 `表格_YYYYMMDD.csv` 命名
- Mongo 失败 → error envelope

`tests/test_etf_data_watcher.py`：
- 首次扫描 → 解析 + 归档 + 写 `.last_import`
- 二次扫描 mtime 未变 → 跳过
- 文件名不匹配 → 跳过
- 未来日期 → 跳过
- Mongo 失败 → 文件留在原位
- 旧 CSV 命名 → 不再被拾取

### 手工验证

```bash
cd backend && pip install -e . && pytest -q && ruff check app
# 211 passed

# 验证真实文件可解析
python -c "
from datetime import date
from app.clients.szse_etf_json import parse_json
from app.mappers.custom import etf_szse_dto_to_entity
content = open(r'D:\stock\etf_data\sz_etf_2026-09-09.json', 'rb').read()
rows = parse_json(content, date(2026, 9, 9))
print(len(rows))  # 730
"
```

```bash
# Docker
docker compose -f docker/docker-compose.yml up -d --build
# 拷贝测试 JSON 到 D:\stock\etf_data\
# 观察 backend 容器日志，5 分钟内完成解析
```

### 不变项验证

- `python -c "from app.main import app"` 无 import error
- `pnpm run lint && pnpm run build`（前端零改动）
- `pytest -q` 全绿（211 passed）
- 现有 `SzseClient.etf()` 实时接口链路不变

## 不做（YAGNI）

- 不新增定时调度框架（APScheduler 等），轮询够用且零依赖。
- 不改 EtfEntity 任何字段（mgr 不入库）。
- 不做历史回溯 UI（手工 endpoint 即可）。
- 不引入 watchdog（polling 已足够 5 分钟精度）。
- 不动现有任何 collection 索引 / mapper。
