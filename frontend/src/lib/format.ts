const DASH = '–';

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export const fmtInt = (v: number | null | undefined): string => fmtNum(v, 0);
export const fmtKw = (v: number | null | undefined, digits = 2): string => (v == null ? DASH : `${fmtNum(v, digits)} kW`);
export const fmtKwh = (v: number | null | undefined, digits = 1): string => (v == null ? DASH : `${fmtNum(v, digits)} kWh`);
export const fmtPct = (v: number | null | undefined, digits = 1): string => (v == null ? DASH : `${fmtNum(v, digits)}%`);

/** completeness etc. arrive as 0..1 fractions */
export const fmtFractionPct = (v: number | null | undefined, digits = 1): string => (v == null ? DASH : `${fmtNum(v * 100, digits)}%`);

/** Money in the tariff's own currency. ISO codes get currency formatting, anything else is appended as given. */
export function fmtMoney(v: number | null | undefined, currency: string, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  if (/^[A-Za-z]{3}$/.test(currency)) {
    try {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency.toUpperCase(), minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
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

/** model_id is long ("bundle_2_1_20261103T001920526790"); show a stable short label. */
export function shortModelId(id: string): string {
  const m = /^bundle_\d+_\d+_(\d{8})T(\d{6})/.exec(id);
  if (!m) return id;
  const [, d = '', t = ''] = m;
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)} ${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4)}`;
}

export const MODEL_LABELS: Record<string, string> = {
  xgboost: 'XGBoost model',
  random_forest: 'Random forest',
  lstm: 'LSTM',
  naive: 'Naive (last value)',
  seasonal_naive_24: 'Seasonal naive (24 h)',
  seasonal_naive_168: 'Seasonal naive (168 h)',
};
export const modelLabel = (k: string): string => MODEL_LABELS[k] ?? humanize(k);

const JOB_KIND_LABEL: Record<string, string> = { ingest: 'Dataset processing', train: 'Model training', anomaly: 'Anomaly detection' };
export const jobKindLabel = (k: string): string => JOB_KIND_LABEL[k] ?? humanize(k);
