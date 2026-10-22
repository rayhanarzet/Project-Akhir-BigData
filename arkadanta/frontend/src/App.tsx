import React, { useEffect, useState } from 'react';
import {
  Activity,
  BrainCircuit,
  Database,
  Layers,
  Server,
  Shield,
} from 'lucide-react';
import {
  DynamicConfigPayload,
  HistoricalBaselineResponse,
} from './types/arkadanta';
import { fetchHistoricalBaseline, SUPPORTED_SYMBOLS } from './services/api';
import { Tab1Ingestion } from './components/Tab1Ingestion';
import { Tab2AnalyticsBI } from './components/Tab2AnalyticsBI';
import { Tab3ModelLabShield } from './components/Tab3ModelLabShield';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'tab1' | 'tab2' | 'tab3'>('tab2');
  const [baseline, setBaseline] = useState<HistoricalBaselineResponse | null>(null);
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);

  const [config, setConfig] = useState<DynamicConfigPayload>({
    symbol: 'BTCUSDT',
    symbols: SUPPORTED_SYMBOLS,
    timeframe: '1h',
    features: [
      'max_volatility',
      'spike_ratio',
      'rsi_14',
      'volume_zscore',
      'bb_width',
      'hl_range',
    ],
    ma_period: 20,
    rsi_period: 14,
    rolling_window: 20,
    anomaly_method: 'adaptive_quantile',
    anomaly_quantile: 0.95,
    anomaly_z_threshold: 2.5,
    anomaly_iqr_multiplier: 1.5,
    cluster_k: 3,
    correlation_window: 30,
    max_lag: 6,
    train_ratio: 0.8,
    rf_num_trees: 200,
    rf_max_depth: 10,
    target_horizon: 1,
  });

  const loadBaseline = async () => {
    const res = await fetchHistoricalBaseline();
    setBaseline(res.data);
    setIsLiveBackend(res.isLiveBackend);
  };

  useEffect(() => {
    loadBaseline();
  }, []);

  const updateConfig = (partial: Partial<DynamicConfigPayload>) => {
    setConfig((prev) => ({ ...prev, ...partial }));
  };

  return (
    <div className="min-h-screen flex flex-col text-slate-100">
      {/* Top Institutional Navigation Header */}
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-[#070b14]/90 border-b border-slate-800/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-cyan-500 to-indigo-600 text-white shadow-lg shadow-cyan-500/20">
              <Shield className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg sm:text-xl font-extrabold tracking-tight text-white">
                  ARKADANTA
                </h1>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                  Lambda Architecture v1.0
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Dynamic Big Data Intelligence Pipeline &mdash; Analisis, Anomali & Prediksi Risiko
                Volatilitas Kripto
              </p>
            </div>
          </div>

          {/* Connection Status & Quick Asset Switcher */}
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-1.5 bg-slate-900/90 border border-slate-800 rounded-xl p-1">
              {SUPPORTED_SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => updateConfig({ symbol: sym })}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition ${
                    config.symbol === sym
                      ? 'bg-cyan-500 text-slate-950 shadow'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {sym.replace('USDT', '')}
                </button>
              ))}
            </div>

            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold ${
                isLiveBackend
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
              }`}
            >
              <Server className="w-3.5 h-3.5" />
              <span>{isLiveBackend ? 'FastAPI Connected' : 'Interactive Engine Active'}</span>
            </div>
          </div>
        </div>

        {/* 3 Main Tabs Bar (Bab 7 Proposal) */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex overflow-x-auto gap-2 border-t border-slate-800/50 pt-2">
          <button
            type="button"
            onClick={() => setActiveTab('tab1')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition whitespace-nowrap ${
              activeTab === 'tab1'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Database className="w-4 h-4" />
            Tab 1 &mdash; Data Ingestion & Preprocessing Manager
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('tab2')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition whitespace-nowrap ${
              activeTab === 'tab2'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Activity className="w-4 h-4" />
            Tab 2 &mdash; Dynamic BI & Historical Explorer
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('tab3')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition whitespace-nowrap ${
              activeTab === 'tab3'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BrainCircuit className="w-4 h-4" />
            Tab 3 &mdash; Model Lab & Live Market Shield
          </button>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {activeTab === 'tab1' && baseline && (
          <Tab1Ingestion baseline={baseline} onRefreshBaseline={loadBaseline} />
        )}
        {activeTab === 'tab2' && (
          <Tab2AnalyticsBI config={config} onChangeConfig={updateConfig} />
        )}
        {activeTab === 'tab3' && (
          <Tab3ModelLabShield config={config} onChangeConfig={updateConfig} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-4 px-6 text-center text-xs text-slate-500">
        Arkadanta &bull; Dynamic Big Data Intelligence Pipeline (Mata Kuliah Big Data & Analitik)
        &bull; Keluaran prediksi hanya untuk analitik akademik, bukan rekomendasi investasi.
      </footer>
    </div>
  );
};

export default App;
