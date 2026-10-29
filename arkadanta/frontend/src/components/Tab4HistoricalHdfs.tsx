import React, { useState } from 'react';
import { Database, Play, Server, Sparkles } from 'lucide-react';
import { HistoricalHdfsRunResponse, Timeframe } from '../types/arkadanta';
import { runHistoricalHdfsPipeline, SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES } from '../services/api';

const DEFAULT_FEATURES = [
  'max_volatility',
  'spike_ratio',
  'rsi_14',
  'volume_zscore',
  'bb_width',
  'hl_range',
];

function dateInput(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export const Tab4HistoricalHdfs: React.FC = () => {
  const today = new Date();
  const yearAgo = new Date(today);
  yearAgo.setUTCDate(yearAgo.getUTCDate() - 364);
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState<Timeframe>('1h');
  const [source, setSource] = useState<'raw' | 'clean'>('clean');
  const [startDate, setStartDate] = useState(dateInput(yearAgo));
  const [endDate, setEndDate] = useState(dateInput(today));
  const [result, setResult] = useState<HistoricalHdfsRunResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const data = await runHistoricalHdfsPipeline({
        symbol,
        timeframe,
        start_date: startDate,
        end_date: endDate,
        features: DEFAULT_FEATURES,
        gmm_components: 3,
        train_ratio: 0.8,
        gb_max_iter: 200,
        gb_max_depth: 10,
        source,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pipeline HDFS gagal');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5 text-white">
      <section className="rounded-lg border border-white/10 bg-[#27293d] p-5">
        <div className="mb-4 flex items-center gap-3">
          <div className="rounded-md bg-cyan-400/15 p-2 text-cyan-300"><Database className="h-5 w-5" /></div>
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide">Historical HDFS Batch</h2>
            <p className="text-xs text-white/60">Baca CSV yang dikirim NiFi ke HDFS, proses fitur dengan PySpark, lalu latih GMM + HistGradientBoosting yang dipakai prediksi live.</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <label className="text-xs text-white/70">Aset
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="mt-1 w-full rounded border border-white/15 bg-[#1e1e2f] p-2 text-sm text-white">
              {SUPPORTED_SYMBOLS.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label className="text-xs text-white/70">Timeframe hasil
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)} className="mt-1 w-full rounded border border-white/15 bg-[#1e1e2f] p-2 text-sm text-white">
              {SUPPORTED_TIMEFRAMES.map((tf) => <option key={tf}>{tf}</option>)}
            </select>
          </label>
          <label className="text-xs text-white/70">Sumber HDFS
            <select value={source} onChange={(e) => setSource(e.target.value as 'raw' | 'clean')} className="mt-1 w-full rounded border border-white/15 bg-[#1e1e2f] p-2 text-sm text-white">
              <option value="raw">Raw — dump Binance per partisi /arkadanta/raw/symbol=ASET</option>
              <option value="clean">Clean — data aplikasi via NiFi outbox</option>
            </select>
          </label>
          <label className="text-xs text-white/70">Dari tanggal
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1 w-full rounded border border-white/15 bg-[#1e1e2f] p-2 text-sm text-white" />
          </label>
          <label className="text-xs text-white/70">Sampai tanggal
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="mt-1 w-full rounded border border-white/15 bg-[#1e1e2f] p-2 text-sm text-white" />
          </label>
          <div className="flex items-end">
            <button type="button" disabled={busy} onClick={run} className="flex w-full items-center justify-center gap-2 rounded bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:cursor-wait disabled:opacity-60">
              {busy ? <><Sparkles className="h-4 w-4 animate-pulse" /> Spark sedang memproses…</> : <><Play className="h-4 w-4" /> Baca HDFS &amp; latih model</>}
            </button>
          </div>
        </div>
        <p className="mt-3 text-[11px] text-white/50">Mendukung CSV Binance Kline 12 kolom tanpa header maupun CSV ber-header timestamp, open, high, low, close, volume. Rentang maksimum 365 hari.</p>
        {error && <div className="mt-4 rounded border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      </section>

      {result && <>
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Baris OHLCV valid', result.raw_valid_rows.toLocaleString()],
            ['Baris timeframe', result.feature_rows.toLocaleString()],
            ['Accuracy klasifikasi', `${(result.classification_metrics.accuracy * 100).toFixed(1)}%`],
            ['RMSE volatilitas', result.regression_metrics.rmse.toFixed(6)],
          ].map(([label, value]) => <div key={label} className="rounded-lg border border-white/10 bg-[#27293d] p-4"><p className="text-[10px] uppercase tracking-wide text-white/50">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>)}
        </section>
        <section className="rounded-lg border border-white/10 bg-[#27293d] p-5 text-sm">
          <h3 className="mb-3 flex items-center gap-2 font-semibold"><Server className="h-4 w-4 text-cyan-300" /> Bukti eksekusi</h3>
          <dl className="grid gap-3 md:grid-cols-2">
            <div><dt className="text-xs text-white/50">Sumber input / penyimpanan output</dt><dd>{result.data_source} / {result.output_storage}</dd></div>
            <div><dt className="text-xs text-white/50">Format output</dt><dd>{result.output_format}</dd></div>
            <div><dt className="text-xs text-white/50">Aset / timeframe</dt><dd>{result.symbol} / {result.timeframe}</dd></div>
            <div className="md:col-span-2"><dt className="text-xs text-white/50">Input HDFS</dt><dd className="break-all font-mono text-xs">{result.input_path}</dd></div>
            <div><dt className="text-xs text-white/50">Timestamp terbaca</dt><dd>{result.data_start} — {result.data_end}</dd></div>
            <div><dt className="text-xs text-white/50">F1 / MAE</dt><dd>{result.classification_metrics.f1_macro.toFixed(4)} / {result.regression_metrics.mae.toFixed(6)}</dd></div>
            <div className="md:col-span-2"><dt className="text-xs text-white/50">Data fitur tersimpan</dt><dd className="break-all font-mono text-xs">{result.curated_path}</dd></div>
            <div className="md:col-span-2"><dt className="text-xs text-white/50">Bundle model GMM/HGB (dipakai /api/ml/predict)</dt><dd className="break-all font-mono text-xs">{result.model_path}</dd></div>
            <div><dt className="text-xs text-white/50">Silhouette GMM / BIC</dt><dd>{result.gmm_metrics.silhouette_score?.toFixed(4) ?? '-'} / {result.gmm_metrics.bic.toFixed(1)}</dd></div>
            <div><dt className="text-xs text-white/50">Run ID</dt><dd className="font-mono text-xs">{result.run_id}</dd></div>
          </dl>
        </section>
      </>}
    </div>
  );
};
