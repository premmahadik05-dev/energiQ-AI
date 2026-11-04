/**
 * Timestamps from the API are naive wall-clock times in the dataset's own (local) time convention.
 * They are displayed exactly as given. For arithmetic and chart axes we map a naive timestamp to
 * "milliseconds as if UTC" and format it back with the UTC getters, so the browser time zone and
 * DST never shift a value.
 */
export const HOUR = 3_600_000;
export const DAY = 24 * HOUR;

const NAIVE_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?/;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = (n: number) => String(n).padStart(2, '0');

/** Parse "YYYY-MM-DD", "YYYY-MM-DD HH:MM:SS" or the ISO "T" form. Any zone suffix is ignored on purpose. */
export function parseNaive(s: string): number {
  const m = NAIVE_RE.exec(s.trim());
  if (!m) return Number.NaN;
  const [, y, mo, d, h = '0', mi = '0', se = '0'] = m;
  return Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(se));
}

/** "2009-12-18T06:00:00" (what the API accepts for datetime query parameters). */
export function toApiTimestamp(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** Value for <input type="datetime-local"> ("YYYY-MM-DDTHH:MM"). */
export function toDatetimeLocal(ms: number): string {
  return toApiTimestamp(ms).slice(0, 16);
}

/** "2009-12-18 06:00" - the API value shown as given (T separator and seconds removed). */
export function formatTs(s: string | null | undefined): string {
  if (!s) return '–';
  const ms = parseNaive(s);
  if (Number.isNaN(ms)) return s;
  const full = toApiTimestamp(ms);
  const date = full.slice(0, 10);
  const time = full.slice(11, 16);
  return /^\d{4}-\d{2}-\d{2}$/.test(s.trim()) ? date : `${date} ${time}`;
}

export function formatDate(s: string | null | undefined): string {
  if (!s) return '–';
  const ms = parseNaive(s);
  return Number.isNaN(ms) ? s : toApiTimestamp(ms).slice(0, 10);
}

export function formatMs(ms: number, style: 'full' | 'date' | 'short' | 'time' | 'month' = 'full'): string {
  const d = new Date(ms);
  const date = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  const time = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  switch (style) {
    case 'date':
      return date;
    case 'time':
      return time;
    case 'month':
      return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
    case 'short':
      return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${time}`;
    default:
      return `${date} ${time}`;
  }
}

const STEPS = [HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 7 * DAY, 14 * DAY];

/**
 * Evenly spaced, human-aligned tick positions for a time axis (hours, days or months), with a label
 * formatter that stays unique at that spacing. Everything is computed on the naive "as if UTC" clock.
 */
export function niceTimeTicks(lo: number, hi: number, maxTicks = 7): { ticks: number[]; format: (ms: number) => string } {
  const span = Math.max(hi - lo, 1);
  if (span > 100 * DAY) {
    const a = new Date(lo);
    const b = new Date(hi);
    const months = (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth() + 1;
    const stepM = [1, 2, 3, 6, 12, 24].find((m) => Math.ceil(months / m) <= maxTicks) ?? 24;
    const ticks: number[] = [];
    let y = a.getUTCFullYear();
    let m = a.getUTCMonth();
    for (let guard = 0; guard < 400; guard++) {
      const t = Date.UTC(y, m, 1);
      if (t > hi) break;
      if (t >= lo) ticks.push(t);
      m += stepM;
      y += Math.floor(m / 12);
      m %= 12;
    }
    return { ticks, format: (ms) => formatMs(ms, 'month') };
  }
  const step = STEPS.find((s) => span / s <= maxTicks) ?? 14 * DAY;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
  const format = step < DAY ? (ms: number) => (ms % DAY === 0 ? `${new Date(ms).getUTCDate()} ${MONTHS[new Date(ms).getUTCMonth()]}` : formatMs(ms, 'time')) : (ms: number) => `${new Date(ms).getUTCDate()} ${MONTHS[new Date(ms).getUTCMonth()]}`;
  return { ticks, format };
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export function weekdayOf(ms: number): string {
  return WEEKDAYS[new Date(ms).getUTCDay()] ?? '';
}

/**
 * Insert a null sample after the last point before any gap so that a line chart breaks there
 * instead of drawing a line across missing hours. No value is invented: the gap stays a gap.
 */
export function withGaps<T extends { t: number }>(rows: T[], stepMs: number, empty: (t: number) => T): T[] {
  const out: T[] = [];
  for (let i = 0; i < rows.length; i++) {
    const cur = rows[i] as T;
    out.push(cur);
    const next = rows[i + 1];
    if (next && next.t - cur.t > stepMs * 1.5) out.push(empty(cur.t + stepMs));
  }
  return out;
}
