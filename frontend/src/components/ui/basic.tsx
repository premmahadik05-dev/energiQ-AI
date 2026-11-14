import { useId, type ReactNode } from 'react';

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[26px] leading-tight">{title}</h1>
        {description && <p className="mt-1.5 max-w-prose text-[14px] leading-relaxed text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, description, actions, children, className = '', padded = true }: { title?: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  const id = useId();
  return (
    <section aria-labelledby={title ? id : undefined} className={`card ${className}`}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-5 sm:px-6">
          <div className="min-w-0">
            {title && (
              <h2 id={id} className="text-[16px]">
                {title}
              </h2>
            )}
            {description && <p className="mt-1 max-w-prose text-[13.5px] leading-relaxed text-ink-2">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={padded ? 'p-4 sm:p-6' : title ? 'mt-4 [&>div]:rounded-none [&>div]:border-x-0 [&>div]:border-b-0 [&>div]:rounded-b-lg' : ''}>{children}</div>
    </section>
  );
}

const BADGE_TONES = {
  neutral: 'bg-sunken text-ink-2 border-line-strong',
  accent: 'bg-accent-soft text-accent border-transparent',
  good: 'bg-good-soft text-good border-transparent',
  warn: 'bg-warn-soft text-warn border-transparent',
  bad: 'bg-bad-soft text-bad border-transparent',
} as const;

export type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({ tone = 'neutral', children, title }: { tone?: BadgeTone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[12px] font-medium leading-tight ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

/** Severity as dots plus the word, so the level never rests on colour alone. */
export function SeverityBadge({ severity }: { severity: string }) {
  const level = severity === 'high' ? 3 : severity === 'medium' ? 2 : 1;
  return (
    <Badge tone={severity === 'high' ? 'bad' : severity === 'medium' ? 'warn' : 'neutral'}>
      <span aria-hidden="true" className="mr-1 tracking-tighter">
        {'●'.repeat(level)}
        {'○'.repeat(3 - level)}
      </span>
      {severity}
    </Badge>
  );
}

/** Same encoding as the charts: a solid blue line marks measured values, a dashed orange line marks forecasts. */
function KpiMarker({ kind }: { kind: 'measured' | 'forecast' }) {
  return (
    <svg width="18" height="8" viewBox="0 0 18 8" aria-hidden="true" className="shrink-0">
      <line x1="1" y1="4" x2="17" y2="4" stroke={kind === 'forecast' ? 'var(--s2)' : 'var(--s1)'} strokeWidth="2.4" strokeLinecap="round" strokeDasharray={kind === 'forecast' ? '4 3' : undefined} />
    </svg>
  );
}

export function KpiTile({ label, value, unit, sub, tone, marker, children }: { label: string; value: ReactNode; unit?: string; sub?: ReactNode; tone?: 'good' | 'warn' | 'bad'; marker?: 'measured' | 'forecast'; children?: ReactNode }) {
  const toneClass = tone === 'good' ? 'text-good' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-bad' : 'text-ink';
  // long text values (a timestamp, "Not available") get a smaller size so they stay on one line
  const size = typeof value === 'string' && value.length > 11 ? 'text-[19px] sm:text-[22px]' : 'text-[22px] sm:text-[28px]';
  return (
    <div className="card p-3.5 sm:p-5">
      <p className="flex items-center gap-2 text-[12.5px] font-medium text-ink-2 sm:text-[13px]">
        {marker && <KpiMarker kind={marker} />}
        {label}
      </p>
      <p className={`num mt-2 font-semibold leading-none tracking-tight ${size} ${toneClass}`}>
        {value}
        {unit && (
          <>
            {' '}
            <span className="ml-0.5 text-[13px] font-medium tracking-normal text-muted sm:text-[15px]">{unit}</span>
          </>
        )}
      </p>
      {sub && <p className="mt-2.5 text-[12px] leading-snug text-ink-2 sm:text-[12.5px]">{sub}</p>}
      {children}
    </div>
  );
}

export function DescriptionList({ items, columns = 2 }: { items: { label: string; value: ReactNode }[]; columns?: 1 | 2 | 3 }) {
  const cols = columns === 3 ? 'sm:grid-cols-3' : columns === 2 ? 'sm:grid-cols-2' : '';
  return (
    <dl className={`grid grid-cols-1 gap-x-8 gap-y-3 ${cols}`}>
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <dt className="text-xs font-medium text-ink-2">{it.label}</dt>
          <dd className="num mt-0.5 break-words text-sm text-ink">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}

/** Status icon + text, never colour alone. */
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { tone: BadgeTone; icon: string }> = {
    ready: { tone: 'good', icon: '✓' },
    succeeded: { tone: 'good', icon: '✓' },
    processing: { tone: 'accent', icon: '…' },
    running: { tone: 'accent', icon: '…' },
    queued: { tone: 'neutral', icon: '…' },
    failed: { tone: 'bad', icon: '!' },
  };
  const m = map[status] ?? { tone: 'neutral' as BadgeTone, icon: '' };
  return (
    <Badge tone={m.tone}>
      <span aria-hidden="true" className="mr-1">
        {m.icon}
      </span>
      {status}
    </Badge>
  );
}
