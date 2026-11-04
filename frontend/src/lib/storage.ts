/**
 * Guarded browser storage. Storage can be unavailable or throw (private windows, blocked site data),
 * so every access is wrapped and the app must render correctly without it.
 *
 * sessionStorage: the auth token and the active dataset (cleared when the tab closes).
 * localStorage: only the theme preference. Never the token.
 */
type Area = 'session' | 'local';

function area(which: Area): Storage | null {
  try {
    return which === 'session' ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function storageGet(which: Area, key: string): string | null {
  try {
    return area(which)?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function storageSet(which: Area, key: string, value: string): void {
  try {
    area(which)?.setItem(key, value);
  } catch {
    /* ignore quota / blocked storage */
  }
}

export function storageRemove(which: Area, key: string): void {
  try {
    area(which)?.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const KEYS = {
  token: 'energiq.token',
  activeDataset: 'energiq.activeDataset',
  theme: 'energiq.theme',
} as const;
