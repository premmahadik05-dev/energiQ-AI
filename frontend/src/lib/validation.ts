/** Client-side checks that mirror the backend rules (backend/app/security.py, services/data.py). The server stays the authority. */

export const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$/;
const COMMON_PASSWORDS = new Set(['password123', '1234567890', 'qwertyuiop', 'password1234', 'letmein1234', 'admin12345']);

export function validateEmail(raw: string): string | null {
  const email = raw.trim();
  if (!email) return 'Enter your e-mail address.';
  if (email.length > 254 || !EMAIL_RE.test(email)) return 'Enter a valid e-mail address.';
  return null;
}

export function validatePassword(pw: string): string | null {
  if (pw.length < 10 || pw.length > 128) return 'Password must be 10-128 characters.';
  if (!(/[A-Za-z]/.test(pw) && /\d/.test(pw))) return 'Password must contain letters and digits.';
  if (COMMON_PASSWORDS.has(pw.toLowerCase()) || new Set(pw).size < 5) return 'Password is too easy to guess.';
  return null;
}

export function validateFullName(name: string): string | null {
  return name.length > 120 ? 'Name can be at most 120 characters.' : null;
}

export const ALLOWED_EXTENSIONS = ['.csv', '.txt', '.tsv'] as const;

export function validateUploadFile(file: { name: string; size: number } | null, maxMb: number): string | null {
  if (!file) return 'Choose a CSV file to upload.';
  const dot = file.name.lastIndexOf('.');
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
  if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(ext)) return `Only ${ALLOWED_EXTENSIONS.join(', ')} files are accepted.`;
  if (file.size === 0) return 'The file is empty.';
  if (file.size > maxMb * 1024 * 1024) return `The file is larger than the ${maxMb} MB limit.`;
  return null;
}

export interface UploadFormValues {
  name: string;
  valueColumn: string;
  mode: 'single' | 'split';
  timestampColumn: string;
  dateColumn: string;
  timeColumn: string;
}

/** Field-level errors for the upload form. Empty object = valid. */
export function validateUploadForm(v: UploadFormValues): Partial<Record<'name' | 'valueColumn' | 'timestampColumn' | 'dateColumn' | 'timeColumn', string>> {
  const e: Partial<Record<'name' | 'valueColumn' | 'timestampColumn' | 'dateColumn' | 'timeColumn', string>> = {};
  if (!v.name.trim()) e.name = 'Give the dataset a name.';
  else if (v.name.trim().length > 120) e.name = 'Name can be at most 120 characters.';
  if (!v.valueColumn.trim()) e.valueColumn = 'Name the column that holds the consumption values.';
  if (v.mode === 'single') {
    if (!v.timestampColumn.trim()) e.timestampColumn = 'Name the timestamp column.';
  } else {
    if (!v.dateColumn.trim()) e.dateColumn = 'Name the date column.';
    if (!v.timeColumn.trim()) e.timeColumn = 'Name the time column.';
  }
  return e;
}

export interface TariffFormValues {
  name: string;
  currency: string;
  dailyFixed: string;
  weekday: string[];
  weekend: string[];
}

export type ParsedTariff = { name: string; currency: string; daily_fixed_charge: number; weekday_rates: number[]; weekend_rates: number[] };

/** Returns either an error message or the request body for POST /tariffs. */
export function parseTariffForm(v: TariffFormValues): { error: string } | { value: ParsedTariff } {
  const name = v.name.trim();
  const currency = v.currency.trim();
  if (!name) return { error: 'Give the tariff a name.' };
  if (name.length > 80) return { error: 'Tariff name can be at most 80 characters.' };
  if (!currency) return { error: 'Enter a currency code or symbol.' };
  if (currency.length > 8) return { error: 'Currency can be at most 8 characters.' };
  const fixed = v.dailyFixed.trim() === '' ? 0 : Number(v.dailyFixed);
  if (!Number.isFinite(fixed) || fixed < 0 || fixed > 1_000_000) return { error: 'Daily fixed charge must be a number between 0 and 1,000,000.' };
  const parse = (label: string, vals: string[]): number[] | string => {
    if (vals.length !== 24) return `${label} needs 24 hourly rates.`;
    const out: number[] = [];
    for (let h = 0; h < 24; h++) {
      const raw = (vals[h] ?? '').trim();
      const n = Number(raw);
      if (raw === '' || !Number.isFinite(n) || n < 0 || n > 1_000_000) return `${label}, hour ${String(h).padStart(2, '0')}:00: enter a rate between 0 and 1,000,000.`;
      out.push(n);
    }
    return out;
  };
  const wd = parse('Weekday rates', v.weekday);
  if (typeof wd === 'string') return { error: wd };
  const we = parse('Weekend rates', v.weekend);
  if (typeof we === 'string') return { error: we };
  return { value: { name, currency, daily_fixed_charge: fixed, weekday_rates: wd, weekend_rates: we } };
}

export function validateSchedule(durationH: string, powerKw: string): { duration_h?: string; power_kw?: string } {
  const e: { duration_h?: string; power_kw?: string } = {};
  const d = Number(durationH);
  if (!Number.isInteger(d) || d < 1 || d > 24) e.duration_h = 'Duration must be a whole number of hours from 1 to 24.';
  const p = Number(powerKw);
  if (!Number.isFinite(p) || p <= 0 || p > 1000) e.power_kw = 'Power must be greater than 0 and at most 1000 kW.';
  return e;
}
