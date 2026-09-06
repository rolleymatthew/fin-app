// Etf.jsx
import { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import { ETF_CODES, PRESET_STOCK_CODES } from './const';
import StockCombobox from './StockCombobox';
import HKFinanceCard from './HKFinanceCard';
import BankPBCard from './BankPBCard';
import { apiGet, apiPost, ApiError } from './api';

const Page = () => {
  const [data, setData] = useState([]);
  const [selectedEtfCode, setSelectedEtfCode] = useState(ETF_CODES[0].code);
  const [selectedTimeRange, setSelectedTimeRange] = useState('90');
  const [inputValue, setInputValue] = useState('');
  const [stockCodesInput, setStockCodesInput] = useState('');
  const [batchCodesInput, setBatchCodesInput] = useState('');
  const [etfKlineCodesInput, setEtfKlineCodesInput] = useState(ETF_CODES[0].code);
  const [manualEtfCode, setManualEtfCode] = useState('');
  const [shouldCrawl, setShouldCrawl] = useState('是'); // 是否爬取东财，默认选择"是"
  const [etfDownloadScope, setEtfDownloadScope] = useState('list');
  const [etfDataVersion, setEtfDataVersion] = useState(0);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isEtfCardOpen, setIsEtfCardOpen] = useState(true);
  const [isStockCardOpen, setIsStockCardOpen] = useState(false);
  const presetStockCodes = [...PRESET_STOCK_CODES].sort((a, b) => a.code.localeCompare(b.code));

  useEffect(() => {
    asyncFetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEtfCode, selectedTimeRange, manualEtfCode, shouldCrawl, etfDataVersion]); // 添加 shouldCrawl 作为依赖

  const asyncFetch = async () => {
    try {
      let codeToFetch = '';
      if (manualEtfCode && /^\d{6}$/.test(manualEtfCode)) { // 优先使用手动输入的有效代码
        codeToFetch = manualEtfCode;
      } else { // 否则使用下拉框选择的代码
        codeToFetch = selectedEtfCode;
      }

      const [etfResponse, kineResponse] = await Promise.all([
        apiGet('/api/etf/get?code=' + codeToFetch),
        apiGet('/api/kline/get?code=' + codeToFetch),
      ]);

      // 每次图表更新，把当前 ETF 的代码同步到输入框
      setEtfKlineCodesInput(codeToFetch);

      const dailyList = etfResponse?.data || [];
      const quarterList = etfResponse?.quarterly || [];

      const dailyData = dailyList.map((item) => ({
        date: item.statDate,
        totVol: parseFloat((item.totVol / 100000000).toFixed(2)),
      }));

      const klineData = (kineResponse.klines || []).map((item) => ({
        date: item.date,
        amountOfAverage: parseFloat(item.amountOfAverage),
      }));

      const quarterData = quarterList.map((item) => ({
        date: item.statDate,
        totVol: parseFloat((item.totVol / 100000000).toFixed(2)),
      }));

      // 合并日度 + 季度数据，按日期排序
      // 日度数据优先（同日期的日度覆盖季度）
      const mergedMap = new Map();
      dailyData.forEach((d) => {
        mergedMap.set(d.date, { date: d.date, vol: d.totVol, price: null });
      });
      quarterData.forEach((q) => {
        if (!mergedMap.has(q.date)) {
          mergedMap.set(q.date, { date: q.date, vol: q.totVol, price: null });
        }
      });
      // 合并价格（仅日度日期有 K 线）
      mergedMap.forEach((item) => {
        const klineItem = klineData.find((k) => k.date === item.date);
        if (klineItem) item.price = klineItem.amountOfAverage;
      });

      const sortedMerged = [...mergedMap.values()]
        .filter((item) => item.vol !== null)
        .sort((a, b) => new Date(a.date) - new Date(b.date));

      const currentDate = new Date();
      let startDate = new Date();

      switch (selectedTimeRange) {
        case '7':
          startDate.setDate(currentDate.getDate() - 7);
          break;
        case '15':
          startDate.setDate(currentDate.getDate() - 15);
          break;
        case '30':
          startDate.setMonth(currentDate.getMonth() - 1);
          break;
        case '90':
          startDate.setMonth(currentDate.getMonth() - 3);
          break;
        case '180':
          startDate.setMonth(currentDate.getMonth() - 6);
          break;
        case '360':
          startDate.setFullYear(currentDate.getFullYear() - 1);
          break;
        case '720':
          startDate.setFullYear(currentDate.getFullYear() - 2);
          break;
        default:
          startDate.setFullYear(currentDate.getMonth() - 3);
      }

      const recentMerged = sortedMerged.filter(
        (item) => new Date(item.date) >= startDate,
      );

      setData(recentMerged);
    } catch (error) {
      console.log('fetch data failed', error);
    }
  };

  const handleEtfDropdownChange = (event) => {
    setManualEtfCode('');
    setSelectedEtfCode(event.target.value);
    setEtfKlineCodesInput(event.target.value);
  };

  const handleTimeRangeDropdownChange = (event) => {
    setSelectedTimeRange(event.target.value);
  };

  const handleInputChange = (event) => {
    setInputValue(event.target.value);
  };

  const handleStockCodesInputChange = (event) => {
    setStockCodesInput(event.target.value);
  };

  const handleBatchCodesInputChange = (event) => {
    setBatchCodesInput(event.target.value);
  };

  const handleEtfDownloadScopeChange = (event) => {
    setEtfDownloadScope(event.target.value);
  };

  // 新增处理爬取选项变化的函数
  const handleCrawlChange = (event) => {
    setShouldCrawl(event.target.value);
  };

  const fetchEtfListByDays = async (daysValue) => {
    const uniqueEtfCodes = Array.from(new Set(ETF_CODES.map((item) => item.code)));
    const url = `/api/etf?days=${daysValue}&code=${uniqueEtfCodes.join(',')}&with_kline=true&with_quarter=true`;

    try {
      const data = await apiGet(url);
      console.log(`ETF List Data (days=${daysValue}):`, data);
      alert(
        `成功调用后台接口（日度 ${data?.daily ?? '?'} 条 / 季度 ${data?.quarter ?? '?'} 条）：\n${url}`
      );
      setEtfDataVersion((v) => v + 1);
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error(`Failed to fetch ETF list data (days=${daysValue}):`, error);
        alert('调用后台接口失败！');
      }
    }
  };

  const handleFetchCustomData = async () => {
    const daysValue = parseInt(inputValue, 10);

    if (isNaN(daysValue) || daysValue < 1) {
      alert('请输入一个大于等于 1 的有效数字！');
      return;
    }

    const uniqueEtfCodes = Array.from(new Set(ETF_CODES.map((item) => item.code)));
    const codeParam = etfDownloadScope === 'list' ? `&code=${uniqueEtfCodes.join(',')}` : '';
    const url = `/api/etf?days=${daysValue}${codeParam}&with_kline=true&with_quarter=true`;

    try {
      const data = await apiGet(url);
      console.log('Custom ETF Data (days):', data);
      alert('成功调用后台接口：' + url);
      setEtfDataVersion((v) => v + 1);
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to fetch custom ETF data (days):', error);
        alert('调用后台接口失败！');
      }
    }
  };

  const handleFetchListOneDay = async () => {
    await fetchEtfListByDays(1);
  };

  const handleFetchListOneWeek = async () => {
    await fetchEtfListByDays(7);
  };

  const handleFetchSzseSync = async () => {
    try {
      const data = await apiPost('/api/etf/szse/sync');
      const message = data?.message ?? JSON.stringify(data);
      console.log('SZSE sync:', data);
      alert(message);
      if (!data?.skipped) {
        setEtfDataVersion((v) => v + 1);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to sync SZSE ETF data:', error);
        alert('调用后台接口失败！');
      }
    }
  };

  const handleFetchStockData = async () => {
    let url = `/api/one?crawl=${shouldCrawl === '是' ? 'true' : 'false'}`;

    if (!stockCodesInput.trim()) {
      const shouldProceed = confirm('将要获取所有上市公司数据，确定要继续吗？');
      if (!shouldProceed) {
        return;
      }
    } else {
      const codes = stockCodesInput.split(',').map(code => code.trim()).filter(code => code !== '');
      if (codes.length === 0) {
        alert('请输入有效的上市公司代码！');
        return;
      }
      url = `${url}&code=${codes.join(',')}`;
    }

    try {
      await apiGet(url);
      console.log('Stock Data fetched:', url);
      alert('成功调用后台接口：' + url);
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to fetch stock data:', error);
        alert('调用后台接口失败！');
      }
    }
  };

  const fetchBatchStockCodes = async (codes) => {
    if (!codes || codes.length === 0) {
      alert('请输入有效的股票代码！');
      return;
    }
    const url = `/api/one?code=${codes.join(',')}&crawl=${shouldCrawl === '是' ? 'true' : 'false'}`;
    try {
      await apiGet(url);
      console.log('Batch Stock Data fetched:', url);
      alert('成功调用后台接口：' + url);
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to fetch batch stock data:', error);
        alert('调用后台接口失败！');
      }
    }
  };

  const handleFetchBatchCodes = async () => {
    const codes = batchCodesInput.split(',').map((code) => code.trim()).filter((code) => code !== '');
    await fetchBatchStockCodes(codes);
  };

  const pickStock = (code) => {
    setStockCodesInput(code);
    setBatchCodesInput((prev) => {
      const trimmed = (prev || '').replace(/[\s,]+$/, '');
      return trimmed ? `${trimmed},${code}` : code;
    });
  };

  const handlePresetSelectChange = (event) => {
    const code = event.target.value;
    if (!code) {
      return;
    }
    pickStock(code);
    fetchBatchStockCodes([code]);
  };

  const handleFetchAllPresetCodes = async () => {
    await fetchBatchStockCodes(presetStockCodes.map((item) => item.code));
  };

  const handleFetchEtfKline = async () => {
    const codes = etfKlineCodesInput.split(',').map((code) => code.trim()).filter((code) => code !== '');
    if (codes.length === 0) {
      alert('请输入有效的ETF代码！');
      return;
    }
    if (!window.confirm(`强制全量重抓以下 K线数据？将删除旧数据后从 Eastmoney 全量拉取。\n${codes.join(', ')}`)) {
      return;
    }

    let successCount = 0;
    let failCount = 0;
    for (const code of codes) {
      try {
        await apiPost(`/api/kline/refresh?code=${code}`);
        successCount += 1;
      } catch (error) {
        if (error instanceof ApiError) {
          console.warn('[api]', error.errorType, error.path, error.code, error.message);
        } else {
          console.error('Failed to refresh kline:', error);
        }
        failCount += 1;
      }
    }

    if (successCount > 0) {
      setEtfDataVersion((v) => v + 1);
    }
    alert(`K线刷新完成：成功 ${successCount} 个，失败 ${failCount} 个`);
  };

  const handleResumeStockData = async () => {
    if (!stockCodesInput.trim()) {
      alert('请输入有效的上市公司代码以继续断点续传！');
      return;
    }

    const codes = stockCodesInput.split(',').map(code => code.trim()).filter(code => code !== '');
    if (codes.length === 0) {
      alert('请输入有效的上市公司代码！');
      return;
    }

    // We'll use the first code as the keepon_code
    const keeponCode = codes[0];
    const url = `/api/one?keepon_code=${keeponCode}&crawl=${shouldCrawl === '是' ? 'true' : 'false'}`;

    try {
      await apiGet(url);
      console.log('Resume Stock Data fetched:', url);
      alert('成功调用断点续传接口：' + url);
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to resume stock data:', error);
        alert('调用断点续传接口失败！');
      }
    }
  };

  const handleSyncSecCode = async () => {
    const confirmed = confirm('将拉取上交所/深交所官方列表并补齐缺失股票，继续吗？');
    if (!confirmed) return;
    try {
      const d = await apiPost('/api/sec/sync', { force: false });
      alert(
        `同步完成：官方 ${d.total_in_official ?? '?'} / 新增 ${d.new_added ?? '?'} / 变更 ${d.state_changed ?? '?'} / 回填 ${d.details_refilled ?? '?'} / 失败 ${(d.failed || []).length}`
      );
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to sync sec_code:', error);
        alert('调用后台接口失败！');
      }
    }
  };

  const handleRefreshAllDetails = async () => {
    const confirmed = confirm('将全量重拉所有股票详情（含退市/ST），耗时较长，继续吗？');
    if (!confirmed) return;
    try {
      const d = await apiPost('/api/sec/refresh-details', { include_delisted: true, only_missing: false });
      alert(`全量更新完成：回填 ${d.details_refilled ?? '?'} / 失败 ${(d.failed || []).length}`);
    } catch (error) {
      if (error instanceof ApiError) {
        console.warn('[api]', error.errorType, error.path, error.code, error.message);
        alert(error.message);
      } else {
        console.error('Failed to refresh details:', error);
        alert('调用后台接口失败！');
      }
    }
  };

  const styles = {
    page: {
      minHeight: '100vh',
      padding: 0,
      width: '100vw',
      background: '#F8FAFC',
      color: '#0f172a',
      fontFamily: '"Plus Jakarta Sans", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      boxSizing: 'border-box',
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '16px',
      flexWrap: 'wrap',
      padding: '10px 12px',
      background: '#ffffff',
      border: '1px solid rgba(148, 163, 184, 0.28)',
      borderRadius: '12px',
      boxShadow: 'none',
    },
    titleWrap: {
      display: 'flex',
      flexDirection: 'column',
      gap: '6px',
    },
    titleDivider: {
      height: '1px',
      width: '40px',
      background: 'linear-gradient(90deg, rgba(180, 83, 9, 0.25), rgba(253, 230, 138, 0.04))',
    },
    title: {
      fontSize: '22px',
      fontWeight: 700,
      letterSpacing: '0.2px',
      margin: 0,
    },
    subtitle: {
      fontSize: '13px',
      color: 'rgba(15, 23, 42, 0.6)',
      margin: 0,
    },
    badgeRow: {
      display: 'flex',
      gap: '8px',
      flexWrap: 'wrap',
    },
    badge: {
      fontSize: '12px',
      padding: '6px 10px',
      borderRadius: '999px',
      background: 'rgba(59, 130, 246, 0.12)',
      border: '1px solid rgba(59, 130, 246, 0.35)',
      color: '#1d4ed8',
    },
    controlGrid: {
      display: 'grid',
      gridTemplateColumns: '1fr',
      gap: '10px',
    },
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
    cardTitle: {
      fontSize: '14px',
      fontWeight: 700,
      color: '#0f172a',
      margin: 0,
      letterSpacing: '0.3px',
    },
    cardHeaderRow: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '8px',
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
    stockCollapseBody: {
      maxHeight: '460px',
      overflowY: 'auto',
      paddingRight: '4px',
    },
    row: {
      display: 'flex',
      alignItems: 'center',
      gap: 20,
      flexWrap: 'wrap',
    },
    label: {
      minWidth: 70,
      textAlign: 'right',
      color: '#5b6470',
      fontSize: 13,
    },
    input: {
      height: 32,
      padding: '0 10px',
      borderRadius: 6,
      border: '1px solid #d9dee5',
      fontSize: 13,
      background: '#fff',
      outline: 'none',
      minWidth: 240,
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
    },
    select: {
      height: 32,
      padding: '0 10px',
      borderRadius: 6,
      border: '1px solid #d9dee5',
      fontSize: 13,
      background: '#fff',
      minWidth: 0,
      flex: '1 1 0',
      outline: 'none',
      boxSizing: 'border-box',
    },
    button: {
      background: '#1677FF',
      border: 'none',
      borderRadius: '8px',
      color: '#ffffff',
      padding: '5px 10px',
      fontWeight: 600,
      fontSize: '12px',
      cursor: 'pointer',
      boxShadow: 'none',
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
    buttonGhost: {
      background: '#f8fafc',
      border: '1px solid rgba(148, 163, 184, 0.6)',
      borderRadius: '8px',
      color: '#0f172a',
      padding: '5px 10px',
      fontWeight: 600,
      fontSize: '12px',
      cursor: 'pointer',
      boxShadow: 'none',
    },
    pill: {
      border: '1px solid rgba(148, 163, 184, 0.6)',
      background: '#ffffff',
      borderRadius: '999px',
      color: '#0f172a',
      padding: '4px 10px',
      fontWeight: 600,
      fontSize: '12px',
      cursor: 'pointer',
    },
    chartWrap: {
      flex: 1,
      minHeight: 0,
      background: 'rgba(255, 255, 255, 0.92)',
      border: 'none',
      borderRadius: 0,
      padding: 0,
      boxShadow: 'none',
    },
    layout: {
      display: 'flex',
      gap: '12px',
      flex: 1,
      minHeight: 0,
      position: 'relative',
    },
    sidebar: {
      width: '260px',
      minWidth: '220px',
      maxWidth: '280px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      position: 'relative',
      zIndex: 2,
      padding: '10px',
      boxSizing: 'border-box',
      transition: 'transform 0.25s ease, opacity 0.25s ease',
      borderRight: '1px solid rgba(148, 163, 184, 0.35)',
      background: 'linear-gradient(180deg, rgba(255, 250, 240, 0.98) 0%, rgba(255, 255, 255, 0.98) 100%)',
    },
    sidebarCollapsed: {
      transform: 'translateX(-100%)',
      opacity: 0,
      pointerEvents: 'none',
      borderRight: 'none',
      width: 0,
      minWidth: 0,
      maxWidth: 0,
      padding: 0,
      overflow: 'hidden',
    },
    content: {
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      position: 'relative',
    },
    toggleButton: {
      position: 'absolute',
      top: '12px',
      left: '12px',
      zIndex: 3,
      background: 'rgba(255, 255, 255, 0.95)',
      border: '1px solid rgba(148, 163, 184, 0.6)',
      borderRadius: '999px',
      color: '#0f172a',
      width: '36px',
      height: '36px',
      padding: 0,
      fontWeight: 600,
      fontSize: '16px',
      cursor: 'pointer',
      boxShadow: '0 10px 18px rgba(15, 23, 42, 0.08)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
  };

  const getOption = () => {
    const dates = data.map((item) => item.date);
    const vols = data.map((item) => item.vol);
    const prices = data.map((item) => item.price);
    const selectedEtf = ETF_CODES.find((etf) => etf.code === selectedEtfCode);
    const selectedLabel = selectedEtf ? `${selectedEtf.name} ${selectedEtf.code}` : selectedEtfCode;

    return {
      grid: {
        left: '3%',
        right: '3%',
        top: '10%',
        bottom: '15%',
        containLabel: true,
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
        },
      },
      legend: {
        data: [
          {
            name: selectedLabel,
            icon: 'roundRect',
            textStyle: { color: '#0f172a', fontWeight: 600 },
          },
          '规模(亿份)',
          '价格(元)',
        ],
        bottom: 10,
        textStyle: {
          color: '#475569',
        },
      },
      xAxis: [
        {
          type: 'category',
          data: dates,
          axisPointer: {
            type: 'shadow',
          },
          axisLabel: {
            color: '#64748b',
          },
          axisLine: {
            lineStyle: { color: 'rgba(148, 163, 184, 0.5)' },
          },
        },
      ],
      yAxis: [
        {
          type: 'value',
          name: '规模(亿份)',
          min: 0,
          axisLabel: {
            formatter: '{value}',
            color: '#64748b',
          },
          position: 'left',
          alignTicks: false,
          splitLine: {
            lineStyle: { color: 'rgba(148, 163, 184, 0.25)' },
          },
        },
        {
          type: 'value',
          name: '价格(元)',
          min: 0,
          axisLabel: {
            formatter: '{value}',
            color: '#64748b',
          },
          position: 'right',
          alignTicks: false,
          splitLine: {
            show: false,
          },
        },
      ],
      series: [
        {
          name: '规模(亿份)',
          type: 'line',
          data: vols,
          yAxisIndex: 0,
          smooth: true,
          connectNulls: true,
          itemStyle: {
            color: '#2563eb',
          },
          areaStyle: {
            color: 'rgba(37, 99, 235, 0.12)',
          },
        },
        {
          name: '价格(元)',
          type: 'line',
          data: prices,
          yAxisIndex: 1,
          smooth: true,
          connectNulls: true,
          itemStyle: {
            color: '#f97316',
          },
          areaStyle: {
            color: 'rgba(249, 115, 22, 0.12)',
          },
        },
      ],
    };
  };

  return (
    <div style={styles.page}>
      <div style={styles.layout}>
        <div style={{ ...styles.sidebar, ...(isSidebarOpen ? {} : styles.sidebarCollapsed) }}>
          <div style={{ ...styles.header, padding: '10px 12px' }}>
            <div style={styles.titleWrap}>
              <h1 style={{ ...styles.title, fontSize: '16px' }}>ETF数据与股票数据</h1>
              <span style={styles.titleDivider} />
            </div>
          </div>

          <div style={styles.controlGrid}>
            <div style={{ ...styles.card, ...styles.cardGoldCorner }}>
              <div style={styles.cardHeaderRow}>
                <p style={styles.cardTitle}>ETF 数据</p>
                <button
                  type="button"
                  onClick={() => setIsEtfCardOpen((prev) => !prev)}
                  style={styles.cardToggle}
                  aria-label={isEtfCardOpen ? '收起ETF数据' : '展开ETF数据'}
                  title={isEtfCardOpen ? '收起ETF数据' : '展开ETF数据'}
                >
                  {isEtfCardOpen ? '▾' : '▸'}
                </button>
              </div>
              <div
                style={{
                  ...styles.collapseBody,
                  maxHeight: isEtfCardOpen ? '420px' : '0px',
                  opacity: isEtfCardOpen ? 1 : 0,
                }}
              >
                <div style={{ paddingTop: '6px' }}>
                  {/* 行1：ETF select + 时间段 select */}
                  <div style={styles.row}>
                    <select id="etf-select" value={selectedEtfCode} onChange={handleEtfDropdownChange} style={styles.select}>
                      {ETF_CODES.map((etf) => (
                        <option key={etf.code} value={etf.code}>
                          {etf.name}
                        </option>
                      ))}
                    </select>
                    <select id="time-range-select" value={selectedTimeRange} onChange={handleTimeRangeDropdownChange} style={styles.select}>
                      <option value="7">最近7天</option>
                      <option value="15">最近半个月</option>
                      <option value="30">最近1个月</option>
                      <option value="90">最近3个月</option>
                      <option value="180">最近半年</option>
                      <option value="360">最近1年</option>
                      <option value="720">最近2年</option>
                    </select>
                  </div>
                  {/* 行1.5：搜索框（独立一行） */}
                  <div style={styles.row}>
                    <StockCombobox
                      apiUrl="/api/etf/search"
                      width={'100%'}
                      placeholder="代码/拼音/名称"
                      onSelect={({ code }) => {
                        if (/^\d{6}$/.test(code)) {
                          setManualEtfCode(code);
                        }
                      }}
                    />
                  </div>
                  {/* 行2：只读代码框 + 按钮 */}
                  <div style={styles.row}>
                    <input
                      type="text"
                      value={etfKlineCodesInput}
                      readOnly
                      style={{ ...styles.input, flex: '1 1 0', minWidth: 0 }}
                    />
                    <button
                      onClick={handleFetchEtfKline}
                      style={styles.buttonUnified}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      获取K线
                    </button>
                  </div>
                  {/* 行3：天数 + 范围 radio */}
                  <div style={styles.row}>
                    <input
                      type="text"
                      id="custom-input"
                      value={inputValue}
                      onChange={handleInputChange}
                      placeholder="输入天数 (>=1)"
                      style={{ ...styles.input, flex: '1 1 0', minWidth: 0 }}
                    />
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#0f172a', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                      <input
                        type="radio"
                        name="etf-download-scope"
                        value="list"
                        checked={etfDownloadScope === 'list'}
                        onChange={handleEtfDownloadScopeChange}
                      />
                      列表
                    </label>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#0f172a', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                      <input
                        type="radio"
                        name="etf-download-scope"
                        value="all"
                        checked={etfDownloadScope === 'all'}
                        onChange={handleEtfDownloadScopeChange}
                      />
                      全部
                    </label>
                  </div>
                  {/* 行4：4 个统一按钮（flex-wrap 自然分两行） */}
                  <div style={styles.row}>
                    <button
                      onClick={handleFetchCustomData}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      获取数据
                    </button>
                    <button
                      onClick={handleFetchListOneDay}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      列表1天
                    </button>
                    <button
                      onClick={handleFetchListOneWeek}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      列表1周
                    </button>
                    <button
                      onClick={handleFetchSzseSync}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      下载深ETF份额
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div style={{ ...styles.card, ...styles.cardGoldCorner }}>
              <div style={styles.cardHeaderRow}>
                <p style={styles.cardTitle}>股票数据</p>
                <button
                  type="button"
                  onClick={() => setIsStockCardOpen((prev) => !prev)}
                  style={styles.cardToggle}
                  aria-label={isStockCardOpen ? '收起股票数据' : '展开股票数据'}
                  title={isStockCardOpen ? '收起股票数据' : '展开股票数据'}
                >
                  {isStockCardOpen ? '▾' : '▸'}
                </button>
              </div>
              <div
                style={{
                  ...styles.collapseBody,
                  ...(isStockCardOpen ? styles.stockCollapseBody : {}),
                  maxHeight: isStockCardOpen ? styles.stockCollapseBody.maxHeight : '0px',
                  opacity: isStockCardOpen ? 1 : 0,
                }}
              >
                <div style={{ paddingTop: '6px' }}>
                  {/* 行1：StockCombobox */}
                  <div style={styles.row}>
                    <StockCombobox
                      width={'100%'}
                      onSelect={({ code }) => pickStock(code)}
                    />
                  </div>
                  {/* 行2：常用 select + 下载常用票 */}
                  <div style={styles.row}>
                    <select
                      id="preset-stock-select"
                      defaultValue=""
                      onChange={handlePresetSelectChange}
                      style={{ ...styles.select, minWidth: '70px', maxWidth: '100px' }}
                      title="原 47 个常用股票快速选择"
                    >
                      <option value="" disabled>常用</option>
                      {presetStockCodes.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.name} {item.code}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={handleFetchAllPresetCodes}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      下载常用票
                    </button>
                  </div>
                  {/* 行3：是否爬取（radio） */}
                  <div style={styles.row}>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#0f172a', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                      <input
                        type="radio"
                        name="crawl-select"
                        value="是"
                        checked={shouldCrawl === '是'}
                        onChange={handleCrawlChange}
                      />
                      抓东财
                    </label>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#0f172a', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                      <input
                        type="radio"
                        name="crawl-select"
                        value="否"
                        checked={shouldCrawl === '否'}
                        onChange={handleCrawlChange}
                      />
                      不抓
                    </label>
                  </div>
                  {/* 行4：单股代码 input（独立一行） */}
                  <div style={styles.row}>
                    <input
                      type="text"
                      id="stock-codes-input"
                      value={stockCodesInput}
                      onChange={handleStockCodesInputChange}
                      placeholder="如: 600519"
                      style={{ ...styles.input, flex: '1 1 0', minWidth: 0 }}
                    />
                  </div>
                  {/* 行5：拉数据 + 断点续传（同一行） */}
                  <div style={styles.row}>
                    <button
                      onClick={handleFetchStockData}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      拉数据
                    </button>
                    <button
                      onClick={handleResumeStockData}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      断点续传
                    </button>
                  </div>
                  {/* 行5：批量代码 textarea */}
                  <div style={styles.row}>
                    <textarea
                      id="batch-codes-input"
                      value={batchCodesInput}
                      onChange={handleBatchCodesInputChange}
                      placeholder="如: 000001,000002"
                      style={{ ...styles.textarea, flex: '1 1 0', minWidth: 0 }}
                    />
                  </div>
                  {/* 行6：批量获取 + 补缺失代码 + 全量更新 */}
                  <div style={styles.row}>
                    <button
                      onClick={handleFetchBatchCodes}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      批量获取
                    </button>
                    <button
                      onClick={handleSyncSecCode}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      补缺失代码
                    </button>
                    <button
                      onClick={handleRefreshAllDetails}
                      style={{ ...styles.buttonUnified, flex: '1 1 0' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = styles.buttonUnifiedHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = styles.buttonUnified.background)}
                    >
                      全量更新
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <HKFinanceCard />
            <BankPBCard />
          </div>
        </div>

        <div style={styles.content}>
          <button
            type="button"
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            style={styles.toggleButton}
            title={isSidebarOpen ? '收起面板' : '展开面板'}
            aria-label={isSidebarOpen ? '收起面板' : '展开面板'}
          >
            {isSidebarOpen ? '◀' : '▶'}
          </button>
          <div style={{ ...styles.card, ...styles.cardGoldCorner, ...styles.chartWrap }}>
            <div style={{ flex: 1, minHeight: 0 }}>
              <ReactECharts option={getOption()} style={{ width: '100%', height: '100%' }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Page;
