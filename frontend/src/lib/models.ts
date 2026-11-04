import type { HorizonEvaluation, ModelEvaluation } from '../api/types';

/** The longest evaluated horizon (24 h when present) - the hardest, most useful headline. */
export function headlineHorizon(ev: Partial<ModelEvaluation> | undefined): { horizon: string; data: HorizonEvaluation } | null {
  const hs = ev?.horizons;
  if (!hs) return null;
  const keys = Object.keys(hs).sort((a, b) => Number(a) - Number(b));
  const k = keys.includes('24') ? '24' : keys[keys.length - 1];
  const data = k ? hs[k] : undefined;
  return k && data ? { horizon: k, data } : null;
}

export function sortedHorizons(ev: Partial<ModelEvaluation> | undefined): [string, HorizonEvaluation][] {
  return Object.entries(ev?.horizons ?? {}).sort((a, b) => Number(a[0]) - Number(b[0]));
}
