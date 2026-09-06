// BankPBCard.jsx
// 银行股 PB（市净率）选择卡片（沿用侧栏卡片视觉风格 + HKFinanceCard 自包含模式）。
// 仅作 picker：通过 onSelectBank 回调通知父组件，主图区由父组件（Etf.jsx）渲染。
// 后端: GET /api/sec/search?org_type_code=3&limit=1000 (银行备选列表)
//       GET /api/sec/search?org_type_code=3&q=        (拼音搜索，限银行)
// 主图组件拉: GET /api/bank/pb/history?code=xxx       (由 Etf.jsx 触发)
/* eslint-disable react/prop-types */
import { useEffect, useState } from 'react';
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
  selectedTag: {
    fontSize: '12px',
    color: 'rgba(15, 23, 42, 0.7)',
    padding: '4px 0 0',
  },
  selectedTagCode: {
    fontFamily: 'Consolas, Menlo, monospace',
    color: '#1d4ed8',
  },
};

function BankPBCard({ selectedBankCode = null, onSelectBank = () => {} }) {
  const [isCardOpen, setIsCardOpen] = useState(true);
  const [bankList, setBankList] = useState([]);
  const [listError, setListError] = useState(null);

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

  const pickFromList = (item) => {
    if (!item || !item.code) return;
    onSelectBank({ code: item.code, name: item.name || '' });
  };

  const pickFromCombobox = ({ code, name }) => {
    if (!code) return;
    onSelectBank({ code, name: name || '' });
  };

  const sortedBankList = (() => {
    const rows = [...bankList];
    rows.sort((a, b) => String(a.code || '').localeCompare(String(b.code || '')));
    return rows;
  })();

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
                    const active = item.code === selectedBankCode;
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
          </div>
        </div>
      </div>
    </div>
  );
}

export default BankPBCard;