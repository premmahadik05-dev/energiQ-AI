import type { Config } from 'tailwindcss';

// Colours are semantic tokens backed by CSS variables (see src/index.css), so light/dark
// is a single switch of variable values and never a per-component concern.
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        page: 'var(--page)',
        surface: 'var(--surface)',
        sunken: 'var(--sunken)',
        ink: 'var(--ink)',
        'ink-2': 'var(--ink-2)',
        muted: 'var(--muted)',
        line: 'var(--line)',
        'line-strong': 'var(--line-strong)',
        accent: 'var(--accent)',
        'accent-ink': 'var(--accent-ink)',
        'accent-soft': 'var(--accent-soft)',
        good: 'var(--good-text)',
        'good-soft': 'var(--good-soft)',
        warn: 'var(--warn-text)',
        'warn-soft': 'var(--warn-soft)',
        bad: 'var(--bad-text)',
        'bad-soft': 'var(--bad-soft)',
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      borderRadius: { DEFAULT: '6px', lg: '8px' },
    },
  },
  plugins: [],
};
export default config;
