# 银行 PB 卡片：移除拼音搜索框 + 新增下载银行数据按钮

日期：2026-09-07
范围：`frontend/src/BankPBCard.jsx`（单文件改动）

## 背景

`BankPBCard` 目前顶部有一个 `StockCombobox`（placeholder `代码/拼音/名称`，走 `/api/sec/search?org_type_code=3&q=`），
与其下方的「备选银行股（45）」列表功能重复——列表本身已可直接点选。
同时缺少批量下载银行股基础数据的入口，而股票数据卡已有等价能力（`Etf.jsx` 的「下载常用票」）。

## 目标

1. 删除卡片内的拼音/代码搜索框。
2. 在原位置新增「下载银行数据」按钮，一次性批量下载全部备选银行股数据。

## 设计

### 移除

- 删除 `BankPBCard.jsx` 中的 `<StockCombobox .../>` 节点。
- 删除 `import StockCombobox from './StockCombobox';`。
- 删除仅供 combobox 使用的 `pickFromCombobox` 回调。
- `StockCombobox.jsx` 本身不动（`Etf.jsx` 仍在使用）。

### 新增按钮

位置：原 combobox 位置，即 `leftPane` 内、`listWrap` 之上，宽度 100%。

行为：点击后调用

```
GET /api/one?code=<全部备选银行股代码逗号拼接>&crawl=true
```

- 代码集合取 `bankList`（`/api/sec/search?org_type_code=3&limit=1000` 的返回），与列表展示的 45 只一致。
- `crawl` 固定为 `true`（抓东财），与「下载常用票」默认行为对齐，卡片内不加 radio 开关。
- 成功：`alert('成功调用后台接口：' + url)`；
  失败：`ApiError` 时 `alert(error.message)` 并 `console.warn('[api]', errorType, path, code, message)`，
  其它错误 `alert('调用后台接口失败！')` 并 `console.error`。
  与 `Etf.jsx:304 fetchBatchStockCodes` 的错误处理形态保持一致。

状态与禁用：

- 新增 `downloading` state。请求期间按钮文案 `下载中…` 且 `disabled`，防重复点击。
- `bankList.length === 0`（加载中或加载失败）时按钮 `disabled`。

样式：卡片保持自包含模式，在本文件 `styles` 内新增与 `Etf.jsx` `buttonUnified` 等价的条目
（height 32 / borderRadius 6 / background `#3b5b7a` / 白字 / fontSize 13），
外加 `width: '100%'`，以及 disabled 时降低不透明度、`cursor: not-allowed`。
hover 色 `#324d68`，沿用 `Etf.jsx` 的 inline `onMouseEnter/onMouseLeave` 写法，disabled 时不变色。

### 不改动

- 后端零改动，复用既有 `/api/one`。
- `onSelectBank` 契约不变；父组件 `Etf.jsx` 无需调整。
- 备选银行股列表的加载、排序、点选逻辑不变。

## 验证

- `cd frontend && pnpm run lint && pnpm run build`
- 手测：展开「银行股 PB 时序」卡 → 搜索框已消失 → 点「下载银行数据」→ 观察 network 请求 URL 含 45 个代码与 `crawl=true`，按钮期间禁用并显示「下载中…」，结束后弹 alert。
