import type { DailyReadingPoint, Forecast, ReadingPoint } from '../api/types';
import type { TsRow } from '../components/charts/TimeSeriesChart';
import { DAY, HOUR, parseNaive, withGaps } from './time';

/** Hourly readings -> chart rows. Missing hours (null kw, or absent timestamps) stay gaps. */
export function readingsToRows(points: ReadingPoint[]): TsRow[] {
  const rows: TsRow[] = [];
  for (const p of points) {
    const t = parseNaive(p.ts);
    if (!Number.isNaN(t)) rows.push({ t, actual: p.kw });
  }
  return withGaps(rows, HOUR, (t) => ({ t, actual: null }));
}

export function dailyToRows(points: DailyReadingPoint[]): TsRow[] {
  const rows: TsRow[] = [];
  for (const p of points) {
    const t = parseNaive(p.ts);
    if (!Number.isNaN(t)) rows.push({ t, actual: p.mean_kw });
  }
  return withGaps(rows, DAY, (t) => ({ t, actual: null }));
}

/** Actual readings plus a saved forecast on one time axis. Forecast and band exist only at forecast timestamps. */
export function forecastRows(actual: ReadingPoint[], fc: Forecast | null): TsRow[] {
  const map = new Map<number, TsRow>();
  for (const r of readingsToRows(actual)) map.set(r.t, { ...r });
  if (fc) {
    for (const p of fc.points) {
      const t = parseNaive(p.ts);
      if (Number.isNaN(t)) continue;
      const row = map.get(t) ?? ({ t, actual: null } as TsRow);
      row.forecast = p.kw;
      row.band = [p.lower_kw, p.upper_kw];
      map.set(t, row);
    }
  }
  return [...map.values()].sort((a, b) => a.t - b.t);
}

export function forecastPeak(fc: Forecast): { kw: number; ts: string; horizon: number } | null {
  let best: Forecast['points'][number] | null = null;
  for (const p of fc.points) if (!best || p.kw > best.kw) best = p;
  return best ? { kw: best.kw, ts: best.ts, horizon: best.horizon } : null;
}
