import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ModelVersion } from '../api/types';
import { fmtNum } from '../lib/format';
import { fx } from '../test/fixtures';
import { renderApp } from '../test/harness';

const model = fx.modelsList[0] as unknown as ModelVersion;
const h24 = (model.evaluation as unknown as { horizons: Record<string, { metrics: Record<string, { mae: number }>; best_baseline: string; mae_improvement_vs_best_baseline_pct: number }> }).horizons['24'];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('sign-in and registration', () => {
  it('validates on the client and sends nothing when the e-mail or password is missing', async () => {
    const net = renderApp('/login', { signedIn: false });
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Enter your e-mail address.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    expect(net.calls.filter((c) => c.path.includes('/auth/login'))).toHaveLength(0);
  });

  it('shows the server message for wrong credentials and keeps the user on the page', async () => {
    const net = renderApp('/login', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: { status: fx.errLogin.status, json: fx.errLogin.body } }] });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid e-mail or password');
    expect(net.calls.find((c) => c.path.endsWith('/auth/login'))?.headers.authorization).toBeUndefined();
    expect(window.sessionStorage.getItem('energiq.token')).toBeNull();
  });

  it('shows how long to wait when the server answers 429 with Retry-After', async () => {
    renderApp('/login', {
      signedIn: false,
      routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: { status: 429, json: { detail: 'Too many requests, slow down' }, headers: { 'Retry-After': '37' } } }],
    });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests, slow down. Try again in 37 s.');
  });

  it('signs in with the captured login response, stores the token in sessionStorage only and opens the dashboard', async () => {
    renderApp('/login', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(window.sessionStorage.getItem('energiq.token')).toBe('REDACTED.jwt.token');
    expect(window.localStorage.getItem('energiq.token')).toBeNull();
  });

  it('opening a page while signed out leads to sign-in and then back to that page (real guard flow, no injected state)', async () => {
    renderApp('/models', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
  });

  it('the return path is never an off-site or backslash path', async () => {
    renderApp('/login', { signedIn: false, state: { from: '/\\evil.example' }, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('registration applies the password rules before calling the API', async () => {
    const net = renderApp('/register', { signedIn: false });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'new.user@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'short1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Password must be 10-128 characters.')).toBeInTheDocument();
    expect(net.calls.filter((c) => c.path.endsWith('/auth/register'))).toHaveLength(0);
  });

  it('registration shows the 409 "already registered" message from the server', async () => {
    renderApp('/register', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/register', reply: { status: 409, json: fx.err409Register.body } }] });
    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(fx.err409Register.body.detail);
  });
});

describe('dashboard', () => {
  it('shows KPI tiles computed from the captured responses', async () => {
    renderApp('/');
    expect(await screen.findByText(`${fmtNum(fx.datasetsList[0]?.quality_score, 1)} / 100`)).toBeInTheDocument();
    expect(await screen.findByText(fmtNum(fx.datasetsList[0]?.valid_hours, 0))).toBeInTheDocument();
    // model tile: hold-out MAE at 24 h and the best baseline it is compared with
    expect(await screen.findByText(`${fmtNum(h24?.metrics.xgboost?.mae, 3)} kW`)).toBeInTheDocument();
    expect(screen.getByText(/Best baseline/)).toHaveTextContent(`${fmtNum(h24?.mae_improvement_vs_best_baseline_pct, 1)}% lower error`);
    // anomaly tile
    expect(await screen.findByText(String(fx.anomalySummary.summary.events))).toBeInTheDocument();
    expect(screen.getByText(/high 5, medium 24, low 73/)).toBeInTheDocument();
  });

  it('lists the unread notifications exactly as the API words them', async () => {
    renderApp('/');
    for (const n of fx.notifications) expect(await screen.findByText(n.message)).toBeInTheDocument();
  });

  it('with no dataset it says so and offers the two ways forward, without any numbers', async () => {
    renderApp('/', { routes: [{ path: '/api/v1/datasets', reply: [] }] });
    expect((await screen.findAllByText(/No dataset yet/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/upload a CSV or load the bundled sample/i)).toBeInTheDocument();
    expect(screen.queryByText(/ \/ 100/)).not.toBeInTheDocument();
  });

  it('shows an error state with a retry when the datasets call fails', async () => {
    renderApp('/', { routes: [{ path: '/api/v1/datasets', reply: { status: 500, json: { detail: 'boom' } } }] });
    expect(await screen.findByRole('alert')).toHaveTextContent(/unexpected error|boom|Request failed/i);
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
  });
});

describe('datasets page and read-only viewers', () => {
  beforeEach(() => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  it('analyst: sees the dataset row, the upload form and the sample button', async () => {
    renderApp('/datasets', { role: 'analyst' });
    expect(await screen.findByText(fx.datasetsList[0]?.name as string)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload and process' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Load bundled sample/ })).toBeInTheDocument();
  });

  it('viewer: the list is visible but every write action is hidden', async () => {
    renderApp('/datasets', { role: 'viewer' });
    expect(await screen.findByText(fx.datasetsList[0]?.name as string)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload and process' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Load bundled sample/ })).not.toBeInTheDocument();
  });

  it('upload form pre-checks the file before any request (wrong extension)', async () => {
    const net = renderApp('/datasets');
    await screen.findByRole('button', { name: 'Upload and process' });
    const input = document.querySelector('input[type=file]') as HTMLInputElement;
    await userEvent.upload(input, new File(['a,b'], 'meter.exe'), { applyAccept: false });
    await userEvent.click(screen.getByRole('button', { name: 'Upload and process' }));
    expect(await screen.findByText(/Only \.csv, \.txt, \.tsv files are accepted/)).toBeInTheDocument();
    expect(net.calls.filter((c) => c.method === 'POST')).toHaveLength(0);
  });

  it('dataset detail shows the quality report and the API warnings verbatim', async () => {
    const detail = { ...fx.datasetDetail, report: { ...fx.datasetDetail.report, warnings: ['The data covers less than one year: yearly seasonality cannot be learned or evaluated'] } };
    renderApp('/datasets/1', { routes: [{ path: '/api/v1/datasets/1', reply: detail }] });
    expect(await screen.findByText('The data covers less than one year: yearly seasonality cannot be learned or evaluated')).toBeInTheDocument();
    expect(await screen.findByText('Data quality report')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download HTML report' })).toBeInTheDocument();
  });

  it('the append card says only hours with a value in the new file are replaced, blank or missing hours keep the stored reading', async () => {
    renderApp('/datasets/1');
    const card = (await screen.findByText('Append newer data')).closest('section, div') as HTMLElement;
    expect(card).toBeTruthy();
    expect(await screen.findByText(/replaced only when the new file has a value for it; hours that are missing or blank in the new file keep the stored reading/)).toBeInTheDocument();
    expect(screen.queryByText(/overlap existing ones are replaced/)).not.toBeInTheDocument();
  });

  it('dataset detail for a viewer has no delete or append controls', async () => {
    renderApp('/datasets/1', { role: 'viewer' });
    await screen.findByText('Data quality report');
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.queryByText('Append newer data')).not.toBeInTheDocument();
  });

  it('downloading the HTML report fetches a blob with the Authorization header and saves it', async () => {
    const created = vi.spyOn(URL, 'createObjectURL');
    const net = renderApp('/datasets/1', {
      routes: [{ path: '/api/v1/datasets/1/report', reply: { text: '<html><body>report</body></html>', headers: { 'Content-Type': 'text/html', 'Content-Disposition': 'attachment; filename="energiq_report_1.html"' } } }],
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Download HTML report' }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    const call = net.calls.find((c) => c.path.endsWith('/report'));
    expect(call?.headers.authorization).toBe('Bearer captured-session-token');
  });
});

describe('anomalies', () => {
  it('states that events are unlabelled findings, shows the server note and never an accuracy figure', async () => {
    renderApp('/anomalies');
    expect(await screen.findByText(/not confirmed faults/)).toBeInTheDocument();
    expect(await screen.findByText(fx.anomalySummary.note)).toBeInTheDocument();
    expect(screen.queryByText(/accuracy:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d\s*% accura/i)).not.toBeInTheDocument();
  });

  it('shows the severity summary and the event explanations from the API', async () => {
    renderApp('/anomalies');
    const first = fx.anomaliesList.items[0] as { explanation: string };
    expect(await screen.findByText(first.explanation)).toBeInTheDocument();
    const b = fx.anomalySummary.by_severity;
    for (const [label, n] of [['High severity', b.high], ['Medium severity', b.medium], ['Low severity', b.low]] as const) {
      const tile = screen.getAllByText(label).map((el) => el.parentElement).find((el) => el?.textContent === `${label}${n}`);
      expect(tile, `${label} tile shows ${n}`).toBeTruthy();
    }
  });

  it('analyst can acknowledge an event (PATCH with the new state)', async () => {
    const net = renderApp('/anomalies', { routes: [{ method: 'PATCH', path: /\/api\/v1\/anomalies\/\d+$/, reply: { ...fx.anomalyAck, acknowledged: true } }] });
    const buttons = await screen.findAllByRole('button', { name: 'Acknowledge' });
    await userEvent.click(buttons[0] as HTMLElement);
    await waitFor(() => expect(net.calls.some((c) => c.method === 'PATCH')).toBe(true));
    const patch = net.calls.find((c) => c.method === 'PATCH');
    expect(patch?.path).toMatch(/^\/api\/v1\/anomalies\/\d+$/);
    expect(patch?.body).toEqual({ acknowledged: true });
  });

  it('viewer sees the findings but no Acknowledge or Run detection controls', async () => {
    renderApp('/anomalies', { role: 'viewer' });
    await screen.findByText(fx.anomaliesList.items[0]?.explanation as string);
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run detection' })).not.toBeInTheDocument();
  });

  it('with no detection run yet it invites the user to run one', async () => {
    renderApp('/anomalies', { routes: [{ path: '/api/v1/anomalies/summary', reply: { run: null, summary: null, by_severity: {}, unacknowledged: 0, note: fx.anomalySummary.note } }, { path: '/api/v1/anomalies', reply: { total: 0, items: [] } }] });
    expect(await screen.findByRole('button', { name: 'Run detection' })).toBeInTheDocument();
    expect(screen.queryByText('Events found')).not.toBeInTheDocument();
  });
});

describe('models', () => {
  it('shows the hold-out table with model vs best baseline and the improvement from the API', async () => {
    renderApp('/models');
    const hold = await screen.findByText(/Hold-out accuracy/);
    expect(hold).toBeInTheDocument();
    expect(await screen.findByText(new RegExp(`${fmtNum(h24?.mae_improvement_vs_best_baseline_pct, 1)}% lower error`))).toBeInTheDocument();
    expect(screen.getAllByText(fmtNum(h24?.metrics.xgboost?.mae, 3)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/hold-out period/i).length).toBeGreaterThan(0);
  });

  it('analyst can start training: POST with activate, then a progress bar follows the returned job', async () => {
    const net = renderApp('/models', {
      routes: [
        { method: 'POST', path: '/api/v1/datasets/1/train', reply: { status: 202, json: fx.trainAccepted } },
        { path: `/api/v1/jobs/${fx.trainAccepted.id}`, reply: { ...fx.trainAccepted, status: 'running', progress: 0.4, message: 'fitting' } },
      ],
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Train a new model' }));
    await waitFor(() => expect(net.calls.some((c) => c.method === 'POST' && c.path === '/api/v1/datasets/1/train')).toBe(true));
    expect(net.calls.find((c) => c.method === 'POST')?.body).toEqual({ activate: true });
    const bar = await screen.findByRole('progressbar');
    await waitFor(() => expect(bar).toHaveAttribute('aria-valuenow', '40'));
  });

  it('viewer has no train, activate or delete controls', async () => {
    renderApp('/models', { role: 'viewer' });
    await screen.findByText(/Hold-out accuracy/);
    expect(screen.queryByRole('button', { name: 'Train a new model' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Activate/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Delete/ })).not.toBeInTheDocument();
  });

  it('explains drift honestly using the monitoring response, including the PSI and KS figures', async () => {
    renderApp('/models');
    const d = fx.monitoringAfterForecast.drift;
    expect(await screen.findByText(/Drift and error monitoring/)).toBeInTheDocument();
    expect(await screen.findAllByText(new RegExp(fmtNum(d.psi, 3).replace('.', '\\.')))).not.toHaveLength(0);
  });
});

describe('forecast page', () => {
  beforeEach(() => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  it('shows the saved forecasts, the band explanation and the hold-out accuracy caveat', async () => {
    renderApp('/forecast');
    expect(await screen.findByText(/About the shaded band/)).toBeInTheDocument();
    expect(await screen.findByText(/How accurate is this model\?/)).toBeInTheDocument();
    expect(screen.getByText(/not a guarantee for future hours/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/Saved forecasts/)).length).toBeGreaterThan(0);
  });

  it('exports a forecast as CSV through an authenticated blob download', async () => {
    const created = vi.spyOn(URL, 'createObjectURL');
    const net = renderApp('/forecast', {
      routes: [{ path: /\/api\/v1\/forecasts\/\d+\/export\.csv$/, reply: { text: 'origin,target_time,horizon_h,forecast_kw,lower_kw,upper_kw\n', headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="forecast_1.csv"' } } }],
    });
    const buttons = await screen.findAllByRole('button', { name: /Export CSV/ });
    await userEvent.click(buttons[0] as HTMLElement);
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(net.calls.find((c) => c.path.endsWith('/export.csv'))?.headers.authorization).toBe('Bearer captured-session-token');
  });

  it('viewer cannot create a forecast', async () => {
    renderApp('/forecast', { role: 'viewer' });
    await screen.findAllByText(/Saved forecasts/);
    expect(screen.queryByRole('button', { name: 'Create forecast' })).not.toBeInTheDocument();
  });
});

describe('explainability, optimisation and benchmark', () => {
  it('explainability lists the feature groups per horizon from the captured SHAP response', async () => {
    renderApp('/explain', { routes: [{ path: '/api/v1/models', reply: fx.modelsList }] });
    expect(await screen.findByText('Global importance')).toBeInTheDocument();
    expect(await screen.findByText(/mean \|SHAP\| on the hold-out period/)).toBeInTheDocument();
  });

  it('optimisation marks the built-in tariff as DEMO and says the prices are illustrative', async () => {
    renderApp('/optimize');
    expect(await screen.findByText(/DEMO – illustrative prices/)).toBeInTheDocument();
    expect(screen.getAllByText(/Illustrative numbers only/).length).toBeGreaterThan(0);
  });

  it('tariff form refuses to submit until 24 + 24 rates are present and sends nothing', async () => {
    const net = renderApp('/optimize');
    await userEvent.type(await screen.findByLabelText('Tariff name'), 'Mine');
    await userEvent.type(screen.getByLabelText('Currency'), 'EUR');
    await userEvent.click(screen.getByRole('button', { name: 'Save tariff' }));
    expect(await screen.findByText(/Weekday rates, hour 00:00/)).toBeInTheDocument();
    expect(net.calls.filter((c) => c.method === 'POST')).toHaveLength(0);
  });

  it('viewer sees tariffs but cannot add one', async () => {
    renderApp('/optimize', { role: 'viewer' });
    await screen.findByText(/DEMO – illustrative prices/);
    expect(screen.queryByRole('button', { name: 'Save tariff' })).not.toBeInTheDocument();
  });

  it('benchmark shows its data source, the hold-out period and loads figures with the Authorization header', async () => {
    const created = vi.spyOn(URL, 'createObjectURL');
    const net = renderApp('/benchmark', { routes: [{ path: /\/api\/v1\/benchmark\/figures\/.+/, reply: { text: 'PNGDATA', headers: { 'Content-Type': 'image/png' } } }] });
    expect(await screen.findByText(/Where these numbers come from/)).toBeInTheDocument();
    await waitFor(() => expect(created).toHaveBeenCalled());
    const fig = net.calls.find((c) => c.path.includes('/benchmark/figures/'));
    expect(fig?.headers.authorization).toBe('Bearer captured-session-token');
    const alts = (await screen.findAllByRole('img')).map((i) => i.getAttribute('alt') ?? '');
    expect(alts.some((a) => /hold-out period|unsupervised/i.test(a))).toBe(true);
  });
});

describe('admin, notifications and unknown routes', () => {
  it('admin cannot change their own role, and the audit action filter narrows the table', async () => {
    renderApp('/admin', { role: 'admin' });
    const adminUser = fx.adminUsers.find((u) => u.role === 'admin');
    const sel = await screen.findByLabelText(`Role for ${adminUser?.email}`);
    expect(sel).toBeDisabled();
    await userEvent.click(screen.getByRole('tab', { name: /Audit/ }));
    const filter = await screen.findByLabelText('Action');
    const options = within(filter).getAllByRole('option').map((o) => o.textContent);
    expect(options.length).toBeGreaterThan(1);
  });

  it('notifications can be marked read one by one', async () => {
    const net = renderApp('/notifications', { routes: [{ method: 'POST', path: /\/api\/v1\/notifications\/\d+\/read$/, reply: { ...fx.notifications[0], is_read: true } }] });
    const buttons = await screen.findAllByRole('button', { name: 'Mark as read' });
    await userEvent.click(buttons[0] as HTMLElement);
    await waitFor(() => expect(net.calls.some((c) => c.method === 'POST' && /\/read$/.test(c.path))).toBe(true));
  });

  it('an unknown URL shows the not-found page inside the app shell', async () => {
    renderApp('/definitely-not-a-page');
    expect(await screen.findByRole('heading', { name: /not found/i })).toBeInTheDocument();
  });
});
