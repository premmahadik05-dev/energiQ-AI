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
import { sfx } from './fixtures/society';

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

/** Routes for the captured Fox society (id 1): read-only endpoints every signed-in user can call; admin ones depend on the role. */
export function societyRoutes(role: Role = 'analyst'): Route[] {
  const s = '/api/v1/societies';
  const id = sfx.societies[0]?.id ?? 1;
  const base = `${s}/${id}`;
  return [
    { path: `${s}/compare`, reply: sfx.compare },
    { path: s, reply: sfx.societies },
    { path: base, reply: role === 'admin' ? sfx.detailAdmin : sfx.detailUser },
    { path: `${base}/overview`, reply: sfx.overview },
    { path: `${base}/consumption`, reply: (c: RecordedCall) => (c.query.get('resolution') === 'hourly' ? sfx.consumptionHourly : sfx.consumptionDaily) },
    { path: `${base}/buildings`, reply: sfx.buildings },
    { path: `${base}/buildings-monthly`, reply: sfx.buildingsMonthly },
    { path: new RegExp(`${base}/buildings/\\d+/consumption$`), reply: sfx.buildingConsumption },
    { path: `${base}/facilities`, reply: sfx.facilities },
    { path: `${base}/peaks`, reply: sfx.peaks },
    { path: `${base}/error-analysis`, reply: sfx.errorAnalysis },
    { path: `${base}/models`, reply: sfx.models },
    { path: `${base}/forecast`, reply: sfx.forecast },
    { path: `${base}/backtest`, reply: sfx.backtest },
    { path: `${base}/explain/global`, reply: sfx.explainGlobal },
    { method: 'POST', path: `${base}/explain/local`, reply: sfx.explainLocal },
    { path: `${base}/anomalies`, reply: sfx.anomalies },
    { method: 'POST', path: `${base}/cost`, reply: sfx.cost },
    { method: 'POST', path: `${base}/recommendations`, reply: sfx.recommendations },
    { path: `${base}/reports`, reply: sfx.reports },
    { method: 'POST', path: `${base}/reports`, reply: { status: 201, json: sfx.reportCreated } },
    { path: `${base}/meters`, reply: sfx.meters },
  ];
}

/** Routes for a signed-in user: the account, tariffs, jobs, notifications, admin and the captured Fox society. Entries passed to renderApp win via prepend. */
export function appRoutes(role: Role = 'analyst'): Route[] {
  const api = '/api/v1';
  return [
    { path: `${api}/auth/me`, reply: userFor(role) },
    { path: `${api}/notifications`, reply: fx.notifications },
    { path: `${api}/jobs`, reply: fx.jobsList },
    { path: `${api}/tariffs`, reply: fx.tariffs },
    { path: `${api}/admin/users`, reply: fx.adminUsers },
    { path: `${api}/admin/audit`, reply: fx.adminAudit },
    { path: `${api}/admin/system`, reply: fx.adminSystem },
    ...societyRoutes(role),
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
    <MemoryRouter initialEntries={[{ pathname: path, state: opts.state }]}>
      <AppProviders>
        <AppRoutes />
      </AppProviders>
    </MemoryRouter>,
  );
  return { ...view, ...net };
}
