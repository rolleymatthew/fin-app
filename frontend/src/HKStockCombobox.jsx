// HKStockCombobox.jsx
// 港股代码选择器：<select>(预设清单) + 2x2 网格（上方 readonly 显示当前选中，下方手动输入）。
// 不依赖 /api/sec/search（港股没有 sec_code 表），全部本地。
/* eslint-disable react/prop-types */
import { useState } from 'react';
import { PRESET_HK_CODES } from './const';

const styles = {
  wrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    width: '100%',
    boxSizing: 'border-box',
  },
  select: {
    height: 32,
    padding: '0 10px',
    borderRadius: 6,
    border: '1px solid #d9dee5',
    fontSize: 13,
    background: '#fff',
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  },
  gridRow: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '8px',
    width: '100%',
  },
  box: {
    height: 38,
    padding: '0 10px',
    borderRadius: 8,
    border: '1px solid rgba(148, 163, 184, 0.55)',
    fontSize: 13,
    outline: 'none',
    boxSizing: 'border-box',
    display: 'flex',
    alignItems: 'center',
  },
  displayBox: {
    background: '#f8fafc',
    color: '#0f172a',
    fontWeight: 600,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  displayBoxPlaceholder: {
    background: '#f8fafc',
    color: 'rgba(15, 23, 42, 0.45)',
    fontWeight: 400,
  },
  input: {
    background: '#fff',
    color: '#0f172a',
    width: '100%',
  },
};

const HKStockCombobox = ({ value, onChange }) => {
  const [code, setCode] = useState(value?.code || '');
  const [name, setName] = useState(value?.name || '');

  const emit = (nextCode, nextName) => {
    if (onChange) onChange({ code: nextCode, name: nextName });
  };

  const handlePresetChange = (e) => {
    const pickedCode = e.target.value;
    if (!pickedCode) return;
    const preset = PRESET_HK_CODES.find((p) => p.code === pickedCode);
    if (!preset) return;
    setCode(preset.code);
    setName(preset.name);
    emit(preset.code, preset.name);
  };

  const handleCodeInput = (e) => {
    const raw = e.target.value.replace(/\D/g, '').slice(0, 5);
    setCode(raw);
    emit(raw, name);
  };

  const handleNameInput = (e) => {
    const v = e.target.value;
    setName(v);
    emit(code, v);
  };

  return (
    <div style={styles.wrap}>
      <select
        value={code}
        onChange={handlePresetChange}
        style={styles.select}
        title="港股快速选择"
      >
        <option value="" disabled>预设港股</option>
        {PRESET_HK_CODES.map((item) => (
          <option key={item.code} value={item.code}>
            {item.name} {item.code}
          </option>
        ))}
      </select>
    </div>
  );
};

export default HKStockCombobox;