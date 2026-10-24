import React, { useEffect, useState } from 'react';
import {
  Activity,
  Cpu,
  Layers,
  Play,
  Shield,
  Sliders,
  Target,
} from 'lucide-react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
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
  SUPPORTED_TIMEFRAMES,
  trainAndEvaluateModels,
} from '../services/api';

interface Props {
  dataRevision: number;
  config: DynamicConfigPayload;
  onChangeConfig: (partial: Partial<DynamicConfigPayload>) => void;
}

const REGIME_COLORS: Record<RiskRegime, string> = {
  SAFE: '#00f2c3',
  WARNING: '#ff8d72',
  DANGER: '#fd5d93',
};

export const Tab3ModelLabShield: React.FC<Props> = ({ config, onChangeConfig, dataRevision }) => {
  const [metrics, setMetrics] = useState<ModelMetricsResponse | null>(null);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [recentPrices, setRecentPrices] = useState<{ time: string; close: number }[]>([]);
  const [training, setTraining] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = async (isActive: () => boolean) => {
    setError(null);
    setMetrics(null);
    setPrediction(null);
    setRecentPrices([]);
    const [mRes, pRes, aRes] = await Promise.allSettled([
      fetchLatestModelMetrics(config),
      predictNextPeriodApi(config.symbol, config.timeframe),
      runDynamicAnalyticsApi(config),
    ]);
    if (!isActive()) return;
    if (mRes.status === 'fulfilled') setMetrics(mRes.value);
    if (pRes.status === 'fulfilled') setPrediction(pRes.value);
    const failures = [mRes, pRes, aRes].filter((r) => r.status === 'rejected') as PromiseRejectedResult[];
    if (failures.length) setError(failures.map((r) => String(r.reason?.message || r.reason)).join(' '));
    if (aRes.status === 'fulfilled') setRecentPrices(
      aRes.value.series.slice(-45).map((pt) => ({
        time: pt.timestamp.slice(11, 16) || pt.timestamp.slice(5, 10),
        close: pt.close,
      }))
    );
  };

  useEffect(() => {
    let active = true;
    loadAll(() => active);
    return () => { active = false; };
  }, [config.symbol, config.timeframe, dataRevision]);

  const handleTrainModel = async () => {
    setTraining(true);
    setError(null);
    setMetrics(null);
    setPrediction(null);
    try {
      const mRes = await trainAndEvaluateModels(config);
      setMetrics(mRes);
      const pRes = await predictNextPeriodApi(config.symbol, config.timeframe);
      setPrediction(pRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pelatihan model gagal.');
    } finally {
      setTraining(false);
    }
  };

  const toggleFeature = (feat: string) => {
    const exists = config.features.includes(feat);
    if (exists && config.features.length <= 2) return;
    const next = exists
      ? config.features.filter((f) => f !== feat)
      : [...config.features, feat];
    onChangeConfig({ features: next });
  };

  const predRegime: RiskRegime = prediction?.predicted_regime_t_plus_1 || 'SAFE';
  const regimeColor = REGIME_COLORS[predRegime];

  const probData = prediction
    ? (['SAFE', 'WARNING', 'DANGER'] as RiskRegime[]).map((r) => ({
        regime: r,
        probPct: Number(((prediction.probabilities_t_plus_1[r] || 0) * 100).toFixed(1)),
      }))
    : [];

  return (
    <div>
      {error && <div role="alert" className="mb-4 p-4 border border-red-400 rounded text-red-300">{error}</div>}
      {/* ROW 1: LIVE MARKET SHIELD & RESISTANCE/STOP-LOSS CORRIDOR */}
      {prediction && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: T+1 Risk Status & Probability Distribution */}
          <div className="lg:col-span-5 bd-card">
            <div className="bd-card-header flex items-start justify-between">
              <div>
                <h5 className="bd-card-category">
                  Speed Layer Inference (Horizon T+{prediction.target_horizon})
                </h5>
                <h2 className="bd-card-title flex items-center gap-2.5">
                  <Shield className="w-5 h-5" style={{ color: regimeColor }} />
                  <span>{prediction.symbol} Market Shield</span>
                </h2>
              </div>
              <span
                style={{
                  color: regimeColor,
                  borderColor: regimeColor,
                }}
                className="px-3 py-1 rounded text-xs font-semibold border bg-black/20 tracking-wider"
              >
                {predRegime}
              </span>
            </div>

            <div className="bd-card-body space-y-5">
              {/* 4 Key Readouts */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                  <span className="text-[11px] text-[#9a9a9a] block">Current Close (T)</span>
                  <span className="text-lg font-mono font-semibold text-white mt-0.5 block">
                    ${prediction.current_price.toLocaleString()}
                  </span>
                  <span className="text-[10px] text-[#9a9a9a]">
                    Cluster #{prediction.current_cluster_id} ({prediction.current_regime_t})
                  </span>
                </div>

                <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                  <span className="text-[11px] text-[#9a9a9a] block">
                    Est. Volatility (T+1)
                  </span>
                  <span className="text-lg font-mono font-semibold text-[#1d8cf8] mt-0.5 block">
                    {prediction.predicted_volatility_pct.toFixed(3)}%
                  </span>
                  <span className="text-[10px] text-[#9a9a9a] font-mono">
                    &plusmn;${prediction.estimated_volatility_nominal.toLocaleString()}
                  </span>
                </div>

                <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                  <span className="text-[11px] text-[#9a9a9a] block">
                    Resistance Bound (T+1)
                  </span>
                  <span className="text-lg font-mono font-semibold text-[#00f2c3] mt-0.5 block">
                    ${prediction.resistance_level.toLocaleString()}
                  </span>
                  <span className="text-[10px] text-[#9a9a9a]">Price + Est. Volatility</span>
                </div>

                <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                  <span className="text-[11px] text-[#9a9a9a] block">
                    Stop Loss Bound (T+1)
                  </span>
                  <span className="text-lg font-mono font-semibold text-[#fd5d93] mt-0.5 block">
                    ${prediction.stop_loss_level.toLocaleString()}
                  </span>
                  <span className="text-[10px] text-[#9a9a9a]">Price &minus; Est. Volatility</span>
                </div>
              </div>

              {/* Class Probability Bars */}
              <div>
                <div className="flex items-center justify-between text-xs text-[#9a9a9a] mb-2">
                  <span>Random Forest T+1 Regime Probabilities</span>
                  <span className="font-mono text-white">
                    P({predRegime}) ={' '}
                    {((prediction.probabilities_t_plus_1[predRegime] || 0) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="h-[115px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={probData} layout="vertical">
                      <CartesianGrid strokeDasharray="2 4" stroke="rgba(255,255,255,0.06)" />
                      <XAxis
                        type="number"
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: '#9a9a9a' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="regime"
                        tick={{ fontSize: 11, fill: '#ffffff' }}
                        axisLine={false}
                        tickLine={false}
                        width={70}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1e1e2f',
                          border: '1px solid #2b3553',
                          fontSize: '11px',
                        }}
                      />
                      <Bar dataKey="probPct" radius={[0, 4, 4, 0]} name="Probability (%)">
                        {probData.map((entry) => (
                          <Cell key={entry.regime} fill={REGIME_COLORS[entry.regime]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Live Price Trajectory & Volatility Corridor Chart */}
          <div className="lg:col-span-7 bd-card">
            <div className="bd-card-header flex flex-wrap items-start justify-between gap-3">
              <div>
                <h5 className="bd-card-category">Dynamic Volatility Corridor</h5>
                <h2 className="bd-card-title">
                  {prediction.symbol} ({prediction.timeframe}) Resistance &amp; Stop Loss Bands
                </h2>
              </div>
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
            </div>

            <div className="bd-card-body">
              <div className="h-[310px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={recentPrices}
                    margin={{ top: 12, right: 16, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="bdShieldGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#1d8cf8" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#1d8cf8" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="2 4" stroke="rgba(29, 140, 248, 0.08)" />
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 10, fill: '#9a9a9a' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      domain={[
                        prediction.stop_loss_level * 0.996,
                        prediction.resistance_level * 1.004,
                      ]}
                      tick={{ fontSize: 11, fill: '#9a9a9a' }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v) => `$${Number(v).toFixed(2)}`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1e1e2f',
                        border: '1px solid #2b3553',
                        fontSize: '12px',
                      }}
                    />
                    <ReferenceLine
                      y={prediction.resistance_level}
                      stroke="#00f2c3"
                      strokeDasharray="4 4"
                      label={{
                        value: `Resistance T+1 ($${prediction.resistance_level})`,
                        fill: '#00f2c3',
                        fontSize: 11,
                        position: 'insideTopRight',
                      }}
                    />
                    <ReferenceLine
                      y={prediction.stop_loss_level}
                      stroke="#fd5d93"
                      strokeDasharray="4 4"
                      label={{
                        value: `Stop Loss T+1 ($${prediction.stop_loss_level})`,
                        fill: '#fd5d93',
                        fontSize: 11,
                        position: 'insideBottomRight',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="close"
                      stroke="#1d8cf8"
                      strokeWidth={2}
                      fill="url(#bdShieldGrad)"
                      name="Close Price"
                      dot={{ r: 2.5, fill: '#27293d', stroke: '#1d8cf8', strokeWidth: 1.5 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ROW 2: MODEL TRAINING & FEATURE SELECTION CONTROLS */}
      <div className="bd-card">
        <div className="bd-card-header flex flex-wrap items-center justify-between gap-4">
          <div>
            <h5 className="bd-card-category">
              Dynamic Machine Learning Pipeline{' '}
              {metrics?.execution_engine ? `— ${metrics.execution_engine}` : ''}
            </h5>
            <h3 className="bd-card-title !text-lg flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#1d8cf8]" />
              K-Means Risk Labeler &amp; Random Forest (T+1) Configuration
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onChangeConfig({ use_spark: !config.use_spark })}
              className={`bd-btn-toggle ${config.use_spark ? 'active' : ''}`}
              title="Toggle between Speed Layer (Scikit-Learn) and Batch Layer (PySpark MLlib)"
            >
              {config.use_spark ? 'Engine: PySpark MLlib' : 'Engine: Scikit-Learn'}
            </button>
            <button
              type="button"
              onClick={handleTrainModel}
              disabled={training}
              className="bd-btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" />
              {training ? 'Training Models (Temporal Split)...' : 'Train & Evaluate Models'}
            </button>
          </div>
        </div>

        <div className="bd-card-body space-y-5">
          {/* Dynamic Feature Subset Selector */}
          <div>
            <label className="block text-xs text-[#9a9a9a] mb-2">
              Active Feature Subset ({config.features.length} Selected &mdash; Minimum 2):
            </label>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_FEATURES.map((feat) => {
                const active = config.features.includes(feat);
                return (
                  <button
                    key={feat}
                    type="button"
                    onClick={() => toggleFeature(feat)}
                    className={`px-3 py-1.5 rounded-[0.35rem] text-xs font-mono transition border ${
                      active
                        ? 'bg-[#1d8cf8]/20 border-[#1d8cf8] text-white'
                        : 'bg-[#1e1e2f] border-[#2b3553] text-[#9a9a9a] hover:text-white'
                    }`}
                  >
                    {feat}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Hyperparameter Inputs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">
                K-Means Clusters (k = {config.cluster_k})
              </label>
              <input
                type="number"
                min={3}
                max={5}
                value={config.cluster_k}
                onChange={(e) => onChangeConfig({ cluster_k: Number(e.target.value) || 3 })}
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">
                Temporal Train Ratio ({Math.round(config.train_ratio * 100)}%)
              </label>
              <input
                type="number"
                step={0.05}
                min={0.6}
                max={0.9}
                value={config.train_ratio}
                onChange={(e) => onChangeConfig({ train_ratio: Number(e.target.value) || 0.8 })}
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">
                Random Forest Trees (n_estimators)
              </label>
              <input
                type="number"
                step={50}
                min={50}
                max={500}
                value={config.rf_num_trees}
                onChange={(e) =>
                  onChangeConfig({ rf_num_trees: Number(e.target.value) || 200 })
                }
                className="bd-input w-full font-mono"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#9a9a9a] mb-1">
                Random Forest Max Depth
              </label>
              <input
                type="number"
                min={3}
                max={25}
                value={config.rf_max_depth}
                onChange={(e) =>
                  onChangeConfig({ rf_max_depth: Number(e.target.value) || 10 })
                }
                className="bd-input w-full font-mono"
              />
            </div>
          </div>
        </div>
      </div>

      {/* ROW 3: EVALUATION METRICS, CENTROID RANKING & FEATURE IMPORTANCES */}
      {metrics && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* K-Means Centroid Risk Ordering Table */}
            <div className="lg:col-span-7 bd-card">
              <div className="bd-card-header flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h5 className="bd-card-category">
                    Unsupervised Regime Discovery (Silhouette Score:{' '}
                    {metrics.kmeans_metrics.silhouette_score})
                  </h5>
                  <h4 className="bd-card-title !text-base flex items-center gap-2">
                    <Target className="w-4 h-4 text-[#00f2c3]" />
                    K-Means Centroid Risk Scoring &amp; Regime Mapping
                  </h4>
                </div>
                <span className="text-xs text-[#9a9a9a] font-mono">
                  Train: {metrics.temporal_split.train_samples} | Test:{' '}
                  {metrics.temporal_split.test_samples}
                </span>
              </div>
              <div className="bd-card-body">
                <div className="overflow-x-auto">
                  <table className="bd-table">
                    <thead>
                      <tr>
                        <th className="text-left">Rank</th>
                        <th className="text-left">Raw Cluster ID</th>
                        <th className="text-left">Mapped Regime</th>
                        <th className="text-right">Composite Risk Score</th>
                        <th className="text-right">Train Observations</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metrics.kmeans_metrics.centroids.map((c) => {
                        const col = REGIME_COLORS[c.assigned_risk_label];
                        return (
                          <tr key={c.cluster_id}>
                            <td className="font-mono text-white">#{c.risk_rank}</td>
                            <td className="font-mono text-[#1d8cf8]">Cluster {c.cluster_id}</td>
                            <td>
                              <span
                                style={{ color: col, borderColor: col }}
                                className="px-2.5 py-0.5 rounded text-xs font-semibold border bg-black/20"
                              >
                                {c.assigned_risk_label}
                              </span>
                            </td>
                            <td className="text-right font-mono text-white">
                              {c.composite_risk_score}
                            </td>
                            <td className="text-right font-mono text-[#9a9a9a]">
                              {c.train_sample_count.toLocaleString()}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Random Forest Feature Importance Chart */}
            <div className="lg:col-span-5 bd-card">
              <div className="bd-card-header flex items-center justify-between">
                <div>
                  <h5 className="bd-card-category">
                    Regression MAE: {metrics.regression_metrics.mae} | RMSE:{' '}
                    {metrics.regression_metrics.rmse}
                  </h5>
                  <h4 className="bd-card-title !text-base flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-[#1d8cf8]" />
                    Random Forest Feature Importance
                  </h4>
                </div>
              </div>
              <div className="bd-card-body">
                <div className="h-[205px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={metrics.feature_importances} layout="vertical">
                      <CartesianGrid strokeDasharray="2 4" stroke="rgba(29, 140, 248, 0.08)" />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 10, fill: '#9a9a9a' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="feature"
                        width={120}
                        tick={{ fontSize: 11, fill: '#ffffff' }}
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
                        dataKey="importance"
                        fill="#1d8cf8"
                        radius={[0, 4, 4, 0]}
                        name="Importance"
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Row: Per-Class Classification Metrics + Confusion Matrix */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-6 bd-card">
              <div className="bd-card-header flex items-center justify-between">
                <div>
                  <h5 className="bd-card-category">
                    Chronological Out-of-Sample Evaluation (Accuracy:{' '}
                    {(metrics.classification_metrics.accuracy * 100).toFixed(2)}%)
                  </h5>
                  <h4 className="bd-card-title !text-base">
                    Per-Class Precision, Recall &amp; F1-Score
                  </h4>
                </div>
                <span className="text-xs font-mono text-[#00f2c3]">
                  Macro F1: {metrics.classification_metrics.f1_macro}
                </span>
              </div>
              <div className="bd-card-body">
                <table className="bd-table">
                  <thead>
                    <tr>
                      <th className="text-left">Regime Class</th>
                      <th className="text-right">Precision</th>
                      <th className="text-right">Recall</th>
                      <th className="text-right">F1-Score</th>
                      <th className="text-right">Test Support</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(['SAFE', 'WARNING', 'DANGER'] as RiskRegime[]).map((cls) => {
                      const row = metrics.classification_metrics.per_class[cls];
                      return (
                        <tr key={cls}>
                          <td
                            style={{ color: REGIME_COLORS[cls] }}
                            className="font-semibold"
                          >
                            {cls}
                          </td>
                          <td className="text-right font-mono">{row?.precision}</td>
                          <td className="text-right font-mono">{row?.recall}</td>
                          <td className="text-right font-mono text-white font-semibold">
                            {row?.f1_score}
                          </td>
                          <td className="text-right font-mono text-[#9a9a9a]">
                            {row?.support}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="lg:col-span-6 bd-card">
              <div className="bd-card-header">
                <h5 className="bd-card-category">Temporal Test Set</h5>
                <h4 className="bd-card-title !text-base">
                  Confusion Matrix (Actual T+1 vs Predicted T+1)
                </h4>
              </div>
              <div className="bd-card-body">
                <table className="bd-table">
                  <thead>
                    <tr>
                      <th className="text-left">Actual \ Predicted</th>
                      {metrics.classification_metrics.labels.map((l) => (
                        <th key={l} className="text-right">
                          {l}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.classification_metrics.confusion_matrix.map((row, rIdx) => {
                      const lbl = metrics.classification_metrics.labels[rIdx];
                      return (
                        <tr key={lbl}>
                          <td
                            style={{ color: REGIME_COLORS[lbl] }}
                            className="font-semibold"
                          >
                            {lbl}
                          </td>
                          {row.map((val, cIdx) => (
                            <td
                              key={cIdx}
                              className={`text-right font-mono ${
                                rIdx === cIdx
                                  ? 'text-[#00f2c3] font-semibold'
                                  : 'text-[#9a9a9a]'
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
            </div>
          </div>
        </>
      )}
    </div>
  );
};
