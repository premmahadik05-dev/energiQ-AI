import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '../test/harness';
import { fx } from '../test/fixtures';
import { sfx } from '../test/fixtures/society';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('compare communities', () => {
  it('lists every community of the captured comparison with its measured figures and no unmocked request', async () => {
    const net = renderApp('/compare');
    expect(await screen.findByRole('heading', { level: 1, name: 'Compare communities' })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: /Side-by-side figures/ });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(sfx.compare.communities.length);
    for (const c of sfx.compare.communities) {
      const row = rows.find((r) => within(r).queryByText(c.key.charAt(0).toUpperCase() + c.key.slice(1)));
      expect(row, c.key).toBeDefined();
      expect(row).toHaveTextContent(String(Math.round(c.peak_kw ?? 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ','));
    }
    expect(net.unmatched).toEqual([]);
    expect(document.title).toBe('Compare communities · EnergiQ AI');
  });

  it('says what the figures mean and never presents the research communities as housing societies', async () => {
    renderApp('/compare');
    expect(await screen.findByText(/not registered housing societies/)).toBeInTheDocument();
    expect(screen.getByText('Energy use per floor area')).toBeInTheDocument();
    expect(screen.getByText('24-hour forecast error')).toBeInTheDocument();
  });

  it('opens a community in the society overview', async () => {
    renderApp('/compare');
    const table = await screen.findByRole('table', { name: /Side-by-side figures/ });
    const other = sfx.compare.communities.find((c) => c.id !== sfx.societies[0]?.id) ?? sfx.compare.communities[0]!;
    await userEvent.click(within(table).getByRole('button', { name: new RegExp(`Open ${other.key.charAt(0).toUpperCase() + other.key.slice(1)} `) }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Society overview' })).toBeInTheDocument();
    expect(window.sessionStorage.getItem('energiq.activeSociety') ?? '').toBe(String(other.id));
  });

  it('shows the server error with a retry instead of an empty page', async () => {
    renderApp('/compare', { routes: [{ path: '/api/v1/societies/compare', reply: { status: 500, json: { detail: 'compare failed' } } }] });
    expect(await screen.findByRole('alert')).toHaveTextContent('compare failed');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('forecast error analysis', () => {
  it('shows the held-out error figures from the API for the chosen horizon', async () => {
    const net = renderApp('/forecasting');
    expect(await screen.findByText(/Forecast error analysis, 24 hours ahead/)).toBeInTheDocument();
    expect(await screen.findByText('Average error (bias)')).toBeInTheDocument();
    // scoped to the card: the same MAE also appears in the model comparison table below it
    const card = screen.getByRole('region', { name: /Forecast error analysis, 24 hours ahead/ });
    expect(within(card).getByText(`${sfx.errorAnalysis.mae_kw.toFixed(1)} kW`)).toBeInTheDocument();
    expect(screen.getByText(`The ${sfx.errorAnalysis.worst.length} largest errors`)).toBeInTheDocument();
    expect(net.calls.some((c) => c.path.endsWith('/error-analysis') && c.query.get('horizon') === '24')).toBe(true);
  });

  it('asks for the other horizon when the horizon changes', async () => {
    const net = renderApp('/forecasting');
    await screen.findByText(/Forecast error analysis, 24 hours ahead/);
    await userEvent.click(screen.getByLabelText('6 hours'));
    await waitFor(() => expect(net.calls.some((c) => c.path.endsWith('/error-analysis') && c.query.get('horizon') === '6')).toBe(true));
  });
});

describe('peak demand', () => {
  it('draws the load duration curve and the demand distribution, and names the methods behind the peak evaluation', async () => {
    renderApp('/cost');
    await userEvent.click(await screen.findByRole('tab', { name: 'Peak demand' }));
    expect(await screen.findByText('Load duration curve')).toBeInTheDocument();
    expect(screen.getByText('Distribution of hourly demand')).toBeInTheDocument();
    expect(screen.queryByText(/\[object Object\]/)).toBeNull();
    expect(await screen.findByText(/Random forest; mean daily peak/)).toBeInTheDocument();
  });
});

describe('tariff manager', () => {
  const form = () => screen.getByRole('form', { name: 'Add a tariff' });

  it('lists the captured tariffs, marks the one in use and the placeholder', async () => {
    renderApp('/cost');
    const table = await screen.findByRole('table', { name: /Available tariffs/ });
    expect(within(table).getByText('Placeholder')).toBeInTheDocument();
    expect(within(table).getByText('In use')).toBeInTheDocument();
  });

  it('sends nothing and shows what is missing when the form is submitted empty', async () => {
    const net = renderApp('/cost');
    await screen.findByRole('form', { name: 'Add a tariff' });
    await userEvent.click(within(form()).getByRole('button', { name: 'Save tariff' }));
    expect(await within(form()).findByText('Give the tariff a name')).toBeInTheDocument();
    expect(within(form()).getByText(/The rate must be a number/)).toBeInTheDocument();
    expect(net.calls.filter((c) => c.method === 'POST' && c.path.endsWith('/tariffs'))).toHaveLength(0);
  });

  it('posts a peak and off-peak tariff as 24 weekday and 24 weekend rates and selects the new tariff', async () => {
    const created = { ...fx.tariffs[0]!, id: 77, name: 'Time of day', currency: 'INR', is_demo: false };
    const net = renderApp('/cost', { routes: [{ method: 'POST', path: '/api/v1/tariffs', reply: { status: 201, json: created } }] });
    await screen.findByRole('form', { name: 'Add a tariff' });
    const f = within(form());
    await userEvent.type(f.getByLabelText('Name'), 'Time of day');
    await userEvent.click(f.getByLabelText('Peak and off-peak'));
    await userEvent.type(f.getByLabelText('Off-peak rate (INR per kWh)'), '5');
    await userEvent.type(f.getByLabelText('Peak rate (INR per kWh)'), '9');
    await userEvent.clear(f.getByLabelText('Fixed charge per day (INR)'));
    await userEvent.type(f.getByLabelText('Fixed charge per day (INR)'), '12');
    await userEvent.click(f.getByRole('button', { name: 'Save tariff' }));
    await waitFor(() => expect(net.calls.some((c) => c.method === 'POST' && c.path === '/api/v1/tariffs')).toBe(true));
    const body = net.calls.find((c) => c.method === 'POST' && c.path === '/api/v1/tariffs')!.body as { name: string; currency: string; weekday_rates: number[]; weekend_rates: number[]; daily_fixed_charge: number };
    expect(body.name).toBe('Time of day');
    expect(body.currency).toBe('INR');
    expect(body.weekday_rates).toHaveLength(24);
    expect(body.weekday_rates.filter((v) => v === 9)).toHaveLength(4); // 18:00 to 22:00 by default
    expect(body.weekend_rates.every((v) => v === 5)).toBe(true);
    expect(body.daily_fixed_charge).toBe(12);
    expect(await screen.findByText(/Tariff "Time of day" saved and selected\./)).toBeInTheDocument();
    expect(window.sessionStorage.getItem('energiq.societyTariff')).toBe('77');
  });

  it('shows the duplicate-name answer of the server on the name field', async () => {
    renderApp('/cost', { routes: [{ method: 'POST', path: '/api/v1/tariffs', reply: { status: 409, json: { detail: 'You already have a tariff with that name' } } }] });
    await screen.findByRole('form', { name: 'Add a tariff' });
    const f = within(form());
    await userEvent.type(f.getByLabelText('Name'), 'Home');
    await userEvent.type(f.getByLabelText('Rate (INR per kWh)'), '7.5');
    await userEvent.click(f.getByRole('button', { name: 'Save tariff' }));
    expect(await f.findByText('You already have a tariff with this name')).toBeInTheDocument();
  });

  it('asks before deleting and deletes only after the confirmation', async () => {
    const own = { ...fx.tariffs[0]!, id: 5, name: 'Mine', is_demo: false };
    const net = renderApp('/cost', {
      routes: [
        { path: '/api/v1/tariffs', reply: [...fx.tariffs, own] },
        { method: 'DELETE', path: '/api/v1/tariffs/5', reply: { status: 204 } },
      ],
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Delete tariff Mine' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(net.calls.filter((c) => c.method === 'DELETE')).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: 'Delete tariff Mine' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete tariff' }));
    await waitFor(() => expect(net.calls.filter((c) => c.method === 'DELETE' && c.path === '/api/v1/tariffs/5')).toHaveLength(1));
  });

  it('does not offer the placeholder tariff for deletion', async () => {
    renderApp('/cost');
    await screen.findByRole('table', { name: /Available tariffs/ });
    expect(screen.queryByRole('button', { name: /Delete tariff DEMO/ })).toBeNull();
  });

  it('lets a viewer read the tariffs but not add or delete any', async () => {
    renderApp('/cost', { role: 'viewer' });
    await screen.findByRole('table', { name: /Available tariffs/ });
    expect(screen.queryByRole('form', { name: 'Add a tariff' })).toBeNull();
  });
});

describe('sign-in error handling', () => {
  it('clears the old server message as soon as the e-mail or password is edited', async () => {
    renderApp('/login', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: { status: fx.errLogin.status, json: fx.errLogin.body } }] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid e-mail or password');
    await userEvent.type(screen.getByLabelText('Password'), 'x');
    expect(screen.queryByText('Invalid e-mail or password')).toBeNull();
  });

  it('does not show the old server message next to new validation errors', async () => {
    renderApp('/login', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: { status: fx.errLogin.status, json: fx.errLogin.body } }] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await screen.findByText('Invalid e-mail or password');
    await userEvent.clear(screen.getByLabelText('Password'));
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Enter your password.')).toBeInTheDocument();
    expect(screen.queryByText('Invalid e-mail or password')).toBeNull();
  });
});
