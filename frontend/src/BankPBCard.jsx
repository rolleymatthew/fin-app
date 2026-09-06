// BankPBCard.jsx
// 银行股 PB（市净率）时序图卡片（沿用侧栏卡片视觉风格 + HKFinanceCard 自包含模式）。
// 后端: GET /api/bank/pb/history?code=xxx        (PB 时序)
//       GET /api/sec/search?org_type_code=3     (银行备选列表，仅银行股)
//       GET /api/sec/search?org_type_code=3&q=  (拼音搜索，限银行)
// 实时计算、不落库。
import { useEffect, useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import StockCombobox from './StockCombobox';
import { apiGet, ApiError } from './api';

const styles = {
  card: {
    background: '#FFFFFF',
    border: '1px solid rgba(148, 163, 184, 0.28)',
    borderRadius: '12px',
    padding: '10px',
    boxShadow: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    position: 'relative',
  },
  cardGoldCorner: {
    boxShadow: 'inset 0 0 0 1px rgba(180, 83, 9, 0.18)',
  },
  cardHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  cardTitle: {
    fontSize: '14px',
    fontWeight: 700,
    color: '#0f172a',
    margin: 0,
    letterSpacing: '0.3px',
  },
  cardToggle: {
    border: '1px solid rgba(148, 163, 184, 0.6)',
    background: '#f8fafc',
    borderRadius: '8px',
    color: '#0f172a',
    width: '34px',
    height: '34px',
    padding: 0,
    fontWeight: 600,
    fontSize: '18px',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  collapseBody: {
    overflow: 'hidden',
    transition: 'max-height 0.25s ease, opacity 0.2s ease',
  },
  splitLayout: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  leftPane: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  rightPane: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  listWrap: {
    border: '1px solid rgba(148, 163, 184, 0.55)',
    borderRadius: '8px',
    background: '#f8fafc',
    overflowY: 'auto',
    maxHeight: '160px',
    minHeight: '120px',
  },
  listHeader: {
    padding: '6px 8px',
    fontSize: '11px',
    color: 'rgba(15, 23, 42, 0.55)',
    borderBottom: '1px solid rgba(148, 163, 184, 0.35)',
    position: 'sticky',
    top: 0,
    background: '#f8fafc',
  },
  listItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    padding: '5px 8px',
    fontSize: '12px',
    color: '#0f172a',
    cursor: 'pointer',
    borderBottom: '1px solid rgba(148, 163, 184, 0.18)',
  },
  listItemActive: {
    background: 'rgba(59, 91, 122, 0.10)',
    fontWeight: 600,
  },
  listItemCode: {
    fontFamily: 'Consolas, Menlo, monospace',
    color: '#1d4ed8',
    minWidth: '64px',
  },
  listItemName: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
  },
  hint: {
    padding: '10px',
    fontSize: '12px',
    color: 'rgba(15, 23, 42, 0.55)',
    lineHeight: 1.5,
  },
  error: {
    color: '#b91c1c',
    background: 'rgba(220, 38, 38, 0.08)',
    border: '1px solid rgba(220, 38, 38, 0.25)',
    borderRadius: '6px',
    padding: '6px 8px',
    fontSize: '12px',
  },
  chartWrap: {
    width: '100%',
    minWidth: 0,
  },
  chartPlaceholder: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '180px',
    color: 'rgba(15, 23, 42, 0.55)',
    fontSize: '12px',
    border: '1px dashed rgba(148, 163, 184, 0.55)',
    borderRadius: '8px',
    textAlign: 'center',
    padding: '0 8px',
  },
  selectedTag: {
    fontSize: '12px',
    color: 'rgba(15, 23, 42, 0.7)',
    padding: '4px 0 0',
  },
  selectedTagCode: {
    fontFamily: 'Consolas, Menlo, monospace',
    color: '#1d4ed8',
  },
  chartOverlay: {
    position: 'fixed',
    top: 64,
    right: 16,
    width: 'min(720px, calc(100vw - 296px))',
    height: 'calc(100vh - 96px)',
    background: '#ffffff',
    border: '1px solid rgba(148, 163, 184, 0.55)',
    borderRadius: '12px',
    boxShadow: '0 16px 48px rgba(15, 23, 42, 0.18)',
    zIndex: 900,
    display: 'flex',
    flexDirection: 'column',
    padding: '14px',
    gap: '10px',
    boxSizing: 'border-box',
  },
  chartOverlayHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    paddingBottom: '8px',
    borderBottom: '1px solid rgba(148, 163, 184, 0.28)',
  },
  chartOverlayTitle: {
    fontSize: '15px',
    fontWeight: 700,
    color: '#0f172a',
    margin: 0,
  },
  chartOverlaySub: {
    fontSize: '12px',
    color: 'rgba(15, 23, 42, 0.6)',
  },
  chartOverlayClose: {
    border: '1px solid rgba(148, 163, 184, 0.6)',
    background: '#f8fafc',
    borderRadius: '8px',
    color: '#0f172a',
    width: '32px',
    height: '32px',
    cursor: 'pointer',
    fontSize: '16px',
    lineHeight: 1,
  },
  chartOverlayBody: {
    flex: '1 1 auto',
    minHeight: 0,
    width: '100%',
  },
  chartOverlayBackdrop: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(15, 23, 42, 0.18)',
    zIndex: 899,
  },
};

function BankPBCard() {
  const [isCardOpen, setIsCardOpen] = useState(true);
  const [bankList, setBankList] = useState([]);
  const [selectedCode, setSelectedCode] = useState(null);
  const [selectedName, setSelectedName] = useState(null);
  const [pbHistory, setPbHistory] = useState([]);
  const [listError, setListError] = useState(null);
  const [historyError, setHistoryError] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isChartOpen, setIsChartOpen] = useState(false);

  // mount: 拉银行备选列表
  useEffect(() => {
    apiGet('/api/sec/search?org_type_code=3&limit=1000')
      .then((rows) => {
        setBankList(Array.isArray(rows) ? rows : []);
        setListError(null);
      })
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : String(err);
        setListError(`加载银行列表失败：${msg}`);
        setBankList([]);
      });
  }, []);

  // 选中股票: 拉 PB 时序
  useEffect(() => {
    if (!selectedCode) {
      setPbHistory([]);
      setHistoryError(null);
      return;
    }
    setHistoryLoading(true);
    apiGet(`/api/bank/pb/history?code=${encodeURIComponent(selectedCode)}`)
      .then((rows) => {
        setPbHistory(Array.isArray(rows) ? rows : []);
        setHistoryError(null);
      })
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : String(err);
        setHistoryError(msg || '加载 PB 时序失败');
        setPbHistory([]);
      })
      .finally(() => setHistoryLoading(false));
  }, [selectedCode]);

  const pickFromList = (item) => {
    if (!item || !item.code) return;
    setSelectedCode(item.code);
    setSelectedName(item.name || '');
    setIsChartOpen(true);
  };

  const pickFromCombobox = ({ code, name }) => {
    if (!code) return;
    setSelectedCode(code);
    setSelectedName(name || '');
    setIsChartOpen(true);
  };

  const closeChart = () => {
    setIsChartOpen(false);
    setSelectedCode(null);
    setSelectedName(null);
    setPbHistory([]);
    setHistoryError(null);
  };

  const sortedBankList = useMemo(() => {
    const rows = [...bankList];
    rows.sort((a, b) => String(a.code || '').localeCompare(String(b.code || '')));
    return rows;
  }, [bankList]);

  const chartOption = useMemo(() => {
    const dates = pbHistory.map((p) => p.reportDate).filter(Boolean);
    const pbs = pbHistory.map((p) => (p.pb == null ? null : Number(p.pb)));
    return {
      grid: { left: '3%', right: '3%', top: '10%', bottom: '15%', containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params) => {
          if (!params || !params.length) return '';
          const idx = params[0].dataIndex;
          const p = pbHistory[idx];
          if (!p) return '';
          const lines = [`<b>${p.reportDate || ''}</b>`];
          if (p.pb != null) lines.push(`PB: ${p.pb}`);
          if (p.bps != null) lines.push(`BPS: ${p.bps}`);
          if (p.close != null) lines.push(`收盘: ${p.close}`);
          if (p.bpsField) lines.push(`(bps=${p.bpsField})`);
          if (p.error) lines.push(`<span style="color:#b91c1c">${p.error}</span>`);
          return lines.join('<br/>');
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: '#64748b' },
        axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.5)' } },
        axisPointer: { type: 'shadow' },
      },
      yAxis: {
        type: 'value',
        name: '市净率(PB)',
        min: 0,
        axisLabel: { formatter: '{value}', color: '#64748b' },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.25)' } },
      },
      series: [
        {
          name: 'PB',
          type: 'line',
          data: pbs,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: '#dc2626' },
          lineStyle: { width: 2, color: '#dc2626' },
        },
      ],
    };
  }, [pbHistory]);

  return (
    <div style={{ ...styles.card, ...styles.cardGoldCorner }}>
      <div style={styles.cardHeaderRow}>
        <p style={styles.cardTitle}>银行股 PB 时序</p>
        <button
          type="button"
          onClick={() => setIsCardOpen((prev) => !prev)}
          style={styles.cardToggle}
          aria-label={isCardOpen ? '收起银行PB时序' : '展开银行PB时序'}
          title={isCardOpen ? '收起银行PB时序' : '展开银行PB时序'}
        >
          {isCardOpen ? '▾' : '▸'}
        </button>
      </div>
      <div
        style={{
          ...styles.collapseBody,
          maxHeight: isCardOpen ? '480px' : '0px',
          opacity: isCardOpen ? 1 : 0,
        }}
      >
        <div style={{ paddingTop: '6px' }}>
          <div style={styles.splitLayout}>
            {/* 左侧：拼音搜索 + 备选列表 */}
            <div style={styles.leftPane}>
              <StockCombobox
                apiUrl="/api/sec/search?org_type_code=3"
                width="100%"
                placeholder="代码/拼音/名称"
                onSelect={pickFromCombobox}
              />
              <div style={styles.listWrap}>
                <div style={styles.listHeader}>
                  {bankList.length > 0
                    ? `备选银行股（${bankList.length}）`
                    : '加载中…'}
                </div>
                {listError && <div style={styles.error}>{listError}</div>}
                {!listError &&
                  sortedBankList.map((item) => {
                    const active = item.code === selectedCode;
                    return (
                      <div
                        key={item.code}
                        role="button"
                        tabIndex={0}
                        style={{
                          ...styles.listItem,
                          ...(active ? styles.listItemActive : null),
                        }}
                        onClick={() => pickFromList(item)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            pickFromList(item);
                          }
                        }}
                      >
                        <span style={styles.listItemCode}>{item.code}</span>
                        <span style={styles.listItemName}>
                          {item.name || ''}
                        </span>
                      </div>
                    );
                  })}
                {!listError && bankList.length === 0 && (
                  <div style={styles.hint}>暂无银行股数据</div>
                )}
              </div>
            </div>

            {/* 右侧：PB 图 —— 选中后在右侧浮层显示，跳出窄侧栏 */}
            <div style={styles.rightPane}>
              {selectedCode && !isChartOpen && (
                <div style={styles.selectedTag}>
                  当前：<span style={styles.selectedTagCode}>{selectedCode}</span>{' '}
                  {selectedName || ''}
                </div>
              )}
              {!isChartOpen && (
                <div style={styles.chartPlaceholder}>
                  请从左侧选择银行股（pinyin 搜索 / 备选列表）
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {isChartOpen && (
        <>
          <div
            style={styles.chartOverlayBackdrop}
            onClick={closeChart}
            aria-hidden="true"
          />
          <div style={styles.chartOverlay} role="dialog" aria-label="银行PB时序">
            <div style={styles.chartOverlayHeader}>
              <div>
                <p style={styles.chartOverlayTitle}>银行 PB 时序</p>
                <div style={styles.chartOverlaySub}>
                  <span style={{ fontFamily: 'Consolas, Menlo, monospace', color: '#1d4ed8' }}>
                    {selectedCode}
                  </span>{' '}
                  {selectedName || ''}
                  {historyError && (
                    <span style={{ color: '#b91c1c', marginLeft: '8px' }}>
                      · {historyError}
                    </span>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={closeChart}
                style={styles.chartOverlayClose}
                aria-label="关闭"
                title="关闭"
              >
                ×
              </button>
            </div>
            <div style={styles.chartOverlayBody}>
              {!historyError &&
                (historyLoading ? (
                  <div style={styles.chartPlaceholder}>加载中…</div>
                ) : pbHistory.length === 0 ? (
                  <div style={styles.chartPlaceholder}>暂无 PB 数据</div>
                ) : (
                  <ReactECharts
                    option={chartOption}
                    style={{ width: '100%', height: '100%', minHeight: '320px' }}
                    notMerge
                    lazyUpdate
                  />
                ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default BankPBCard;