import { describe, expect, it } from 'vitest';
import type { Forecast } from '../api/types';
import { fx } from '../test/fixtures';
import { evidenceLabel, evidenceValue } from './evidence';
import { fmtBytes, fmtFractionPct, fmtMoney, fmtNum, fmtPct, fmtSeconds, fmtSigned, humanize, jobKindLabel, modelLabel, plural, shortModelId } from './format';
import { safeInternalLink } from './links';
import { niceScale } from './scale';
import { forecastPeak, forecastRows, readingsToRows } from './series';
import { DAY, HOUR, formatMs, formatTs, niceTimeTicks, parseNaive, toApiTimestamp, toDatetimeLocal, weekdayOf, withGaps } from './time';

describe('formatting', () => {
  it('formats numbers with fixed decimals and en-US grouping; null and NaN become a dash', () => {
    expect(fmtNum(8687, 0)).toBe('8,687');
    expect(fmtNum(0.5173, 3)).toBe('0.517');
    expect(fmtNum(null)).toBe('–');
    expect(fmtNum(Number.NaN)).toBe('–');
    expect(fmtPct(17.14)).toBe('17.1%');
    expect(fmtFractionPct(0.9917)).toBe('99.2%');
    expect(fmtSigned(-0.021, 3)).toBe('−0.021');
    expect(fmtSigned(0.002, 3)).toBe('+0.002');
    expect(fmtSigned(0, 1)).toBe('0.0');
  });

  it('formats money in the tariff currency, falling back to the raw currency text', () => {
    expect(fmtMoney(1887.17, 'EUR')).toBe('€1,887.17');
    expect(fmtMoney(3, 'kr')).toBe('3.00 kr');
    expect(fmtMoney(null, 'EUR')).toBe('–');
  });

  it('formats sizes, durations, plurals and labels', () => {
    expect(fmtBytes(512)).toBe('512 B');
    expect(fmtBytes(2048)).toBe('2.0 KB');
    expect(fmtBytes(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(fmtSeconds(17.6)).toBe('18 s');
    expect(fmtSeconds(125)).toBe('2 min 5 s');
    expect(plural(1, 'event')).toBe('1 event');
    expect(plural(3, 'event')).toBe('3 events');
    expect(modelLabel('seasonal_naive_168')).toBe('Seasonal naive (168 h)');
    expect(modelLabel('mystery_model')).toBe('Mystery model');
    expect(jobKindLabel('train')).toBe('Model training');
  });

  it('shortens the model id to its training time and keeps unknown ids as they are', () => {
    expect(shortModelId('bundle_2_1_20261103T001920526790')).toBe('2026-11-03 00:19:20');
    expect(shortModelId('custom')).toBe('custom');
  });

  it('humanize keeps unit spelling (kWh, kW) and sentence case', () => {
    expect(humanize('peak_kwh_in_window')).toBe('Peak kWh in window');
    expect(humanize('baseload_kw')).toBe('Baseload kW');
    expect(humanize('flagged_pct')).toBe('Flagged pct');
  });
});

describe('evidence formatting (API evidence keys)', () => {
  it('turns unit suffixes of keys into labels and formats values', () => {
    expect(evidenceLabel('baseload_kw')).toBe('Baseload (kW)');
    expect(evidenceLabel('avg_rate_per_kwh')).toBe('Avg rate (per kWh)');
    expect(evidenceLabel('estimated_kwh_saved_per_30d')).toBe('Estimated kWh saved (per 30 days)');
    expect(evidenceLabel('peak_share_pct')).toBe('Peak share (%)');
    expect(evidenceValue(1.6116035455278002)).toBe('1.61');
    expect(evidenceValue(8760)).toBe('8,760');
    expect(evidenceValue(true)).toBe('yes');
    expect(evidenceValue([17, 18, 19])).toBe('17, 18, 19');
    expect(evidenceValue(null)).toBe('–');
    expect(evidenceValue('2009-12-12T23:00:00')).toBe('2009-12-12T23:00:00');
  });

  it('every evidence key in the captured recommendations gets a readable label without underscores', () => {
    for (const rec of fx.recommendations.recommendations) {
      for (const key of Object.keys(rec.evidence)) expect(evidenceLabel(key)).not.toMatch(/_/);
    }
  });
});

describe('naive timestamps are never shifted by the browser time zone', () => {
  it('parses the space and T forms to the same instant and ignores a zone suffix', () => {
    expect(parseNaive('2009-07-15 08:00:00')).toBe(parseNaive('2009-07-15T08:00:00'));
    expect(parseNaive('2009-07-15T08:00:00+05:30')).toBe(parseNaive('2009-07-15T08:00:00'));
    expect(parseNaive('2009-07-15')).toBe(Date.UTC(2009, 6, 15));
    expect(Number.isNaN(parseNaive('garbage'))).toBe(true);
  });

  it('shows API values exactly as given (no conversion), in both formats', () => {
    expect(formatTs('2009-12-12T23:00:00')).toBe('2009-12-12 23:00');
    expect(formatTs('2009-12-12 23:00:00')).toBe('2009-12-12 23:00');
    expect(formatTs('2009-12-12')).toBe('2009-12-12');
    expect(formatTs(null)).toBe('–');
    expect(formatTs('not a date')).toBe('not a date');
    expect(formatMs(parseNaive('2009-03-29 02:00:00'))).toBe('2009-03-29 02:00'); // a DST-gap hour in many zones
  });

  it('round-trips through the API and datetime-local formats', () => {
    const ms = parseNaive('2010-01-01 20:00:00');
    expect(toApiTimestamp(ms)).toBe('2010-01-01T20:00:00');
    expect(toDatetimeLocal(ms)).toBe('2010-01-01T20:00');
    expect(weekdayOf(ms)).toBe('Fri');
  });

  it('withGaps inserts one null sample after a missing stretch and invents no values', () => {
    const rows = [{ t: 0, v: 1 as number | null }, { t: HOUR, v: 2 }, { t: 5 * HOUR, v: 3 }];
    const out = withGaps(rows, HOUR, (t) => ({ t, v: null }));
    expect(out.map((r) => r.v)).toEqual([1, 2, null, 3]);
    expect(out[2]?.t).toBe(2 * HOUR);
  });

  it('niceTimeTicks gives aligned, unique, labelled ticks for a few days and for a year', () => {
    const lo = parseNaive('2009-07-13 00:00:00');
    const hi = parseNaive('2009-07-16 23:00:00');
    const days = niceTimeTicks(lo, hi, 7);
    expect(days.ticks.length).toBeGreaterThan(2);
    expect(days.ticks.length).toBeLessThanOrEqual(8);
    expect(new Set(days.ticks.map(days.format)).size).toBe(days.ticks.length);
    expect(days.ticks.every((t) => t % HOUR === 0)).toBe(true);
    const year = niceTimeTicks(parseNaive('2009-01-01'), parseNaive('2009-12-31 23:00:00'), 7);
    expect(year.ticks.length).toBeLessThanOrEqual(7);
    expect(year.format(year.ticks[0] as number)).toBe('Jan 2009');
    expect(new Set(year.ticks.map(year.format)).size).toBe(year.ticks.length);
    expect(DAY).toBe(24 * HOUR);
  });
});

describe('axis scale', () => {
  it('rounds up to a nice maximum and always includes zero', () => {
    const s = niceScale(0, 2.68);
    expect(s.min).toBe(0);
    expect(s.max).toBeGreaterThanOrEqual(2.68);
    expect(s.ticks[0]).toBe(0);
    expect(s.ticks.at(-1)).toBe(s.max);
    expect(s.ticks.length).toBeLessThanOrEqual(7);
  });

  it('handles tiny ranges, negative values and empty data', () => {
    expect(niceScale(0, 0.4).max).toBeCloseTo(0.4, 5);
    const neg = niceScale(-1.2, 3);
    expect(neg.min).toBeLessThanOrEqual(-1.2);
    expect(neg.max).toBeGreaterThanOrEqual(3);
    expect(niceScale(Number.NaN, Number.NaN).ticks.length).toBeGreaterThan(1);
    expect(niceScale(0, 0).max).toBeGreaterThan(0);
  });

  it('reports the decimals needed to print every tick exactly', () => {
    expect(niceScale(0, 220).decimals).toBe(0);
    expect(niceScale(0, 0.3).decimals).toBeGreaterThanOrEqual(1);
  });
});

describe('series helpers on captured data', () => {
  it('keeps missing hours as gaps in the readings series', () => {
    const rows = readingsToRows([{ ts: '2009-01-01T00:00:00', kw: 1 }, { ts: '2009-01-01T01:00:00', kw: 2 }, { ts: '2009-01-01T04:00:00', kw: 3 }]);
    expect(rows.map((r) => r.actual)).toEqual([1, 2, null, 3]);
  });

  it('merges a saved forecast onto the actuals and keeps the band as [lower, upper]', () => {
    const fc = fx.forecastCreated as unknown as Forecast;
    const rows = forecastRows(fx.readingsHourlyDefault.points, fc);
    const withForecast = rows.filter((r) => typeof r.forecast === 'number');
    expect(withForecast.length).toBeGreaterThan(0);
    const first = fc.points[0] as Forecast['points'][number];
    const row = rows.find((r) => r.t === parseNaive(first.ts));
    expect(row?.forecast).toBe(first.kw);
    expect(row?.band).toEqual([first.lower_kw, first.upper_kw]);
    expect(rows.every((r, i) => i === 0 || r.t >= (rows[i - 1] as { t: number }).t)).toBe(true);
  });

  it('finds the forecast peak and its horizon', () => {
    const fc = fx.forecastCreated as unknown as Forecast;
    const peak = forecastPeak(fc);
    expect(peak?.kw).toBe(Math.max(...fc.points.map((p) => p.kw)));
    expect(peak?.horizon).toBeGreaterThanOrEqual(1);
  });
});

describe('notification links', () => {
  it('only follows paths inside the app', () => {
    expect(safeInternalLink('/anomalies?dataset=1')).toBe('/anomalies?dataset=1');
    expect(safeInternalLink('//evil.example/x')).toBeNull();
    expect(safeInternalLink('https://evil.example')).toBeNull();
    expect(safeInternalLink('javascript:alert(1)')).toBeNull();
    expect(safeInternalLink('/\\evil.example')).toBeNull(); // browsers read /\host as //host
    expect(safeInternalLink('/models/x\\..\\y')).toBeNull();
    for (const n of fx.notifications) expect(safeInternalLink(n.link)).not.toBeNull();
  });
});
