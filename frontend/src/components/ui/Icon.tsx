const PATHS: Record<string, string> = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  database: 'M12 3C7.6 3 4 4.3 4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6c0-1.7-3.6-3-8-3zm0 2c3.9 0 6 1 6 1s-2.1 1-6 1-6-1-6-1 2.1-1 6-1zM6 18v-2.3c1.4.8 3.5 1.3 6 1.3s4.6-.5 6-1.3V18s-2.1 1-6 1-6-1-6-1zm0-4.6V11c1.4.8 3.5 1.3 6 1.3s4.6-.5 6-1.3v2.4c-1.4.8-3.5 1.3-6 1.3s-4.6-.5-6-1.3z',
  forecast: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  model: 'M12 2l9 5v10l-9 5-9-5V7l9-5zm0 6.5L7 11.3v5.4l5 2.8 5-2.8v-5.4l-5-2.8z',
  alert: 'M12 3l10 18H2L12 3zm0 6v6m0 3v.01',
  explain: 'M4 20V10m6 10V4m6 16v-8m6 8H2',
  coin: 'M12 3a9 9 0 100 18 9 9 0 000-18zm0 4v10m-3-7.5c0-1 1.3-1.5 3-1.5s3 .5 3 1.5-1.3 1.5-3 1.5-3 .5-3 1.5 1.3 1.5 3 1.5 3-.5 3-1.5',
  benchmark: 'M5 4v16M5 5h11l-2 3.5L16 12H5',
  jobs: 'M12 6v6l4 2M12 3a9 9 0 100 18 9 9 0 000-18z',
  bell: 'M18 16v-5a6 6 0 10-12 0v5l-2 2h16l-2-2zm-4 4a2 2 0 01-4 0',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zm-8 9a8 8 0 0116 0',
  admin: 'M12 2l8 3v6c0 5-3.4 9.3-8 11-4.6-1.7-8-6-8-11V5l8-3z',
  sun: 'M12 17a5 5 0 100-10 5 5 0 000 10zM12 1v3m0 16v3M4.2 4.2l2.1 2.1m11.4 11.4l2.1 2.1M1 12h3m16 0h3M4.2 19.8l2.1-2.1m11.4-11.4l2.1-2.1',
  moon: 'M21 13.5A9 9 0 1110.5 3a7 7 0 0010.5 10.5z',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'M6 6l12 12M18 6L6 18',
  upload: 'M12 16V4m0 0l-4 4m4-4l4 4M4 20h16',
  download: 'M12 4v12m0 0l-4-4m4 4l4-4M4 20h16',
  chevron: 'M6 9l6 6 6-6',
};

export function Icon({ name, className = 'h-5 w-5' }: { name: keyof typeof PATHS | string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? ''} />
    </svg>
  );
}

export function Logo({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <path d="M4 21h5l3-8 4 13 3-9 2 4h7" fill="none" stroke="var(--accent-ink)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
