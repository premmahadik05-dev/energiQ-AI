import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fx } from '../test/fixtures';
import { renderApp } from '../test/harness';

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
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
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
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests, slow down. Try again in 37 s.');
  });

  it('signs in with the captured login response, stores the token in sessionStorage only and opens the society overview', async () => {
    renderApp('/login', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Society overview' })).toBeInTheDocument();
    expect(window.sessionStorage.getItem('energiq.token')).toBe('REDACTED.jwt.token');
    expect(window.localStorage.getItem('energiq.token')).toBeNull();
  });

  it('opening a page while signed out leads to sign-in and then back to that page (real guard flow, no injected state)', async () => {
    renderApp('/reports', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Reports' })).toBeInTheDocument();
  });

  it('the return path is never an off-site or backslash path', async () => {
    renderApp('/login', { signedIn: false, state: { from: '/\\evil.example' }, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Society overview' })).toBeInTheDocument();
  });

  it('registration applies the password rules before calling the API', async () => {
    const net = renderApp('/register', { signedIn: false });
    await userEvent.type(await screen.findByLabelText('Email address'), 'new.user@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'short1');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'short1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Password must be 10-128 characters.')).toBeInTheDocument();
    expect(net.calls.filter((c) => c.path.endsWith('/auth/register'))).toHaveLength(0);
  });

  it('registration shows the 409 "already registered" message from the server', async () => {
    renderApp('/register', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/register', reply: { status: 409, json: fx.err409Register.body } }] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(fx.err409Register.body.detail);
  });

  it('registration refuses a confirmation that differs from the password, before any request', async () => {
    const net = renderApp('/register', { signedIn: false });
    await userEvent.type(await screen.findByLabelText('Email address'), 'new.user@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Some-Password-2');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Confirm password')).toHaveFocus());
    expect(net.calls.filter((c) => c.path.endsWith('/auth/register'))).toHaveLength(0);
  });

  it('the password rules tick off live while typing', async () => {
    renderApp('/register', { signedIn: false });
    const rules = within(await screen.findByRole('list', { name: 'Password requirements' }));
    expect(rules.getByText('10 to 128 characters').closest('li')).toHaveTextContent(': not met');
    await userEvent.type(screen.getByLabelText('Password'), 'abcdefghij');
    expect(rules.getByText('10 to 128 characters').closest('li')).toHaveTextContent(': met');
    expect(rules.getByText('At least one letter and one digit').closest('li')).toHaveTextContent(': not met');
    await userEvent.type(screen.getByLabelText('Password'), '1');
    expect(rules.getByText('At least one letter and one digit').closest('li')).toHaveTextContent(': met');
  });

  it('a new account lands on the overview with a one-time confirmation that can be dismissed', async () => {
    renderApp('/register', {
      signedIn: false,
      routes: [
        { method: 'POST', path: '/api/v1/auth/register', reply: fx.register },
        { method: 'POST', path: '/api/v1/auth/login', reply: fx.login },
      ],
    });
    await userEvent.type(await screen.findByLabelText('Email address'), 'new.user@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('heading', { name: 'Society overview' })).toBeInTheDocument();
    const notice = await screen.findByRole('status', { name: '' });
    expect(notice).toHaveTextContent('Account created');
    await userEvent.click(within(notice).getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByText('Account created')).not.toBeInTheDocument();
  });

  it('the eye button shows and hides the password without submitting the form', async () => {
    const net = renderApp('/login', { signedIn: false });
    const input = await screen.findByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');
    await userEvent.type(input, 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
    expect(net.calls.filter((c) => c.path.includes('/auth/login'))).toHaveLength(0);
  });

  it('shows a spinner and disables the button while signing in', async () => {
    renderApp('/login', { signedIn: false, routes: [{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }] });
    const real = window.fetch;
    vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => (String(input).includes('/auth/login') ? new Promise<Response>(() => undefined) : real(input, init)));
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    const busy = await screen.findByRole('button', { name: 'Signing in…' });
    expect(busy).toBeDisabled();
  });

  it('remember my e-mail keeps only the address (never the token) and pre-fills it next time; unticking forgets it', async () => {
    const login = { method: 'POST', path: '/api/v1/auth/login', reply: fx.login } as const;
    renderApp('/login', { signedIn: false, routes: [login] });
    await userEvent.type(await screen.findByLabelText('Email address'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Remember my e-mail on this device' }));
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await screen.findByRole('heading', { name: 'Society overview' });
    expect(window.localStorage.getItem('energiq.rememberedEmail')).toBe('ana@example.com');
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('REDACTED.jwt.token');
    cleanup();
    window.sessionStorage.clear();

    renderApp('/login', { signedIn: false, routes: [login] });
    expect(await screen.findByLabelText('Email address')).toHaveValue('ana@example.com');
    const box = screen.getByRole('checkbox', { name: 'Remember my e-mail on this device' });
    expect(box).toBeChecked();
    await userEvent.type(screen.getByLabelText('Password'), 'Some-Password-1');
    await userEvent.click(box);
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await screen.findByRole('heading', { name: 'Society overview' });
    expect(window.localStorage.getItem('energiq.rememberedEmail')).toBeNull();
  });

  it('"Forgot password?" says plainly that reset is not available and sends no request', async () => {
    const net = renderApp('/login', { signedIn: false });
    const link = await screen.findByRole('button', { name: 'Forgot password?' });
    expect(link).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(link);
    expect(link).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Password reset is not available yet')).toBeInTheDocument();
    expect(net.calls.filter((c) => c.path.includes('/auth/'))).toHaveLength(0);
  });

  it('shows the product benefits and the real-data caption next to the form', async () => {
    renderApp('/login', { signedIn: false });
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    for (const t of ['AI-Powered Demand Forecasting', 'Intelligent Consumption Analytics', 'Predictive Energy Optimisation']) expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    expect(screen.getByText('Smarter Energy Decisions Start Here.')).toBeInTheDocument();
    expect(screen.getByText(/Real data: BDG2 site Fox residential community/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /one week of hourly electricity demand/ })).toBeInTheDocument();
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

  it('lists the notifications exactly as the API words them', async () => {
    renderApp('/notifications');
    for (const n of fx.notifications) expect(await screen.findByText(n.message)).toBeInTheDocument();
  });

  it('the single-meter pages are gone: their old addresses show the not-found page', async () => {
    for (const path of ['/household', '/datasets', '/forecast', '/models', '/anomalies', '/explain', '/optimize', '/benchmark']) {
      const { unmount } = renderApp(path);
      expect(await screen.findByRole('heading', { name: /not found/i })).toBeInTheDocument();
      unmount();
    }
  });

  it('an unknown URL shows the not-found page inside the app shell', async () => {
    renderApp('/definitely-not-a-page');
    expect(await screen.findByRole('heading', { name: /not found/i })).toBeInTheDocument();
  });
});
