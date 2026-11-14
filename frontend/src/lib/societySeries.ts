import type { ConsumptionPoint, SocietyAnomaly } from '../api/societyTypes';
import type { TsRow } from '../components/charts/TimeSeriesChart';
import { DAY, parseNaive, toApiTimestamp } from './time';

/** Consumption points -> chart rows; an hour/day with no valid data stays null (a gap), never zero. */
export function consumptionRows(points: ConsumptionPoint[], field: 'energy_kwh' | 'avg_kw' | 'peak_kw' = 'avg_kw'): TsRow[] {
  return points.map((p) => ({ t: parseNaive(p.ts), v: p[field] ?? null }));
}

export type RangePreset = '7d' | '30d' | '90d' | '1y' | 'all';

export const PRESET_LABEL: Record<RangePreset, string> = { '7d': 'Last 7 days', '30d': 'Last 30 days', '90d': 'Last 90 days', '1y': 'Last year', all: 'All data' };
const PRESET_DAYS: Record<Exclude<RangePreset, 'all'>, number> = { '7d': 7, '30d': 30, '90d': 90, '1y': 365 };

/** Start/end (API timestamps) for a preset, counted back from the last hour of the society's data. */
export function presetRange(preset: RangePreset, startIso: string, endIso: string): { start: string; end: string } {
  const endMs = parseNaive(endIso);
  const first = parseNaive(startIso);
  if (preset === 'all') return { start: toApiTimestamp(first), end: toApiTimestamp(endMs) };
  const from = Math.max(first, endMs - PRESET_DAYS[preset] * DAY + 3_600_000);
  return { start: toApiTimestamp(from), end: toApiTimestamp(endMs) };
}

export const SEVERITY_TONE = { low: 'neutral', medium: 'warn', high: 'bad' } as const;

export function alertTitle(a: Pick<SocietyAnomaly, 'types' | 'scope' | 'building'>): string {
  const kind = a.types.includes('spike') ? 'Unusually high demand' : a.types.includes('drop') ? 'Unusually low demand' : a.types.includes('flat_run') ? 'Flat (stuck) readings' : 'Unusual demand pattern';
  return `${kind} - ${a.scope === 'society' ? 'whole society' : (a.building ?? 'building')}`;
}

/** Number of calendar months in [start, end] label rows for a stacked/grouped monthly chart. */
export function monthLabel(iso: string): string {
  return iso.slice(0, 7);
}
