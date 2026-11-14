/** Response shapes of the society-level API (/api/v1/societies/...). Units: energy kWh, demand kW (hourly mean). */

export interface SocietySummary {
  id: number;
  key: string;
  name: string;
  description: string;
  timezone: string;
  start: string;
  end: string;
  hours: number;
  valid_hours: number;
  buildings: number;
  floor_area_sqm: number | null;
  has_model: boolean;
  forecast_ready: boolean | null;
  source_name: string;
  license: string;
  status: string;
}

export interface SocietyDetail extends SocietySummary {
  source_url: string;
  lat: number | null;
  lng: number | null;
  model_id: string | null;
  trained_through: string | null;
  data_card: {
    source?: Record<string, unknown>;
    downloaded_at?: string;
    rule?: Record<string, unknown>;
    cleaning?: Record<string, unknown>;
    cleaning_report?: Record<string, unknown>;
    excluded_meters?: Record<string, unknown>[];
    excluded_count?: number;
    cleaning_totals?: Record<string, number>;
    upload?: Record<string, unknown>;
    [k: string]: unknown;
  };
}

export interface WindowStats {
  hours: number;
  energy_kwh: number | null;
  avg_kw: number | null;
  peak_kw: number | null;
  valid_hours: number;
  change_vs_previous_pct: number | null;
}

export interface CostBlock {
  valid_hours: number;
  energy_kwh: number;
  energy_cost: number;
  fixed_cost: number;
  total_cost: number;
  currency: string;
  is_demo_tariff: boolean;
  avg_cost_per_kwh: number | null;
}

export interface ForecastSummary {
  origin: string;
  trained_through: string;
  next_24h_energy_kwh?: number;
  next_24h_energy_range_kwh?: [number, number];
  peak_kw?: number;
  peak_range_kw?: [number, number];
  peak_time?: string;
  range_note?: string;
  cost?: CostBlock | null;
  note?: string;
  error?: string;
  [k: string]: unknown;
}

export interface AnomalyCounts {
  society: Record<string, number>;
  building: Record<string, number>;
  open: number;
  total: number;
}

export interface SocietyOverview {
  society: SocietySummary;
  as_of: string;
  as_of_note: string;
  latest: { ts: string; demand_kw: number; energy_kwh: number };
  windows: { last_24h: WindowStats; last_7d: WindowStats; last_30d: WindowStats };
  totals: { energy_kwh: number; avg_kw: number; peak_kw: number; peak_ts: string; load_factor: number; valid_hours: number; hours: number };
  tariff: { name: string; currency: string; is_demo: boolean };
  cost_last_24h: CostBlock | null;
  cost_last_30d: CostBlock | null;
  forecast: ForecastSummary | null;
  anomalies: AnomalyCounts;
}

export type Resolution = 'hourly' | 'daily' | 'weekly' | 'monthly';

export interface ConsumptionPoint {
  ts: string;
  energy_kwh: number | null;
  avg_kw: number | null;
  peak_kw: number | null;
  valid_hours: number;
  expected_hours: number;
  complete: boolean;
}

export interface ConsumptionResponse {
  society_id: number;
  resolution: Resolution;
  start: string;
  end: string;
  points: ConsumptionPoint[];
}

export interface BuildingRow {
  id: number;
  code: string;
  source_id?: string;
  sub_use: string;
  floor_area_sqm: number | null;
  year_built: number | null;
  floors: number | null;
  valid_share_overall: number | null;
  energy_kwh: number | null;
  share_pct: number | null;
  kwh_per_sqm: number | null;
  avg_kw: number | null;
  peak_kw: number | null;
  valid_hours: number;
  expected_hours: number;
}

export interface BuildingsResponse {
  society_id: number;
  start: string;
  end: string;
  buildings: BuildingRow[];
  note: string;
}

export interface BuildingsMonthly {
  months: string[];
  buildings: { code: string; energy_kwh: (number | null)[]; valid_hours: number[] }[];
}

export interface FacilityCategory {
  category: string;
  label: string;
  measured: boolean;
  meters: unknown[];
  status?: string;
  series?: ConsumptionPoint[];
}

export interface FacilitiesResponse {
  available: boolean;
  categories: FacilityCategory[];
  message?: string;
}

export interface PeakProfileRow {
  hour: number;
  mean_kw: number;
  p05_kw: number;
  p95_kw: number;
  weekday_mean_kw: number;
  weekend_mean_kw: number;
}

export interface PeakDay {
  day: string;
  peak_kw: number;
  hour: number;
}

export interface PeakEvalSide {
  peak_mae_kw: number;
  peak_mape_pct: number;
  peak_bias_kw: number;
  peak_hour_exact_pct: number;
  peak_hour_within_1h_pct: number;
  peak_hour_within_2h_pct: number;
}

export interface PeakEvaluation {
  days: number;
  model?: PeakEvalSide;
  baseline?: PeakEvalSide;
  /** method behind `model` / `baseline` (the saved metrics replaced them in older files; the API fills them in) */
  model_name?: string | null;
  baseline_name?: string | null;
  horizon_h?: number;
  basis?: string;
  mean_actual_peak_kw?: number;
  mae_improvement_vs_baseline_pct?: number;
  note?: string;
}

export interface PeaksResponse {
  profile: PeakProfileRow[];
  peak_hour_histogram: { hour: number; days: number }[];
  top_hours: { ts: string; kw: number }[];
  overall: { mean_kw: number; peak_kw: number; load_factor: number; p95_kw: number; p99_kw: number; peak_to_average: number; days: number };
  monthly: { month: string; mean_kw: number; peak_kw: number; load_factor: number }[];
  note: string;
  forecast_evaluation: PeakEvaluation | null;
  /** demand sorted from the highest hour to the lowest: kW exceeded for `percent_of_time` % of the valid hours */
  load_duration: { percent_of_time: number; kw: number }[];
  /** how many valid hours fall in each demand band */
  distribution: { from_kw: number; to_kw: number; hours: number }[];
}

export interface ErrorAnalysis {
  horizon: number;
  model: string;
  baseline: string;
  test_period: [string, string];
  hours: number;
  bias_kw: number;
  mae_kw: number;
  rmse_kw: number;
  baseline_mae_kw: number | null;
  abs_error_percentiles_kw: { p50: number; p90: number; p95: number; p99: number };
  interval_coverage_pct: number | null;
  by_hour: { hour: number; n: number; mae_kw: number; bias_kw: number; baseline_mae_kw: number | null }[];
  histogram: { from_kw: number; to_kw: number; hours: number }[];
  histogram_note: string | null;
  worst: { ts: string; actual_kw: number; predicted_kw: number; error_kw: number }[];
  note: string;
}

export interface CommunityRow {
  id: number;
  key: string;
  name: string;
  description: string;
  timezone: string;
  buildings: number;
  floor_area_sqm: number | null;
  hours: number;
  valid_hours: number;
  period_start: string;
  period_end: string;
  energy_kwh: number;
  avg_kw: number | null;
  peak_kw: number | null;
  load_factor: number | null;
  kwh_per_sqm_year: number | null;
  avg_w_per_sqm: number | null;
  peak_w_per_sqm: number | null;
  source_name: string | null;
  license: string | null;
  forecast_ready: boolean;
  accuracy_24h: {
    model: string;
    mae_kw: number;
    rmse_kw: number;
    mape_pct: number | null;
    r2: number | null;
    baseline: string | null;
    baseline_mae_kw: number | null;
    mae_pct_of_average: number | null;
    gain_vs_baseline_pct: number | null;
  } | null;
}

export interface CommunityComparison {
  communities: CommunityRow[];
  notes: string[];
}

export interface ModelMetric {
  n: number;
  mae: number;
  rmse: number;
  mape_pct: number | null;
  mape_excluded: number;
  smape_pct: number | null;
  r2: number | null;
  band_80_coverage_pct?: number;
}

export interface HorizonResult {
  horizon: number;
  test: Record<string, ModelMetric>;
  /** Cross-validation results; baselines are keyed by their name, learned families by `family#candidate`. */
  cv?: Record<string, { _summary?: { mean_fold_mae: number } }>;
  chosen: Record<string, { index: number; params: Record<string, unknown>; cv_mean_fold_mae: number; residual_q10: number; residual_q90: number }>;
  chosen_baselines: Record<string, { column: string; residual_q10: number; residual_q90: number }>;
  best_overall_by_cv: string;
  best_overall_is_baseline: boolean;
  best_model_by_cv: string;
  best_baseline_by_cv: string;
  best_baseline_by_test: string;
  mae_improvement_vs_best_baseline_pct: number;
  learned_beats_best_baseline: boolean;
  bootstrap_vs_best_baseline?: { model: string; baseline: string; mae_diff: number; ci95_low: number; ci95_high: number; days: number };
  test_best_by_test_mae?: string;
  counts?: { test_rows_scored: number; test_rows_excluded: number };
}

export interface DeployedEntry {
  model_id: string | null;
  family: string;
  baseline?: string;
  weather: boolean;
  selected_from_horizon: number;
}

export interface ModelsResponse {
  model: {
    id: string;
    trained_through: string;
    created_at: string;
    protocol: { cv_folds: { name: string; test_start: string; test_end: string }[]; test_period: [string, string]; selection: string; weather: string; mape_excludes_actuals_below_kw: number };
    data: { hours: number; valid_hours: number; first: string; last: string };
    versions: Record<string, string>;
    unit: string;
  } | null;
  message?: string;
  horizons: Record<string, HorizonResult>;
  deployed: Record<string, DeployedEntry>;
  evaluated_horizons: number[];
  note?: string;
}

export interface ForecastPoint {
  horizon: number;
  ts: string;
  kw: number;
  lower_kw: number;
  upper_kw: number;
  family: string;
  actual_kw: number | null;
}

export interface SocietyForecast {
  origin: string;
  trained_through: string;
  points: ForecastPoint[];
  summary: ForecastSummary | Record<string, never>;
  model_id: string;
  accuracy: Record<string, { model: string; mae_kw: number; rmse_kw: number; mape_pct: number | null; r2: number | null; baseline: string; baseline_mae_kw: number }>;
  note: string;
}

export interface BacktestPoint {
  origin: string;
  ts: string;
  actual_kw: number | null;
  predicted_kw: number;
  lower_kw: number | null;
  upper_kw: number | null;
  baseline_kw: number | null;
}

export interface Backtest {
  horizon: number;
  model: string;
  baseline: string;
  test_period: [string, string];
  metrics: ModelMetric;
  baseline_metrics: ModelMetric;
  points: BacktestPoint[];
}

export interface ShapFeature {
  feature: string;
  label: string;
  group: string;
  mean_abs_shap_kw: number;
  share_pct: number;
}

export interface SocietyGlobalExplanation {
  society_id: number;
  model_id: string;
  basis: string;
  horizons: Record<string, { model: string; rows: number; top_features: ShapFeature[]; group_share_pct: Record<string, number> }>;
}

export interface SocietyLocalExplanation {
  origin: string;
  prediction_kw: number;
  base_value_kw: number;
  drivers: { feature: string; label: string; value: number | null; contribution_kw: number; direction: string }[];
  [k: string]: unknown;
}

export type AlertSeverity = 'low' | 'medium' | 'high';

export interface SocietyAnomaly {
  id: number;
  scope: 'society' | 'building';
  building: string | null;
  start_ts: string;
  end_ts: string;
  hours: number;
  types: string[];
  severity: AlertSeverity;
  severity_level: number;
  peak_ts: string;
  peak_kw: number | null;
  expected_kw: number | null;
  excess_ratio: number | null;
  explanation: string;
  top_contributors: { building: string; deviation_kwh: number; share_of_total_deviation_pct: number }[];
  context: Record<string, unknown>;
  acknowledged: boolean;
}

export interface SocietyAnomalyList {
  total: number;
  summary: AnomalyCounts;
  events: SocietyAnomaly[];
  note: string;
}

export interface SocietyCost {
  total: CostBlock;
  daily: { ts: string; energy_kwh: number; energy_cost: number; valid_hours: number; total_cost: number }[];
  [k: string]: unknown;
}

export interface SocietyReport {
  id: number;
  society_id: number;
  kind: string;
  format: 'pdf' | 'csv';
  title: string;
  period_start: string | null;
  period_end: string | null;
  created_at: string;
  filename: string;
  size_bytes: number;
}

export type ReportKind = 'monthly' | 'consumption' | 'forecast' | 'anomalies' | 'cost' | 'buildings';
