import { useId, type ReactNode } from 'react';

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-prose text-sm text-ink-2">{description}</p>}
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
        <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4 sm:px-5">
          <div className="min-w-0">
            {title && (
              <h2 id={id} className="text-base">
                {title}
              </h2>
            )}
            {description && <p className="mt-0.5 max-w-prose text-sm text-ink-2">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={padded ? 'p-4 sm:p-5' : ''}>{children}</div>
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
    <span title={title} className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium leading-tight ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

export function KpiTile({ label, value, sub, tone, children }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'good' | 'warn' | 'bad'; children?: ReactNode }) {
  const toneClass = tone === 'good' ? 'text-good' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-bad' : 'text-ink';
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-ink-2">{label}</p>
      <p className={`num mt-1 text-2xl font-semibold leading-tight ${toneClass}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-ink-2">{sub}</p>}
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
