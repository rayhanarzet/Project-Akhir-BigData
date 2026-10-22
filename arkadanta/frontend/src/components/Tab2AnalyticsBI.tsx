import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertOctagon,
  BarChart3,
  GitCompare,
  Layers,
  Sliders,
} from 'lucide-react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
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

export const Tab2AnalyticsBI: React.FC<Props> = ({ config, onChangeConfig }) => {
  const [analytics, setAnalytics] = useState<AnalyticsRunResponse | null>(null);
  const [correlation, setCorrelation] = useState<CorrelationResponse | null>(null);
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

  const seriesData = (analytics?.series || []).slice(-100).map((d) => ({
    ...d,
    shortTime: d.timestamp.slice(5, 16).replace('T', ' '),
    anomalyPrice: d.is_anomaly ? d.high * 1.002 : null,
  }));

  const thresholdVal =
    analytics?.anomaly_summary.threshold_info.per_symbol_threshold[config.symbol] ?? 0;

  return (
    <div className="space-y-6">
      {/* Dynamic Control Bar */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-cyan-400" />
            <h3 className="text-base font-semibold text-white">
              Konfigurasi Dinamis Timeframe, Indikator Teknikal & Metode Anomali
            </h3>
          </div>
          {loading && (
            <span className="text-xs text-cyan-400 animate-pulse font-medium">
              Memperbarui agregasi & fitur...
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Aset Utama</label>
            <select
              value={config.symbol}
              onChange={(e) => onChangeConfig({ symbol: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white font-semibold"
            >
              {SUPPORTED_SYMBOLS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Timeframe Agregasi</label>
            <select
              value={config.timeframe}
              onChange={(e) => onChangeConfig({ timeframe: e.target.value as Timeframe })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-cyan-400 font-bold"
            >
              {SUPPORTED_TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Metode Anomali</label>
            <select
              value={config.anomaly_method}
              onChange={(e) =>
                onChangeConfig({ anomaly_method: e.target.value as AnomalyMethod })
              }
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-amber-300 font-semibold"
            >
              <option value="adaptive_quantile">Adaptive Quantile</option>
              <option value="rolling_zscore">Rolling Z-Score</option>
              <option value="iqr">Interquartile Range (IQR)</option>
              <option value="kmeans">K-Means Distance</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">
              Kuantil ({Math.round(config.anomaly_quantile * 100)}%)
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
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Periode SMA/EMA/BB</label>
            <input
              type="number"
              min={5}
              max={100}
              value={config.ma_period}
              onChange={(e) => onChangeConfig({ ma_period: Number(e.target.value) || 20 })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Periode RSI</label>
            <input
              type="number"
              min={5}
              max={50}
              value={config.rsi_period}
              onChange={(e) => onChangeConfig({ rsi_period: Number(e.target.value) || 14 })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Rolling Window</label>
            <input
              type="number"
              min={5}
              max={100}
              value={config.rolling_window}
              onChange={(e) =>
                onChangeConfig({ rolling_window: Number(e.target.value) || 20 })
              }
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">Z-Score / IQR Thresh</label>
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
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white font-mono"
            />
          </div>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-400">Total Candle Teragregasi ({config.timeframe})</p>
          <p className="text-2xl font-bold text-white mt-1">
            {analytics?.total_candles.toLocaleString() || '-'}
          </p>
          <p className="text-[11px] text-cyan-400 mt-1">Urutan Timestamp Kronologis Eksplisit</p>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-400">Kejadian Anomali Terdeteksi</p>
          <p className="text-2xl font-bold text-rose-400 mt-1">
            {analytics?.anomaly_summary.total_anomalies ?? 0}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">
            Metode: <span className="text-amber-300 font-mono">{config.anomaly_method}</span>
          </p>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-400">Rasio Anomali Periode</p>
          <p className="text-2xl font-bold text-amber-400 mt-1">
            {analytics?.anomaly_summary.anomaly_rate_pct ?? 0}%
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Ambang dinamis spesifik aset</p>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-400">Ambang Adaptif ({config.symbol})</p>
          <p className="text-2xl font-bold text-emerald-400 font-mono mt-1">{thresholdVal}</p>
          <p className="text-[11px] text-slate-400 mt-1">Dihitung otomatis dari distribusi</p>
        </div>
      </div>

      {/* Main Price + SMA/EMA + Bollinger + Anomaly Points Chart */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            Tren Harga {config.symbol} ({config.timeframe}), SMA/EMA, Bollinger Bands & Deteksi
            Titik Anomali
          </h3>
          <span className="text-xs text-rose-400 font-medium">
            ● Titik Merah = Lonjakan Anomali Pasar Terdeteksi
          </span>
        </div>

        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={seriesData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="shortTime" stroke="#64748b" tick={{ fontSize: 11 }} />
              <YAxis
                domain={['auto', 'auto']}
                stroke="#64748b"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `$${Number(v).toLocaleString()}`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0f172a',
                  borderColor: '#334155',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Area
                type="monotone"
                dataKey="bb_upper"
                stroke="none"
                fill="#38bdf8"
                fillOpacity={0.07}
                name="Bollinger Upper"
              />
              <Line
                type="monotone"
                dataKey="close"
                stroke="#f8fafc"
                strokeWidth={2}
                dot={false}
                name="Close Price"
              />
              <Line
                type="monotone"
                dataKey="sma_20"
                stroke="#38bdf8"
                strokeWidth={1.5}
                dot={false}
                name={`SMA (${config.ma_period})`}
              />
              <Line
                type="monotone"
                dataKey="ema_20"
                stroke="#a855f7"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                name={`EMA (${config.ma_period})`}
              />
              <Scatter
                dataKey="anomalyPrice"
                fill="#ef4444"
                name="Anomali Terdeteksi"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Volatility & RSI Sub-charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-rose-400" />
            Dinamika Volatilitas (Max Volatility, Rolling Volatility & Bollinger Width)
          </h3>
          <div className="h-60 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={seriesData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="shortTime" stroke="#64748b" tick={{ fontSize: 10 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    fontSize: '12px',
                  }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Line
                  type="monotone"
                  dataKey="max_volatility"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={false}
                  name="Max Volatility"
                />
                <Line
                  type="monotone"
                  dataKey="rolling_volatility"
                  stroke="#06b6d4"
                  strokeWidth={1.6}
                  dot={false}
                  name="Rolling Volatility"
                />
                <Line
                  type="monotone"
                  dataKey="bb_width"
                  stroke="#f59e0b"
                  strokeWidth={1.3}
                  strokeDasharray="3 3"
                  dot={false}
                  name="Bollinger Width"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-amber-400" />
            Indikator Momentum RSI ({config.rsi_period}) & Volume Transaksi
          </h3>
          <div className="h-60 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={seriesData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="shortTime" stroke="#64748b" tick={{ fontSize: 10 }} />
                <YAxis yAxisId="rsi" domain={[0, 100]} stroke="#f59e0b" tick={{ fontSize: 11 }} />
                <YAxis
                  yAxisId="vol"
                  orientation="right"
                  stroke="#64748b"
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    fontSize: '12px',
                  }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <ReferenceLine yAxisId="rsi" y={70} stroke="#ef4444" strokeDasharray="3 3" />
                <ReferenceLine yAxisId="rsi" y={30} stroke="#10b981" strokeDasharray="3 3" />
                <Bar
                  yAxisId="vol"
                  dataKey="volume"
                  fill="#334155"
                  opacity={0.55}
                  name="Volume"
                />
                <Line
                  yAxisId="rsi"
                  type="monotone"
                  dataKey="rsi_14"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                  name="RSI-14"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Anomaly Scatter & Inspection Log */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <h3 className="text-sm font-semibold text-white">
            Scatter Plot: Volume Z-Score vs Max Volatility
          </h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  type="number"
                  dataKey="volume_zscore"
                  name="Volume Z-Score"
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="max_volatility"
                  name="Max Volatility"
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    fontSize: '12px',
                  }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Scatter
                  name="Candle Normal"
                  data={seriesData.filter((d) => !d.is_anomaly)}
                  fill="#38bdf8"
                />
                <Scatter
                  name="Anomali Pasar"
                  data={seriesData.filter((d) => d.is_anomaly)}
                  fill="#ef4444"
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <AlertOctagon className="w-4 h-4 text-rose-400" />
              Log Kejadian Anomali Terdeteksi ({analytics?.anomalies_log.length || 0} Kejadian)
            </h3>
            <span className="text-xs text-slate-400">Diurutkan dari kejadian terbaru</span>
          </div>

          <div className="overflow-auto max-h-64">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 uppercase">
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">Harga Close</th>
                  <th className="py-2.5 px-3">Max Volatility</th>
                  <th className="py-2.5 px-3">Spike Ratio</th>
                  <th className="py-2.5 px-3">Skor Anomali</th>
                  <th className="py-2.5 px-3">Keterangan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {(analytics?.anomalies_log || []).map((row, i) => (
                  <tr key={i} className="hover:bg-rose-500/5">
                    <td className="py-2 px-3 font-mono text-slate-300">
                      {row.timestamp.slice(0, 16).replace('T', ' ')}
                    </td>
                    <td className="py-2 px-3 font-mono text-white">
                      ${row.close.toLocaleString()}
                    </td>
                    <td className="py-2 px-3 font-mono text-rose-400 font-semibold">
                      {(row.max_volatility * 100).toFixed(2)}%
                    </td>
                    <td className="py-2 px-3 font-mono text-amber-300">{row.spike_ratio}x</td>
                    <td className="py-2 px-3 font-mono text-cyan-400">{row.anomaly_score}</td>
                    <td className="py-2 px-3 text-rose-300">{row.anomaly_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Cross-Asset Correlation & Market-Wide Risk Score */}
      {correlation && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-lg space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <GitCompare className="w-5 h-5 text-cyan-400" />
                Analisis Hubungan Lintas Aset (Pearson, Rolling & Lag Correlation)
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Dihitung secara dinamis dari pergerakan return dan volatilitas seluruh aset aktif
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div>
                <label className="block text-[10px] text-slate-400">Aset Acuan (Base)</label>
                <select
                  value={corrBase}
                  onChange={(e) => setCorrBase(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white font-semibold"
                >
                  {SUPPORTED_SYMBOLS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-slate-400">Aset Pembanding (Target)</label>
                <select
                  value={corrTarget}
                  onChange={(e) => setCorrTarget(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white font-semibold"
                >
                  {SUPPORTED_SYMBOLS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div className="px-4 py-2 rounded-xl bg-slate-950 border border-slate-800 text-right">
                <p className="text-[10px] uppercase text-slate-400">Market-Wide Risk Score</p>
                <p className="text-lg font-bold text-amber-400">
                  {correlation.market_wide_risk_score} / 100 ({correlation.market_wide_regime})
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Pearson Matrix Table */}
            <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
              <p className="text-xs font-semibold text-slate-300 mb-3">
                Matriks Korelasi Pearson (Log Return)
              </p>
              <table className="w-full text-center text-xs border-collapse">
                <thead>
                  <tr>
                    <th className="p-2 text-slate-400">Aset</th>
                    {correlation.symbols.map((sym) => (
                      <th key={sym} className="p-2 text-slate-300 font-bold">
                        {sym.replace('USDT', '')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {correlation.symbols.map((rSym) => (
                    <tr key={rSym} className="border-t border-slate-800/60">
                      <td className="p-2 font-bold text-slate-300 text-left">
                        {rSym.replace('USDT', '')}
                      </td>
                      {correlation.symbols.map((cSym) => {
                        const val = correlation.pearson_matrix[rSym]?.[cSym] ?? 0;
                        const bg =
                          val >= 0.85
                            ? 'bg-cyan-500/30 text-cyan-200'
                            : val >= 0.65
                            ? 'bg-cyan-500/15 text-cyan-300'
                            : 'bg-slate-900 text-slate-300';
                        return (
                          <td key={cSym} className={`p-2 font-mono rounded ${bg}`}>
                            {val.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Rolling Correlation */}
            <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
              <p className="text-xs font-semibold text-slate-300 mb-2">
                Rolling Correlation ({corrBase} vs {corrTarget})
              </p>
              <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={correlation.rolling_correlation.slice(-60)}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="timestamp"
                      tickFormatter={(v) => String(v).slice(5, 10)}
                      stroke="#64748b"
                      tick={{ fontSize: 10 }}
                    />
                    <YAxis domain={[-1, 1]} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        fontSize: '11px',
                      }}
                    />
                    <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                    <Line
                      type="monotone"
                      dataKey="rolling_corr"
                      stroke="#38bdf8"
                      strokeWidth={2}
                      dot={false}
                      name="Rolling Corr"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Lag Correlation */}
            <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
              <p className="text-xs font-semibold text-slate-300 mb-2">
                Lag Correlation ({corrBase} mendahului {corrTarget} pada Lag &gt; 0)
              </p>
              <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={correlation.lag_correlation}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="lag" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis domain={[-1, 1]} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        fontSize: '11px',
                      }}
                    />
                    <Bar dataKey="correlation" fill="#a855f7" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
