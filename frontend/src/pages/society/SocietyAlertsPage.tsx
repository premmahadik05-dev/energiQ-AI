import { useEffect, useMemo, useState } from 'react';
import { societyApi } from '../../api/endpoints';
import type { SocietyAnomaly, SocietySummary } from '../../api/societyTypes';
import { WriteOnly } from '../../auth/guards';
import type { TsMarker } from '../../components/charts/TimeSeriesChart';
import { SocietyGate, SocietyHeader } from '../../components/society/common';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Badge, Card, KpiTile, SeverityBadge } from '../../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice, Spinner } from '../../components/ui/feedback';
import { Segmented, SelectField } from '../../components/ui/forms';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtNum } from '../../lib/format';
import { alertTitle, consumptionRows } from '../../lib/societySeries';
import { formatTs, parseNaive } from '../../lib/time';
import { useToast } from '../../state/ToastContext';

const PAGE_SIZE = 15;
type Level = 'attention' | 'all';
type Status = 'open' | 'acknowledged' | 'any';
const shapeFor = (types: string[]): TsMarker['shape'] => (types.includes('flat_run') ? 'diamond' : types.includes('spike') ? 'triangleUp' : types.includes('drop') ? 'triangleDown' : 'circle');
const SEV_COLOR = { high: 'var(--sev-high)', medium: 'var(--sev-medium)', low: 'var(--sev-low)' } as const;

function Alerts({ society }: { society: SocietySummary }) {
  const toast = useToast();
  const [level, setLevel] = useState<Level>('attention');
  const [scope, setScope] = useState<'all' | 'society' | 'building'>('society');
  const [status, setStatus] = useState<Status>('any');
  const [building, setBuilding] = useState('');
  const [sort, setSort] = useState<'time' | 'severity'>('time');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => setPage(0), [level, scope, status, building, sort, society.id]);

  const buildings = useApi(`soc-alert-b:${society.id}`, (signal) => societyApi.buildings(society.id, {}, { signal }));
  const list = useApi(`soc-alerts:${society.id}:${level}:${scope}:${status}:${building}:${sort}:${page}:${nonce}`, (signal) =>
    societyApi.anomalies(
      society.id,
      { min_severity: level === 'attention' ? 2 : 1, scope: scope === 'all' ? undefined : scope, building_id: building ? Number(building) : undefined, acknowledged: status === 'any' ? undefined : status === 'acknowledged', sort, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
      { signal },
    ),
  );
  // timeline: whole-society alerts needing attention drawn on the daily peak demand
  const timeline = useApi(`soc-alert-tl:${society.id}:${nonce}`, (signal) => societyApi.anomalies(society.id, { scope: 'society', min_severity: 2, sort: 'time', limit: 500 }, { signal }));
  const daily = useApi(`soc-alert-daily:${society.id}`, (signal) => societyApi.consumption(society.id, { resolution: 'daily' }, { signal }));

  const markers = useMemo<TsMarker[]>(
    () => (timeline.data?.events ?? []).map((e) => ({ id: e.id, t: parseNaive(e.peak_ts), v: e.peak_kw ?? 0, shape: shapeFor(e.types), color: SEV_COLOR[e.severity], label: `${e.severity} alert, ${formatTs(e.peak_ts)}`, selected: e.id === selected })),
    [timeline.data, selected],
  );
  const events = list.data?.events ?? [];
  const current: SocietyAnomaly | null = events.find((e) => e.id === selected) ?? timeline.data?.events.find((e) => e.id === selected) ?? null;
  const sum = list.data?.summary;
  const total = list.data?.total ?? 0;

  const ack = async (e: SocietyAnomaly) => {
    setBusy(e.id);
    try {
      await societyApi.acknowledge(society.id, e.id, !e.acknowledged);
      setNonce((n) => n + 1);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Could not update the alert.', 'error');
    } finally {
      setBusy(null);
    }
  };

  const columns: Column<SocietyAnomaly>[] = [
    { key: 't', header: 'When', render: (e) => <button type="button" className="text-left text-accent underline" onClick={() => setSelected(e.id)}>{formatTs(e.peak_ts)}</button> },
    { key: 's', header: 'Severity', render: (e) => <SeverityBadge severity={e.severity} /> },
    { key: 'w', header: 'Where', render: (e) => (e.scope === 'society' ? 'Whole society' : (e.building ?? 'Building')) },
    { key: 'k', header: 'What', render: (e) => e.types.map((t) => t.replace('_', ' ')).join(', ') },
    { key: 'v', header: 'Demand vs expected', align: 'right', render: (e) => (e.peak_kw != null && e.expected_kw != null ? `${fmtNum(e.peak_kw, 0)} vs ${fmtNum(e.expected_kw, 0)} kW` : '–') },
    { key: 'h', header: 'Hours', align: 'right', render: (e) => fmtInt(e.hours) },
    {
      key: 'a',
      header: 'Status',
      render: (e) => (
        <span className="flex items-center gap-2">
          {e.acknowledged ? <Badge tone="good">Acknowledged</Badge> : <Badge>Open</Badge>}
          <WriteOnly>
            <button type="button" className="btn-ghost text-xs" onClick={() => void ack(e)} disabled={busy === e.id} aria-label={`${e.acknowledged ? 'Reopen' : 'Acknowledge'} alert at ${formatTs(e.peak_ts)}`}>
              {busy === e.id ? <Spinner /> : e.acknowledged ? 'Reopen' : 'Acknowledge'}
            </button>
          </WriteOnly>
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <Notice title="What an alert means">
        An alert marks demand that is unusual for that hour of the week compared with the previous weeks. It is not a confirmed fault: term breaks, holidays and events create alerts too, and the dataset has no fault labels, so no detection accuracy is claimed.
      </Notice>
      {sum && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiTile label="Whole-society alerts" value={fmtInt((sum.society.high ?? 0) + (sum.society.medium ?? 0) + (sum.society.low ?? 0))} sub={`${fmtInt(sum.society.high ?? 0)} high, ${fmtInt(sum.society.medium ?? 0)} medium, ${fmtInt(sum.society.low ?? 0)} low`} />
          <KpiTile label="Building alerts" value={fmtInt((sum.building.high ?? 0) + (sum.building.medium ?? 0) + (sum.building.low ?? 0))} sub={`${fmtInt(sum.building.high ?? 0)} high, ${fmtInt(sum.building.medium ?? 0)} medium`} />
          <KpiTile label="Open (not acknowledged)" value={fmtInt(sum.open)} tone={sum.open > 0 ? 'warn' : 'good'} />
          <KpiTile label="Matching the filters" value={fmtInt(total)} />
        </div>
      )}
      <Card title="Alert timeline" description="Daily peak demand with the medium and high alerts on the whole society. Click a marker to read its explanation.">
        {daily.error ? (
          <ErrorState error={daily.error} onRetry={daily.reload} />
        ) : daily.loading && !daily.data ? (
          <Loading label="Loading timeline" />
        ) : (
          <SeriesChart
            title="Daily peak demand with alerts"
            summary={`Daily peak demand with ${markers.length} marked alerts on the whole society. The alert list below has every alert with its explanation.`}
            rows={consumptionRows(daily.data?.points ?? [], 'peak_kw')}
            lines={[{ key: 'v', name: 'Daily peak demand (kW)', color: 'var(--s1)' }]}
            markers={markers}
            onMarkerClick={(id) => setSelected(Number(id))}
            unit="kW"
            digits={0}
            style="day"
            height={300}
            footer="Triangles up: unusually high. Triangles down: unusually low. Diamonds: flat (stuck) readings. Circles: unusual pattern. Colour shows severity and the label repeats it."
          />
        )}
      </Card>
      {current && (
        <Card title={alertTitle(current)} actions={<button type="button" className="btn-ghost" onClick={() => setSelected(null)}>Close</button>}>
          <p className="text-sm">{current.explanation}</p>
          <p className="mt-2 text-xs text-ink-2">
            {formatTs(current.start_ts)} to {formatTs(current.end_ts)} ({current.hours} h). Severity {current.severity}
            {current.excess_ratio != null ? `, ${fmtNum(current.excess_ratio, 1)} times the usual range for that hour` : ''}.
          </p>
          {current.top_contributors.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm">
              {current.top_contributors.map((c) => (
                <li key={c.building}>
                  {c.building}: {fmtNum(Math.abs(c.deviation_kwh), 0)} kWh {c.deviation_kwh >= 0 ? 'above' : 'below'} its own expected load ({fmtNum(c.share_of_total_deviation_pct, 0)}% of the summed deviations)
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      <Card
        title="Alerts"
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <Segmented label="Severity" value={level} onChange={setLevel} options={[{ value: 'attention', label: 'Medium and high' }, { value: 'all', label: 'All severities' }]} />
            <Segmented label="Scope" value={scope} onChange={setScope} options={[{ value: 'society', label: 'Whole society' }, { value: 'building', label: 'Buildings' }, { value: 'all', label: 'Both' }]} />
            <Segmented label="Status" value={status} onChange={setStatus} options={[{ value: 'any', label: 'Any' }, { value: 'open', label: 'Open' }, { value: 'acknowledged', label: 'Acknowledged' }]} />
            <SelectField label="Building" value={building} onChange={(e) => setBuilding(e.target.value)}>
              <option value="">All buildings</option>
              {(buildings.data?.buildings ?? []).map((b) => (
                <option key={b.id} value={b.id}>{b.code}</option>
              ))}
            </SelectField>
            <SelectField label="Sort" value={sort} onChange={(e) => setSort(e.target.value as 'time' | 'severity')}>
              <option value="time">Newest first</option>
              <option value="severity">Most severe first</option>
            </SelectField>
          </div>
        }
        padded={false}
      >
        {list.error ? (
          <div className="p-4"><ErrorState error={list.error} onRetry={list.reload} /></div>
        ) : list.loading && !list.data ? (
          <div className="p-4"><Loading label="Loading alerts" /></div>
        ) : events.length === 0 ? (
          <div className="p-4"><EmptyState title="No alerts match these filters">Try showing all severities or both scopes.</EmptyState></div>
        ) : (
          <>
            <Table columns={columns} rows={events} rowKey={(e) => e.id} caption="Alerts with time, severity, location, type and status" dense rowClassName={(e) => (e.id === selected ? 'bg-accent-soft' : '')} />
            <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm">
              <span className="text-ink-2">{page * PAGE_SIZE + 1} to {Math.min(total, (page + 1) * PAGE_SIZE)} of {fmtInt(total)}</span>
              <span className="flex gap-2">
                <button type="button" className="btn-secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
                <button type="button" className="btn-secondary" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
              </span>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

export function SocietyAlertsPage() {
  return (
    <>
      <SocietyHeader title="Alerts" description="Unusual demand on the whole society or on a single building, with the time, severity, size and an explanation built from the measured values." />
      <SocietyGate>{(s) => <Alerts society={s} />}</SocietyGate>
    </>
  );
}
