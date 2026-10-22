import React, { useEffect, useState } from 'react';
import {
  BrainCircuit,
  Cpu,
  Play,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  DynamicConfigPayload,
  ModelMetricsResponse,
  PredictionResponse,
  RiskRegime,
  Timeframe,
} from '../types/arkadanta';
import {
  AVAILABLE_FEATURES,
  fetchLatestModelMetrics,
  predictNextPeriodApi,
  runDynamicAnalyticsApi,
  SUPPORTED_SYMBOLS,
  SUPPORTED_TIMEFRAMES,
  trainAndEvaluateModels,
} from '../services/api';

interface Props {
  config: DynamicConfigPayload;
  onChangeConfig: (partial: Partial<DynamicConfigPayload>) => void;
}

const REGIME_STYLES: Record<
  RiskRegime,
  { badge: string; border: string; text: string; hex: string }
> = {
  SAFE: {
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    border: 'border-emerald-500/40',
    text: 'text-emerald-400',
    hex: '#10b981',
  },
  WARNING: {
    badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    border: 'border-amber-500/40',
    text: 'text-amber-400',
    hex: '#f59e0b',
  },
  DANGER: {
    badge: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
    border: 'border-rose-500/40',
    text: 'text-rose-400',
    hex: '#ef4444',
  },
};

export const Tab3ModelLabShield: React.FC<Props> = ({ config, onChangeConfig }) => {
  const [metrics, setMetrics] = useState<ModelMetricsResponse | null>(null);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [recentPrices, setRecentPrices] = useState<{ time: string; close: number }[]>([]);
  const [training, setTraining] = useState<boolean>(false);

  const loadAll = async () => {
    const [mRes, pRes, aRes] = await Promise.all([
      fetchLatestModelMetrics(config),
      predictNextPeriodApi(config.symbol, config.timeframe),
      runDynamicAnalyticsApi(config),
    ]);
    setMetrics(mRes);
    setPrediction(pRes);
    setRecentPrices(
      aRes.series.slice(-45).map((pt) => ({
        time: pt.timestamp.slice(11, 16) || pt.timestamp.slice(5, 10),
        close: pt.close,
      }))
    );
  };

  useEffect(() => {
    loadAll();
  }, [config.symbol, config.timeframe]);

  const handleTrainModel = async () => {
    setTraining(true);
    try {
      const mRes = await trainAndEvaluateModels(config);
      setMetrics(mRes);
      const pRes = await predictNextPeriodApi(config.symbol, config.timeframe);
      setPrediction(pRes);
    } finally {
      setTraining(false);
    }
  };

  const toggleFeature = (feat: string) => {
    const exists = config.features.includes(feat);
    if (exists && config.features.length <= 2) return; // Minimal 2 fitur
    const next = exists
      ? config.features.filter((f) => f !== feat)
      : [...config.features, feat];
    onChangeConfig({ features: next });
  };

  const predRegime: RiskRegime = prediction?.predicted_regime_t_plus_1 || 'SAFE';
  const style = REGIME_STYLES[predRegime];

  const probData = prediction
    ? (['SAFE', 'WARNING', 'DANGER'] as RiskRegime[]).map((r) => ({
        regime: r,
        probPct: Number(((prediction.probabilities_t_plus_1[r] || 0) * 100).toFixed(1)),
      }))
    : [];

  return (
    <div className="space-y-6">
      {/* LIVE MARKET SHIELD (HERO SECTION) */}
      {prediction && (
        <div
          className={`bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border-2 ${style.border} rounded-2xl p-6 shadow-2xl space-y-6`}
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3.5">
              <div className={`p-3.5 rounded-xl border ${style.badge}`}>
                {predRegime === 'SAFE' ? (
                  <ShieldCheck className="w-8 h-8" />
                ) : predRegime === 'WARNING' ? (
                  <Shield className="w-8 h-8" />
                ) : (
                  <ShieldAlert className="w-8 h-8" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase tracking-widest text-slate-400 font-bold">
                    Live Market Shield (Prediksi Periode T+{prediction.target_horizon})
                  </span>
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                </div>
                <h2 className="text-2xl font-extrabold text-white mt-0.5">
                  {prediction.symbol} ({prediction.timeframe}) &mdash; Status Risiko:{' '}
                  <span className={style.text}>{predRegime}</span>
                </h2>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <select
                value={config.symbol}
                onChange={(e) => onChangeConfig({ symbol: e.target.value })}
                className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-bold"
              >
                {SUPPORTED_SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <select
                value={config.timeframe}
                onChange={(e) => onChangeConfig({ timeframe: e.target.value as Timeframe })}
                className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-cyan-400 font-bold"
              >
                {SUPPORTED_TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 4 Main Shield Metrics: Current Price, Est Volatility, Resistance, Stop Loss */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4">
              <p className="text-xs text-slate-400">Harga Saat Ini (Close T)</p>
              <p className="text-2xl font-extrabold text-white font-mono mt-1">
                ${prediction.current_price.toLocaleString()}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Cluster Saat Ini: #{prediction.current_cluster_id} ({prediction.current_regime_t})
              </p>
            </div>

            <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4">
              <p className="text-xs text-slate-400">Estimasi Volatilitas (T+1)</p>
              <p className="text-2xl font-extrabold text-cyan-400 font-mono mt-1">
                {prediction.predicted_volatility_pct.toFixed(3)}%
              </p>
              <p className="text-xs text-slate-400 mt-1 font-mono">
                Rentang &plusmn;${prediction.estimated_volatility_nominal.toLocaleString()}
              </p>
            </div>

            <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-emerald-300 font-semibold">
                  Batas Atas (Resistance T+1)
                </p>
                <TrendingUp className="w-4 h-4 text-emerald-400" />
              </div>
              <p className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">
                ${prediction.resistance_level.toLocaleString()}
              </p>
              <p className="text-[11px] text-emerald-300/80 mt-1">
                Harga Saat Ini + Estimasi Volatilitas
              </p>
            </div>

            <div className="bg-rose-950/20 border border-rose-500/30 rounded-xl p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-rose-300 font-semibold">
                  Batas Bawah (Stop Loss T+1)
                </p>
                <TrendingDown className="w-4 h-4 text-rose-400" />
              </div>
              <p className="text-2xl font-extrabold text-rose-400 font-mono mt-1">
                ${prediction.stop_loss_level.toLocaleString()}
              </p>
              <p className="text-[11px] text-rose-300/80 mt-1">
                Harga Saat Ini &minus; Estimasi Volatilitas
              </p>
            </div>
          </div>

          {/* Probability Bars + Live Price Band Chart */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-5 bg-slate-950/70 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3">
                  Distribusi Probabilitas Rezim Risiko (T+1)
                </h4>
                <div className="h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={probData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis type="number" domain={[0, 100]} stroke="#64748b" tick={{ fontSize: 11 }} />
                      <YAxis
                        type="category"
                        dataKey="regime"
                        stroke="#cbd5e1"
                        tick={{ fontSize: 12, fontWeight: 700 }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#334155',
                          fontSize: '12px',
                        }}
                      />
                      <Bar dataKey="probPct" radius={[0, 6, 6, 0]} name="Probabilitas (%)">
                        {probData.map((entry) => (
                          <Cell
                            key={entry.regime}
                            fill={REGIME_STYLES[entry.regime].hex}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 italic mt-2">{prediction.disclaimer}</p>
            </div>

            <div className="lg:col-span-7 bg-slate-950/70 border border-slate-800/80 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3">
                Pergerakan Harga Terbaru dengan Koridor Resistance & Stop Loss (T+1)
              </h4>
              <div className="h-52 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={recentPrices}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis
                      domain={[
                        prediction.stop_loss_level * 0.996,
                        prediction.resistance_level * 1.004,
                      ]}
                      stroke="#64748b"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => `$${Number(v).toFixed(2)}`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        fontSize: '12px',
                      }}
                    />
                    <ReferenceLine
                      y={prediction.resistance_level}
                      stroke="#10b981"
                      strokeDasharray="5 5"
                      label={{
                        value: `Resistance: $${prediction.resistance_level}`,
                        fill: '#10b981',
                        fontSize: 11,
                      }}
                    />
                    <ReferenceLine
                      y={prediction.stop_loss_level}
                      stroke="#ef4444"
                      strokeDasharray="5 5"
                      label={{
                        value: `Stop Loss: $${prediction.stop_loss_level}`,
                        fill: '#ef4444',
                        fontSize: 11,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="close"
                      stroke="#38bdf8"
                      strokeWidth={2.5}
                      dot={false}
                      name="Harga Close"
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODEL LAB CONFIGURATION PANEL */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-lg space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-white flex items-center gap-2">
              <BrainCircuit className="w-5 h-5 text-cyan-400" />
              Model Lab: Konfigurasi Dinamis K-Means Clustering & Random Forest (T+1)
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Pilih kombinasi fitur, jumlah cluster K-Means, rasio validasi temporal, dan
              hyperparameter Random Forest
            </p>
          </div>

          <button
            type="button"
            onClick={handleTrainModel}
            disabled={training}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 disabled:opacity-40 text-white font-bold text-sm transition flex items-center gap-2 shadow-lg"
          >
            <Play className="w-4 h-4" />
            {training
              ? 'Melatih K-Means & Random Forest...'
              : 'Latih Ulang & Evaluasi Model (Temporal Split)'}
          </button>
        </div>

        {/* Feature Pills Selector */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">
            Subset Fitur Dinamis Terpilih ({config.features.length} Fitur Aktif):
          </label>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_FEATURES.map((feat) => {
              const active = config.features.includes(feat);
              return (
                <button
                  type="button"
                  key={feat}
                  onClick={() => toggleFeature(feat)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono transition border ${
                    active
                      ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300 font-semibold'
                      : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  {feat}
                </button>
              );
            })}
          </div>
        </div>

        {/* Hyperparameters */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              Jumlah Cluster K-Means (k = {config.cluster_k})
            </label>
            <input
              type="range"
              min={3}
              max={5}
              value={config.cluster_k}
              onChange={(e) => onChangeConfig({ cluster_k: Number(e.target.value) })}
              className="w-full accent-cyan-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              Temporal Split Train Ratio ({Math.round(config.train_ratio * 100)}%)
            </label>
            <input
              type="range"
              min={0.6}
              max={0.9}
              step={0.05}
              value={config.train_ratio}
              onChange={(e) => onChangeConfig({ train_ratio: Number(e.target.value) })}
              className="w-full accent-cyan-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              RF Num Trees (n_estimators)
            </label>
            <input
              type="number"
              min={50}
              max={500}
              step={50}
              value={config.rf_num_trees}
              onChange={(e) => onChangeConfig({ rf_num_trees: Number(e.target.value) || 200 })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-sm text-white font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">RF Max Depth</label>
            <input
              type="number"
              min={3}
              max={25}
              value={config.rf_max_depth}
              onChange={(e) => onChangeConfig({ rf_max_depth: Number(e.target.value) || 10 })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-sm text-white font-mono"
            />
          </div>
        </div>
      </div>

      {/* EVALUATION & CENTROID RANKING RESULTS */}
      {metrics && (
        <>
          {/* Metric KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
              <p className="text-[11px] text-slate-400">K-Means Silhouette</p>
              <p className="text-xl font-bold text-cyan-400 font-mono mt-1">
                {metrics.kmeans_metrics.silhouette_score}
              </p>
            </div>
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
              <p className="text-[11px] text-slate-400">RF Accuracy (T+1)</p>
              <p className="text-xl font-bold text-emerald-400 font-mono mt-1">
                {(metrics.classification_metrics.accuracy * 100).toFixed(2)}%
              </p>
            </div>
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
              <p className="text-[11px] text-slate-400">Macro F1-Score</p>
              <p className="text-xl font-bold text-white font-mono mt-1">
                {metrics.classification_metrics.f1_macro}
              </p>
            </div>
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
              <p className="text-[11px] text-slate-400">Macro Precision</p>
              <p className="text-xl font-bold text-white font-mono mt-1">
                {metrics.classification_metrics.precision_macro}
              </p>
            </div>
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
              <p className="text-[11px] text-slate-400">Volatilitas MAE (T+1)</p>
              <p className="text-xl font-bold text-amber-400 font-mono mt-1">
                {metrics.regression_metrics.mae}
              </p>
            </div>
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
              <p className="text-[11px] text-slate-400">Volatilitas RMSE (T+1)</p>
              <p className="text-xl font-bold text-rose-400 font-mono mt-1">
                {metrics.regression_metrics.rmse}
              </p>
            </div>
          </div>

          {/* K-Means Centroid Ranking Table (Bab 5.5 Proof) */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-lg space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-white flex items-center gap-2">
                  <Target className="w-5 h-5 text-emerald-400" />
                  Tabel Interpretasi Centroid K-Means & Pemetaan Risiko Dinamis (Bab 5.5)
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  ID cluster mentah (0, 1, 2) diurutkan berdasarkan{' '}
                  <span className="text-cyan-300 font-semibold">Composite Risk Score</span> dari
                  terendah ke tertinggi menjadi SAFE, WARNING, dan DANGER
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Train: {metrics.temporal_split.train_samples} | Test:{' '}
                {metrics.temporal_split.test_samples} (Temporal Split)
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 uppercase">
                    <th className="py-3 px-4">Urutan Risiko</th>
                    <th className="py-3 px-4">ID Cluster K-Means</th>
                    <th className="py-3 px-4">Label Risiko Terpetakan</th>
                    <th className="py-3 px-4">Skor Risiko Gabungan (Z)</th>
                    <th className="py-3 px-4">Jumlah Sampel Latih</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {metrics.kmeans_metrics.centroids.map((c) => {
                    const rStyle = REGIME_STYLES[c.assigned_risk_label];
                    return (
                      <tr key={c.cluster_id} className="hover:bg-slate-800/40">
                        <td className="py-3 px-4 font-bold text-slate-200">
                          Peringkat #{c.risk_rank}
                        </td>
                        <td className="py-3 px-4 font-mono text-cyan-400">
                          Cluster {c.cluster_id}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-bold border ${rStyle.badge}`}
                          >
                            {c.assigned_risk_label}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-white font-semibold">
                          {c.composite_risk_score}
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-300">
                          {c.train_sample_count.toLocaleString()} candle
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Confusion Matrix, Per-Class Metrics & Feature Importance */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Per-Class Precision, Recall, F1 */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
              <h4 className="text-sm font-semibold text-white">
                Evaluasi Per Kelas Risiko pada Data Uji Kronologis
              </h4>
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-2 px-2">Kelas</th>
                    <th className="py-2 px-2">Precision</th>
                    <th className="py-2 px-2">Recall</th>
                    <th className="py-2 px-2">F1-Score</th>
                    <th className="py-2 px-2">Support</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {(['SAFE', 'WARNING', 'DANGER'] as RiskRegime[]).map((cls) => {
                    const row = metrics.classification_metrics.per_class[cls];
                    return (
                      <tr key={cls}>
                        <td className={`py-2.5 px-2 font-bold ${REGIME_STYLES[cls].text}`}>
                          {cls}
                        </td>
                        <td className="py-2.5 px-2 font-mono text-slate-200">{row?.precision}</td>
                        <td className="py-2.5 px-2 font-mono text-slate-200">{row?.recall}</td>
                        <td className="py-2.5 px-2 font-mono text-cyan-400 font-semibold">
                          {row?.f1_score}
                        </td>
                        <td className="py-2.5 px-2 font-mono text-slate-400">{row?.support}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Confusion Matrix */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
              <h4 className="text-sm font-semibold text-white">
                Confusion Matrix (Aktual vs Prediksi T+1)
              </h4>
              <table className="w-full text-center border-collapse text-xs">
                <thead>
                  <tr>
                    <th className="p-2 text-slate-400">Aktual \ Pred</th>
                    {metrics.classification_metrics.labels.map((l) => (
                      <th key={l} className="p-2 text-slate-300 font-bold">
                        {l}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {metrics.classification_metrics.confusion_matrix.map((row, rIdx) => {
                    const lbl = metrics.classification_metrics.labels[rIdx];
                    return (
                      <tr key={lbl} className="border-t border-slate-800/60">
                        <td className="p-2 font-bold text-slate-300 text-left">{lbl}</td>
                        {row.map((val, cIdx) => (
                          <td
                            key={cIdx}
                            className={`p-2.5 font-mono rounded ${
                              rIdx === cIdx
                                ? 'bg-cyan-500/25 text-cyan-200 font-bold'
                                : 'bg-slate-950 text-slate-400'
                            }`}
                          >
                            {val}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Feature Importances */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
              <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                Random Forest Feature Importance
              </h4>
              <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metrics.feature_importances} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis type="number" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis
                      type="category"
                      dataKey="feature"
                      width={115}
                      stroke="#cbd5e1"
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        fontSize: '11px',
                      }}
                    />
                    <Bar dataKey="importance" fill="#06b6d4" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
