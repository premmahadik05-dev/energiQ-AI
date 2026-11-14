const DASH = '–';

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export const fmtInt = (v: number | null | undefined): string => fmtNum(v, 0);
export const fmtKw = (v: number | null | undefined, digits = 2): string => (v == null ? DASH : `${fmtNum(v, digits)} kW`);
export const fmtKwh = (v: number | null | undefined, digits = 1): string => (v == null ? DASH : `${fmtNum(v, digits)} kWh`);
export const fmtPct = (v: number | null | undefined, digits = 1): string => (v == null ? DASH : `${fmtNum(v, digits)}%`);

/** Money in the tariff's own currency. ISO codes get currency formatting, anything else is appended as given. */
export function fmtMoney(v: number | null | undefined, currency: string, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  if (/^[A-Za-z]{3}$/.test(currency)) {
    try {
      // Indian digit grouping (12,34,567) for rupees, international grouping for everything else
      const code = currency.toUpperCase();
      return new Intl.NumberFormat(code === 'INR' ? 'en-IN' : 'en-US', { style: 'currency', currency: code, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
    } catch {
      /* fall through */
    }
  }
  return `${fmtNum(v, digits)} ${currency}`;
}

export function fmtSigned(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmtNum(Math.abs(v), digits)}`;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtSeconds(s: number | null | undefined): string {
  if (s == null) return DASH;
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

export function humanize(key: string): string {
  const s = key.replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
  const cased = s.charAt(0).toUpperCase() + s.slice(1);
  // keep SI-style unit spelling (kWh, kW) instead of "Kwh" / "kwh"
  return cased.replace(/\bkwh\b/gi, 'kWh').replace(/\bkw\b/gi, 'kW');
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export const MODEL_LABELS: Record<string, string> = {
  xgboost: 'XGBoost model',
  random_forest: 'Random forest',
  lstm: 'LSTM',
  naive: 'Naive (last value)',
  seasonal_naive_24: 'Seasonal naive (24 h)',
  seasonal_naive_168: 'Seasonal naive (168 h)',
  seasonal_naive_336: 'Seasonal naive (336 h)',
  linear: 'Linear regression',
  xgboost_weather: 'XGBoost + weather',
};
export const modelLabel = (k: string): string => MODEL_LABELS[k] ?? humanize(k);

const JOB_KIND_LABEL: Record<string, string> = {
  ingest: 'Dataset processing',
  train: 'Model training',
  anomaly: 'Anomaly detection',
  society_import: 'Society import',
  society_upload: 'Society upload',
  society_train: 'Society model training',
};
export const jobKindLabel = (k: string): string => JOB_KIND_LABEL[k] ?? humanize(k);
