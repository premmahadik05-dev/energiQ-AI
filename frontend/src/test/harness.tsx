/**
 * Test harness: a fetch mock that answers with CAPTURED backend payloads (see fixtures/index.ts),
 * and a renderer that mounts the real app (providers + routes) at a given URL.
 */
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { AppRoutes } from '../App';
import type { Role } from '../api/types';
import { resetTokenStoreForTests } from '../auth/tokenStore';
import { AppProviders } from '../providers';
import { fx } from './fixtures';

export const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

export interface RecordedCall {
  method: string;
  path: string;
  query: URLSearchParams;
  headers: Record<string, string>;
  body: unknown;
}

export interface Reply {
  status?: number;
  json?: unknown;
  headers?: Record<string, string>;
  /** raw body (e.g. CSV text); takes precedence over json */
  text?: string;
}

/** A payload (sent as JSON), an explicit Reply (status / headers / text), or a function of the recorded call returning either. */
export type Responder = unknown;
export interface Route {
  method?: string;
  path: RegExp | string;
  reply: Responder;
}

function toResponse(r: Reply | unknown): Response {
  // a payload is wrapped as { json } unless it is explicitly a Reply (numeric status, json or text); API objects carry string `status` fields
  const isReply = !!r && typeof r === 'object' && !Array.isArray(r) && (typeof (r as { status?: unknown }).status === 'number' || 'json' in r || 'text' in r);
  const reply = (isReply ? r : { json: r }) as Reply;
  const status = reply.status ?? 200;
  const headers = { ...(reply.text !== undefined ? {} : { 'Content-Type': 'application/json' }), ...reply.headers };
  const body = status === 204 ? null : reply.text !== undefined ? reply.text : JSON.stringify(reply.json ?? null);
  return new Response(body, { status, headers });
}

/** Install a fetch mock. Unmatched requests answer 404 and are listed in `unmatched` so tests can assert none happened. */
export function mockFetch(routes: Route[]) {
  const calls: RecordedCall[] = [];
  const unmatched: string[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://localhost');
    const method = (init?.method ?? 'GET').toUpperCase();
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((v, k) => {
      headers[k] = v;
    });
    let body: unknown = init?.body ?? undefined;
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body);
      } catch {
        /* keep text */
      }
    }
    const call: RecordedCall = { method, path: url.pathname, query: url.searchParams, headers, body };
    calls.push(call);
    const route = routes.find((r) => (r.method ?? 'GET') === method && (typeof r.path === 'string' ? r.path === url.pathname : r.path.test(url.pathname)));
    if (!route) {
      unmatched.push(`${method} ${url.pathname}${url.search}`);
      return toResponse({ status: 404, json: { detail: 'not mocked' } });
    }
    return toResponse(typeof route.reply === 'function' ? (route.reply as (c: RecordedCall) => unknown)(call) : route.reply);
  });
  vi.stubGlobal('fetch', fn);
  return { calls, unmatched, fn };
}

export const userFor = (role: Role) => ({ ...(role === 'admin' ? fx.loginAdmin.user : fx.login.user), role });

/** Routes for a signed-in user on the captured sample dataset (dataset id 1). Later entries win via prepend. */
export function appRoutes(role: Role = 'analyst'): Route[] {
  const api = '/api/v1';
  return [
    { path: `${api}/auth/me`, reply: userFor(role) },
    { path: `${api}/datasets`, reply: fx.datasetsList },
    { path: `${api}/datasets/1`, reply: fx.datasetDetail },
    { path: `${api}/datasets/1/readings`, reply: (c: RecordedCall) => (c.query.get('resolution') === 'daily' ? fx.readingsDaily : fx.readingsHourlyDefault) },
    { path: `${api}/datasets/1/profile`, reply: fx.profile },
    { path: `${api}/models`, reply: fx.modelsList },
    { path: /\/models\/[^/]+\/monitoring$/, reply: fx.monitoringAfterForecast },
    { path: `${api}/notifications`, reply: fx.notifications },
    { path: `${api}/jobs`, reply: fx.jobsList },
    { path: `${api}/anomalies/summary`, reply: fx.anomalySummary },
    { path: `${api}/anomalies`, reply: fx.anomaliesList },
    { path: `${api}/forecasts`, reply: fx.forecastsList },
    { path: `${api}/forecasts/1`, reply: fx.forecastCreated },
    { path: `${api}/tariffs`, reply: fx.tariffs },
    { path: `${api}/explain/global`, reply: fx.explainGlobal },
    { path: `${api}/benchmark`, reply: fx.benchmark },
    { path: `${api}/admin/users`, reply: fx.adminUsers },
    { path: `${api}/admin/audit`, reply: fx.adminAudit },
    { path: `${api}/admin/system`, reply: fx.adminSystem },
  ];
}

export function signIn(token = 'captured-session-token'): void {
  window.sessionStorage.setItem('energiq.token', token);
  resetTokenStoreForTests();
}

export function renderApp(path: string, opts: { role?: Role; routes?: Route[]; signedIn?: boolean; state?: unknown } = {}) {
  const { role = 'analyst', signedIn = true } = opts;
  if (signedIn) signIn();
  else resetTokenStoreForTests();
  const net = mockFetch([...(opts.routes ?? []), ...appRoutes(role)]);
  const view = render(
    <MemoryRouter initialEntries={[{ pathname: path, state: opts.state }]} future={ROUTER_FUTURE}>
      <AppProviders>
        <AppRoutes />
      </AppProviders>
    </MemoryRouter>,
  );
  return { ...view, ...net };
}
