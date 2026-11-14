/**
 * Value-axis scale helper. Recharts' own "auto" domain was unreliable when a scatter series with
 * its own data sits on the same axis (a short window rendered with a 0 to 0.4 axis while the load
 * went far beyond it), so the charts compute an explicit, rounded domain and tick list from the
 * values that are actually drawn.
 */
export interface NiceScale {
  min: number;
  max: number;
  ticks: number[];
  /** decimals needed to print every tick exactly */
  decimals: number;
}

const STEP_MULTIPLIERS = [1, 2, 2.5, 5, 10];

function niceStep(rawStep: number): number {
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  for (const m of STEP_MULTIPLIERS) {
    if (m * magnitude >= rawStep) return m * magnitude;
  }
  return 10 * magnitude;
}

/**
 * Rounded axis range that always includes [lo, hi], with at most about `target + 1` ticks.
 * `includeZero` (default) also forces 0 into the range: right for bars, whose length encodes the value.
 * Lines encode position and slope, so they pass `includeZero: false` and get a tight range with a little padding;
 * the axis then never starts below 0 for data that are all non-negative.
 */
export function niceScale(lo: number, hi: number, target = 5, includeZero = true): NiceScale {
  let low = Number.isFinite(lo) ? lo : 0;
  let high = Number.isFinite(hi) ? hi : 0;
  if (includeZero) {
    low = Math.min(0, low);
    high = Math.max(0, high);
  } else if (high - low > 0) {
    const pad = (high - low) * 0.08;
    low = lo >= 0 ? Math.max(0, low - pad) : low - pad;
    high += pad;
  }
  if (high - low <= 0) high = low + 1;
  const step = niceStep((high - low) / target);
  const min = Math.floor(low / step + 1e-9) * step;
  const max = Math.ceil(high / step - 1e-9) * step;
  const ticks: number[] = [];
  let decimals = 0;
  while (decimals < 8 && Math.abs(step * 10 ** decimals - Math.round(step * 10 ** decimals)) > 1e-9) decimals += 1;
  for (let v = min; v <= max + step / 2; v += step) ticks.push(Number(v.toFixed(decimals)));
  return { min: Number(min.toFixed(decimals)), max: Number(max.toFixed(decimals)), ticks, decimals };
}
