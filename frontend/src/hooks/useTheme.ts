import { useCallback, useEffect, useState } from 'react';
import { KEYS, storageGet, storageSet } from '../lib/storage';

export type ThemeChoice = 'light' | 'dark' | 'system';

export function readThemeChoice(): ThemeChoice {
  const v = storageGet('local', KEYS.theme);
  return v === 'light' || v === 'dark' ? v : 'system';
}

export function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', choice);
}

/** Manual light/dark toggle layered on prefers-color-scheme. The choice is a per-viewer convenience kept in localStorage. */
export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(readThemeChoice);
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  useEffect(() => {
    applyTheme(choice);
  }, [choice]);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const on = () => setSystemDark(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);

  const effective: 'light' | 'dark' = choice === 'system' ? (systemDark ? 'dark' : 'light') : choice;
  const set = useCallback((c: ThemeChoice) => {
    storageSet('local', KEYS.theme, c);
    setChoice(c);
  }, []);
  const toggle = useCallback(() => set(effective === 'dark' ? 'light' : 'dark'), [effective, set]);
  return { choice, effective, set, toggle };
}
