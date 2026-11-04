/**
 * Small typed fetch wrapper for the EnergiQ API.
 *  - Authorization: Bearer <token> on every authenticated request (never in a URL).
 *  - A 401 on an authenticated request clears the session via the registered handler.
 *  - Errors become ApiError with a readable message (FastAPI "detail" strings and validation lists, 429 + Retry-After).
 */
export const API_PREFIX = '/api/v1';

export function apiBase(): string {
  const raw = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';
  return raw.replace(/\/+$/, '');
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly retryAfter: number | null;
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, opts: { detail?: unknown; retryAfter?: number | null; fieldErrors?: Record<string, string> } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = opts.detail;
    this.retryAfter = opts.retryAfter ?? null;
    this.fieldErrors = opts.fieldErrors ?? {};
  }
}

export const isAbortError = (e: unknown): boolean => e instanceof DOMException && e.name === 'AbortError';

interface Hooks {
  getToken: () => string | null;
  onUnauthorized: () => void;
}

let hooks: Hooks = { getToken: () => null, onUnauthorized: () => undefined };

export function configureApi(h: Partial<Hooks>): void {
  hooks = { ...hooks, ...h };
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  form?: FormData;
  /** false for endpoints that are called without a session (login, register) */
  auth?: boolean;
  signal?: AbortSignal;
}

export function buildQuery(query?: RequestOptions['query']): string {
  if (!query) return '';
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

function statusMessage(status: number): string {
  if (status === 0) return 'Cannot reach the server. Check your connection and try again.';
  if (status === 502 || status === 503 || status === 504) return 'The server is unavailable right now. Try again in a moment.';
  if (status >= 500) return 'The server hit an unexpected error. Try again; if it keeps happening, contact an administrator.';
  if (status === 413) return 'The file is too large for the server.';
  return `Request failed (HTTP ${status}).`;
}

/** FastAPI sends detail as a string, or as a list of {loc, msg} for request-validation errors. */
export function parseDetail(detail: unknown): { message: string; fieldErrors: Record<string, string> } {
  if (typeof detail === 'string') return { message: detail, fieldErrors: {} };
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    const parts: string[] = [];
    for (const item of detail) {
      if (item && typeof item === 'object' && 'msg' in item) {
        const rec = item as { loc?: unknown[]; msg: unknown };
        const loc = Array.isArray(rec.loc) ? rec.loc.filter((x) => x !== 'body' && x !== 'query' && x !== 'path').map(String) : [];
        const field = loc.join('.');
        const msg = String(rec.msg);
        if (field) fieldErrors[field] = msg;
        parts.push(field ? `${field}: ${msg}` : msg);
      }
    }
    if (parts.length) return { message: parts.join('; '), fieldErrors };
  }
  return { message: '', fieldErrors: {} };
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    const ct = res.headers.get('content-type') ?? '';
    if (ct.includes('json')) detail = ((await res.json()) as { detail?: unknown }).detail;
  } catch {
    /* non-JSON error body (e.g. proxy page) */
  }
  const parsed = parseDetail(detail);
  const ra = Number.parseInt(res.headers.get('Retry-After') ?? '', 10);
  const retryAfter = Number.isFinite(ra) ? ra : null;
  let message = parsed.message || statusMessage(res.status);
  if (res.status === 429) {
    const base = parsed.message || 'Too many requests, slow down';
    message = `${base.replace(/[.\s]+$/, '')}. ${retryAfter !== null ? `Try again in ${retryAfter} s.` : 'Try again shortly.'}`;
  }
  return new ApiError(res.status, message, { detail, retryAfter, fieldErrors: parsed.fieldErrors });
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = opts.auth === false ? null : hooks.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}${buildQuery(opts.query)}`, { method: opts.method ?? 'GET', headers, body, signal: opts.signal });
  } catch (e) {
    if (isAbortError(e)) throw e;
    throw new ApiError(0, statusMessage(0));
  }
  if (!res.ok) {
    const err = await toApiError(res);
    if (res.status === 401 && token) {
      hooks.onUnauthorized();
      throw new ApiError(401, 'Your session has expired. Sign in again.', { detail: err.detail });
    }
    throw err;
  }
  return res;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(res.status, 'The server returned an unreadable response.');
  }
}

export interface BlobResult {
  blob: Blob;
  filename: string | null;
  type: string;
}

/** Authenticated download. The caller owns the blob (save it with saveBlob or show it through an object URL and revoke that). */
export async function requestBlob(path: string, opts: RequestOptions = {}): Promise<BlobResult> {
  const res = await send(path, opts);
  const cd = res.headers.get('Content-Disposition') ?? '';
  const m = /filename="?([^";]+)"?/i.exec(cd);
  const blob = await res.blob();
  return { blob, filename: m?.[1] ?? null, type: blob.type || res.headers.get('Content-Type') || '' };
}
