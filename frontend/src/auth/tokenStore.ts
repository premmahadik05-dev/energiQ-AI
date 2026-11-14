import { KEYS, storageGet, storageRemove, storageSet } from '../lib/storage';

/**
 * The access token lives in memory and in sessionStorage (so a reload of the same tab keeps the session).
 * It is never written to localStorage, never put in a URL, and is cleared on logout and on any 401.
 */
let memoryToken: string | null = null;
let hydrated = false;

export function getToken(): string | null {
  if (!hydrated) {
    hydrated = true;
    memoryToken = storageGet('session', KEYS.token);
  }
  return memoryToken;
}

export function setToken(token: string): void {
  hydrated = true;
  memoryToken = token;
  storageSet('session', KEYS.token, token);
}

export function clearToken(): void {
  hydrated = true;
  memoryToken = null;
  storageRemove('session', KEYS.token);
}

/** test helper: forget the in-memory copy so the next getToken() re-reads sessionStorage */
export function resetTokenStoreForTests(): void {
  memoryToken = null;
  hydrated = false;
}
