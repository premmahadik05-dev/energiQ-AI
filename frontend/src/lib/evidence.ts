import { fmtNum, humanize } from './format';

const UNIT_SUFFIX: [RegExp, string][] = [
  [/_per_kwh$/, ' (per kWh)'],
  [/_per_30d$/, ' (per 30 days)'],
  [/_pct$/, ' (%)'],
  [/_kwh$/, ' (kWh)'],
  [/_kw$/, ' (kW)'],
];

/** Readable label for an API evidence/scenario key, keeping the unit that is encoded in the key name. */
export function evidenceLabel(key: string): string {
  for (const [re, unit] of UNIT_SUFFIX) {
    if (re.test(key)) return humanize(key.replace(re, '')) + unit;
  }
  return humanize(key);
}

export function evidenceValue(v: unknown): string {
  if (typeof v === 'number') return fmtNum(v, Number.isInteger(v) ? 0 : 2);
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (Array.isArray(v)) return v.map(evidenceValue).join(', ');
  if (v === null || v === undefined) return '–';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
