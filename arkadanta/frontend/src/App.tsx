import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  Cpu,
  Database,
  Layers,
  Menu,
  Radio,
  Sliders,
  X,
} from 'lucide-react';
import {
  DynamicConfigPayload,
  HistoricalBaselineResponse,
} from './types/arkadanta';
import {
  fetchHistoricalBaseline,
  SUPPORTED_SYMBOLS,
} from './services/api';
import { Tab1Ingestion } from './components/Tab1Ingestion';
import { Tab2AnalyticsBI } from './components/Tab2AnalyticsBI';
import { Tab3ModelLabShield } from './components/Tab3ModelLabShield';
import { LiveMarketPanel } from './components/LiveMarketPanel';

type SidebarTheme = 'blue' | 'green' | 'primary';

const SIDEBAR_GRADIENTS: Record<SidebarTheme, string> = {
  blue: 'linear-gradient(0deg, #3358f4 0%, #1d8cf8 100%)',
  green: 'linear-gradient(0deg, #0098f0 0%, #00f2c3 100%)',
  primary: 'linear-gradient(0deg, #ba54f5 0%, #e14eca 100%)',
};

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'tab2' | 'tab3' | 'tab1'>('tab2');
  const [sidebarTheme, setSidebarTheme] = useState<SidebarTheme>('blue');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [baseline, setBaseline] = useState<HistoricalBaselineResponse>(
    { pipeline_status: 'UNKNOWN', hdfs_cluster_path: '', assets: [], audit_logs: [] }
  );
  const [baselineError, setBaselineError] = useState<string | null>(null);
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);
  const [dataRevision, setDataRevision] = useState(0);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    gmm_components: 3,
    correlation_window: 30,
    max_lag: 6,
    train_ratio: 0.8,
    gb_max_iter: 200,
    gb_max_depth: 10,
    gb_learning_rate: 0.1,
    target_horizon: 1,
    use_spark: false,
  });

  const loadBaseline = useCallback(async () => {
    try {
      const res = await fetchHistoricalBaseline();
      setBaseline(res.data);
      setIsLiveBackend(res.isLiveBackend);
      setBaselineError(null);
    } catch (err) {
      setIsLiveBackend(false);
      setBaseline({ pipeline_status: 'UNAVAILABLE', hdfs_cluster_path: '', assets: [], audit_logs: [] });
      setBaselineError(err instanceof Error ? err.message : 'Data backend tidak tersedia.');
    }
  }, []);

  const onCandleClosed = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      loadBaseline();
      setDataRevision((value) => value + 1);
    }, 750);
  }, [loadBaseline]);

  useEffect(() => {
    loadBaseline();
    return () => { if (refreshTimer.current) clearTimeout(refreshTimer.current); };
  }, [loadBaseline]);

  const updateConfig = (partial: Partial<DynamicConfigPayload>) => {
    setConfig((prev) => ({ ...prev, ...partial }));
  };

  const navItems: {
    id: 'tab2' | 'tab3' | 'tab1';
    label: string;
    subtitle: string;
    icon: React.ReactNode;
  }[] = [
    {
      id: 'tab2',
      label: 'Market Analytics',
      subtitle: 'Dynamic BI & Anomalies',
      icon: <Activity className="w-4 h-4" />,
    },
    {
      id: 'tab3',
      label: 'Model Lab & Shield',
      subtitle: 'Gaussian Mixture & HGB T+1 Risk',
      icon: <Cpu className="w-4 h-4" />,
    },
    {
      id: 'tab1',
      label: 'Data Ingestion',
      subtitle: 'HDFS, NiFi & Cron Sync',
      icon: <Database className="w-4 h-4" />,
    },
  ];

  const activeNav = navItems.find((n) => n.id === activeTab) || navItems[0];

  return (
    <div className="min-h-screen bg-[#1e1e2f] text-white flex relative">
      {/* Black Dashboard Floating Left Sidebar */}
      <aside
        style={{ background: SIDEBAR_GRADIENTS[sidebarTheme] }}
        className={`fixed z-40 top-0 lg:top-5 left-0 lg:left-5 bottom-0 lg:bottom-5 w-[230px] lg:rounded-[5px] shadow-2xl transition-transform duration-200 flex flex-col justify-between ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div>
          {/* Brand Logo Header */}
          <div className="px-5 py-4 flex items-center justify-between border-b border-white/20">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-full bg-white/15 flex items-center justify-center text-white font-semibold text-xs tracking-wider">
                AK
              </div>
              <div>
                <span className="text-sm font-semibold tracking-wider uppercase block text-white">
                  Arkadanta
                </span>
                <span className="text-[10px] text-white/75 tracking-wide block">
                  Lambda Risk Pipeline
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setMobileMenuOpen(false)}
              className="lg:hidden text-white/80 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Navigation List */}
          <nav className="mt-5 px-3 space-y-1.5">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setActiveTab(item.id);
                    setMobileMenuOpen(false);
                  }}
                  className={`w-full flex items-center gap-3.5 px-4 py-3 rounded-[4px] text-left transition-all relative ${
                    isActive
                      ? 'text-white font-semibold bg-white/10'
                      : 'text-white/75 hover:text-white hover:bg-white/5 font-light'
                  }`}
                >
                  {isActive && (
                    <span className="w-1.5 h-1.5 rounded-full bg-white absolute right-3.5 top-1/2 -translate-y-1/2" />
                  )}
                  <span className="shrink-0 opacity-90">{item.icon}</span>
                  <div>
                    <p className="text-[11px] uppercase tracking-wider leading-tight">
                      {item.label}
                    </p>
                    <p className="text-[10px] text-white/65 font-light mt-0.5">
                      {item.subtitle}
                    </p>
                  </div>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom Sidebar Context & Theme Switcher (Black Dashboard Fixed Plugin Style) */}
        <div className="p-4 border-t border-white/20 space-y-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-white/70 mb-1.5">
              Active Pair & Timeframe
            </p>
            <div className="bg-black/20 rounded px-3 py-2 flex items-center justify-between text-xs font-mono">
              <span className="font-semibold text-white">{config.symbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-white/15 text-[11px]">
                {config.timeframe}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] uppercase tracking-wider text-white/75">
              Sidebar Accent
            </span>
            <div className="flex items-center gap-1.5">
              {(
                [
                  { id: 'blue', color: '#1d8cf8' },
                  { id: 'green', color: '#00f2c3' },
                  { id: 'primary', color: '#e14eca' },
                ] as { id: SidebarTheme; color: string }[]
              ).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSidebarTheme(t.id)}
                  style={{ backgroundColor: t.color }}
                  className={`w-4 h-4 rounded-full border transition-transform ${
                    sidebarTheme === t.id
                      ? 'border-white scale-110'
                      : 'border-transparent opacity-75 hover:opacity-100'
                  }`}
                  aria-label={`Theme ${t.id}`}
                />
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* Main Panel Area */}
      <div className="flex-1 lg:pl-[270px] flex flex-col min-h-screen w-full">
        {/* Top Navbar */}
        <header className="px-6 pt-5 pb-3 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded bg-[#27293d] text-white/80 hover:text-white"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <p className="text-[11px] uppercase tracking-widest text-[#9a9a9a] font-normal">
                Arkadanta Big Data Pipeline / {activeNav.label}
              </p>
              <h1 className="text-lg font-light tracking-wide text-white mt-0.5">
                {activeNav.label}{' '}
                <span className="text-[#9a9a9a] font-light text-sm">
                  &mdash; {activeNav.subtitle}
                </span>
              </h1>
            </div>
          </div>

          {/* Right Top Controls: Segmented Asset Switcher & API Status */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex">
              {SUPPORTED_SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => updateConfig({ symbol: sym })}
                  className={`bd-btn-toggle ${config.symbol === sym ? 'active' : ''}`}
                >
                  {sym}
                </button>
              ))}
            </div>

            <div className="bg-[#27293d] px-3.5 py-1.5 rounded-[0.4285rem] flex items-center gap-2 text-xs border border-[#2b3553]">
              <Radio
                className={`w-3.5 h-3.5 ${
                  isLiveBackend ? 'text-[#00f2c3]' : 'text-[#1d8cf8]'
                }`}
              />
              <span className="text-[#9a9a9a]">Serving Layer:</span>
              <span className="font-medium text-white">
                {isLiveBackend ? 'FastAPI Live (8000)' : 'Backend belum terhubung'}
              </span>
            </div>
          </div>
        </header>

        {/* View Content */}
        <main className="flex-1 px-6 py-3">
          <LiveMarketPanel symbol={config.symbol} onCandleClosed={onCandleClosed} />
          {baselineError && (
            <div role="alert" className="mb-4 p-4 border border-red-400 rounded text-red-300">
              {baselineError}
              <button type="button" onClick={loadBaseline} className="ml-3 underline">Coba lagi</button>
            </div>
          )}
          {isLiveBackend && baseline.assets.length === 0 && (
            <div role="status" className="mb-4 p-4 border border-amber-400 rounded text-amber-200">
              Data penelitian belum tersedia. Buka Data Ingestion untuk sinkronisasi Binance atau unggah data nyata. Data lama tidak digunakan otomatis.
            </div>
          )}
          {activeTab === 'tab1' && baseline && (
            <Tab1Ingestion baseline={baseline} onRefreshBaseline={loadBaseline} />
          )}
          {activeTab === 'tab2' && (
            <Tab2AnalyticsBI config={config} onChangeConfig={updateConfig} dataRevision={dataRevision} />
          )}
          {activeTab === 'tab3' && (
            <Tab3ModelLabShield config={config} onChangeConfig={updateConfig} dataRevision={dataRevision} />
          )}
        </main>

        {/* Black Dashboard Footer */}
        <footer className="px-6 py-5 flex flex-wrap items-center justify-between text-xs text-[#9a9a9a] border-t border-white/5 mt-6">
          <div className="flex items-center gap-4">
            <span className="text-white font-normal">ARKADANTA</span>
            <span>Big Data &amp; Analytics Final Project</span>
            <span>Lambda Architecture (HDFS &bull; PySpark &bull; FastAPI)</span>
          </div>
          <div>
            <span>Academic Quantitative Risk Analysis &mdash; Non-Advisory Output</span>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default App;
