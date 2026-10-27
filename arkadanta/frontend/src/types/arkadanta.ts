export type RiskRegime = 'SAFE' | 'WARNING' | 'DANGER';
export type Timeframe = '5m' | '15m' | '1h' | '4h' | '1d' | '1w';
export type AnomalyMethod = 'adaptive_quantile' | 'rolling_zscore' | 'iqr' | 'gmm';

export interface AssetBaseline {
  symbol: string;
  rows_5m: number;
  start_timestamp: string;
  end_timestamp: string;
  latest_close: number;
  avg_volume_5m: number;
  hdfs_partition: string;
  status: string;
}

export interface IngestionAuditReport {
  run_id: string;
  timestamp: string;
  source_name: string;
  format_detected: 'CSV' | 'JSON' | 'BINANCE_API';
  selected_pipeline: string;
  column_mapping: Record<string, string>;
  symbols_detected: string[];
  rows_before: number;
  rows_after: number;
  duplicates_removed: number;
  imputed_ohlc_rows: number;
  imputed_volume_rows: number;
  rejected_rows: number;
  error_reasons: {
    high_less_than_low: number;
    non_positive_price: number;
    negative_volume: number;
    invalid_timestamp: number;
  };
  drop_zone_path: string;
  hdfs_target_path: string;
  nifi_hdfs_status: 'SYNCED' | 'QUEUED_DROP_ZONE' | 'LOCAL_FALLBACK';
  quality_score_pct: number;
}

export interface HistoricalBaselineResponse {
  pipeline_status: string;
  hdfs_cluster_path: string;
  assets: AssetBaseline[];
  audit_logs: IngestionAuditReport[];
}

export interface CronStatus {
  enabled: boolean;
  interval_minutes: number;
  symbols: string[];
  limit: number;
  last_run: string | null;
  next_run: string | null;
  last_status: string;
  last_synced_count: number;
  total_runs: number;
}

export interface CandlePoint {
  timestamp: string;
  coin_symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  max_volatility: number;
  avg_volatility: number;
  rolling_volatility: number;
  spike_ratio: number;
  log_return: number;
  hl_range: number;
  co_change: number;
  sma_20: number;
  ema_20: number;
  rsi_14: number;
  bb_upper: number;
  bb_lower: number;
  bb_width: number;
  upper_wick_ratio: number;
  lower_wick_ratio: number;
  body_ratio: number;
  buy_sell_pressure_ratio: number | null;
  volume_zscore: number;
  is_anomaly: boolean;
  anomaly_score: number;
  anomaly_reason: string;
}

export interface HistoricalFactorAttribution {
  feature: string;
  dominant_lag: string;
  lag_periods: number;
  correlation_to_today: number;
  abs_impact_score: number;
  lag_profile: Record<string, number>;
  bi_insight: string;
}

export interface AnalyticsRunResponse {
  symbol: string;
  timeframe: Timeframe;
  execution_engine?: string;
  total_candles: number;
  selected_features: string[];
  anomaly_summary: {
    method: AnomalyMethod;
    total_observations: number;
    total_anomalies: number;
    anomaly_rate_pct: number;
    threshold_info: {
      method: string;
      per_symbol_threshold: Record<string, number | null>;
      causal: boolean;
    };
  };
  historical_factor_attribution?: HistoricalFactorAttribution[];
  anomalies_log: CandlePoint[];
  series: CandlePoint[];
}

export interface CorrelationResponse {
  symbols: string[];
  base_symbol: string;
  target_symbol: string;
  pearson_matrix: Record<string, Record<string, number>>;
  rolling_correlation: { timestamp: string; rolling_corr: number }[];
  lag_correlation: { lag: number; correlation: number; interpretation: string }[];
  market_wide_risk_score: number;
  market_wide_regime: RiskRegime;
  market_risk_timeline: { timestamp: string; risk_score: number }[];
}

export interface CentroidRecord {
  cluster_id: number;
  risk_rank: number;
  assigned_risk_label: RiskRegime;
  composite_risk_score: number;
  train_sample_count: number;
  [key: string]: string | number;
}

export interface ModelMetricsResponse {
  model_version: string;
  feature_importance_method: string;
  trained_at: string;
  execution_engine?: string;
  symbol: string;
  timeframe: Timeframe;
  target_horizon: number;
  features: string[];
  gmm_components: number;
  train_ratio: number;
  gb_max_iter: number;
  gb_max_depth: number;
  gb_learning_rate: number;
  temporal_split: {
    total_samples: number;
    train_samples: number;
    test_samples: number;
    train_start: string;
    train_end: string;
    test_start: string;
    test_end: string;
  };
  gmm_metrics: {
    silhouette_score: number | null;
    bic: number;
    aic: number;
    converged: boolean;
    cluster_to_label: Record<string, RiskRegime>;
    centroids: CentroidRecord[];
    regime_distribution: Record<RiskRegime, number>;
  };
  classification_metrics: {
    accuracy: number;
    precision_macro: number;
    recall_macro: number;
    f1_macro: number;
    per_class: Record<
      RiskRegime,
      { precision: number; recall: number; f1_score: number; support: number }
    >;
    labels: RiskRegime[];
    confusion_matrix: number[][];
  };
  regression_metrics: {
    mae: number;
    rmse: number;
  };
  feature_importances: { feature: string; importance: number }[];
}

export interface HistoricalHdfsRunRequest {
  symbol: string;
  timeframe: Timeframe;
  start_date?: string;
  end_date?: string;
  features: string[];
  gmm_components: number;
  train_ratio: number;
  gb_max_iter: number;
  gb_max_depth: number;
  source: 'raw' | 'clean';
}

export interface HistoricalHdfsRunResponse extends ModelMetricsResponse {
  run_id: string;
  data_source: string;
  output_storage: string;
  input_path: string;
  curated_path: string;
  model_path: string;
  metrics_path: string;
  output_format: string;
  model_persisted: boolean;
  symbol: string;
  timeframe: Timeframe;
  raw_valid_rows: number;
  feature_rows: number;
  data_start: string;
  data_end: string;
  requested_start: string;
  requested_end: string;
}

export interface PredictionResponse {
  timestamp: string;
  candle_timestamp: string;
  symbol: string;
  timeframe: Timeframe;
  target_horizon: number;
  current_price: number;
  current_component_id: number;
  current_regime_t: RiskRegime;
  predicted_regime_t_plus_1: RiskRegime;
  probabilities_t_plus_1: Record<RiskRegime, number>;
  predicted_volatility_pct: number;
  estimated_volatility_nominal: number;
  resistance_level: number;
  stop_loss_level: number;
  feature_snapshot: Record<string, number>;
  disclaimer: string;
}

export interface DynamicConfigPayload {
  symbol: string;
  symbols?: string[];
  timeframe: Timeframe;
  features: string[];
  ma_period: number;
  rsi_period: number;
  rolling_window: number;
  anomaly_method: AnomalyMethod;
  anomaly_quantile: number;
  anomaly_z_threshold: number;
  anomaly_iqr_multiplier: number;
  gmm_components: number;
  correlation_window: number;
  max_lag: number;
  train_ratio: number;
  gb_max_iter: number;
  gb_max_depth: number;
  gb_learning_rate: number;
  target_horizon: number;
  use_spark?: boolean;
}
