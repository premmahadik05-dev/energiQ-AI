/**
 * Response shapes of the EnergiQ API. They follow what backend/app/schemas.py and the route handlers
 * really return (verified against a running backend), including endpoints that return plain dicts.
 * Timestamps are naive strings in the dataset's own time convention and must be shown as given.
 */
export type Role = 'admin' | 'analyst' | 'viewer';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

// ----------------------------------------------------------------------------- datasets
export interface IngestConfig {
  value_column: string;
  unit: string;
  timestamp_column: string | null;
  date_column: string | null;
  time_column: string | null;
  delimiter: string | null;
  dayfirst: boolean;
  timestamp_format: string | null;
  extra_columns: Record<string, string>;
  min_valid_fraction: number;
  timezone_convention: string;
}

export type DatasetStatus = 'processing' | 'ready' | 'failed' | string;

export interface Dataset {
  id: number;
  name: string;
  original_filename: string;
  status: DatasetStatus;
  error: string | null;
  quality_score: number | null;
  hours: number;
  valid_hours: number;
  start_ts: string | null;
  end_ts: string | null;
  created_at: string;
  config: Partial<IngestConfig>;
}

export interface QualityBlock {
  score: number;
  grade: string;
  completeness: number;
  invalid_fraction: number;
  regularity: number;
}

export interface AppendRecord {
  at: string;
  rows_read: number;
  range: [string, string];
  quality_score: number;
  warnings: string[];
}

export interface DatasetReport {
  rows_read?: number;
  skipped_malformed_lines?: number;
  unparseable_timestamps?: number;
  missing_value_tokens?: number;
  non_numeric_values?: number;
  negative_values?: number;
  duplicate_timestamps?: number;
  out_of_order_steps?: number;
  first_timestamp?: string;
  last_timestamp?: string;
  span_days?: number;
  sampling_interval_seconds?: number;
  irregular_steps?: number;
  gaps_longer_than_1_5_intervals?: number;
  largest_gap_minutes?: number;
  expected_readings?: number;
  valid_readings?: number;
  hours_in_span?: number;
  valid_hours?: number;
  min_valid_fraction?: number;
  unit_declared?: string;
  timezone_convention?: string;
  quality?: QualityBlock;
  suitable_for_forecasting?: boolean;
  unsuitable_reasons?: string[];
  warnings?: string[];
  value_summary_kw?: { min: number; mean: number; max: number };
  appends?: AppendRecord[];
}

export interface DatasetDetail extends Dataset {
  report: DatasetReport;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export const TERMINAL_JOB_STATUSES: readonly JobStatus[] = ['succeeded', 'failed'];

export interface Job {
  id: number;
  kind: string;
  status: JobStatus;
  progress: number;
  message: string;
  dataset_id: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface UploadAccepted {
  dataset: Dataset;
  job: Job;
}

export interface ReadingPoint {
  ts: string;
  kw: number | null;
}
export interface DailyReadingPoint {
  ts: string;
  mean_kw: number | null;
  kwh: number | null;
  valid_hours: number;
}
export interface ReadingsResponse<P = ReadingPoint> {
  dataset_id: number;
  resolution: 'hourly' | 'daily';
  points: P[];
}

export interface DatasetProfile {
  hourly_profile: { hour: number; mean_kw: number | null }[];
  weekday_vs_weekend: { hour: number; weekday_kw: number | null; weekend_kw: number | null }[];
  monthly_mean_kw: { month: string; mean_kw: number | null }[];
  valid_hours?: number;
  min_hours_needed_for_forecasting?: number;
}

// ----------------------------------------------------------------------------- models / forecasts
export interface MetricSet {
  n: number;
  mae: number;
  rmse: number;
  mape_pct: number;
  mape_excluded: number;
  smape_pct: number;
  r2: number;
}

export interface HorizonEvaluation {
  metrics: Record<string, MetricSet>;
  rows_scored: number;
  best_baseline: string;
  mae_improvement_vs_best_baseline_pct: number;
  residual_q10_kw: number;
  residual_q90_kw: number;
}

export interface ModelEvaluation {
  protocol: string;
  holdout_start: string;
  holdout_end: string;
  horizons: Record<string, HorizonEvaluation>;
  xgboost_params?: Record<string, unknown>;
  seed?: number;
  caveat: string | null;
}

export interface ImportanceRow {
  feature: string;
  label: string;
  group: string;
  mean_abs_shap_kw: number;
  share_pct: number;
}
export interface HorizonExplanation {
  top_features: ImportanceRow[];
  group_share_pct: Record<string, number>;
}

export interface ModelVersion {
  id: string;
  dataset_id: number;
  family: string;
  is_active: boolean;
  train_rows: number;
  train_end: string | null;
  created_at: string;
  evaluation: Partial<ModelEvaluation>;
  explanation: Record<string, HorizonExplanation>;
}

export interface ForecastPoint {
  horizon: number;
  ts: string;
  kw: number;
  lower_kw: number;
  upper_kw: number;
}

export interface Forecast {
  id: number;
  dataset_id: number;
  model_id: string;
  origin: string;
  points: ForecastPoint[];
  origin_value_missing: boolean;
  created_at: string;
}

export interface MonitoringDrift {
  status: string;
  new_data_since_training: boolean;
  psi?: number;
  ks_statistic?: number;
  ks_pvalue?: number;
  reference_hours?: number;
  recent_hours?: number;
  recent_days?: number;
  mean_ratio_recent_to_reference?: number | null;
}

export interface MonitoringRealised {
  forecasts_checked: number;
  points_scored: number;
  realized_mae_kw: number | null;
  holdout_mae_kw_mean_over_1_6_24h: number | null;
  ratio_realized_to_holdout: number | null;
  status: string;
  note: string;
}

export interface Monitoring {
  model_id: string;
  trained_through: string;
  data_through: string | null;
  drift: MonitoringDrift;
  realized_performance: MonitoringRealised;
  retrain_recommended: boolean;
}

// ----------------------------------------------------------------------------- explainability
export interface GlobalExplanation {
  model_id: string;
  basis: string;
  horizons: Record<string, HorizonExplanation>;
}

export interface LocalDriver {
  feature: string;
  label: string;
  value: number | null;
  contribution_kw: number;
  direction: 'raises' | 'lowers';
}

export interface LocalExplanation {
  origin: string;
  target_time: string;
  prediction_kw: number;
  base_value_kw: number;
  drivers: LocalDriver[];
  grouped_kw: Record<string, number>;
  additivity_error_kw: number;
  narrative: string;
}

// ----------------------------------------------------------------------------- anomalies
export type Severity = 'low' | 'medium' | 'high';

export interface AnomalyEvent {
  id: number;
  run_id: number;
  dataset_id: number;
  start_ts: string;
  end_ts: string;
  hours: number;
  types: string[];
  severity: Severity;
  severity_level: number;
  peak_ts: string;
  peak_value_kw: number | null;
  expected_kw: number | null;
  peak_excess_ratio: number | null;
  explanation: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

export interface AnomalyList {
  total: number;
  items: AnomalyEvent[];
}

export interface AnomalyRunSummary {
  hours_total: number;
  hours_valid: number;
  hours_flagged: number;
  flagged_pct_of_valid: number;
  hours_with_baseline: number;
  hours_flagged_by: Record<string, number>;
  events: number;
  events_by_severity: Record<string, number>;
  events_by_type: Record<string, number>;
  isolation_forest?: { fit_end: string; fit_rows: number; score_threshold: number; note: string };
}

export type AnomalySummary =
  | { run: null }
  | {
      run: { id: number; created_at: string; sensitivity: string; config: Record<string, unknown> };
      summary: AnomalyRunSummary;
      by_severity: Partial<Record<Severity, number>>;
      unacknowledged: number;
      note: string;
    };

// ----------------------------------------------------------------------------- optimisation
export interface Tariff {
  id: number | string;
  name: string;
  currency: string;
  weekday_rates: number[];
  weekend_rates: number[];
  daily_fixed_charge: number;
  is_demo: boolean;
  note: string;
}

export interface CostBlock {
  valid_hours: number;
  energy_kwh: number;
  energy_cost: number;
  fixed_cost: number;
  total_cost: number;
  currency: string;
  is_demo_tariff: boolean;
  avg_cost_per_kwh?: number | null;
}

export interface CostResponse {
  total: CostBlock;
  monthly: { month: string; valid_hours: number; energy_kwh: number; total_cost: number }[];
  tariff: Omit<Tariff, 'id'>;
  range: [string, string];
}

export interface Recommendation {
  id: string;
  category: string;
  priority: 'high' | 'medium' | 'low';
  title: string;
  explanation: string;
  evidence: Record<string, unknown>;
  scenario: (Record<string, unknown> & { assumption: string; currency: string }) | null;
  caveats: string[];
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
  window: { start: string; end: string; valid_hours: number; days_covered: number } | null;
  baseline_cost?: Pick<CostBlock, 'energy_kwh' | 'energy_cost' | 'total_cost' | 'currency' | 'is_demo_tariff'>;
  tariff: Omit<Tariff, 'id'>;
  message?: string;
}

export interface ScheduleResponse {
  best_start: string;
  best_end: string;
  cost: number;
  cost_if_started_first_hour: number;
  cost_at_worst_start: number;
  worst_start: string;
  saving_vs_first_hour: number;
  currency: string;
  is_demo_tariff: boolean;
  energy_kwh: number;
}

// ----------------------------------------------------------------------------- notifications / admin
export interface Notification {
  id: number;
  kind: string;
  message: string;
  link: string;
  is_read: boolean;
  created_at: string;
}

export interface AuditEvent {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: string;
  ip: string;
  detail: Record<string, unknown>;
  ts: string;
}

export interface SystemInfo {
  counts: Record<string, number>;
  jobs_by_status: Record<string, number>;
  http: {
    uptime_seconds: number;
    requests_total: number;
    responses_5xx: number;
    responses_4xx: number;
    latency_seconds: { p50: number | null; p95: number | null; max: number | null; window: number };
  };
  environment: string;
}

// ----------------------------------------------------------------------------- benchmark (offline UCI results)
export interface BenchmarkBootstrap {
  mae_diff: number;
  ci95_low: number;
  ci95_high: number;
  days: number;
}

export interface BenchmarkHorizon {
  n_rows_scored?: number;
  counts?: Record<string, number>;
  metrics?: Record<string, Partial<MetricSet>>;
  mean_actual_kw?: number;
  hindsight_best_baseline?: string;
  bootstrap_mae_diff_vs_best_cv_baseline?: Record<string, BenchmarkBootstrap>;
  pairwise_mae_diff?: Record<string, BenchmarkBootstrap>;
  chosen_params?: Record<string, Record<string, unknown>>;
  cv_mean_fold_mae?: Record<string, number>;
}

export interface BenchmarkEvaluation {
  protocol?: {
    target?: string;
    cv_folds?: { name: string; test_start: string; test_end: string }[];
    test_period?: [string, string];
    seed?: number;
    data_hash?: string;
  };
  best_cv_baseline?: Record<string, string>;
  horizons?: Record<string, BenchmarkHorizon>;
  lstm_seed_robustness?: Record<string, Record<string, number>>;
  lstm_headline_seed?: number;
}

export interface BenchmarkAnomaly {
  config?: Record<string, unknown>;
  summary?: AnomalyRunSummary;
  top_events?: {
    start: string;
    end: string;
    hours: number;
    types: string[];
    severity: string;
    peak_value_kw: number | null;
    expected_kw: number | null;
    peak_excess_ratio: number | null;
  }[];
}

export interface BenchmarkInjection {
  synthetic?: boolean;
  n_injected_per_kind?: number;
  clean_flag_rate_pct?: number;
  kinds?: Record<string, { injected: number; recall_on_injected: number; recall_when_expected_ge_1kw: number | null; flag_rate_untouched_pct: number }>;
}

export interface Benchmark {
  dataset: string;
  evaluation: BenchmarkEvaluation | null;
  anomaly: BenchmarkAnomaly | null;
  anomaly_injection_check: BenchmarkInjection | null;
  shap: Record<string, { model_id?: string; rows_explained?: number; max_additivity_error_kw?: number; top_features?: ImportanceRow[] }> | null;
  figures: Record<string, string[]>;
}
