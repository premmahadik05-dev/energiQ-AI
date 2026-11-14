/**
 * Response shapes of the EnergiQ API. They follow what backend/app/schemas.py and the route handlers
 * really return (verified against a running backend), including endpoints that return plain dicts.
 * Timestamps are naive strings in the site's own time convention and must be shown as given.
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

// ----------------------------------------------------------------------------- background jobs
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

// ----------------------------------------------------------------------------- tariffs and recommendations
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

/** Body of POST /tariffs. Rates are the price per kWh for hour 0..23. */
export interface TariffInput {
  name: string;
  currency: string;
  weekday_rates: number[];
  weekend_rates: number[];
  daily_fixed_charge: number;
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
