import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
});

// jsdom has no matchMedia or ResizeObserver
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => undefined, removeEventListener: () => undefined, addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;
}
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = (globalThis as unknown as { ResizeObserver?: typeof RO }).ResizeObserver ?? RO;
// jsdom logs "not implemented" for scrollTo; the app scrolls to top on navigation
Object.defineProperty(window, 'scrollTo', { value: () => undefined, writable: true, configurable: true });

// jsdom has no object URLs; authenticated downloads and figures go through URL.createObjectURL / revokeObjectURL
if (!URL.createObjectURL) {
  Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:test-object-url', writable: true, configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: () => undefined, writable: true, configurable: true });
}

// Recharts measures its container; jsdom has no layout, so every chart warns "width(0) and height(0)". The chart
// content is covered through the table alternative that every chart has; keep other warnings visible.
const realWarn = console.warn.bind(console);
console.warn = (...args: unknown[]) => {
  if (typeof args[0] === 'string' && args[0].includes('width(0) and height(0) of chart')) return;
  realWarn(...args);
};
