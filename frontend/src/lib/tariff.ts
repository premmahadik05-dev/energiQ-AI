/**
 * Building a tariff from the form fields. Pure functions: the form and the tests share them.
 *
 * A tariff is the price per kWh for each of the 24 hours of a weekday and of a weekend day. The form offers two ways
 * to describe it, and both end in the same 24 + 24 numbers the server stores:
 *   flat    one rate all day;
 *   window  an off-peak rate with a dearer rate inside a peak window (start inclusive, end exclusive, may wrap past
 *           midnight, so 18 to 6 means 18:00 to 06:00).
 */
export type TariffMode = 'flat' | 'window';

export interface TariffDraft {
  name: string;
  currency: string;
  mode: TariffMode;
  flatRate: string;
  offPeakRate: string;
  peakRate: string;
  peakStart: string;
  peakEnd: string;
  /** apply the peak rate on weekends as well (otherwise weekends are charged the off-peak rate all day) */
  peakOnWeekend: boolean;
  fixedCharge: string;
}

export type TariffField = keyof TariffDraft;
export type TariffErrors = Partial<Record<TariffField, string>>;

export const MAX_RATE = 1_000_000;

export const emptyDraft = (currency = 'INR'): TariffDraft => ({
  name: '',
  currency,
  mode: 'flat',
  flatRate: '',
  offPeakRate: '',
  peakRate: '',
  peakStart: '18',
  peakEnd: '22',
  peakOnWeekend: false,
  fixedCharge: '0',
});

/** Parses a decimal typed by a person. Empty, non-numeric and non-finite input return null. */
export function parseAmount(text: string): number | null {
  const t = text.trim();
  if (t === '' || !/^\d*\.?\d+$|^\d+\.$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function parseHour(text: string): number | null {
  const t = text.trim();
  if (!/^\d{1,2}$/.test(t)) return null;
  const n = Number(t);
  return n >= 0 && n <= 23 ? n : null;
}

export const inPeakWindow = (hour: number, start: number, end: number): boolean => (start < end ? hour >= start && hour < end : hour >= start || hour < end);

function checkRate(text: string, label: string): string | null {
  const n = parseAmount(text);
  if (n === null) return `${label} must be a number such as 6.5`;
  if (n > MAX_RATE) return `${label} must not exceed ${MAX_RATE.toLocaleString('en-US')}`;
  return null;
}

export function validateDraft(d: TariffDraft): TariffErrors {
  const e: TariffErrors = {};
  if (d.name.trim() === '') e.name = 'Give the tariff a name';
  else if (d.name.trim().length > 80) e.name = 'Use at most 80 characters';
  const cur = d.currency.trim();
  if (cur === '') e.currency = 'Enter a currency code or symbol';
  else if (cur.length > 8) e.currency = 'Use at most 8 characters';
  if (d.mode === 'flat') {
    const m = checkRate(d.flatRate, 'The rate');
    if (m) e.flatRate = m;
  } else {
    const o = checkRate(d.offPeakRate, 'The off-peak rate');
    if (o) e.offPeakRate = o;
    const p = checkRate(d.peakRate, 'The peak rate');
    if (p) e.peakRate = p;
    if (parseHour(d.peakStart) === null) e.peakStart = 'A whole hour from 0 to 23';
    if (parseHour(d.peakEnd) === null) e.peakEnd = 'A whole hour from 0 to 23';
    if (!e.peakStart && !e.peakEnd && parseHour(d.peakStart) === parseHour(d.peakEnd)) e.peakEnd = 'The window must end at a different hour than it starts';
  }
  const f = checkRate(d.fixedCharge, 'The daily fixed charge');
  if (f) e.fixedCharge = f;
  return e;
}

export interface BuiltRates {
  weekday_rates: number[];
  weekend_rates: number[];
  daily_fixed_charge: number;
}

/** The 24 + 24 rates for a draft that passes validation; null when it does not. */
export function buildRates(d: TariffDraft): BuiltRates | null {
  if (Object.keys(validateDraft(d)).length > 0) return null;
  const fixed = parseAmount(d.fixedCharge) as number;
  if (d.mode === 'flat') {
    const r = parseAmount(d.flatRate) as number;
    return { weekday_rates: Array<number>(24).fill(r), weekend_rates: Array<number>(24).fill(r), daily_fixed_charge: fixed };
  }
  const off = parseAmount(d.offPeakRate) as number;
  const peak = parseAmount(d.peakRate) as number;
  const start = parseHour(d.peakStart) as number;
  const end = parseHour(d.peakEnd) as number;
  const day = Array.from({ length: 24 }, (_, h) => (inPeakWindow(h, start, end) ? peak : off));
  return { weekday_rates: day, weekend_rates: d.peakOnWeekend ? [...day] : Array<number>(24).fill(off), daily_fixed_charge: fixed };
}

export const CURRENCIES = [
  { code: 'INR', label: 'INR – Indian rupee (₹)' },
  { code: 'USD', label: 'USD – US dollar ($)' },
  { code: 'EUR', label: 'EUR – euro (€)' },
  { code: 'GBP', label: 'GBP – pound sterling (£)' },
] as const;

/** One-line description of a stored tariff for a table: lowest to highest rate on weekdays. */
export function rateSummary(rates: number[]): string {
  if (rates.length === 0) return '–';
  const lo = Math.min(...rates);
  const hi = Math.max(...rates);
  const f = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2).replace(/\.?0+$/, ''));
  return lo === hi ? f(lo) : `${f(lo)} to ${f(hi)}`;
}
