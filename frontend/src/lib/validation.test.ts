import { describe, expect, it } from 'vitest';
import { fx } from '../test/fixtures';
import { parseTariffForm, validateEmail, validateFullName, validatePassword, validateSchedule, validateUploadFile, validateUploadForm } from './validation';

describe('e-mail and password rules (mirror the backend)', () => {
  it('accepts normal addresses and rejects malformed ones', () => {
    expect(validateEmail('ana@example.com')).toBeNull();
    expect(validateEmail('  ana@example.com  ')).toBeNull();
    expect(validateEmail('')).toMatch(/Enter your e-mail/);
    for (const bad of ['not-an-email', 'a@b', 'a b@example.com', '@example.com', 'a@@example.com']) expect(validateEmail(bad)).toBe('Enter a valid e-mail address.');
  });

  it('requires 10-128 characters with letters and digits', () => {
    expect(validatePassword('short1')).toMatch(/10-128/);
    expect(validatePassword('x'.repeat(129) + '1')).toMatch(/10-128/);
    expect(validatePassword('onlyletterspassword')).toMatch(/letters and digits/);
    expect(validatePassword('1234567890123')).toMatch(/letters and digits/);
    expect(validatePassword('Tester-Pass-2026')).toBeNull();
  });

  it('rejects common and low-variety passwords the backend would refuse', () => {
    expect(validatePassword('password1234')).toMatch(/too easy/);
    expect(validatePassword('aaaaaaaaa1')).toMatch(/too easy/); // fewer than 5 distinct characters
  });

  it('limits the display name to 120 characters', () => {
    expect(validateFullName('x'.repeat(120))).toBeNull();
    expect(validateFullName('x'.repeat(121))).toMatch(/120/);
  });
});

describe('upload checks', () => {
  it('requires a file with an accepted extension, content and a size under the limit', () => {
    expect(validateUploadFile(null, 50)).toMatch(/Choose a CSV/);
    expect(validateUploadFile({ name: 'meter.exe', size: 10 }, 50)).toMatch(/Only \.csv, \.txt, \.tsv/);
    expect(validateUploadFile({ name: 'noextension', size: 10 }, 50)).toMatch(/Only/);
    expect(validateUploadFile({ name: 'a.csv', size: 0 }, 50)).toMatch(/empty/);
    expect(validateUploadFile({ name: 'a.csv', size: 51 * 1024 * 1024 }, 50)).toMatch(/50 MB/);
    expect(validateUploadFile({ name: 'DATA.CSV', size: 1024 }, 50)).toBeNull();
    expect(validateUploadFile({ name: 'a.tsv', size: 1024 }, 50)).toBeNull();
  });

  it('upload form needs a name, a value column and the right timestamp columns for the chosen layout', () => {
    const base = { name: '', valueColumn: '', mode: 'single' as const, timestampColumn: '', dateColumn: '', timeColumn: '' };
    expect(Object.keys(validateUploadForm(base)).sort()).toEqual(['name', 'timestampColumn', 'valueColumn']);
    expect(Object.keys(validateUploadForm({ ...base, mode: 'split' })).sort()).toEqual(['dateColumn', 'name', 'timeColumn', 'valueColumn']);
    expect(validateUploadForm({ name: 'x', valueColumn: 'kw', mode: 'single', timestampColumn: 'time', dateColumn: '', timeColumn: '' })).toEqual({});
    expect(validateUploadForm({ ...base, name: 'x'.repeat(121), valueColumn: 'kw', timestampColumn: 't' }).name).toMatch(/120/);
  });
});

describe('tariff form', () => {
  const rates = (v: number) => Array.from({ length: 24 }, () => String(v));
  const ok = { name: 'Night saver', currency: 'EUR', dailyFixed: '0.1', weekday: rates(0.2), weekend: rates(0.15) };

  it('builds the exact request body the API expects (24 + 24 numeric rates)', () => {
    const r = parseTariffForm(ok);
    expect(r).toEqual({ value: { name: 'Night saver', currency: 'EUR', daily_fixed_charge: 0.1, weekday_rates: Array(24).fill(0.2), weekend_rates: Array(24).fill(0.15) } });
  });

  it('treats an empty fixed charge as 0 and reports the first bad hour', () => {
    expect(parseTariffForm({ ...ok, dailyFixed: '' })).toMatchObject({ value: { daily_fixed_charge: 0 } });
    const bad = [...ok.weekday];
    bad[7] = '';
    expect(parseTariffForm({ ...ok, weekday: bad })).toEqual({ error: expect.stringContaining('Weekday rates, hour 07:00') });
    expect(parseTariffForm({ ...ok, weekend: [...rates(0.1).slice(1)] })).toEqual({ error: 'Weekend rates needs 24 hourly rates.' });
  });

  it('rejects negative or absurd rates, bad names and currencies', () => {
    expect(parseTariffForm({ ...ok, weekday: rates(-1) })).toHaveProperty('error');
    expect(parseTariffForm({ ...ok, weekday: rates(2_000_000) })).toHaveProperty('error');
    expect(parseTariffForm({ ...ok, name: ' ' })).toEqual({ error: 'Give the tariff a name.' });
    expect(parseTariffForm({ ...ok, currency: 'TOOLONGCUR' })).toHaveProperty('error');
    expect(parseTariffForm({ ...ok, dailyFixed: '-3' })).toHaveProperty('error');
  });

  it('the captured DEMO tariff has the same 24 + 24 shape the form produces', () => {
    const t = fx.tariffs[0];
    expect(t?.weekday_rates).toHaveLength(24);
    expect(t?.weekend_rates).toHaveLength(24);
  });
});

describe('scheduler form', () => {
  it('requires whole hours from 1 to 24 and a positive power up to 1000 kW', () => {
    expect(validateSchedule('3', '2')).toEqual({});
    expect(validateSchedule('0', '2').duration_h).toBeDefined();
    expect(validateSchedule('25', '2').duration_h).toBeDefined();
    expect(validateSchedule('2.5', '2').duration_h).toBeDefined();
    expect(validateSchedule('3', '0').power_kw).toBeDefined();
    expect(validateSchedule('3', '1001').power_kw).toBeDefined();
    expect(validateSchedule('3', 'abc').power_kw).toBeDefined();
  });
});
