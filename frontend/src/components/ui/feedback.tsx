import type { ReactNode } from 'react';
import { ApiError } from '../../api/client';

export function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg className={`h-4 w-4 animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-ink-2">
      <Spinner />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'Could not load this' }: { error: Error; onRetry?: () => void; title?: string }) {
  const status = error instanceof ApiError ? error.status : null;
  return (
    <div role="alert" className="rounded-lg border border-bad bg-bad-soft p-4 text-sm">
      <p className="font-semibold text-bad">{title}</p>
      <p className="mt-1 text-ink">{error.message}</p>
      {status === 429 && <p className="mt-1 text-ink-2">The server rate-limits requests; wait for the time above before retrying.</p>}
      {onRetry && (
        <button type="button" className="btn-secondary mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
      <p className="text-base font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-prose text-sm text-ink-2">{children}</div>}
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

const NOTICE_TONES = {
  info: 'border-line-strong bg-sunken text-ink',
  warn: 'border-warn bg-warn-soft text-ink',
  error: 'border-bad bg-bad-soft text-ink',
  good: 'border-good bg-good-soft text-ink',
} as const;

export function Notice({ tone = 'info', title, children, role }: { tone?: keyof typeof NOTICE_TONES; title?: string; children?: ReactNode; role?: 'status' | 'alert' }) {
  return (
    <div role={role ?? (tone === 'error' ? 'alert' : undefined)} className={`rounded-lg border-l-4 border px-4 py-3 text-sm ${NOTICE_TONES[tone]}`}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={title ? 'mt-1 text-ink-2' : ''}>{children}</div>}
    </div>
  );
}

export function ProgressBar({ value, label, message }: { value: number; label: string; message?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-3 text-xs text-ink-2">
        <span>{message || label}</span>
        <span className="num">{pct}%</span>
      </div>
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="h-2 overflow-hidden rounded-full bg-sunken ring-1 ring-line">
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
