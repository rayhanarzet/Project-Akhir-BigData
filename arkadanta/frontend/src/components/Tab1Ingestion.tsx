import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Database,
  FileSpreadsheet,
  HardDrive,
  Play,
  RefreshCw,
  ShieldCheck,
  StopCircle,
  UploadCloud,
} from 'lucide-react';
import {
  CronStatus,
  HistoricalBaselineResponse,
  IngestionAuditReport,
} from '../types/arkadanta';
import {
  backfillBinanceHistory,
  fetchCronStatus,
  SUPPORTED_SYMBOLS,
  triggerBinanceLiveSync,
  updateCronConfig,
  uploadDatasetFile,
} from '../services/api';

interface Props {
  baseline: HistoricalBaselineResponse;
  onRefreshBaseline: () => void;
}

const INTERVAL_PRESETS = [
  { label: '5m (1 Candle)', value: 5 },
  { label: '15m', value: 15 },
  { label: '25m', value: 25 },
  { label: '1h (60m)', value: 60 },
  { label: '4h (240m)', value: 240 },
  { label: '1d (1440m)', value: 1440 },
];

export const Tab1Ingestion: React.FC<Props> = ({ baseline, onRefreshBaseline }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [defaultSymbol, setDefaultSymbol] = useState<string>('BTCUSDT');
  const [customMapping, setCustomMapping] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncLimit, setSyncLimit] = useState<number>(300);
  const [backfillDays, setBackfillDays] = useState<number>(365);
  const [selectedSyncSymbols, setSelectedSyncSymbols] = useState<string[]>(SUPPORTED_SYMBOLS);
  const [latestReport, setLatestReport] = useState<IngestionAuditReport | null>(
    baseline.audit_logs[0] || null
  );
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const [cronStatus, setCronStatus] = useState<CronStatus>({
    enabled: false,
    interval_minutes: 5,
    symbols: SUPPORTED_SYMBOLS,
    limit: 60,
    last_run: null,
    next_run: null,
    last_status: 'IDLE',
    last_synced_count: 0,
    total_runs: 0,
  });
  const [selectedInterval, setSelectedInterval] = useState<number>(5);
  const [isCustomInterval, setIsCustomInterval] = useState<boolean>(false);
  const [customIntervalValue, setCustomIntervalValue] = useState<number>(5);
  const [cronLoading, setCronLoading] = useState<boolean>(false);

  useEffect(() => {
    let active = true;
    const loadStatus = async () => {
      try {
      const res = await fetchCronStatus();
      if (active) {
        setCronStatus(res);
        setSelectedInterval(res.interval_minutes);
        const matchPreset = INTERVAL_PRESETS.some((p) => p.value === res.interval_minutes);
        setIsCustomInterval(!matchPreset);
        if (!matchPreset) setCustomIntervalValue(res.interval_minutes);
      }
      } catch (err) {
        if (active) {
          setCronStatus((previous) => ({ ...previous, enabled: false, last_status: 'UNAVAILABLE', next_run: null }));
          setStatusMessage(err instanceof Error ? err.message : 'Status scheduler tidak tersedia.');
        }
      }
    };
    loadStatus();
    const timer = setInterval(loadStatus, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const handleToggleCron = async () => {
    setCronLoading(true);
    setStatusMessage(null);
    try {
      const interval = isCustomInterval ? customIntervalValue : selectedInterval;
      const res = await updateCronConfig(
        !cronStatus.enabled,
        interval,
        selectedSyncSymbols,
        60
      );
      setCronStatus(res);
      setStatusMessage(
        res.enabled
          ? `Automated Cron Scheduler enabled (Every ${res.interval_minutes} minutes).`
          : 'Automated Cron Scheduler stopped. Manual synchronization remains available.'
      );
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Konfigurasi scheduler gagal.');
    } finally {
      setCronLoading(false);
    }
  };

  const handleIntervalChange = async (newInterval: number, custom = false) => {
    setIsCustomInterval(custom);
    if (!custom) setSelectedInterval(newInterval);
    if (cronStatus.enabled) {
      setCronLoading(true);
      try {
        const res = await updateCronConfig(true, newInterval, selectedSyncSymbols, 60);
        setCronStatus(res);
        setStatusMessage(`Cron interval updated to ${newInterval} minutes.`);
      } catch (err) {
        setStatusMessage(err instanceof Error ? err.message : 'Perubahan interval gagal.');
      } finally {
        setCronLoading(false);
      }
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setStatusMessage(null);
    try {
      const report = await uploadDatasetFile(selectedFile, defaultSymbol, customMapping);
      setLatestReport(report);
      setStatusMessage(
        `Processed ${report.source_name} — Data Quality Score: ${report.quality_score_pct}% (${report.rows_after}/${report.rows_before} valid rows)`
      );
      onRefreshBaseline();
    } catch (err: any) {
      setStatusMessage(`Error: ${err.message || 'Upload failed'}`);
    } finally {
      setUploading(false);
    }
  };

  const handleLiveSync = async () => {
    if (selectedSyncSymbols.length === 0) return;
    setSyncing(true);
    setStatusMessage(null);
    try {
      const res = await triggerBinanceLiveSync(selectedSyncSymbols, syncLimit);
      if (res.reports.length > 0) {
        setLatestReport(res.reports[0]);
      }
      setStatusMessage(
        `Manual Binance synchronization completed for ${res.synced_assets} assets (${syncLimit} 5m candles).`
      );
      onRefreshBaseline();
    } catch (err) {
      setLatestReport(null);
      setStatusMessage(err instanceof Error ? err.message : 'Sinkronisasi Binance gagal.');
      onRefreshBaseline();
    } finally {
      setSyncing(false);
    }
  };

  const handleBackfill = async () => {
    if (selectedSyncSymbols.length === 0) return;
    setSyncing(true);
    setStatusMessage(null);
    try {
      const res = await backfillBinanceHistory(selectedSyncSymbols, backfillDays);
      if (res.reports.length > 0) setLatestReport(res.reports[res.reports.length - 1]);
      setStatusMessage(`Backfill ${backfillDays} hari selesai untuk ${res.synced_assets} aset.`);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Backfill Binance gagal.');
    } finally {
      onRefreshBaseline();
      setSyncing(false);
    }
  };

  const toggleSyncSymbol = (sym: string) => {
    setSelectedSyncSymbols((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]
    );
  };

  const activeAudit = latestReport || baseline.audit_logs[0];

  return (
    <div>
      {/* Top 3 Summary Cards (Pipeline Status, HDFS Target, Data Quality Score) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bd-card">
          <div className="bd-card-body flex items-center justify-between !py-5">
            <div className="w-11 h-11 rounded-full bg-[#00f2c3]/15 flex items-center justify-center text-[#00f2c3]">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div className="text-right">
              <p className="bd-card-category">Pipeline Controller Status</p>
              <h3 className="bd-card-title !text-xl">{baseline.pipeline_status}</h3>
            </div>
          </div>
          <div className="px-5 py-2.5 border-t border-white/5 text-xs text-[#9a9a9a]">
            Rule-Based Schema &amp; Sanity Guard Active
          </div>
        </div>

        <div className="bd-card">
          <div className="bd-card-body flex items-center justify-between !py-5">
            <div className="w-11 h-11 rounded-full bg-[#1d8cf8]/15 flex items-center justify-center text-[#1d8cf8]">
              <HardDrive className="w-5 h-5" />
            </div>
            <div className="text-right">
              <p className="bd-card-category">Apache NiFi PutHDFS Target</p>
              <h3 className="text-sm font-mono text-white mt-1">
                {baseline.hdfs_cluster_path}
              </h3>
            </div>
          </div>
          <div className="px-5 py-2.5 border-t border-white/5 text-xs text-[#9a9a9a]">
            Partitioned by symbol / year / month / timeframe
          </div>
        </div>

        <div className="bd-card">
          <div className="bd-card-body flex items-center justify-between !py-5">
            <div className="w-11 h-11 rounded-full bg-[#e14eca]/15 flex items-center justify-center text-[#e14eca]">
              <Database className="w-5 h-5" />
            </div>
            <div className="text-right">
              <p className="bd-card-category">Latest Data Quality Score</p>
              <h3 className="bd-card-title !text-xl">
                {activeAudit ? `${activeAudit.quality_score_pct}%` : 'Belum tersedia'}
              </h3>
            </div>
          </div>
          <div className="px-5 py-2.5 border-t border-white/5 text-xs text-[#9a9a9a]">
            {activeAudit
              ? `${activeAudit.rows_after.toLocaleString()} clean OHLCV records verified`
              : 'Belum ada hasil validasi data penelitian'}
          </div>
        </div>
      </div>

      {statusMessage && (
        <div role="status" aria-live="polite" className="bd-card !mb-6 border-l-4 !border-l-[#1d8cf8]">
          <div className="px-5 py-3.5 flex items-center gap-3 text-xs text-white">
            <span>{statusMessage}</span>
          </div>
        </div>
      )}

      {/* Batch Upload + Speed Layer Cron/Manual Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Batch Layer: CSV/JSON Upload */}
        <form onSubmit={handleUpload} className="lg:col-span-6 bd-card flex flex-col justify-between">
          <div>
            <div className="bd-card-header flex items-center justify-between">
              <div>
                <h5 className="bd-card-category">Batch Layer Ingestion</h5>
                <h3 className="bd-card-title !text-lg">CSV / JSON Dataset Upload</h3>
              </div>
              <span className="text-xs font-mono text-[#1d8cf8]">Auto Format Detector</span>
            </div>

            <div className="bd-card-body space-y-4">
              <label className="block border border-dashed border-[#2b3553] hover:border-[#1d8cf8] transition rounded-[0.4285rem] p-6 text-center cursor-pointer bg-[#1e1e2f]">
                <input
                  type="file"
                  accept=".csv,.json"
                  className="hidden"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
                <FileSpreadsheet className="w-7 h-7 text-[#1d8cf8] mx-auto mb-2" />
                {selectedFile ? (
                  <div>
                    <p className="text-sm font-medium text-[#00f2c3]">{selectedFile.name}</p>
                    <p className="text-xs text-[#9a9a9a] mt-0.5">
                      {(selectedFile.size / 1024).toFixed(1)} KB &mdash; Ready for Dynamic Pipeline
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-xs text-white font-normal">
                      Select raw <span className="text-[#1d8cf8]">.CSV</span> or{' '}
                      <span className="text-[#1d8cf8]">.JSON</span> file to ingest
                    </p>
                    <p className="text-[11px] text-[#9a9a9a] mt-1">
                      Automatic alias resolution (open_time &rarr; timestamp, vol &rarr; volume)
                    </p>
                  </div>
                )}
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] text-[#9a9a9a] mb-1">
                    Default Asset Symbol
                  </label>
                  <select
                    value={defaultSymbol}
                    onChange={(e) => setDefaultSymbol(e.target.value)}
                    className="bd-input w-full"
                  >
                    {SUPPORTED_SYMBOLS.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-[#9a9a9a] mb-1">
                    Custom Column Mapping (Optional JSON)
                  </label>
                  <input
                    type="text"
                    value={customMapping}
                    onChange={(e) => setCustomMapping(e.target.value)}
                    placeholder='{"open_time": "timestamp", "vol": "volume"}'
                    className="bd-input w-full font-mono"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="px-5 pb-5">
            <button
              type="submit"
              disabled={!selectedFile || uploading}
              className="bd-btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-40"
            >
              <UploadCloud className="w-4 h-4" />
              {uploading ? 'Validating & Normalizing...' : 'Run Dynamic Ingestion Pipeline'}
            </button>
          </div>
        </form>

        {/* Speed Layer: Background Cron Scheduler & Manual Binance Sync */}
        <div className="lg:col-span-6 bd-card">
          <div className="bd-card-header flex items-center justify-between">
            <div>
              <h5 className="bd-card-category">Speed Layer (/api/v3/klines)</h5>
              <h3 className="bd-card-title !text-lg">
                Automated Cron Scheduler &amp; Manual Sync
              </h3>
            </div>
            <span
              className={`px-2.5 py-1 rounded text-xs font-mono border ${
                cronStatus.enabled
                  ? 'border-[#00f2c3] text-[#00f2c3] bg-[#00f2c3]/10'
                  : 'border-[#2b3553] text-[#9a9a9a] bg-[#1e1e2f]'
              }`}
            >
              {cronStatus.enabled ? `CRON ON (${cronStatus.interval_minutes}m)` : 'CRON IDLE'}
            </span>
          </div>

          <div className="bd-card-body space-y-4">
            {/* Cron Controls Box */}
            <div className="bg-[#1e1e2f] border border-[#2b3553] rounded-[0.4285rem] p-4 space-y-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs text-white">
                  <Clock className="w-4 h-4 text-[#1d8cf8]" />
                  <span>Background Periodic Synchronization</span>
                </div>
                <button
                  type="button"
                  onClick={handleToggleCron}
                  disabled={cronLoading}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition flex items-center gap-1.5 border ${
                    cronStatus.enabled
                      ? 'border-[#fd5d93] text-[#fd5d93] hover:bg-[#fd5d93]/10'
                      : 'border-[#00f2c3] text-[#00f2c3] hover:bg-[#00f2c3]/10'
                  }`}
                >
                  {cronStatus.enabled ? (
                    <>
                      <StopCircle className="w-3.5 h-3.5" /> Stop Cron
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" /> Enable Auto Cron
                    </>
                  )}
                </button>
              </div>

              <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5">
                {INTERVAL_PRESETS.map((p) => {
                  const selected = !isCustomInterval && selectedInterval === p.value;
                  return (
                    <button
                      key={p.value}
                      type="button"
                      onClick={() => handleIntervalChange(p.value, false)}
                      className={`py-1.5 px-2 rounded text-[11px] font-mono border transition ${
                        selected
                          ? 'border-[#1d8cf8] bg-[#1d8cf8]/20 text-white'
                          : 'border-[#2b3553] text-[#9a9a9a] hover:text-white'
                      }`}
                    >
                      {p.label}
                    </button>
                  );
                })}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-white/5 text-xs">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleIntervalChange(customIntervalValue, true)}
                    className={`px-2.5 py-1 rounded text-[11px] border ${
                      isCustomInterval
                        ? 'border-[#1d8cf8] text-[#1d8cf8]'
                        : 'border-[#2b3553] text-[#9a9a9a]'
                    }`}
                  >
                    Custom (min):
                  </button>
                  <input
                    type="number"
                    min={1}
                    max={1440}
                    value={customIntervalValue}
                    onChange={(e) => {
                      const val = Math.max(1, Number(e.target.value) || 1);
                      setCustomIntervalValue(val);
                      if (isCustomInterval) handleIntervalChange(val, true);
                    }}
                    className="bd-input !w-20 !py-1 font-mono"
                  />
                </div>

                <div className="text-[11px] text-[#9a9a9a] font-mono">
                  Next Run:{' '}
                  <span className="text-white">
                    {cronStatus.enabled && cronStatus.next_run
                      ? cronStatus.next_run.slice(11, 19) + ' UTC'
                      : 'Manual Mode'}
                  </span>
                </div>
              </div>
            </div>

            {/* Manual Trigger Controls */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-[#9a9a9a]">Target Assets:</span>
                <div className="flex flex-wrap gap-1.5">
                  {SUPPORTED_SYMBOLS.map((sym) => {
                    const active = selectedSyncSymbols.includes(sym);
                    return (
                      <button
                        key={sym}
                        type="button"
                        onClick={() => toggleSyncSymbol(sym)}
                        className={`px-2.5 py-1 rounded text-xs font-mono border transition ${
                          active
                            ? 'border-[#1d8cf8] bg-[#1d8cf8]/20 text-white'
                            : 'border-[#2b3553] text-[#9a9a9a]'
                        }`}
                      >
                        {sym}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[#9a9a9a]">Candles Limit:</span>
                  <input
                    type="number"
                    step={50}
                    min={50}
                    max={1000}
                    value={syncLimit}
                    onChange={(e) => setSyncLimit(Number(e.target.value) || 300)}
                    className="bd-input !w-24 !py-1.5 font-mono"
                  />
                </div>

                <button
                  type="button"
                  onClick={handleLiveSync}
                  disabled={syncing || selectedSyncSymbols.length === 0}
                  className="bd-btn-teal flex items-center gap-2 disabled:opacity-40"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
                  {syncing ? 'Synchronizing...' : 'Manual Sync Now'}
                </button>
              </div>

              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[#9a9a9a]">Backfill (hari):</span>
                  <input
                    type="number"
                    min={1}
                    max={365}
                    value={backfillDays}
                    onChange={(e) => setBackfillDays(Math.min(365, Math.max(1, Number(e.target.value) || 365)))}
                    className="bd-input !w-24 !py-1.5 font-mono"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleBackfill}
                  disabled={syncing || selectedSyncSymbols.length === 0}
                  className="bd-btn-teal flex items-center gap-2 disabled:opacity-40"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
                  {syncing ? 'Menarik histori...' : 'Backfill Histori'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Audit Log Inspection Card (Output Orang 1) */}
      {activeAudit && (
        <div className="bd-card">
          <div className="bd-card-header flex flex-wrap items-center justify-between gap-2">
            <div>
              <h5 className="bd-card-category">Data Veracity &amp; Preprocessing Audit</h5>
              <h4 className="bd-card-title !text-base">
                Pipeline Execution: <span className="font-mono text-sm text-[#1d8cf8]">{activeAudit.selected_pipeline}</span>
              </h4>
            </div>
            <span className="text-xs font-mono text-[#00f2c3]">
              NiFi/HDFS Status: {activeAudit.nifi_hdfs_status}
            </span>
          </div>
          <div className="bd-card-body">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
              <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                <span className="text-[11px] text-[#9a9a9a] block">Detected Format</span>
                <span className="text-base font-mono font-semibold text-white mt-0.5 block">
                  {activeAudit.format_detected}
                </span>
              </div>
              <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                <span className="text-[11px] text-[#9a9a9a] block">Raw Input Rows</span>
                <span className="text-base font-mono font-semibold text-white mt-0.5 block">
                  {activeAudit.rows_before.toLocaleString()}
                </span>
              </div>
              <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                <span className="text-[11px] text-[#9a9a9a] block">Clean Output Rows</span>
                <span className="text-base font-mono font-semibold text-[#00f2c3] mt-0.5 block">
                  {activeAudit.rows_after.toLocaleString()}
                </span>
              </div>
              <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                <span className="text-[11px] text-[#9a9a9a] block">Duplicates Removed</span>
                <span className="text-base font-mono font-semibold text-[#ff8d72] mt-0.5 block">
                  {activeAudit.duplicates_removed}
                </span>
              </div>
              <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                <span className="text-[11px] text-[#9a9a9a] block">Imputed (FFill / Vol)</span>
                <span className="text-base font-mono font-semibold text-[#1d8cf8] mt-0.5 block">
                  {activeAudit.imputed_ohlc_rows + activeAudit.imputed_volume_rows}
                </span>
              </div>
              <div className="bg-[#1e1e2f] p-3.5 rounded-[0.4285rem] border border-[#2b3553]">
                <span className="text-[11px] text-[#9a9a9a] block">Rejected Invalid Rows</span>
                <span className="text-base font-mono font-semibold text-[#fd5d93] mt-0.5 block">
                  {activeAudit.rejected_rows}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Historical Baseline Partitions Table */}
      <div className="bd-card">
        <div className="bd-card-header">
          <h5 className="bd-card-category">Clean OHLCV Storage</h5>
          <h4 className="bd-card-title !text-base">
            5-Minute Baseline Partitions &amp; HDFS Paths
          </h4>
        </div>
        <div className="bd-card-body">
          <div className="overflow-x-auto">
            <table className="bd-table">
              <thead>
                <tr>
                  <th className="text-left">Asset Symbol</th>
                  <th className="text-right">Clean Rows (5m)</th>
                  <th className="text-right">Latest Close</th>
                  <th className="text-right">Mean Volume (5m)</th>
                  <th className="text-left">HDFS Partition Directory</th>
                  <th className="text-right">State</th>
                </tr>
              </thead>
              <tbody>
                {baseline.assets.map((asset) => (
                  <tr key={asset.symbol}>
                    <td className="font-semibold text-white">{asset.symbol}</td>
                    <td className="text-right font-mono">{asset.rows_5m.toLocaleString()}</td>
                    <td className="text-right font-mono text-[#00f2c3]">
                      ${asset.latest_close.toLocaleString()}
                    </td>
                    <td className="text-right font-mono text-[#9a9a9a]">
                      {asset.avg_volume_5m.toLocaleString()}
                    </td>
                    <td className="font-mono text-xs text-[#1d8cf8]">
                      {asset.hdfs_partition}
                    </td>
                    <td className="text-right">
                      <span className="text-xs font-mono text-[#00f2c3]">{asset.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
