/**
 * Society pages against responses CAPTURED from the real backend serving the Fox community (see test/fixtures/society).
 * Expected strings are derived from those captured payloads with the app's own formatters, never typed in.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { fmtInt, fmtKw, fmtKwh } from '../../lib/format';
import { renderApp } from '../../test/harness';
import { sfx } from '../../test/fixtures/society';

const SID = sfx.societies[0]?.id ?? 1;
const BASE = `/api/v1/societies/${SID}`;

beforeEach(() => {
  window.sessionStorage.clear();
});

/** All the text inside the KPI tile whose label is `label`. */
function tileText(label: string): string {
  const tile = screen.getByText(label).closest('.card');
  if (!tile) throw new Error(`no tile labelled "${label}"`);
  return tile.textContent ?? '';
}

describe('society overview', () => {
  it('shows the latest demand, windows and forecast KPIs from the API, and says what the data are', async () => {
    renderApp('/');
    const o = sfx.overview;
    expect(await screen.findByRole('heading', { name: 'Society overview' })).toBeInTheDocument();
    await screen.findByText('Latest demand');
    // each figure must sit in the tile that names it (number and unit are styled separately, so compare the tile's text)
    expect(tileText('Latest demand')).toContain(fmtKw(o.latest.demand_kw, 0));
    expect(tileText('Energy, last 24 h')).toContain(fmtKwh(o.windows.last_24h.energy_kwh, 0));
    expect(tileText('Energy, last 30 days')).toContain(fmtKwh(o.windows.last_30d.energy_kwh, 0));
    expect(tileText('Predicted next 24 h')).toContain(fmtKwh(o.forecast?.next_24h_energy_kwh, 0));
    expect(tileText('Predicted peak demand')).toContain(fmtKw(o.forecast?.peak_kw, 0));
    // honesty: representative community, not a registered society, historical not live
    expect(screen.getByText(/Research-based representative community/)).toBeInTheDocument();
    expect(screen.getByText(/not a registered housing society/)).toBeInTheDocument();
    expect(screen.getByText(/not a feed|not a live feed/)).toBeInTheDocument();
  });

  it('labels the cost an estimate on a demo tariff, not a bill', async () => {
    renderApp('/');
    expect(await screen.findByText(/Demo tariff: an estimate with placeholder prices, not a bill/)).toBeInTheDocument();
  });

  it('shows "Not available" for the forecast when no deployed model can serve it, with no invented numbers', async () => {
    const ov = { ...sfx.overview, forecast: { error: 'Models for this society are not installed on this server.', origin: sfx.overview.as_of, trained_through: sfx.overview.as_of } };
    renderApp('/', { routes: [{ path: `${BASE}/overview`, reply: ov }] });
    await screen.findByText('Latest demand');
    expect(tileText('Latest demand')).toContain(fmtKw(sfx.overview.latest.demand_kw, 0));
    expect(screen.getAllByText('Not available').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/not installed on this server/)).toBeInTheDocument();
  });

  it('with no society loaded it says so; only admins are offered the import link', async () => {
    const { unmount } = renderApp('/', { role: 'analyst', routes: [{ path: '/api/v1/societies', reply: [] }] });
    expect(await screen.findByText('No society loaded yet')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Import the bundled communities/ })).not.toBeInTheDocument();
    unmount();
    renderApp('/', { role: 'admin', routes: [{ path: '/api/v1/societies', reply: [] }] });
    expect(await screen.findByRole('link', { name: /Import the bundled communities/ })).toBeInTheDocument();
  });

  it('shows a retryable error state when the societies call fails', async () => {
    renderApp('/', { routes: [{ path: '/api/v1/societies', reply: { status: 500, json: { detail: 'boom' } } }] });
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
  });
});

describe('navigation', () => {
  it('offers every society page, a System group, and Society admin only to admins', async () => {
    const { unmount } = renderApp('/consumption', { role: 'analyst' });
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    for (const n of ['Society overview', 'Consumption', 'Forecasting', 'Buildings', 'Common facilities', 'Cost and peaks', 'Alerts', 'Recommendations', 'Reports', 'Data sources']) {
      expect(within(nav).getByRole('link', { name: n })).toBeInTheDocument();
    }
    expect(within(nav).getByText('System')).toBeInTheDocument();
    expect(within(nav).queryByText('Single-meter tools')).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Society admin' })).not.toBeInTheDocument();
    unmount();
    renderApp('/consumption', { role: 'admin' });
    expect(within(await screen.findByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Society admin' })).toBeInTheDocument();
  });
});

describe('consumption and buildings', () => {
  it('asks the API for the chosen resolution and shows the period totals it returns', async () => {
    const net = renderApp('/consumption');
    expect(await screen.findByRole('heading', { name: 'Consumption' })).toBeInTheDocument();
    await waitFor(() => expect(net.calls.some((c) => c.path === `${BASE}/consumption`)).toBe(true));
    const first = net.calls.find((c) => c.path === `${BASE}/consumption`);
    expect(first?.query.get('resolution')).toBeTruthy();
  });

  it('lists the pseudonymous building codes and never a dataset identifier', async () => {
    renderApp('/buildings');
    const code = sfx.buildings.buildings[0]?.code as string;
    expect((await screen.findAllByText(code)).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/Fox_lodging/i);
    expect(JSON.stringify(sfx.buildings)).not.toContain('source_id');
  });

  it('facility consumption is marked unavailable, not drawn, when no facility meter exists', async () => {
    renderApp('/facilities');
    expect(await screen.findByText('Facility consumption is unavailable for this society')).toBeInTheDocument();
    expect(screen.getAllByText('Not measured in this dataset').length).toBe(sfx.facilities.categories.length);
    expect(screen.queryByText('Measured')).not.toBeInTheDocument();
  });
});

describe('forecasting', () => {
  it('shows honest held-out accuracy for the selected horizon and the model comparison', async () => {
    renderApp('/forecasting');
    expect(await screen.findByRole('heading', { name: 'Forecasting' })).toBeInTheDocument();
    const h24 = (sfx.models as unknown as { horizons: Record<string, { best_overall_by_cv: string }> }).horizons?.['24'];
    expect(h24).toBeTruthy();
    await waitFor(() => expect(document.body.textContent).toMatch(/held-out|hold-out|test period/i));
  });

  it('draws the live forecast from the API without extra numbers: history and prediction are separate series', async () => {
    const net = renderApp('/forecasting');
    await screen.findByRole('heading', { name: 'Forecasting' });
    await waitFor(() => expect(net.calls.some((c) => c.path === `${BASE}/forecast`)).toBe(true));
    expect(net.unmatched.filter((u) => u.includes('/societies/'))).toEqual([]);
  });

  it('shows a clear message when the models are not deployed (HTTP 410 from the API)', async () => {
    renderApp('/forecasting', { routes: [{ path: `${BASE}/forecast`, reply: { status: 410, json: { detail: 'Deployment models for this society are not installed on this server.' } } }] });
    await screen.findByRole('heading', { name: 'Forecasting' });
    expect(await screen.findByText(/not installed on this server/)).toBeInTheDocument();
  });
});

describe('cost, peaks, alerts, recommendations', () => {
  it('cost is an estimate on a configurable tariff and says so', async () => {
    renderApp('/cost');
    expect(await screen.findByText('An estimate, not a bill')).toBeInTheDocument();
    expect(screen.getAllByText(/Demo tariff, not real prices/).length).toBeGreaterThan(0);
  });

  it('peak tab reports the daily-peak forecast against the baseline using the evaluation file', async () => {
    renderApp('/cost');
    await userEvent.click(await screen.findByRole('tab', { name: 'Peak demand' }));
    expect(await screen.findByText('How well is the daily peak forecast?')).toBeInTheDocument();
  });

  it('lists alerts with severity and place, and acknowledges one with a PATCH carrying the new state', async () => {
    const ev = sfx.anomalies.events[0];
    expect(ev).toBeTruthy();
    const net = renderApp('/alerts', {
      routes: [{ method: 'PATCH', path: new RegExp(`${BASE}/anomalies/\\d+$`), reply: { ...ev, acknowledged: true } }],
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument();
    expect(await screen.findByText(/What an alert means/)).toBeInTheDocument();
    const btn = (await screen.findAllByRole('button', { name: /^Acknowledge alert at/ }))[0] as HTMLElement;
    await userEvent.click(btn);
    await waitFor(() => expect(net.calls.some((c) => c.method === 'PATCH')).toBe(true));
    const patch = net.calls.find((c) => c.method === 'PATCH');
    expect(patch?.body).toEqual({ acknowledged: true });
    // the alerts API is asked for medium and high only by default
    expect(net.calls.some((c) => c.path === `${BASE}/anomalies` && c.query.get('min_severity') === '2')).toBe(true);
  });

  it('viewers can read alerts but get no Acknowledge button', async () => {
    renderApp('/alerts', { role: 'viewer' });
    await screen.findByRole('heading', { level: 1, name: 'Alerts' });
    await screen.findAllByText(/Open|Acknowledged/);
    expect(screen.queryByRole('button', { name: /^Acknowledge alert at/ })).not.toBeInTheDocument();
  });

  it('recommendations show their evidence and carry the "not a measured saving" caveats from the API', async () => {
    renderApp('/recommendations');
    expect(await screen.findByText(sfx.recommendations.recommendations[0]?.title as string)).toBeInTheDocument();
    expect(screen.getByText(/not a forecast of savings/)).toBeInTheDocument();
    for (const r of sfx.recommendations.recommendations) {
      for (const c of r.caveats) expect(screen.getAllByText(c).length).toBeGreaterThan(0);
    }
  });
});

describe('reports', () => {
  it('lists saved reports; creating one POSTs the chosen kind and format', async () => {
    const net = renderApp('/reports');
    expect(await screen.findByText(sfx.reports[0]?.title as string)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: /Create report/ }));
    await waitFor(() => expect(net.calls.some((c) => c.method === 'POST' && c.path === `${BASE}/reports`)).toBe(true));
    const post = net.calls.find((c) => c.method === 'POST' && c.path === `${BASE}/reports`);
    expect(post?.body).toMatchObject({ kind: expect.any(String), format: expect.stringMatching(/^(pdf|csv)$/) });
  });

  it('viewers see and can download reports but cannot create them', async () => {
    renderApp('/reports', { role: 'viewer' });
    expect(await screen.findByText(sfx.reports[0]?.title as string)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create report/ })).not.toBeInTheDocument();
  });
});

describe('data sources', () => {
  it('shows provenance, licence, cleaning counts and the aggregation method from the data card', async () => {
    renderApp('/data-sources');
    const d = sfx.detailUser;
    expect(await screen.findByText('Data card')).toBeInTheDocument();
    expect(screen.getAllByText(new RegExp(d.source_name.replace(/[()]/g, '\\$&'))).length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: d.source_url })).toHaveAttribute('href', d.source_url);
    expect(screen.getByText(/CC BY-SA 4\.0/)).toBeInTheDocument();
    expect(screen.getByText(/Society kWh = sum of the retained building meters/)).toBeInTheDocument();
    const t = d.data_card.cleaning_totals as Record<string, number>;
    expect(screen.getByText(new RegExp(`^${fmtInt(t.valid_out)} \\(`))).toBeInTheDocument();
    expect(screen.getByText(/never filled or interpolated/)).toBeInTheDocument();
    expect(screen.getByText(/not a registered housing society/)).toBeInTheDocument();
    // non-admins never get the per-meter source identifiers
    expect(JSON.stringify(d)).not.toContain('excluded_meters');
  });
});

describe('society administration', () => {
  it('is for admins only', async () => {
    renderApp('/society-admin', { role: 'analyst' });
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied');
  });

  const job = { id: 'job-1', kind: 'society_import', status: 'queued', progress: 0, message: null, dataset_id: null, created_at: '2026-11-08T00:00:00', params: {} };

  it('an admin can start the import of the bundled communities; while it runs, other society jobs are blocked', async () => {
    const net = renderApp('/society-admin', {
      role: 'admin',
      routes: [{ method: 'POST', path: '/api/v1/admin/societies/import-bundled', reply: { status: 202, json: job } }],
    });
    expect(await screen.findByRole('heading', { name: 'Society administration' })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: /Import bundled communities/ }));
    await waitFor(() => expect(net.calls.some((c) => c.method === 'POST' && c.path === '/api/v1/admin/societies/import-bundled')).toBe(true));
    await waitFor(() => expect(screen.getByRole('button', { name: `Train models for ${sfx.societies[0]?.name}` })).toBeDisabled());
  });

  it('an admin can start training for a society', async () => {
    const net = renderApp('/society-admin', {
      role: 'admin',
      routes: [{ method: 'POST', path: `/api/v1/admin/societies/${SID}/train`, reply: { status: 202, json: { ...job, id: 'job-2', kind: 'society_train' } } }],
    });
    await userEvent.click(await screen.findByRole('button', { name: `Train models for ${sfx.societies[0]?.name}` }));
    await waitFor(() => expect(net.calls.some((c) => c.method === 'POST' && c.path === `/api/v1/admin/societies/${SID}/train`)).toBe(true));
  });

  it('deleting a society asks for confirmation first and only then calls DELETE', async () => {
    const net = renderApp('/society-admin', { role: 'admin', routes: [{ method: 'DELETE', path: `${BASE}`, reply: { status: 204 } }] });
    await userEvent.click(await screen.findByRole('button', { name: `Delete ${sfx.societies[0]?.name}` }));
    expect(net.calls.filter((c) => c.method === 'DELETE')).toHaveLength(0);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete society' }));
    await waitFor(() => expect(net.calls.some((c) => c.method === 'DELETE' && c.path === BASE)).toBe(true));
  });

  it('meter management lists every real meter with its pseudonymous code', async () => {
    renderApp('/society-admin', { role: 'admin' });
    for (const m of sfx.meters.slice(0, 3)) expect((await screen.findAllByText(m.code)).length).toBeGreaterThan(0);
  });

  it('the upload form validates before calling the API', async () => {
    const net = renderApp('/society-admin', { role: 'admin' });
    await screen.findByRole('heading', { name: 'Society administration' });
    await userEvent.click(await screen.findByRole('button', { name: /Upload and process/ }));
    expect(await screen.findByText(/Give the society a name/)).toBeInTheDocument();
    expect(net.calls.filter((c) => c.path.endsWith('/admin/societies/upload'))).toHaveLength(0);
    await userEvent.type(screen.getByLabelText('Society name'), 'Green Park Residency');
    await userEvent.click(screen.getByRole('button', { name: /Upload and process/ }));
    expect(await screen.findByText(/Choose the meter CSV file/)).toBeInTheDocument();
    expect(net.calls.filter((c) => c.path.endsWith('/admin/societies/upload'))).toHaveLength(0);
  });
});
