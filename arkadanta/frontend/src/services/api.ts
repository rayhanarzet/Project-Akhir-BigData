import {
  AnalyticsRunResponse, CorrelationResponse, CronStatus, DynamicConfigPayload,
  HistoricalBaselineResponse, HistoricalHdfsRunRequest, HistoricalHdfsRunResponse,
  IngestionAuditReport, ModelMetricsResponse,
  PredictionResponse, Timeframe,
} from '../types/arkadanta';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function request<T>(path: string, options: RequestInit = {}, timeoutMs = 15000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, signal: controller.signal });
    } catch {
      throw new Error('Backend tidak dapat dihubungi atau waktu permintaan habis. Periksa FastAPI dan koneksi Anda.');
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(typeof body?.detail === 'string' ? body.detail : `Permintaan gagal (HTTP ${response.status}). Periksa data dan backend.`);
    }
    try {
      return await response.json();
    } catch {
      throw new Error('Respons backend tidak valid. Periksa alamat API dan layanan FastAPI.');
    }
  } finally {
    clearTimeout(timer);
  }
}

function post(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export const SUPPORTED_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT'];
export const SUPPORTED_TIMEFRAMES: Timeframe[] = ['5m', '15m', '1h', '4h', '1d', '1w'];
export const AVAILABLE_FEATURES = [
  'max_volatility', 'avg_volatility', 'rolling_volatility', 'spike_ratio',
  'log_return', 'hl_range', 'co_change', 'sma_20', 'ema_20', 'rsi_14',
  'bb_width', 'upper_wick_ratio', 'lower_wick_ratio', 'body_ratio',
  'buy_sell_pressure_ratio', 'volume_zscore',
];

export async function fetchHistoricalBaseline(): Promise<{ data: HistoricalBaselineResponse; isLiveBackend: boolean }> {
  const data = await request<HistoricalBaselineResponse>('/api/historical-baseline');
  return { data, isLiveBackend: true };
}

export function uploadDatasetFile(file: File, defaultSymbol: string, customMappingJson: string): Promise<IngestionAuditReport> {
  const form = new FormData();
  form.append('file', file);
  form.append('default_symbol', defaultSymbol);
  if (customMappingJson.trim()) form.append('column_mapping_json', customMappingJson.trim());
  return request('/api/ingestion/upload', { method: 'POST', body: form });
}

export function triggerBinanceLiveSync(symbols: string[], limit: number): Promise<{ synced_assets: number; reports: IngestionAuditReport[] }> {
  return request('/api/ingestion/live-sync', post({ symbols, interval: '5m', limit }), Math.max(15000, symbols.length * 10000));
}

export function fetchCronStatus(): Promise<CronStatus> {
  return request('/api/ingestion/cron-status');
}

export function updateCronConfig(enabled: boolean, intervalMinutes: number, symbols = SUPPORTED_SYMBOLS, limit = 60): Promise<CronStatus> {
  return request('/api/ingestion/cron-config', post({ enabled, interval_minutes: intervalMinutes, symbols, limit }));
}

export function runDynamicAnalyticsApi(cfg: DynamicConfigPayload): Promise<AnalyticsRunResponse> {
  return request('/api/analytics/run', post(cfg), 120000);
}

export function fetchCrossAssetCorrelation(timeframe: Timeframe, baseSymbol: string, targetSymbol: string, rollingWindow: number): Promise<CorrelationResponse> {
  const params = new URLSearchParams({ timeframe, base_symbol: baseSymbol, target_symbol: targetSymbol, rolling_window: String(rollingWindow), max_lag: '6' });
  return request(`/api/analytics/correlation?${params}`, {}, 60000);
}

export function trainAndEvaluateModels(cfg: DynamicConfigPayload): Promise<ModelMetricsResponse> {
  return request('/api/ml/train', post(cfg), 120000);
}

export function fetchLatestModelMetrics(cfg: DynamicConfigPayload): Promise<ModelMetricsResponse> {
  const params = new URLSearchParams({ symbol: cfg.symbol, timeframe: cfg.timeframe });
  return request(`/api/models/metrics?${params}`, {}, 120000);
}

export function predictNextPeriodApi(symbol: string, timeframe: Timeframe, targetHorizon = 1): Promise<PredictionResponse> {
  return request('/api/ml/predict', post({ symbol, timeframe, target_horizon: targetHorizon }), 120000);
}

export interface LiveQuote {
  symbol: string;
  event_time: number;
  received_at: string;
  candle_time: number;
  closed: boolean;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type MarketEvent =
  | ({ type: 'quote'; snapshot: boolean } & LiveQuote)
  | { type: 'status'; connected: boolean; message: string }
  | { type: 'storage_error'; message: string }
  | { type: 'candle_closed'; symbol: string; candle_time: number };

export function subscribeMarket(onEvent: (event: MarketEvent) => void, onError: (message: string) => void): () => void {
  const source = new EventSource(`${API_BASE}/api/market/stream`);
  source.onmessage = (message) => {
    try {
      const event: MarketEvent = JSON.parse(message.data);
      if (event.type === 'quote' && (!SUPPORTED_SYMBOLS.includes(event.symbol) || !Number.isFinite(event.close))) {
        throw new Error('Invalid quote');
      }
      onEvent(event);
    } catch {
      onError('Pesan stream tidak valid.');
    }
  };
  source.onerror = () => onError('Koneksi stream backend terputus. Mencoba menghubungkan kembali...');
  return () => {
    source.onmessage = null;
    source.onerror = null;
    source.close();
  };
}

export function runHistoricalHdfsPipeline(payload: HistoricalHdfsRunRequest): Promise<HistoricalHdfsRunResponse> {
  return request('/api/historical-hdfs/run', post(payload), 15 * 60 * 1000);
}
