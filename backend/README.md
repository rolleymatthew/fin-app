# Backend

## 安装依赖

```bash
pip install -e .
```

## 运行服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## K 线多源：hybrid pipeline（TDX 优先 + 网络补 gap）

**架构**：`KLinePipeline` 编排器 4 阶段：TDX 探测 → 网络补 gap → 纯网络兜底 → 合并切片。
`source=online`（默认）走 hybrid；`source=offline` 走纯 TDX（既有行为保留）。

**TDX-first**：本地通达信 vipdoc + gbbq 覆盖历史（无网络、零频率限制、字段完整）。
`TdxAdapter` 复用 `app/services/tdx_offline/fetch_local_day`，不重写。

**网络补 gap**：TDX 的 `max_date` 距今天数 = gap，用网络链补最近 gap+5 天。
网络链顺序默认 `sina,tencent,eastmoney`（env `FIN_KLINE_NETWORK_CHAIN` 覆盖），先轻后全。

**TDX 不可用时**：env `FIN_KLINE_PRIMARY`（默认 `tencent`）+ `FIN_KLINE_FALLBACKS`（默认 `eastmoney,sina`）
驱动纯网络兜底链——与改造前 online 行为一致，零回归。

**TDX 不必天天下载**：`tdx_daily_fetcher` 每包 525MB，hybrid 自动用网络补最近 gap。

**env 总览**：
- `FIN_KLINE_PRIMARY`（默认 `tencent`）— TDX 不可用时纯网络主源
- `FIN_KLINE_FALLBACKS`（默认 `eastmoney,sina`）— 同上回退
- `FIN_KLINE_NETWORK_CHAIN`（默认 `sina,tencent,eastmoney`）— TDX gap 补抓网络链
- `FIN_TDX_HOME`（默认 `D:\stock\data`）— TDX 主目录

**详见**：`docs/superpowers/specs/2026-09-29-kline-hybrid-pipeline-design.md`

## sec_code 同步

服务启动时不自动同步 `sec_code`。手动触发方式：

```bash
curl -X POST http://127.0.0.1:8080/api/sec/sync -H "Content-Type: application/json" -d '{"force": false}'
curl -X POST http://127.0.0.1:8080/api/sec/refresh-details -H "Content-Type: application/json" -d '{"include_delisted": true, "only_missing": false}'
```

## 打包成可执行 EXE（Windows 10）

```bash
# 1) 创建并激活虚拟环境（可选但推荐）
python -m venv .venv
.venv\Scripts\activate

# 2) 安装依赖
pip install -e .
pip install pyinstaller

# 3) 打包
pyinstaller --onefile --name fin-service app\entrypoint.py
```

打包完成后，生成的可执行文件在 `dist\fin-service.exe`。

### 输出目录（Excel）

默认输出目录已固定为 `D:\stock\pyallinone`。  
如需临时覆盖，可设置环境变量 `FIN_EXCEL_DIR`，例如：

```bat
set FIN_EXCEL_DIR=D:\stock\pyallinone
```

### 一键清理并打包

已提供 `build_fin_service_exe.bat`，双击即可清理旧产物并重新打包：

```bat
build_fin_service_exe.bat
```

运行示例：

```bash
# 可选：通过环境变量配置监听地址和端口
set HOST=0.0.0.0
set PORT=8080
set DEBUG_LOG_URL=true
# 可选：指定 URL 日志文件路径
set DEBUG_LOG_URL_PATH=D:\stock\logs\urlLogs.log

dist\fin-service.exe
```

### 一键启动（双击）

已提供 `start_fin_service_exe.bat`，双击即可启动：

```bat
start_fin_service_exe.bat
```

### 东方财富 URL 日志

当 `DEBUG_LOG_URL=true` 时，抓取东方财富接口的完整 URL 与响应内容会写入日志文件。
默认日志文件为 `backend-python\urlLogs.log`。如需覆盖路径，可设置：

```bat
set DEBUG_LOG_URL_PATH=D:\stock\logs\urlLogs.log
```

### 一键源码启动（双击）

已提供 `start_fin_service_src.bat`，双击即可用源码启动（自动尝试使用 `.venv`）：

```bat
start_fin_service_src.bat
```

### 东方财富 Cookie 配置

支持以下来源（按优先级从高到低，仅一个生效）：

1. `FIN_COOKIE_DIR`：目录路径，目录下所有 `.txt` 文件按文件名顺序拼接为最终 Cookie
2. `EASTMONEY_COOKIE_DIR`：同上的兼容别名
3. `EASTMONEY_COOKIE_FILE`：单个文件路径（兼容旧版）
4. `EASTMONEY_COOKIE`：直接注入 Cookie 字符串（兼容旧版）
5. 默认目录：`.eastmoney_cookies/`（不存在则空启动，由首次请求日志告警）

启用目录模式后，**修改任一 `.txt` 文件即可热加载**，无需重启服务。
当响应内容表明 Cookie 已失效时，服务会打印 `【COOKIE_INVALID】reason=...` 并尝试一次刷新，
随后请求重试一次；若仍失败，请在目录中替换 Cookie 文件即可。

示例：

```bat
set FIN_COOKIE_DIR=D:\stock\cookies
:: D:\stock\cookies\01-primary.txt
:: D:\stock\cookies\02-extra.txt
```
