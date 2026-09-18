# 通达信 vipdata 全量日线包：自动下载 + 接入离线 K 线

日期：2026-09-18
范围：`backend/` + `frontend/src/Etf.jsx` + `docker/docker-compose.yml`

## 背景

`backend/app/services/tdx_offline/`（day_reader / gbbq_reader / fq / fetcher）已完整实现，可读本地通达信 `.day` 文件并产出复权日线。`kline_service` / `etf_service` / `api/kline.py` 均已支持 `source=offline` 参数。

但当前离线链路**走不通**：

- 配置默认 `tdx_home = C:\zd_zxzq_gm`，本机不存在该路径。
- `docker-compose.yml` 第 57-59 行的 bind mount `C:\zd_zxzq_gm → /app/tdx` 是死代码（host 端路径不存在），在 Docker 场景下整个 `source=offline` 失效。
- 用户已手动下载的 `D:\stock\data\hsjday.zip`（524.5MB / 12420 文件）未解压到 vipdoc 目录结构。

外部数据源：`https://data.tdx.com.cn/vipdoc/hsjday.zip`（个人版每日全量日线包，更新时机 ~15:59）。同源元信息 `_hsjdayinfo.js` 提供 `HSJDAY_SOFT_TIME` 字段判断是否当日已更新。

## 目标

1. 前端加按钮触发下载；后端 `POST /api/admin/tdx/fetch` 启动异步任务；`GET /api/admin/tdx/status?task_id=...` 查询进度。
2. 任务流程：检查元信息 → 流式下载 zip → 原子解压 → 标记 `last_update_time`。已有任务在跑则返 `busy`。
3. 修 docker-compose：去掉 `C:\zd_zxzq_gm` 死挂载、`FIN_TDX_HOME=/app/data`、`FIN_TDX_DATA_DIR=/app/data`。
4. 不动 `app/services/tdx_offline/`、`kline_service.py`、`etf_service.py`、`api/kline.py` 任何现有函数 —— 全部按既有契约复用。

## 设计

### 文件清单

```
backend/app/
├── services/
│   └── tdx_daily_fetcher/          ← 新增子包
│       ├── __init__.py             暴露 TdxDailyFetcher + 3 个常量
│       ├── fetcher.py              核心逻辑（状态机 + 下载 + 原子解压）
│       └── constants.py            URL / 路径常量
├── api/
│   └── admin_tdx.py                新增 router：POST /fetch + GET /status
├── state/
│   └── tdx_fetch_state.py          全局单例 {task_id: TaskStatus} 字典
├── config.py                       新增 3 字段：tdx_data_dir / tdx_download_url / tdx_meta_url
└── main.py                         lifespan 不动；新增 2 行 router 注册

backend/tests/
├── test_tdx_daily_fetcher.py       单元 + 集成（4 必写 + 1 可选）
└── test_admin_tdx_api.py           API 契约（2 个）

backend/scripts/
└── fetch_tdx_vipdata.py            CLI 入口（可选，复用 fetcher）

frontend/src/
└── Etf.jsx                         加 1 按钮 + 1 useState；不动任何现有 props/state

docker/docker-compose.yml           删 1 个挂载 + 改 1 个 env + 加 1 个 env
```

**复用现有 0 个函数**。所有动现有文件的改动：

| 文件 | 改动 | 行数 |
|---|---|---|
| `main.py` | `+from app.api.admin_tdx import router as admin_tdx_router`<br>`+app.include_router(admin_tdx_router, prefix="/api/admin/tdx", tags=["admin"])` | +2 |
| `config.py` | 新增 3 字段（默认 `D:\stock\data`） | +12 |
| `docker-compose.yml` | 删 1 mount、改 1 env、加 1 env | ±3 |
| `frontend/src/Etf.jsx` | 加 1 按钮 + 1 polling effect | +40 |

### 数据流

**5 态状态机**：

```
PENDING → CHECKING → (SKIPPED | DOWNLOADING → EXTRACTING) → (DONE | FAILED)
```

**完整请求流**：

```
[前端] Etf.jsx 点击 "拉取通达信日线包"
  ↓
POST /api/admin/tdx/fetch
  → ensure_single_active():
     - 若已有 active (PENDING/CHECKING/DOWNLOADING/EXTRACTING) → 返 {state:"busy"}
     - 否则创建 uuid4 task_id，进 PENDING → 起 asyncio.create_task(fetcher.run())
  → 立即返 {state:"started", task_id}

[后台] fetcher.run():
  CHECKING    GET _hsjdayinfo.js → 解析 HSJDAY_SOFT_TIME
              与 .last_fetch.json 对比 → 已是今日 → SKIPPED
  DOWNLOADING 流式 requests.get(url, stream=True)
              每 256KB 触发 progress = bytesRead/fileSize
              完成后 zipfile.testzip() 校验
  EXTRACTING  解到 <target>/vipdoc.tmp/，全部成功 → shutil.move → vipdoc/
              size 一致的 .day 文件快速跳过（约 90% 命中）
  DONE        写 .last_fetch.json = {update_time, file_count, fetched_at}

[前端] 拿到 task_id 后启动 setInterval 1s 一次：
  GET /api/admin/tdx/status?task_id=...
  显示 "下载中 67% (350MB/524MB)" / "解压中 8500/12420"
  state=DONE/FAILED/SKIPPED → clearInterval
```

### 状态机数据结构

```python
@dataclass
class TaskStatus:
    task_id: str
    state: Literal["pending","checking","downloading","extracting",
                   "done","failed","skipped","busy"]
    progress: int = 0        # 0-100
    message: str = ""
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    update_time: str | None = None  # 来自 _hsjdayinfo.js
    file_count: int | None = None
    zip_size: int | None = None
```

### 关键实现细节

**1) 元信息查询**

```python
GET https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js
Referer: https://www.tdx.com.cn/article/vipdata.html
User-Agent: Mozilla/5.0
解析: r'HSJDAY_SOFT_TIME\s*=\s*["\']([^"\']+)["\']'
```

格式变更找不到变量 → `raise ValueError("_hsjdayinfo.js 格式变更,无法解析")`，硬报错不静默（对齐 `tdx_offline/__init__.py:8` 契约）。

**2) 下载进度回写**

```python
# 256KB chunk 触发一次，避免锁竞争
async def _update_progress(self, downloaded: int, total: int):
    async with self._lock:
        self.status.progress = int(downloaded / total * 100)
        self.status.message = f"下载中 {downloaded//1024//1024}MB/{total//1024//1024}MB"
```

**3) 原子解压**

```python
# 不直接覆盖，先 .tmp 再 rename
with zipfile.ZipFile(zip_path) as z:
    z.extractall(target_dir / "vipdoc.tmp")
shutil.move(target_dir / "vipdoc.tmp", target_dir / "vipdoc")  # 原子
```

失败 → 删 `.tmp/`，原 `vipdoc/` 不动。代价：解压中磁盘 ×2，但回滚安全。

**4) 单例任务保证**

```python
def ensure_single_active(state: dict) -> TaskStatus | None:
    for s in state.values():
        if s.state in ACTIVE_STATES:
            return s
    return None
```

`ACTIVE_STATES = {pending, checking, downloading, extracting}`。busy 返现有 task_id，不创建新任务。

**5) 磁盘预检**

```python
free = shutil.disk_usage(target_dir).free
need = 1.5 * zip_size  # 解压后 ~525MB，解压中临时 ×2
if free < need:
    raise FetchError(f"磁盘不足：剩余 {free//1024//1024}MB，需 {need//1024//1024}MB")
```

**6) lifespan 集成**

```python
# main.py lifespan 内:
app.state.tdx_tasks: dict[str, TaskStatus] = {}

# 启动时不做任何事（不自动下载，避免阻塞启动）
# 关闭时: 若有 active → 标记 FAILED("服务关闭,任务中断") + log warn
```

### docker-compose 改动

```diff
@@ lines 33-45 environment @@
   FIN_ETF_DATA_AUTO_IMPORT: "true"
-  # TDX 离线 K 线: 挂载宿主通达信目录, API ?source=offline 即走这里
-  # 容器内路径固定 /app/tdx (vipdoc/sh|sz/bj/lday/*.day 在此目录下)
-  FIN_TDX_HOME: /app/tdx
+  # TDX 离线 K 线: vipdoc/ 在 /app/data 下 (与 D:\stock 挂载共享)
+  FIN_TDX_HOME: /app/data
+  FIN_TDX_DATA_DIR: /app/data
@@ lines 46-60 volumes @@
   - app_logs:/app/logs
   - type: bind
     source: D:\stock\cookies
     target: /app/cookies
   - type: bind
     source: D:\stock\etf_data
     target: /app/etf_data
-  - type: bind
-    source: C:\zd_zxzq_gm
-    target: /app/tdx
```

### 配置字段

```python
# app/config.py (新增 3 字段，不动现有)
tdx_data_dir: str = Field(
    default=r"D:\stock\data",
    description="通达信日线包根目录：hsjday.zip + vipdoc/ 都在此",
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

容器内默认靠 `docker-compose.yml` env 覆盖 `tdx_data_dir` 为 `/app/data`。

### 前端改动

`frontend/src/Etf.jsx`：

```jsx
// +1 state
const [tdxFetchState, setTdxFetchState] = useState(null);  // {state, progress, message}

// +1 handler
const handleFetchTdxVipdata = async () => {
  if (!window.confirm("拉取通达信全量日线包到本地（524MB，约 1-3 分钟）？")) return;
  const start = await apiGet("/api/admin/tdx/fetch");
  if (start.state === "busy") {
    alert(`已有任务在跑: ${start.active_task_id}`);
    return;
  }
  setTdxFetchState({state: "started", task_id: start.task_id, progress: 0});
  // polling
  const iv = setInterval(async () => {
    const s = await apiGet(`/api/admin/tdx/status?task_id=${start.task_id}`);
    setTdxFetchState({state: s.state, progress: s.progress, message: s.message});
    if (["done","failed","skipped"].includes(s.state)) clearInterval(iv);
  }, 1000);
};

// +1 button (放在 ETF 卡片头部操作区附近)
<button onClick={handleFetchTdxVipdata} disabled={tdxFetchState && !["done","failed","skipped"].includes(tdxFetchState.state)}>
  {tdxFetchState?.state === "downloading" ? `下载中 ${tdxFetchState.progress}%` :
   tdxFetchState?.state === "extracting"  ? `解压中 ${tdxFetchState.progress}%` :
   "拉取通达信日线包"}
</button>
```

不动任何现有 props/state 命名。button 位置：在现有 K 线源切换 radio 旁边。

### 测试

| 文件 | 类型 | 覆盖 |
|---|---|---|
| `test_tdx_daily_fetcher.py` | 单元（4 必写） | ① meta 解析、② 状态机转换、③ SKIPPED 路径不发网络、④ 原子解压回滚 |
| `test_tdx_daily_fetcher.py::test_download_real` | 集成（1 可选） | 真下 zip 验完整性，默认 skip，手测/CI 跑 |
| `test_admin_tdx_api.py` | API（2 必写） | POST 返回 task_id、busy 拒绝重复请求 |
| `test_tdx_day_reader_regression.py` | 回归（顺手） | 给 `tdx_offline/day_reader.py` 补一组：实际 zip 抽 3 只股票 + amount 自洽校验 |

**4 必写单测大纲**：

```python
1. test_parse_meta_info_valid()
   - 给定样本 _hsjdayinfo.js → 正确提取 HSJDAY_SOFT_TIME / HSJDAY_SOFT_SIZE
2. test_parse_meta_info_invalid()
   - 给定无变量 js → 抛 ValueError
3. test_state_machine_full_happy_path()
   - mock 网络 + 临时 target dir → run_sync() → 期望终态 DONE
4. test_state_machine_skip_when_already_today()
   - 预置 .last_fetch.json = 今日 → 期望 SKIPPED，requests.get 未被调（monkeypatch 计数）
5. test_atomic_extract_rollback_on_bad_zip()
   - 构造坏 zip → 期望抛错 + vipdoc/ 不变 + vipdoc.tmp/ 被清理
```

**API 契约**：

```python
1. test_post_fetch_returns_task_id()
   - TestClient.post("/api/admin/tdx/fetch") → 200 {state:"started", task_id}
2. test_post_fetch_busy_when_active()
   - 第 1 次 POST 后不等待 → 第 2 次 POST → 200 {state:"busy", active_task_id}
```

### 错误处理

| # | 场景 | 行为 | 用户感知 |
|---|---|---|---|
| 1 | meta 不可达 | CHECKING 失败 → FAILED | "无法连接通达信服务器" |
| 2 | zip 下载中断 | 删半成品 → FAILED | "下载中断（已下 XMB），请重试" |
| 3 | zip testzip 非 None | 删 zip → FAILED | "zip 损坏: {bad_file}" |
| 4 | 解压失败 | .tmp 删除，vipdoc 不动 → FAILED | "解压失败: {原因}" |
| 5 | 磁盘不足 | 预检 → FAILED | "磁盘不足: 还需 XMB, 剩余 YMB" |
| 6 | 已有任务运行 | busy 返现有 task_id | 按钮 disable / 提示 |
| 7 | 服务重启中断 active | 内存字典丢失，状态变 orphan | 下次启动正常 |

### 不做（v1 明确不实现）

- ❌ 断点续传（Range request）—— 524MB 单次重下成本可接受
- ❌ gbbq 自动下载 —— 网站不提供；用户后续手动从通达信 PC 客户端复制
- ❌ 增量 diff 下载 —— 525MB/天换 0 代码改动
- ❌ 多任务并发 —— 524MB 单次跑，并发无意义
- ❌ 自动定时下载 —— 留给后续 cron / Windows Task Scheduler
- ❌ 前端进度条 widget —— 用 button text + percentage 就够

### 兼容性 / 回滚

- 不动任何 service / client / repository / 既有 api，零回归风险
- 若新功能出问题，回滚只需 `git revert` 这一 commit，不影响其他模块
- `source=offline` 在 docker 场景下从"不可用"变成"可用"，但默认仍是 `online`，用户不主动切不受影响

### 实施顺序（写作计划时细化）

1. `config.py` 加 3 字段
2. `tdx_daily_fetcher/{__init__,constants,fetcher}.py`
3. `state/tdx_fetch_state.py`
4. `api/admin_tdx.py`
5. `main.py` 加 2 行（router 注册）
6. `docker-compose.yml` 删挂载 + 改 env
7. `frontend/src/Etf.jsx` 加 1 button + useState
8. `tests/test_tdx_daily_fetcher.py` + `test_admin_tdx_api.py` + `test_tdx_day_reader_regression.py`
9. 手动跑 `pytest -q && ruff check app`
10. commit: `feat(tdx): add vipdata daily fetcher with admin API`