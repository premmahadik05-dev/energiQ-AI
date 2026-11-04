import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Role } from '../api/types';
import { appRoutes, mockFetch, renderApp, ROUTER_FUTURE, signIn, userFor } from '../test/harness';
import { fx } from '../test/fixtures';
import { AuthProvider, useAuth } from './AuthContext';
import { PublicOnly, RequireAuth, RequireRole, WriteOnly } from './guards';
import { clearToken, getToken, resetTokenStoreForTests, setToken } from './tokenStore';

describe('token storage', () => {
  it('keeps the token in sessionStorage only, never in localStorage', () => {
    setToken('tok-1');
    expect(window.sessionStorage.getItem('energiq.token')).toBe('tok-1');
    expect(window.localStorage.getItem('energiq.token')).toBeNull();
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('tok-1');
    expect(getToken()).toBe('tok-1');
  });

  it('survives a reload of the tab (memory copy dropped, sessionStorage kept)', () => {
    setToken('tok-2');
    resetTokenStoreForTests();
    expect(getToken()).toBe('tok-2');
  });

  it('clearToken wipes both the memory copy and sessionStorage', () => {
    setToken('tok-3');
    clearToken();
    expect(getToken()).toBeNull();
    expect(window.sessionStorage.getItem('energiq.token')).toBeNull();
  });

  it('works without storage (blocked site data): the token stays in memory', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => setToken('tok-4')).not.toThrow();
    expect(getToken()).toBe('tok-4');
    spy.mockRestore();
  });
});

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('AuthProvider', () => {
  beforeEach(() => resetTokenStoreForTests());
  afterEach(() => vi.unstubAllGlobals());

  it('starts anonymous without a token and makes no request', () => {
    const net = mockFetch([]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.status).toBe('anonymous');
    expect(net.calls).toHaveLength(0);
  });

  it('login stores the token and the user; the token is sent on the next request', async () => {
    const net = mockFetch([{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }, { path: '/api/v1/auth/me', reply: fx.me }]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login('  ana@example.com ', 'Some-Password-1');
    });
    expect(result.current.status).toBe('authenticated');
    expect(result.current.user?.email).toBe('ana@example.com');
    expect(window.sessionStorage.getItem('energiq.token')).toBe('REDACTED.jwt.token');
    expect(net.calls[0]?.body).toEqual({ email: 'ana@example.com', password: 'Some-Password-1' });
    expect(net.calls[0]?.headers.authorization).toBeUndefined();
  });

  it('logout clears the token and the user', async () => {
    mockFetch([{ method: 'POST', path: '/api/v1/auth/login', reply: fx.login }]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login('ana@example.com', 'Some-Password-1');
    });
    act(() => result.current.logout());
    expect(result.current.status).toBe('anonymous');
    expect(result.current.user).toBeNull();
    expect(window.sessionStorage.getItem('energiq.token')).toBeNull();
    expect(result.current.sessionExpired).toBe(false);
  });

  it('a 401 on any authenticated request signs the user out and flags the session as expired', async () => {
    signIn('stale-token');
    const net = mockFetch([{ path: '/api/v1/auth/me', reply: fx.me }, { path: '/api/v1/datasets', reply: { status: 401, json: { detail: 'Invalid token' } } }]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('authenticated'));
    expect(net.calls[0]?.headers.authorization).toBe('Bearer stale-token');
    const { datasetApi } = await import('../api/endpoints');
    await act(async () => {
      await datasetApi.list().catch(() => undefined);
    });
    await waitFor(() => expect(result.current.status).toBe('anonymous'));
    expect(result.current.sessionExpired).toBe(true);
    expect(window.sessionStorage.getItem('energiq.token')).toBeNull();
    expect(getToken()).toBeNull();
  });

  it('drops a stored token the server no longer accepts (me fails) without claiming expiry', async () => {
    signIn('revoked');
    mockFetch([{ path: '/api/v1/auth/me', reply: { status: 401, json: { detail: 'Not authenticated' } } }]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('anonymous'));
    expect(window.sessionStorage.getItem('energiq.token')).toBeNull();
  });

  it('canWrite is true for analyst and admin, false for viewer', async () => {
    const results: Record<string, boolean> = {};
    for (const role of ['viewer', 'analyst', 'admin'] as Role[]) {
      signIn();
      mockFetch([{ path: '/api/v1/auth/me', reply: userFor(role) }]);
      const { result, unmount } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.status).toBe('authenticated'));
      results[role] = result.current.canWrite;
      unmount();
    }
    expect(results).toEqual({ viewer: false, analyst: true, admin: true });
  });
});

describe('route guards', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('RequireAuth sends an anonymous visitor to /login', async () => {
    mockFetch([]);
    resetTokenStoreForTests();
    render(
      <MemoryRouter initialEntries={['/secret']} future={ROUTER_FUTURE}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>login screen</p>} />
            <Route element={<RequireAuth />}>
              <Route path="/secret" element={<p>secret data</p>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText('login screen')).toBeInTheDocument();
    expect(screen.queryByText('secret data')).not.toBeInTheDocument();
  });

  it('PublicOnly sends a signed-in user away from /login', async () => {
    signIn();
    mockFetch([{ path: '/api/v1/auth/me', reply: fx.me }]);
    render(
      <MemoryRouter initialEntries={['/login']} future={ROUTER_FUTURE}>
        <AuthProvider>
          <Routes>
            <Route element={<PublicOnly />}>
              <Route path="/login" element={<p>login screen</p>} />
            </Route>
            <Route path="/" element={<p>home</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText('home')).toBeInTheDocument();
  });

  it('RequireRole shows "Access denied" with both roles named when the role does not match', async () => {
    signIn();
    mockFetch([{ path: '/api/v1/auth/me', reply: fx.me }]);
    render(
      <MemoryRouter initialEntries={['/admin']} future={ROUTER_FUTURE}>
        <AuthProvider>
          <Routes>
            <Route element={<RequireRole roles={['admin']} />}>
              <Route path="/admin" element={<p>admin console</p>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('needs the admin role');
    expect(screen.getByRole('alert')).toHaveTextContent('analyst');
    expect(screen.queryByText('admin console')).not.toBeInTheDocument();
  });

  it('WriteOnly hides its children from a viewer and shows them to an analyst', async () => {
    for (const [role, visible] of [['viewer', false], ['analyst', true]] as const) {
      signIn();
      mockFetch([{ path: '/api/v1/auth/me', reply: userFor(role) }]);
      const { unmount } = render(
        <AuthProvider>
          <Probe />
        </AuthProvider>,
      );
      await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('authenticated'));
      if (visible) expect(screen.getByRole('button', { name: 'Delete everything' })).toBeInTheDocument();
      else expect(screen.queryByRole('button', { name: 'Delete everything' })).not.toBeInTheDocument();
      unmount();
    }
  });
});

function Probe() {
  const { status } = useAuth();
  return (
    <>
      <p data-testid="state">{status}</p>
      <WriteOnly>
        <button type="button">Delete everything</button>
      </WriteOnly>
    </>
  );
}

describe('whole app guards (real routes, captured payloads)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('a non-admin who opens /admin never sees the admin console and no admin endpoint is requested', async () => {
    const net = renderApp('/admin', { role: 'analyst' });
    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(net.calls.some((c) => c.path.startsWith('/api/v1/admin'))).toBe(false);
  });

  it('an admin reaches /admin and sees the captured users', async () => {
    renderApp('/admin', { role: 'admin' });
    expect(await screen.findByRole('heading', { name: 'Administration' })).toBeInTheDocument();
    expect(await screen.findByText(fx.adminUsers[0]?.email as string)).toBeInTheDocument();
  });

  it('an anonymous visitor on / is sent to the sign-in page', async () => {
    renderApp('/', { signedIn: false });
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('appRoutes helper answers /me with the requested role', () => {
    expect(appRoutes('viewer')[0]?.reply).toMatchObject({ role: 'viewer' });
  });
});
