import type { Config } from 'tailwindcss';

// Colours are semantic tokens backed by CSS variables (see src/index.css), so a colour change is made once
// in the token and never per component.
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
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
        brand: 'var(--brand)',
        azure: 'var(--blue)',
        'accent-ink': 'var(--accent-ink)',
        'accent-soft': 'var(--accent-soft)',
        good: 'var(--good-text)',
        'good-soft': 'var(--good-soft)',
        warn: 'var(--warn-text)',
        'warn-soft': 'var(--warn-soft)',
        bad: 'var(--bad-text)',
        'bad-soft': 'var(--bad-soft)',
        'nav-bg': 'var(--nav-bg)',
        'nav-ink': 'var(--nav-ink)',
        'nav-ink-strong': 'var(--nav-ink-strong)',
        'nav-muted': 'var(--nav-muted)',
        'nav-hover': 'var(--nav-hover)',
        'nav-active': 'var(--nav-active)',
        'nav-bar': 'var(--nav-bar)',
        'nav-line': 'var(--nav-line)',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      borderRadius: { DEFAULT: '6px', md: '7px', lg: '10px' },
    },
  },
  plugins: [],
};
export default config;
