import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertCircle,
  BarChart2,
  GitCommit,
  Sliders,
  TrendingUp,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AnalyticsRunResponse,
  AnomalyMethod,
  CorrelationResponse,
  DynamicConfigPayload,
  Timeframe,
} from '../types/arkadanta';
import {
  fetchCrossAssetCorrelation,
  runDynamicAnalyticsApi,
  SUPPORTED_SYMBOLS,
  SUPPORTED_TIMEFRAMES,
} from '../services/api';

interface Props {
  config: DynamicConfigPayload;
  onChangeConfig: (partial: Partial<DynamicConfigPayload>) => void;
}

type HeroChartMode = 'price' | 'volatility' | 'oscillator';

export const Tab2AnalyticsBI: React.FC<Props> = ({ config, onChangeConfig }) => {
  const [analytics, setAnalytics] = useState<AnalyticsRunResponse | null>(null);
  const [correlation, setCorrelation] = useState<CorrelationResponse | null>(null);
  const [heroMode, setHeroMode] = useState<HeroChartMode>('price');
  const [corrBase, setCorrBase] = useState<string>('BTCUSDT');
  const [corrTarget, setCorrTarget] = useState<string>('ETHUSDT');
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      runDynamicAnalyticsApi(config),
      fetchCrossAssetCorrelation(
        config.timeframe,
        corrBase,
        corrTarget,
        config.correlation_window
      ),
    ]).then(([aRes, cRes]) => {
      if (!active) return;
      setAnalytics(aRes);
      setCorrelation(cRes);
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [
    config.symbol,
    config.timeframe,
    config.ma_period,
    config.rsi_period,
    config.rolling_window,
    config.anomaly_method,
    config.anomaly_quantile,
    config.anomaly_z_threshold,
    config.correlation_window,
    corrBase,
    corrTarget,
  ]);

  const seriesData = (analytics?.series || []).slice(-85).map((d) => ({
    ...d,
    shortTime: d.timestamp.slice(5, 16).replace('T', ' '),
    volPct: Number((d.max_volatility * 100).toFixed(3)),
    rollVolPct: Number((d.rolling_volatility * 100).toFixed(3)),
    bbWidthPct: Number((d.bb_width * 100).toFixed(3)),
    anomalyMarker: d.is_anomaly ? d.close : null,
  }));

  const latestPoint = seriesData[seriesData.length - 1];
  const thresholdVal =
    analytics?.anomaly_summary.threshold_info.per_symbol_threshold[config.symbol] ?? 0;

  return (
    <div>
      {/* ROW 1: BLACK DASHBOARD HERO PERFORMANCE CHART CARD */}
      <div className="bd-card">
        <div className="bd-card-header flex flex-wrap items-start justify-between gap-4">
          <div>
            <h5 className="bd-card-category">
              Multi-Timeframe OHLCV Aggregation &amp; Anomaly Detection ({config.timeframe})
            </h5>
            <h2 className="bd-card-title flex items-center gap-3">
              <span>{config.symbol} Performance</span>
              {latestPoint && (
                <span className="text-base font-mono text-[#00f2c3] font-normal">
                  ${latestPoint.close.toLocaleString()}
                </span>
              )}
              {loading && (
                <span className="text-xs font-normal text-[#1d8cf8]">Updating...</span>
              )}
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Timeframe Selector Group */}
            <div className="inline-flex">
              {SUPPORTED_TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onChangeConfig({ timeframe: tf })}
                  className={`bd-btn-toggle ${config.timeframe === tf ? 'active' : ''}`}
                >
                  {tf}
                </button>
              ))}
            </div>

            {/* Chart Layer Mode Toggle (Accounts / Purchases / Sessions style) */}
            <div className="inline-flex">
              <button
                type="button"
                onClick={() => setHeroMode('price')}
                className={`bd-btn-toggle ${heroMode === 'price' ? 'active' : ''}`}
              >
                Price &amp; MA
              </button>
              <button
                type="button"
                onClick={() => setHeroMode('volatility')}
                className={`bd-btn-toggle ${heroMode === 'volatility' ? 'active' : ''}`}
              >
                Bollinger &amp; Volatility
              </button>
              <button
                type="button"
                onClick={() => setHeroMode('oscillator')}
                className={`bd-btn-toggle ${heroMode === 'oscillator' ? 'active' : ''}`}
              >
                RSI-14 &amp; Volume
              </button>
            </div>
          </div>
        </div>

        <div className="bd-card-body">
          <div className="h-[310px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              {heroMode === 'price' ? (
                <ComposedChart data={seriesData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="bdBlueGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1d8cf8" stopOpacity={0.32} />
                      <stop offset="95%" stopColor="#1d8cf8" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="2 4"
                    stroke="rgba(29, 140, 248, 0.09)"
                    vertical={true}
                  />
                  <XAxis
                    dataKey="shortTime"
                    stroke="#9a9a9a"
                    tick={{ fontSize: 11, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    stroke="#9a9a9a"
                    tick={{ fontSize: 11, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `$${Number(v).toLocaleString()}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e1e2f',
                      border: '1px solid #2b3553',
                      borderRadius: '6px',
                      fontSize: '12px',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="close"
                    stroke="#1d8cf8"
                    strokeWidth={2}
                    fill="url(#bdBlueGrad)"
                    name="Close Price"
                    dot={{ r: 2, fill: '#27293d', stroke: '#1d8cf8', strokeWidth: 1.5 }}
                    activeDot={{ r: 5, fill: '#1d8cf8', stroke: '#ffffff', strokeWidth: 2 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="sma_20"
                    stroke="#00f2c3"
                    strokeWidth={1.5}
                    dot={false}
                    name={`SMA (${config.ma_period})`}
                  />
                  <Line
                    type="monotone"
                    dataKey="ema_20"
                    stroke="#e14eca"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    dot={false}
                    name={`EMA (${config.ma_period})`}
                  />
                  <Scatter
                    dataKey="anomalyMarker"
                    fill="#fd5d93"
                    name="Anomaly Detected"
                  />
                </ComposedChart>
              ) : heroMode === 'volatility' ? (
                <AreaChart data={seriesData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="bdPinkGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#e14eca" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#e14eca" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(225, 78, 202, 0.09)" />
                  <XAxis
                    dataKey="shortTime"
                    stroke="#9a9a9a"
                    tick={{ fontSize: 11, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="#9a9a9a"
                    tick={{ fontSize: 11, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e1e2f',
                      border: '1px solid #2b3553',
                      borderRadius: '6px',
                      fontSize: '12px',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="bbWidthPct"
                    stroke="#e14eca"
                    strokeWidth={2}
                    fill="url(#bdPinkGrad)"
                    name="Bollinger Width (%)"
                  />
                  <Line
                    type="monotone"
                    dataKey="volPct"
                    stroke="#fd5d93"
                    strokeWidth={2}
                    dot={false}
                    name="Max Volatility (%)"
                  />
                </AreaChart>
              ) : (
                <ComposedChart data={seriesData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(0, 242, 195, 0.08)" />
                  <XAxis
                    dataKey="shortTime"
                    stroke="#9a9a9a"
                    tick={{ fontSize: 11, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="rsi"
                    domain={[0, 100]}
                    stroke="#9a9a9a"
                    tick={{ fontSize: 11, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="vol"
                    orientation="right"
                    stroke="#9a9a9a"
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e1e2f',
                      border: '1px solid #2b3553',
                      borderRadius: '6px',
                      fontSize: '12px',
                    }}
                  />
                  <ReferenceLine yAxisId="rsi" y={70} stroke="#fd5d93" strokeDasharray="3 3" />
                  <ReferenceLine yAxisId="rsi" y={30} stroke="#00f2c3" strokeDasharray="3 3" />
                  <Bar
                    yAxisId="vol"
                    dataKey="volume"
                    fill="#1d8cf8"
                    opacity={0.25}
                    name="Volume"
                  />
                  <Line
                    yAxisId="rsi"
                    type="monotone"
                    dataKey="rsi_14"
                    stroke="#00f2c3"
                    strokeWidth={2}
                    dot={{ r: 2, fill: '#27293d', stroke: '#00f2c3' }}
                    name={`RSI (${config.rsi_period})`}
                  />
                </ComposedChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ROW 2: DYNAMIC ANALYTICS & ANOMALY FILTER BAR */}
      <div className="bd-card">
        <div className="bd-card-header flex items-center justify-between">
          <div>
            <h5 className="bd-card-category">Dynamic Pipeline Configuration</h5>
            <h4 className="text-sm font-normal text-white flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#1d8cf8]" />
              Feature Parameters &amp; Anomaly Detection Thresholds
            </h4>
          </div>
          <div className="flex items-center gap-4 text-xs text-[#9a9a9a]">
            <span>
              Candles: <strong className="text-white">{analytics?.total_candles ?? 0}</strong>
            </span>
            <span>
              Anomalies:{' '}
              <strong className="text-[#fd5d93]">
                {analytics?.anomaly_summary.total_anomalies ?? 0} (
                {analytics?.anomaly_summary.anomaly_rate_pct ?? 0}%)
              </strong>
            </span>
            <span>
              Threshold: <strong className="text-[#00f2c3] font-mono">{thresholdVal}</strong>
            </span>
          </div>
        </div>
        <div className="bd-card-body">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">Anomaly Method</label>
              <select
                value={config.anomaly_method}
                onChange={(e) =>
                  onChangeConfig({ anomaly_method: e.target.value as AnomalyMethod })
                }
                className="bd-input w-full"
              >
                <option value="adaptive_quantile">Adaptive Quantile</option>
                <option value="rolling_zscore">Rolling Z-Score</option>
                <option value="iqr">Interquartile Range (IQR)</option>
                <option value="kmeans">K-Means Distance</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">
                Quantile ({Math.round(config.anomaly_quantile * 100)}%)
              </label>
              <input
                type="number"
                step={0.01}
                min={0.85}
                max={0.99}
                value={config.anomaly_quantile}
                onChange={(e) =>
                  onChangeConfig({ anomaly_quantile: Number(e.target.value) || 0.95 })
                }
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">Z-Score / IQR Cutoff</label>
              <input
                type="number"
                step={0.1}
                min={1.2}
                max={5.0}
                value={config.anomaly_z_threshold}
                onChange={(e) =>
                  onChangeConfig({
                    anomaly_z_threshold: Number(e.target.value) || 2.5,
                    anomaly_iqr_multiplier: Number(e.target.value) || 1.5,
                  })
                }
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">SMA / EMA Period</label>
              <input
                type="number"
                min={5}
                max={100}
                value={config.ma_period}
                onChange={(e) => onChangeConfig({ ma_period: Number(e.target.value) || 20 })}
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">RSI Period</label>
              <input
                type="number"
                min={5}
                max={50}
                value={config.rsi_period}
                onChange={(e) => onChangeConfig({ rsi_period: Number(e.target.value) || 14 })}
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">Rolling Window</label>
              <input
                type="number"
                min={5}
                max={100}
                value={config.rolling_window}
                onChange={(e) =>
                  onChangeConfig({ rolling_window: Number(e.target.value) || 20 })
                }
                className="bd-input w-full font-mono"
              />
            </div>
          </div>
        </div>
      </div>

      {/* ROW 3: BLACK DASHBOARD ICONIC 3-COLUMN METRIC CHARTS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Card 1: Max Volatility vs Rolling Volatility (Teal #00f2c3) */}
        <div className="bd-card">
          <div className="bd-card-header">
            <h5 className="bd-card-category">Intra-Window Volatility</h5>
            <h3 className="bd-card-title flex items-center gap-2.5">
              <Activity className="w-5 h-5 text-[#00f2c3]" />
              <span>{latestPoint ? `${latestPoint.volPct}%` : '0.00%'}</span>
              <span className="text-xs text-[#9a9a9a] font-light">Max / Rolling Spread</span>
            </h3>
          </div>
          <div className="bd-card-body">
            <div className="h-[200px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={seriesData.slice(-35)}>
                  <defs>
                    <linearGradient id="bdTealSub" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00f2c3" stopOpacity={0.28} />
                      <stop offset="95%" stopColor="#00f2c3" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(0, 242, 195, 0.08)" />
                  <XAxis
                    dataKey="shortTime"
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e1e2f',
                      border: '1px solid #2b3553',
                      fontSize: '11px',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="volPct"
                    stroke="#00f2c3"
                    strokeWidth={2}
                    fill="url(#bdTealSub)"
                    name="Max Volatility (%)"
                    dot={{ r: 2, fill: '#27293d', stroke: '#00f2c3' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="rollVolPct"
                    stroke="#1d8cf8"
                    strokeWidth={1.5}
                    dot={false}
                    name="Rolling Volatility (%)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Card 2: Cross-Asset Rolling Correlation (Blue #1d8cf8) */}
        <div className="bd-card">
          <div className="bd-card-header flex items-start justify-between gap-2">
            <div>
              <h5 className="bd-card-category">Rolling Cross-Correlation</h5>
              <h3 className="bd-card-title flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-[#1d8cf8]" />
                <span>
                  {corrBase.replace('USDT', '')} / {corrTarget.replace('USDT', '')}
                </span>
              </h3>
            </div>
            <div className="flex items-center gap-1.5">
              <select
                value={corrBase}
                onChange={(e) => setCorrBase(e.target.value)}
                className="bd-input !py-1 !px-2 !text-xs"
              >
                {SUPPORTED_SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s.replace('USDT', '')}
                  </option>
                ))}
              </select>
              <select
                value={corrTarget}
                onChange={(e) => setCorrTarget(e.target.value)}
                className="bd-input !py-1 !px-2 !text-xs"
              >
                {SUPPORTED_SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s.replace('USDT', '')}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="bd-card-body">
            <div className="h-[200px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={(correlation?.rolling_correlation || []).slice(-35)}>
                  <defs>
                    <linearGradient id="bdBlueSub" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1d8cf8" stopOpacity={0.28} />
                      <stop offset="95%" stopColor="#1d8cf8" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(29, 140, 248, 0.08)" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(v) => String(v).slice(11, 16)}
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[-1, 1]}
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e1e2f',
                      border: '1px solid #2b3553',
                      fontSize: '11px',
                    }}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
                  <Area
                    type="monotone"
                    dataKey="rolling_corr"
                    stroke="#1d8cf8"
                    strokeWidth={2}
                    fill="url(#bdBlueSub)"
                    name="Rolling Correlation"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Card 3: Lag Correlation Bar Chart (Magenta #e14eca) */}
        <div className="bd-card">
          <div className="bd-card-header">
            <h5 className="bd-card-category">Lead-Lag Structure (Lag -6 to +6)</h5>
            <h3 className="bd-card-title flex items-center gap-2">
              <BarChart2 className="w-5 h-5 text-[#e14eca]" />
              <span>Temporal Lead Analysis</span>
            </h3>
          </div>
          <div className="bd-card-body">
            <div className="h-[200px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={correlation?.lag_correlation || []}>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(225, 78, 202, 0.08)" />
                  <XAxis
                    dataKey="lag"
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[-1, 1]}
                    tick={{ fontSize: 10, fill: '#9a9a9a' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e1e2f',
                      border: '1px solid #2b3553',
                      fontSize: '11px',
                    }}
                  />
                  <Bar
                    dataKey="correlation"
                    fill="#e14eca"
                    radius={[3, 3, 0, 0]}
                    name="Lag Correlation"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* ROW 4: BOTTOM 2-COLUMN TABLES (PEARSON MATRIX + ANOMALY AUDIT LOG) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Pearson Correlation Matrix & Market-Wide Risk */}
        <div className="lg:col-span-5 bd-card">
          <div className="bd-card-header flex items-center justify-between">
            <div>
              <h5 className="bd-card-category">Cross-Asset Matrix</h5>
              <h4 className="bd-card-title !text-base">Pearson Correlation &amp; Market Risk</h4>
            </div>
            {correlation && (
              <div className="text-right">
                <span className="text-[10px] uppercase text-[#9a9a9a] block">
                  Market Risk Index
                </span>
                <span className="text-sm font-mono font-semibold text-[#ff8d72]">
                  {correlation.market_wide_risk_score} / 100 ({correlation.market_wide_regime})
                </span>
              </div>
            )}
          </div>
          <div className="bd-card-body">
            {correlation && (
              <div className="overflow-x-auto">
                <table className="bd-table">
                  <thead>
                    <tr>
                      <th className="text-left">Asset</th>
                      {correlation.symbols.map((sym) => (
                        <th key={sym} className="text-right">
                          {sym.replace('USDT', '')}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {correlation.symbols.map((rSym) => (
                      <tr key={rSym}>
                        <td className="font-medium text-white">{rSym}</td>
                        {correlation.symbols.map((cSym) => {
                          const val = correlation.pearson_matrix[rSym]?.[cSym] ?? 0;
                          return (
                            <td
                              key={cSym}
                              className={`text-right font-mono ${
                                val >= 0.8
                                  ? 'text-[#00f2c3]'
                                  : val >= 0.6
                                  ? 'text-[#1d8cf8]'
                                  : 'text-[#9a9a9a]'
                              }`}
                            >
                              {val.toFixed(3)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right: Anomaly Events Table */}
        <div className="lg:col-span-7 bd-card">
          <div className="bd-card-header flex items-center justify-between">
            <div>
              <h5 className="bd-card-category">
                Method: {config.anomaly_method} ({analytics?.anomalies_log.length || 0} Events)
              </h5>
              <h4 className="bd-card-title !text-base flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-[#fd5d93]" />
                Detected Market Anomalies Log
              </h4>
            </div>
          </div>
          <div className="bd-card-body">
            <div className="overflow-auto max-h-[260px]">
              <table className="bd-table">
                <thead>
                  <tr>
                    <th className="text-left">Timestamp (UTC)</th>
                    <th className="text-right">Close Price</th>
                    <th className="text-right">Volatility</th>
                    <th className="text-right">Spike Ratio</th>
                    <th className="text-right">Score</th>
                    <th className="text-left">Trigger</th>
                  </tr>
                </thead>
                <tbody>
                  {(analytics?.anomalies_log || []).map((row, idx) => (
                    <tr key={idx} className="hover:bg-white/[0.02]">
                      <td className="font-mono text-xs text-[#9a9a9a]">
                        {row.timestamp.slice(0, 16).replace('T', ' ')}
                      </td>
                      <td className="text-right font-mono text-white">
                        ${row.close.toLocaleString()}
                      </td>
                      <td className="text-right font-mono text-[#fd5d93]">
                        {(row.max_volatility * 100).toFixed(2)}%
                      </td>
                      <td className="text-right font-mono text-[#ff8d72]">
                        {row.spike_ratio}x
                      </td>
                      <td className="text-right font-mono text-[#1d8cf8]">
                        {row.anomaly_score}
                      </td>
                      <td className="text-xs text-[#9a9a9a]">{row.anomaly_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
