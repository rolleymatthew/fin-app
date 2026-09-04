// StockCombobox.jsx
// 股票搜索下拉框：输入 代码 / 拼音首字母 / 中文名，实时模糊匹配。
// 后端接口：GET /api/sec/search?q=<str>&limit=<int>
// 0 外部依赖，纯手写（input + 浮层 + 键盘导航）。
/* eslint-disable react/prop-types */
import { useState, useRef, useEffect, useCallback } from 'react';
import { apiGet, ApiError } from './api';

const DEFAULT_DEBOUNCE = 200;
const DEFAULT_LIMIT = 200;

const styles = {
  wrap: { position: 'relative', display: 'inline-block', width: '100%' },
  input: {
    height: 32,
    background: '#fff',
    border: '1px solid #d9dee5',
    borderRadius: 6,
    color: '#0f172a',
    padding: '0 10px',
    fontSize: 13,
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    marginTop: '2px',
    background: '#ffffff',
    border: '1px solid #d9dee5',
    borderRadius: 6,
    boxShadow: '0 6px 20px rgba(15, 23, 42, 0.14)',
    maxHeight: '320px',
    overflowY: 'auto',
    zIndex: 1000,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 10px',
    fontSize: 13,
    cursor: 'pointer',
    color: '#0f172a',
  },
  itemActive: {
    background: 'rgba(59, 91, 122, 0.10)',
  },
  colCode: { fontFamily: 'Consolas, Menlo, monospace', color: '#1d4ed8', minWidth: '64px' },
  colName: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  colPinyin: { color: 'rgba(15, 23, 42, 0.4)', fontFamily: 'Consolas, Menlo, monospace', fontSize: '11px' },
  hint: { padding: '10px', fontSize: '13px', color: 'rgba(15, 23, 42, 0.5)' },
  match: { color: '#3b5b7a', fontWeight: 600 },
};

function highlight(text, query) {
  if (!text || !query) return text;
  const lower = String(text).toLowerCase();
  const q = String(query).toLowerCase();
  const idx = lower.indexOf(q);
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <span style={styles.match}>{text.slice(idx, idx + query.length)}</span>
      {text.slice(idx + query.length)}
    </>
  );
}

const StockCombobox = ({
  placeholder = '代码/拼音/名称 (nd)',
  onSelect,
  debounceMs = DEFAULT_DEBOUNCE,
  limit = DEFAULT_LIMIT,
  width = 200,
  apiUrl = '/api/sec/search',
}) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const [displayQuery, setDisplayQuery] = useState('');

  const wrapRef = useRef(null);
  const inputRef = useRef(null);
  const itemRefs = useRef([]);
  const debounceTimer = useRef(null);
  const closeTimer = useRef(null);
  const cacheRef = useRef(new Map());
  const reqIdRef = useRef(0);

  const fetchData = useCallback(
    (q) => {
      const cacheKey = q || '__empty__';
      const cached = cacheRef.current.get(cacheKey);
      if (cached) {
        setItems(cached);
        setHighlightIdx(0);
        setLoading(false);
        return;
      }
      setLoading(true);
      const myId = ++reqIdRef.current;
      const url = `${apiUrl}?limit=${limit}` + (q ? `&q=${encodeURIComponent(q)}` : '');
      apiGet(url)
        .then((rows) => {
          if (myId !== reqIdRef.current) return; // 过期响应丢弃
          const list = Array.isArray(rows) ? rows : [];
          cacheRef.current.set(cacheKey, list);
          setItems(list);
          setHighlightIdx(0);
          setLoading(false);
        })
        .catch((err) => {
          if (myId !== reqIdRef.current) return;
          if (err instanceof ApiError) {
            console.warn('[api]', err.errorType, err.path, err.code, err.message);
          }
          setItems([]);
          setHighlightIdx(0);
          setLoading(false);
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [limit],
  );

  const scheduleFetch = useCallback(
    (q) => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => fetchData(q), debounceMs);
    },
    [debounceMs, fetchData],
  );

  const handleChange = (e) => {
    const val = e.target.value;
    setDisplayQuery(val);
    setQuery(val);
    setOpen(true);
    scheduleFetch(val);
  };

  const handleFocus = (e) => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setOpen(true);
    if (items.length === 0 && !loading) {
      fetchData(query);
    }
    if (displayQuery && e && e.target && e.target.select) {
      e.target.select();
    }
  };

  const handleClick = () => {
    if (!open) setOpen(true);
  };

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  const handleBlur = () => {
    closeTimer.current = setTimeout(close, 180);
  };

  const pick = useCallback(
    (item) => {
      if (!item) return;
      if (closeTimer.current) {
        clearTimeout(closeTimer.current);
        closeTimer.current = null;
      }
      const label = item.name ? `${item.name} ${item.code}` : item.code;
      setDisplayQuery(label);
      setQuery('');
      setOpen(false);
      if (onSelect) onSelect({ code: item.code, name: item.name });
    },
    [onSelect],
  );

  const handleKeyDown = (e) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) {
      setOpen(true);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (items[highlightIdx]) pick(items[highlightIdx]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  };

  useEffect(() => {
    if (!open) return;
    const node = itemRefs.current[highlightIdx];
    if (node && node.scrollIntoView) {
      node.scrollIntoView({ block: 'nearest' });
    }
  }, [highlightIdx, open]);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (closeTimer.current) clearTimeout(closeTimer.current);
    };
  }, []);

  const showDropdown = open;
  const activeQuery = displayQuery || query;

  return (
    <div ref={wrapRef} style={{ ...styles.wrap, width }}>
      <input
        ref={inputRef}
        type="text"
        value={displayQuery}
        placeholder={placeholder}
        onChange={handleChange}
        onFocus={handleFocus}
        onClick={handleClick}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        style={styles.input}
        autoComplete="off"
      />
      {showDropdown && (
        <div style={styles.dropdown}>
          {loading && <div style={styles.hint}>加载中…</div>}
          {!loading && items.length === 0 && (
            <div style={styles.hint}>
              {activeQuery ? `无匹配「${activeQuery}」` : '暂无数据'}
            </div>
          )}
          {!loading &&
            items.map((item, idx) => (
              <div
                key={item.code}
                ref={(el) => (itemRefs.current[idx] = el)}
                style={{ ...styles.item, ...(idx === highlightIdx ? styles.itemActive : null) }}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(item);
                }}
                onMouseEnter={() => setHighlightIdx(idx)}
              >
                <span style={styles.colCode}>{highlight(item.code, activeQuery)}</span>
                <span style={styles.colName}>{highlight(item.name, activeQuery)}</span>
                <span style={styles.colPinyin}>{item.pinyin || ''}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
};

export default StockCombobox;
