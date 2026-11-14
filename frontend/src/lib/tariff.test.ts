import { describe, expect, it } from 'vitest';
import { fmtMoney } from './format';
import { pageTitle } from './pageTitle';
import { buildRates, emptyDraft, inPeakWindow, parseAmount, rateSummary, validateDraft, type TariffDraft } from './tariff';

const flat = (o: Partial<TariffDraft> = {}): TariffDraft => ({ ...emptyDraft('INR'), name: 'Home', flatRate: '7.5', ...o });
const window = (o: Partial<TariffDraft> = {}): TariffDraft => ({ ...emptyDraft('INR'), name: 'Time of day', mode: 'window', offPeakRate: '5', peakRate: '9', peakStart: '18', peakEnd: '22', ...o });

describe('parsing a typed amount', () => {
  it('accepts plain decimals and rejects everything that is not one', () => {
    expect(parseAmount('7.5')).toBe(7.5);
    expect(parseAmount(' 12 ')).toBe(12);
    expect(parseAmount('.5')).toBe(0.5);
    expect(parseAmount('0')).toBe(0);
    for (const bad of ['', 'abc', '-1', '1e3', '1,000', '1.2.3', 'Infinity', 'NaN', '7.5kWh']) expect(parseAmount(bad), bad).toBeNull();
  });
});

describe('tariff validation', () => {
  it('accepts a complete flat tariff and a complete peak tariff', () => {
    expect(validateDraft(flat())).toEqual({});
    expect(validateDraft(window())).toEqual({});
  });

  it('reports every problem of an empty form at once', () => {
    const e = validateDraft(emptyDraft('INR'));
    expect(Object.keys(e).sort()).toEqual(['flatRate', 'name']);
  });

  it('rejects a missing name, an over-long name and a bad currency', () => {
    expect(validateDraft(flat({ name: '  ' })).name).toBeDefined();
    expect(validateDraft(flat({ name: 'x'.repeat(81) })).name).toBeDefined();
    expect(validateDraft(flat({ currency: '' })).currency).toBeDefined();
    expect(validateDraft(flat({ currency: 'TOOLONGCODE' })).currency).toBeDefined();
  });

  it('rejects negative, non-numeric and absurdly large rates', () => {
    expect(validateDraft(flat({ flatRate: '-3' })).flatRate).toBeDefined();
    expect(validateDraft(flat({ flatRate: 'seven' })).flatRate).toBeDefined();
    expect(validateDraft(flat({ flatRate: '1000001' })).flatRate).toBeDefined();
    expect(validateDraft(flat({ fixedCharge: '-1' })).fixedCharge).toBeDefined();
  });

  it('checks the peak window: whole hours 0 to 23, and a window that actually has a length', () => {
    expect(validateDraft(window({ peakStart: '24' })).peakStart).toBeDefined();
    expect(validateDraft(window({ peakEnd: '7.5' })).peakEnd).toBeDefined();
    expect(validateDraft(window({ peakStart: '18', peakEnd: '18' })).peakEnd).toMatch(/different hour/);
  });
});

describe('building the 24 + 24 rates the server stores', () => {
  it('a flat tariff has the same rate in every hour of weekdays and weekends', () => {
    const r = buildRates(flat())!;
    expect(r.weekday_rates).toHaveLength(24);
    expect(r.weekend_rates).toHaveLength(24);
    expect(new Set([...r.weekday_rates, ...r.weekend_rates])).toEqual(new Set([7.5]));
    expect(r.daily_fixed_charge).toBe(0);
  });

  it('a peak window charges the peak rate exactly inside the window (end excluded)', () => {
    const r = buildRates(window())!;
    expect(r.weekday_rates.map((v, h) => (v === 9 ? h : -1)).filter((h) => h >= 0)).toEqual([18, 19, 20, 21]);
    expect(r.weekday_rates.filter((v) => v === 5)).toHaveLength(20);
  });

  it('weekends are off-peak all day unless the peak rate is ticked for weekends', () => {
    expect(new Set(buildRates(window())!.weekend_rates)).toEqual(new Set([5]));
    expect(buildRates(window({ peakOnWeekend: true }))!.weekend_rates).toEqual(buildRates(window())!.weekday_rates);
  });

  it('a window that crosses midnight covers the evening and the early morning', () => {
    const r = buildRates(window({ peakStart: '22', peakEnd: '6' }))!;
    const peakHours = r.weekday_rates.map((v, h) => (v === 9 ? h : -1)).filter((h) => h >= 0);
    expect(peakHours).toEqual([0, 1, 2, 3, 4, 5, 22, 23]);
    expect(inPeakWindow(23, 22, 6)).toBe(true);
    expect(inPeakWindow(6, 22, 6)).toBe(false);
    expect(inPeakWindow(12, 22, 6)).toBe(false);
  });

  it('keeps the fixed charge and refuses to build from an invalid draft', () => {
    expect(buildRates(flat({ fixedCharge: '12.5' }))!.daily_fixed_charge).toBe(12.5);
    expect(buildRates(flat({ flatRate: '' }))).toBeNull();
  });
});

describe('describing a stored tariff', () => {
  it('shows one number for a flat tariff and a range otherwise', () => {
    expect(rateSummary(Array(24).fill(7.5))).toBe('7.5');
    expect(rateSummary([5, 5, 9, 5])).toBe('5 to 9');
    expect(rateSummary([0.12, 0.3])).toBe('0.12 to 0.3');
    expect(rateSummary([])).toBe('–');
  });
});

describe('rupees use Indian digit grouping, other currencies do not', () => {
  it('formats INR with lakh and crore grouping', () => {
    expect(fmtMoney(23126989, 'INR', 0)).toBe('₹2,31,26,989');
    expect(fmtMoney(1234567.5, 'USD', 0)).toBe('$1,234,568');
    expect(fmtMoney(1234.5, 'AED', 1).replace(/\u00a0/g, ' ')).toBe('AED 1,234.5'); // any ISO code is formatted by Intl (with a no-break space)
    expect(fmtMoney(1234.5, 'Rs', 1)).toBe('1,234.5 Rs'); // a symbol or short label is appended as typed
  });
});

describe('browser tab titles', () => {
  it('names the open page and falls back for unknown paths', () => {
    expect(pageTitle('/')).toBe('Society overview · EnergiQ AI');
    expect(pageTitle('/compare')).toBe('Compare communities · EnergiQ AI');
    expect(pageTitle('/cost/')).toBe('Cost and peaks · EnergiQ AI');
    expect(pageTitle('/nope')).toBe('Page not found · EnergiQ AI');
  });
});
