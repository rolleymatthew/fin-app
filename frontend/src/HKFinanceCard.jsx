// HKFinanceCard.jsx
// 港股财报下载卡片（沿用 echart-etf 现有侧栏卡片视觉风格，样式完全自包含）。
// 后端: GET /api/hk/one?code=&name= （Python FastAPI / Java Spring Boot 同签名）
// Excel 落盘位置: {FIN_EXCEL_DIR}/HKallinone/{code}{name}.xlsx
import { useState } from 'react';
import HKStockCombobox from './HKStockCombobox';
import { PRESET_HK_CODES } from './const';

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
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
  },
  input: {
    height: 32,
    padding: '0 10px',
    borderRadius: 6,
    border: '1px solid #d9dee5',
    fontSize: 13,
    background: '#fff',
    outline: 'none',
    minWidth: '90px',
    flex: '1 1 90px',
    boxSizing: 'border-box',
  },
  textarea: {
    background: '#f8fafc',
    border: '1px solid rgba(148, 163, 184, 0.55)',
    borderRadius: '8px',
    color: '#0f172a',
    padding: '6px 8px',
    fontSize: '12px',
    outline: 'none',
    minWidth: '220px',
    minHeight: '62px',
    resize: 'vertical',
    boxShadow: 'none',
    flex: '1 1 0',
    boxSizing: 'border-box',
  },
  buttonUnified: {
    height: 32,
    padding: '0 14px',
    borderRadius: 6,
    background: '#3b5b7a',
    color: '#fff',
    border: 'none',
    fontSize: 13,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s',
  },
  buttonUnifiedHover: '#324d68',
  hint: {
    fontSize: '11px',
    color: 'rgba(15, 23, 42, 0.55)',
    lineHeight: 1.5,
  },
};

const HKFinanceCard = () => {
  const [isCardOpen, setIsCardOpen] = useState(false);
  const [comboboxValue, setComboboxValue] = useState({ code: '', name: '' });
  const [manualCode, setManualCode] = useState('');
  const [manualName, setManualName] = useState('');
  const [batchInput, setBatchInput] = useState('');

  const handleManualCodeChange = (e) => {
    const raw = e.target.value.replace(/\D/g, '').slice(0, 5);
    setManualCode(raw);
  };

  const fetchOne = async (code, name) => {
    const url = `/api/hk/one?code=${encodeURIComponent(code)}&name=${encodeURIComponent(name || '')}`;
    try {
      const res = await fetch(url);
      const data = await res.json().catch(() => ({}));
      if (data && data.code === 200) {
        return { ok: true, code, name };
      }
      return { ok: false, code, name, message: data?.message || `HTTP ${res.status}` };
    } catch (err) {
      return { ok: false, code, name, message: String(err) };
    }
  };

  const downloadSingle = async () => {
    const code = (comboboxValue.code || manualCode || '').trim();
    const name = (comboboxValue.name || manualName || '').trim();
    if (!/^\d{5}$/.test(code)) {
      alert('请输入有效的 5 位港股代码！');
      return;
    }
    if (!name) {
      alert('请输入公司简称（用于 Excel 文件名）！');
      return;
    }
    const r = await fetchOne(code, name);
    if (r.ok) {
      alert(`港股财报下载完成：${code} ${name}\n请查看 ${code}${name}.xlsx`);
    } else {
      alert(`港股财报下载失败：${code} ${name}\n${r.message}`);
    }
  };

  const parseBatchLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return null;
    const parts = trimmed.split(/[,\s，\t]+/).filter(Boolean);
    const code = parts[0] || '';
    const name = parts.slice(1).join(' ') || '';
    return { code, name };
  };

  const downloadBatch = async () => {
    const lines = batchInput.split('\n').map(parseBatchLine).filter(Boolean);
    if (lines.length === 0) {
      alert('请输入批量港股代码（每行：code 或 code,name）！');
      return;
    }
    const invalid = lines.filter((l) => !/^\d{5}$/.test(l.code));
    if (invalid.length > 0) {
      alert(`以下代码格式无效（需 5 位数字）：\n${invalid.map((l) => l.code).join('\n')}`);
      return;
    }
    const missingName = lines.filter((l) => !l.name);
    if (missingName.length > 0) {
      alert(`以下代码缺少公司简称：\n${missingName.map((l) => l.code).join('\n')}\n请补全或使用预设清单。`);
      return;
    }
    if (!window.confirm(`将依次下载 ${lines.length} 个港股财报（顺序执行），继续？`)) {
      return;
    }
    let success = 0;
    let failed = 0;
    const failedList = [];
    for (const item of lines) {
      const r = await fetchOne(item.code, item.name);
      if (r.ok) {
        success += 1;
      } else {
        failed += 1;
        failedList.push(`${item.code} ${item.name} (${r.message})`);
      }
    }
    const summary = `港股批量财报下载完成：成功 ${success} 个，失败 ${failed} 个`;
    if (failed === 0) {
      alert(summary);
    } else {
      alert(`${summary}\n失败明细：\n${failedList.join('\n')}`);
    }
  };

  const downloadPresets = async () => {
    if (!window.confirm(`将依次下载 ${PRESET_HK_CODES.length} 个常用港股财报（顺序执行），继续？`)) {
      return;
    }
    let success = 0;
    let failed = 0;
    const failedList = [];
    for (const item of PRESET_HK_CODES) {
      const r = await fetchOne(item.code, item.name);
      if (r.ok) {
        success += 1;
      } else {
        failed += 1;
        failedList.push(`${item.code} ${item.name} (${r.message})`);
      }
    }
    const summary = `常用港股财报下载完成：成功 ${success} 个，失败 ${failed} 个`;
    if (failed === 0) {
      alert(summary);
    } else {
      alert(`${summary}\n失败明细：\n${failedList.join('\n')}`);
    }
  };

  return (
    <div style={{ ...styles.card, ...styles.cardGoldCorner }}>
      <div style={styles.cardHeaderRow}>
        <p style={styles.cardTitle}>港股财报数据</p>
        <button
          type="button"
          onClick={() => setIsCardOpen((prev) => !prev)}
          style={styles.cardToggle}
          aria-label={isCardOpen ? '收起港股财报数据' : '展开港股财报数据'}
          title={isCardOpen ? '收起港股财报数据' : '展开港股财报数据'}
        >
          {isCardOpen ? '▾' : '▸'}
        </button>
      </div>
      <div
        style={{
          ...styles.collapseBody,
          maxHeight: isCardOpen ? '520px' : '0px',
          opacity: isCardOpen ? 1 : 0,
        }}
      >
        <div style={{ paddingTop: '6px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={styles.row}>
            <HKStockCombobox value={comboboxValue} onChange={setComboboxValue} />
          </div>

          <div style={styles.row}>
            <button
              type="button"
              onClick={downloadSingle}
              style={styles.buttonUnified}
              onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
              onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
            >
              下载单股财报
            </button>
          </div>

          <div style={styles.row}>
            <textarea
              value={batchInput}
              onChange={(e) => setBatchInput(e.target.value)}
              placeholder={'批量下载（每行：code 或 code,name）\n例：\n00700,腾讯控股\n09988,阿里巴巴-W'}
              style={styles.textarea}
            />
          </div>

          <div style={styles.row}>
            <button
              type="button"
              onClick={downloadBatch}
              style={{ ...styles.buttonUnified, flex: '1 1 0' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
              onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
            >
              批量下载
            </button>
            <button
              type="button"
              onClick={downloadPresets}
              style={{ ...styles.buttonUnified, flex: '1 1 0' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
              onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
            >
              下载常用港股
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HKFinanceCard;