import { useId, type ChangeEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { PRESET_LABEL, presetRange, type RangePreset } from '../../lib/societySeries';
import { useSociety } from '../../state/SocietyContext';
import { Badge, Card, PageHeader } from '../ui/basic';
import { Icon } from '../ui/Icon';
import { EmptyState, ErrorState, Loading } from '../ui/feedback';
import { SelectField } from '../ui/forms';
import type { SocietySummary } from '../../api/societyTypes';

/** Header with the society picker. Every society page starts with this so the context is always visible. */
export function SocietyHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  const { societies, active, setActiveId } = useSociety();
  return (
    <PageHeader
      title={title}
      description={description}
      actions={
        <>
          {actions}
          {societies.length > 1 && active && (
            <SelectField label="Society" value={active.id} onChange={(e) => setActiveId(Number(e.target.value))} className="min-w-[14rem]">
              {societies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          )}
        </>
      }
    />
  );
}

/** Renders children only when a society is selected; otherwise a loading, error or empty state. */
export function SocietyGate({ children }: { children: (society: SocietySummary) => ReactNode }) {
  const { active, loading, error, refresh } = useSociety();
  const { hasRole } = useAuth();
  if (loading) return <Loading label="Loading societies" />;
  if (error) return <ErrorState error={error} onRetry={refresh} />;
  if (!active) {
    return (
      <EmptyState
        title="No society loaded yet"
        action={
          hasRole('admin') ? (
            <Link to="/society-admin" className="btn-primary">
              Import the bundled communities
            </Link>
          ) : undefined
        }
      >
        {hasRole('admin')
          ? 'Import the bundled real-data communities (or upload your own meter CSV) from the society admin page.'
          : 'An administrator needs to import a society before these pages have data.'}
      </EmptyState>
    );
  }
  return <>{children(active)}</>;
}

/** The honesty note about what a society in this project is. Slim on purpose: it is on every page, so it must not dominate any of them. */
export function DataBasisNote({ society }: { society: SocietySummary }) {
  const upload = society.source_name === 'Administrator upload';
  return (
    <div role="note" className="flex items-start gap-3 rounded-lg border border-line bg-accent-soft px-4 py-2.5 text-[13px] leading-relaxed text-ink-2">
      <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <p>
        <strong className="font-semibold text-ink">{upload ? 'Administrator-uploaded meter data' : 'Research-based representative community (real data)'}</strong>{' '}
        {upload ? (
          <>Readings were uploaded by an administrator and cleaned with the documented rules; nothing is generated or filled in.</>
        ) : (
          <>
            {society.buildings} real residential-use buildings from {society.source_name}, summed per hour. It is not a registered housing society, and the data are a historical record (
            {society.start.slice(0, 10)} to {society.end.slice(0, 10)}), not a live feed.
          </>
        )}
      </p>
    </div>
  );
}

export function RangePresets({ society, value, onChange, presets = ['7d', '30d', '90d', '1y', 'all'] }: { society: SocietySummary; value: RangePreset; onChange: (v: RangePreset, range: { start: string; end: string }) => void; presets?: RangePreset[] }) {
  return (
    <div role="group" aria-label="Date range" className="inline-flex flex-wrap gap-0.5 rounded-md border border-line bg-sunken p-0.5">
      {presets.map((p) => (
        <button
          key={p}
          type="button"
          aria-pressed={value === p}
          onClick={() => onChange(p, presetRange(p, society.start, society.end))}
          className={`rounded-[5px] px-3 py-1 text-[13.5px] font-medium transition-colors ${value === p ? 'bg-surface font-semibold text-ink shadow-sm ring-1 ring-line' : 'text-ink-2 hover:text-ink'}`}
        >
          {PRESET_LABEL[p]}
        </button>
      ))}
    </div>
  );
}

export function TariffPicker({ compact = false }: { compact?: boolean }) {
  const { tariffs, tariffId, setTariffId, tariff } = useSociety();
  const id = useId();
  const onChange = (e: ChangeEvent<HTMLSelectElement>) => setTariffId(e.target.value === 'demo' ? 'demo' : Number(e.target.value));
  const options = tariffs.map((t) => (
    <option key={String(t.id)} value={String(t.id)}>
      {t.name}
    </option>
  ));
  if (compact) {
    // inline label and select; the demo-tariff warning stays visible in the cost figure's own caption
    return (
      <div className="flex items-center gap-2">
        <label htmlFor={id} className="text-[13px] font-medium text-ink-2">
          Tariff
        </label>
        <select id={id} className="input !min-h-[34px] w-auto max-w-[min(20rem,60vw)] py-1 pr-8" value={String(tariffId)} onChange={onChange}>
          {options}
        </select>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <SelectField label="Tariff" value={String(tariffId)} onChange={onChange} className="min-w-[14rem]">
        {options}
      </SelectField>
      {tariff?.is_demo && <Badge tone="warn" title="Placeholder rates for illustration, not a utility's real prices">Demo tariff, not real prices</Badge>}
    </div>
  );
}

export function CardNote({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-xs text-ink-2">{children}</p>;
}

export function Section({ title, description, actions, children }: { title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card title={title} description={description} actions={actions}>
      {children}
    </Card>
  );
}
