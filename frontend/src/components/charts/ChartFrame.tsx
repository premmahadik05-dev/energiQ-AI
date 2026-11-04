import { useId, useState, type ReactNode } from 'react';
import { Segmented } from '../ui/forms';

export type LegendKind = 'line' | 'dash' | 'area' | 'bar' | 'triangleUp' | 'triangleDown' | 'diamond' | 'circle';
export interface LegendItem {
  label: string;
  color: string;
  kind: LegendKind;
}

export function LegendSwatch({ kind, color }: { kind: LegendKind; color: string }) {
  const common = { width: 18, height: 12, viewBox: '0 0 18 12', 'aria-hidden': true } as const;
  switch (kind) {
    case 'line':
      return (
        <svg {...common}>
          <line x1="1" y1="6" x2="17" y2="6" stroke={color} strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    case 'dash':
      return (
        <svg {...common}>
          <line x1="1" y1="6" x2="17" y2="6" stroke={color} strokeWidth="2" strokeDasharray="4 3" strokeLinecap="round" />
        </svg>
      );
    case 'area':
      return (
        <svg {...common}>
          <rect x="1" y="1" width="16" height="10" rx="2" fill={color} stroke={color} strokeOpacity="0.5" />
        </svg>
      );
    case 'bar':
      return (
        <svg {...common}>
          <rect x="3" y="1" width="12" height="10" rx="2" fill={color} />
        </svg>
      );
    case 'triangleUp':
      return (
        <svg {...common}>
          <path d="M9 1 L15 11 H3 Z" fill={color} stroke="var(--ink)" strokeWidth="1" />
        </svg>
      );
    case 'triangleDown':
      return (
        <svg {...common}>
          <path d="M9 11 L15 1 H3 Z" fill={color} stroke="var(--ink)" strokeWidth="1" />
        </svg>
      );
    case 'diamond':
      return (
        <svg {...common}>
          <path d="M9 0.5 L15 6 L9 11.5 L3 6 Z" fill={color} stroke="var(--ink)" strokeWidth="1" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="9" cy="6" r="4.5" fill={color} stroke="var(--ink)" strokeWidth="1" />
        </svg>
      );
  }
}

export function Legend({ items }: { items: LegendItem[] }) {
  if (items.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2" aria-label="Chart legend">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-2">
          <LegendSwatch kind={it.kind} color={it.color} />
          <span>{it.label}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Every chart gets: a title, a plain-language summary for assistive tech, a legend when there are two or more
 * series, and a Chart/Table switch so the same numbers are available as a table.
 */
export function ChartFrame({ title, description, summary, legend, table, children, toolbar, footer }: { title: string; description?: ReactNode; summary: string; legend?: LegendItem[]; table: ReactNode; children: ReactNode; toolbar?: ReactNode; footer?: ReactNode }) {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const id = useId();
  return (
    <figure className="m-0" aria-labelledby={`${id}-t`}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <figcaption id={`${id}-t`} className="text-sm font-semibold text-ink">
            {title}
          </figcaption>
          {description && <p className="mt-0.5 max-w-prose text-xs text-ink-2">{description}</p>}
        </div>
        <Segmented label={`${title}: view`} value={view} onChange={setView} options={[{ value: 'chart', label: 'Chart' }, { value: 'table', label: 'Table' }]} />
      </div>
      {view === 'chart' ? (
        <>
          <p className="sr-only">{summary}</p>
          {legend && legend.length > 1 && (
            <div className="mb-2">
              <Legend items={legend} />
            </div>
          )}
          {toolbar}
          <div role="img" aria-label={summary}>
            {children}
          </div>
        </>
      ) : (
        <div className="max-h-[420px] overflow-auto">{table}</div>
      )}
      {footer && <div className="mt-2 text-xs text-ink-2">{footer}</div>}
    </figure>
  );
}
