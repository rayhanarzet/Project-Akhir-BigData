import React, { useState } from 'react';
import {
  CheckCircle2,
  CloudDownload,
  Database,
  FileSpreadsheet,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  AlertTriangle,
} from 'lucide-react';
import {
  HistoricalBaselineResponse,
  IngestionAuditReport,
} from '../types/arkadanta';
import {
  SUPPORTED_SYMBOLS,
  triggerBinanceLiveSync,
  uploadDatasetFile,
} from '../services/api';

interface Props {
  baseline: HistoricalBaselineResponse;
  onRefreshBaseline: () => void;
}

export const Tab1Ingestion: React.FC<Props> = ({ baseline, onRefreshBaseline }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [defaultSymbol, setDefaultSymbol] = useState<string>('BTCUSDT');
  const [customMapping, setCustomMapping] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncLimit, setSyncLimit] = useState<number>(300);
  const [selectedSyncSymbols, setSelectedSyncSymbols] = useState<string[]>(SUPPORTED_SYMBOLS);
  const [latestReport, setLatestReport] = useState<IngestionAuditReport | null>(
    baseline.audit_logs[0] || null
  );
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setStatusMessage(null);
    try {
      const report = await uploadDatasetFile(selectedFile, defaultSymbol, customMapping);
      setLatestReport(report);
      setStatusMessage(
        `Berhasil memproses ${report.source_name} — Skor Kualitas: ${report.quality_score_pct}% (${report.rows_after}/${report.rows_before} baris valid)`
      );
      onRefreshBaseline();
    } catch (err: any) {
      setStatusMessage(`Error: ${err.message || 'Gagal mengunggah file'}`);
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
        `Sinkronisasi Binance /api/v3/klines berhasil untuk ${res.synced_assets} aset (${syncLimit} candle 5m)!`
      );
      onRefreshBaseline();
    } finally {
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
    <div className="space-y-6">
      {/* Top Status Banner (Kontrak Integrasi Orang 1) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 flex items-center justify-between shadow-lg">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              Status Pipeline Orang 1
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-2xl font-bold text-white">{baseline.pipeline_status}</span>
            </div>
            <p className="text-xs text-emerald-400 mt-1">
              Dynamic Pipeline Controller Ready
            </p>
          </div>
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <ShieldCheck className="w-7 h-7" />
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 flex items-center justify-between shadow-lg">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              Target Cluster Apache NiFi &rarr; HDFS
            </p>
            <p className="text-sm font-mono font-semibold text-cyan-400 mt-1.5 break-all">
              {baseline.hdfs_cluster_path}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Partisi: symbol / year / month / timeframe
            </p>
          </div>
          <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <HardDrive className="w-7 h-7" />
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 flex items-center justify-between shadow-lg">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              Skor Kualitas Data Terakhir
            </p>
            <p className="text-2xl font-bold text-white mt-1">
              {activeAudit ? `${activeAudit.quality_score_pct}%` : '99.1%'}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {activeAudit
                ? `${activeAudit.rows_after.toLocaleString()} baris lolos sanity check`
                : 'Semua skema OHLCV tervalidasi'}
            </p>
          </div>
          <div className="p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Database className="w-7 h-7" />
          </div>
        </div>
      </div>

      {statusMessage && (
        <div className="bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 px-4 py-3 rounded-xl text-sm flex items-center gap-2.5">
          <CheckCircle2 className="w-5 h-5 text-cyan-400 shrink-0" />
          <span>{statusMessage}</span>
        </div>
      )}

      {/* Upload & Live Sync Forms */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Upload CSV / JSON */}
        <form
          onSubmit={handleUpload}
          className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-xl p-6 space-y-4 shadow-lg"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <UploadCloud className="w-5 h-5 text-cyan-400" />
              <h3 className="text-base font-semibold text-white">
                Batch Ingestion: Upload CSV / JSON & Mapping Skema
              </h3>
            </div>
            <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
              Auto Format Detector
            </span>
          </div>

          <label className="block border-2 border-dashed border-slate-700 hover:border-cyan-500/60 transition rounded-xl p-6 text-center cursor-pointer bg-slate-950/50">
            <input
              type="file"
              accept=".csv,.json"
              className="hidden"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
            />
            <FileSpreadsheet className="w-9 h-9 text-cyan-400 mx-auto mb-2" />
            {selectedFile ? (
              <div>
                <p className="text-sm font-semibold text-emerald-400">{selectedFile.name}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {(selectedFile.size / 1024).toFixed(1)} KB — Siap divalidasi oleh Dynamic Pipeline Controller
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm text-slate-200 font-medium">
                  Klik untuk memilih file <span className="text-cyan-400">.CSV</span> atau{' '}
                  <span className="text-cyan-400">.JSON</span>
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Mendukung pencocokan alias kolom otomatis (open_time &rarr; timestamp, vol &rarr; volume)
                </p>
              </div>
            )}
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Simbol Default (bila kolom coin_symbol kosong)
              </label>
              <select
                value={defaultSymbol}
                onChange={(e) => setDefaultSymbol(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
              >
                {SUPPORTED_SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Custom Column Mapping (JSON Opsional)
              </label>
              <input
                type="text"
                value={customMapping}
                onChange={(e) => setCustomMapping(e.target.value)}
                placeholder='{"open_time": "timestamp", "vol": "volume"}'
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!selectedFile || uploading}
            className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-40 text-white font-semibold text-sm transition flex items-center justify-center gap-2 shadow-md"
          >
            {uploading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Memvalidasi & Menormalisasi Data...
              </>
            ) : (
              <>
                <UploadCloud className="w-4 h-4" />
                Jalankan Dynamic Pipeline & Simpan ke Drop Zone
              </>
            )}
          </button>
        </form>

        {/* Speed Layer: Binance API Sync */}
        <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-xl p-6 flex flex-col justify-between shadow-lg">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <CloudDownload className="w-5 h-5 text-amber-400" />
                <h3 className="text-base font-semibold text-white">
                  Speed Layer: Binance API Live Sync
                </h3>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
                /api/v3/klines
              </span>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Menarik candle 5 menit terbaru langsung dari endpoint publik Binance, menjalankan
              deduplikasi timestamp, dan memperbarui partisi data bersih untuk inferensi real-time.
            </p>

            <div>
              <label className="block text-xs text-slate-400 mb-2">
                Pilih Pasangan Aset Kripto
              </label>
              <div className="flex flex-wrap gap-2">
                {SUPPORTED_SYMBOLS.map((sym) => {
                  const active = selectedSyncSymbols.includes(sym);
                  return (
                    <button
                      type="button"
                      key={sym}
                      onClick={() => toggleSyncSymbol(sym)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                        active
                          ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      {sym}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-400">Jumlah Candle 5m per Aset</span>
                <span className="text-amber-400 font-semibold">{syncLimit} candles</span>
              </div>
              <input
                type="range"
                min={100}
                max={1000}
                step={50}
                value={syncLimit}
                onChange={(e) => setSyncLimit(Number(e.target.value))}
                className="w-full accent-amber-500"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={handleLiveSync}
            disabled={syncing || selectedSyncSymbols.length === 0}
            className="mt-6 w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 disabled:opacity-40 text-slate-950 font-bold text-sm transition flex items-center justify-center gap-2 shadow-md"
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Menyinkronkan Candle Live...' : 'Sinkronkan Data Live Binance Sekarang'}
          </button>
        </div>
      </div>

      {/* Audit Detail Card from Orang 1 */}
      {activeAudit && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-cyan-400" />
                Inspeksi Audit Preprocessing & Validasi Skema (Output Orang 1)
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Alur Terpilih:{' '}
                <span className="font-mono text-cyan-300">{activeAudit.selected_pipeline}</span>
              </p>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              NiFi/HDFS: {activeAudit.nifi_hdfs_status}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
              <p className="text-[11px] text-slate-400">Format Input</p>
              <p className="text-lg font-bold text-white mt-0.5">{activeAudit.format_detected}</p>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
              <p className="text-[11px] text-slate-400">Baris Masuk</p>
              <p className="text-lg font-bold text-white mt-0.5">
                {activeAudit.rows_before.toLocaleString()}
              </p>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
              <p className="text-[11px] text-slate-400">Baris Bersih</p>
              <p className="text-lg font-bold text-emerald-400 mt-0.5">
                {activeAudit.rows_after.toLocaleString()}
              </p>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
              <p className="text-[11px] text-slate-400">Duplikat Dihapus</p>
              <p className="text-lg font-bold text-amber-400 mt-0.5">
                {activeAudit.duplicates_removed}
              </p>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
              <p className="text-[11px] text-slate-400">Imputasi (FFill / Vol)</p>
              <p className="text-lg font-bold text-cyan-400 mt-0.5">
                {activeAudit.imputed_ohlc_rows + activeAudit.imputed_volume_rows}
              </p>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3">
              <p className="text-[11px] text-slate-400">Baris Ditolak (Invalid)</p>
              <p className="text-lg font-bold text-rose-400 mt-0.5">{activeAudit.rejected_rows}</p>
            </div>
          </div>
        </div>
      )}

      {/* Tabel Ketersediaan Baseline Historis */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-lg">
        <h3 className="text-base font-semibold text-white mb-4">
          Ketersediaan Baseline Data Historis 5 Menit & Partisi HDFS
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-xs uppercase">
                <th className="py-3 px-4">Simbol Aset</th>
                <th className="py-3 px-4">Total Baris (5m)</th>
                <th className="py-3 px-4">Harga Penutupan Terakhir</th>
                <th className="py-3 px-4">Rata-Rata Volume (5m)</th>
                <th className="py-3 px-4">Path Partisi HDFS</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {baseline.assets.map((asset) => (
                <tr key={asset.symbol} className="hover:bg-slate-800/40 transition">
                  <td className="py-3 px-4 font-bold text-white">{asset.symbol}</td>
                  <td className="py-3 px-4 text-slate-300">{asset.rows_5m.toLocaleString()}</td>
                  <td className="py-3 px-4 text-emerald-400 font-mono">
                    ${asset.latest_close.toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-slate-300 font-mono">
                    {asset.avg_volume_5m.toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-xs font-mono text-cyan-400">
                    {asset.hdfs_partition}
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      {asset.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
