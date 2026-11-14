import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, buildQuery, configureApi, parseDetail, request, requestBlob } from './client';
import { fx } from '../test/fixtures';

const json = (body: unknown, init: ResponseInit = {}) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' }, ...init });

describe('API client', () => {
  const onUnauthorized = vi.fn();
  const fetchMock = vi.fn();

  beforeEach(() => {
    onUnauthorized.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    configureApi({ getToken: () => 'abc.def.ghi', onUnauthorized });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    configureApi({ getToken: () => null, onUnauthorized: () => undefined });
  });

  it('sends the bearer token in the Authorization header, never in the URL', async () => {
    fetchMock.mockResolvedValue(json(fx.me));
    await request('/api/v1/auth/me', { query: { limit: 5 } });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/me?limit=5');
    expect(url).not.toContain('abc.def.ghi');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer abc.def.ghi');
  });

  it('does not attach a token to login and register calls', async () => {
    fetchMock.mockResolvedValue(json({ ok: true }));
    await request('/api/v1/auth/login', { method: 'POST', body: { email: 'a@b.co', password: 'x' }, auth: false });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(init.body).toBe('{"email":"a@b.co","password":"x"}');
  });

  it('on 401 with a session: calls the unauthorized handler and throws a session-expired error', async () => {
    fetchMock.mockResolvedValue(json(fx.err401.body, { status: 401 }));
    await expect(request('/api/v1/datasets')).rejects.toMatchObject({ status: 401, message: 'Your session has expired. Sign in again.' });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('does not treat a failed login (401 without a session token) as an expired session', async () => {
    fetchMock.mockResolvedValue(json(fx.errLogin.body, { status: 401 }));
    await expect(request('/api/v1/auth/login', { method: 'POST', body: {}, auth: false })).rejects.toMatchObject({ status: 401, message: 'Invalid e-mail or password' });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('429: message carries the server text and the Retry-After seconds', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'Too many requests, slow down' }, { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': '42' } }));
    const err = (await request('/api/v1/auth/login', { method: 'POST', body: {}, auth: false }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(429);
    expect(err.retryAfter).toBe(42);
    expect(err.message).toBe('Too many requests, slow down. Try again in 42 s.');
  });

  it('429 without a Retry-After header still gives a usable message', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'Too many requests' }, { status: 429 }));
    await expect(request('/api/v1/datasets')).rejects.toMatchObject({ retryAfter: null, message: 'Too many requests. Try again shortly.' });
  });

  it('parses FastAPI validation-error lists into a message and per-field errors', async () => {
    fetchMock.mockResolvedValue(json(fx.err422Validation.body, { status: 422 }));
    const err = (await request('/api/v1/auth/register', { method: 'POST', body: {}, auth: false }).catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(422);
    expect(err.fieldErrors).toEqual({ password: 'Field required' });
    expect(err.message).toBe('password: Field required');
  });

  it('uses string detail messages as given (409, 403, 404)', async () => {
    fetchMock.mockResolvedValueOnce(json(fx.err409Register.body, { status: 409 }));
    await expect(request('/api/v1/auth/register', { method: 'POST', body: {}, auth: false })).rejects.toMatchObject({ status: 409, message: fx.err409Register.body.detail });
    fetchMock.mockResolvedValueOnce(json(fx.err403.body, { status: 403 }));
    await expect(request('/api/v1/admin/users')).rejects.toMatchObject({ status: 403, message: fx.err403.body.detail });
  });

  it('falls back to a status message when the error body is not JSON (proxy page)', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } }));
    await expect(request('/api/v1/datasets')).rejects.toMatchObject({ status: 502, message: 'The server is unavailable right now. Try again in a moment.' });
  });

  it('turns a network failure into a readable status-0 error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(request('/api/v1/datasets')).rejects.toMatchObject({ status: 0, message: expect.stringContaining('Cannot reach the server') });
  });

  it('passes an AbortError through unchanged so callers can ignore cancelled requests', async () => {
    fetchMock.mockRejectedValue(new DOMException('Aborted', 'AbortError'));
    await expect(request('/api/v1/datasets')).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('returns undefined for 204 No Content', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(request('/api/v1/datasets/1', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  it('requestBlob sends the Authorization header and reads the filename from Content-Disposition', async () => {
    fetchMock.mockResolvedValue(new Response('origin,target_time\n', { status: 200, headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="forecast_5.csv"' } }));
    const res = await requestBlob('/api/v1/forecasts/5/export.csv');
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer abc.def.ghi' });
    expect(res.filename).toBe('forecast_5.csv');
    expect(res.type).toContain('text/csv');
    expect(await res.blob.text()).toBe('origin,target_time\n');
  });

  it('requestBlob also runs the 401 handling', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'Not authenticated' }, { status: 401 }));
    await expect(requestBlob('/api/v1/datasets/1/report')).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalled();
  });
});

describe('query and detail helpers', () => {
  it('buildQuery drops empty values and encodes the rest', () => {
    expect(buildQuery({ a: 1, b: '', c: null, d: undefined, e: 'x y', f: false })).toBe('?a=1&e=x+y&f=false');
    expect(buildQuery()).toBe('');
    expect(buildQuery({ a: undefined })).toBe('');
  });

  it('parseDetail copes with strings, lists and unknown shapes', () => {
    expect(parseDetail('plain')).toEqual({ message: 'plain', fieldErrors: {} });
    expect(parseDetail([{ loc: ['body', 'email'], msg: 'bad' }, { loc: ['query', 'limit'], msg: 'too big' }]).fieldErrors).toEqual({ email: 'bad', limit: 'too big' });
    expect(parseDetail({ unexpected: true })).toEqual({ message: '', fieldErrors: {} });
    expect(parseDetail(undefined).message).toBe('');
  });
});
