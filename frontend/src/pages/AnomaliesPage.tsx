import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { anomalyApi, datasetApi } from '../api/endpoints';
import type { AnomalyEvent, Severity } from '../api/types';
import { WriteOnly } from '../auth/guards';
import { ChartFrame, type LegendItem } from '../components/charts/ChartFrame';
import { TimeSeriesChart, type TsMarker } from '../components/charts/TimeSeriesChart';
import { Badge, Card, KpiTile, PageHeader } from '../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice, ProgressBar, Spinner } from '../components/ui/feedback';
import { SelectField, Segmented, TextField } from '../components/ui/forms';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { fmtInt, fmtNum, fmtPct } from '../lib/format';
import { readingsToRows } from '../lib/series';
import { DAY, formatTs, parseNaive, toApiTimestamp } from '../lib/time';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';
import { useToast } from '../state/ToastContext';
import { NoDatasetState } from './DashboardPage';

const SEV_COLOR: Record<Severity, string> = { high: 'var(--sev-high)', medium: 'var(--sev-medium)', low: 'var(--sev-low)' };
const TYPE_LABEL: Record<string, string> = { spike: 'Spike (unusually high)', drop: 'Drop (unusually low)', flat_run: 'Flat run (identical readings)', unusual_pattern: 'Unusual pattern' };
const PAGE_SIZE = 15;

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

function shapeFor(types: string[]): TsMarker['shape'] {
  if (types.includes('flat_run')) return 'diamond';
  if (types.includes('spike')) return 'triangleUp';
  if (types.includes('drop')) return 'triangleDown';
  return 'circle';
}

export function AnomaliesPage() {
  const { active, loading: dsLoading, setActiveId, datasets } = useDatasets();
  const { track, active: activeJobs, settledSeq } = useJobs();
  const toast = useToast();
  const [params] = useSearchParams();
  const id = active?.id ?? null;
  const ready = active?.status === 'ready';

  // notification links look like /anomalies?dataset=3
  const linked = Number(params.get('dataset'));
  useEffect(() => {
    if (Number.isInteger(linked) && linked > 0 && datasets.some((d) => d.id === linked)) setActiveId(linked);
  }, [linked, datasets, setActiveId]);

  const [sensitivity, setSensitivity] = useState<'low' | 'medium' | 'high'>('medium');
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [severity, setSeverity] = useState<'' | Severity>('');
  const [ackFilter, setAckFilter] = useState<'all' | 'open' | 'acknowledged'>('all');
  const [sort, setSort] = useState<'severity' | 'time'>('severity');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<number | string | null>(null);
  const [win, setWin] = useState<'30' | '90' | 'all' | 'event'>('90');
  const [ackBusy, setAckBusy] = useState<number | null>(null);

  const summary = useApi(ready && id ? `an-sum:${id}:${settledSeq}` : null, (signal) => anomalyApi.summary(id as number, { signal }));
  const list = useApi(ready && id ? `an-list:${id}:${settledSeq}:${severity}:${ackFilter}:${sort}` : null, (signal) =>
    anomalyApi.list({ dataset_id: id as number, severity: severity || undefined, acknowledged: ackFilter === 'all' ? undefined : ackFilter === 'acknowledged', sort, limit: 500 }, { signal }),
  );

  useEffect(() => setPage(0), [severity, ackFilter, sort, from, to, id]);

  const fromMs = from ? parseNaive(from) : null;
  const toMs = to ? parseNaive(to) + DAY - 1 : null;
  const items = useMemo(
    () =>
      (list.data?.items ?? []).filter((e) => {
        const s = parseNaive(e.start_ts);
        return (fromMs === null || s >= fromMs) && (toMs === null || s <= toMs);
      }),
    [list.data, fromMs, toMs],
  );
  const selected = items.find((e) => e.id === selectedId) ?? null;

  const endMs = active?.end_ts ? parseNaive(active.end_ts) : null;
  const startMs = active?.start_ts ? parseNaive(active.start_ts) : null;
  const winRange = useMemo(() => {
    if (endMs === null || startMs === null) return null;
    if (win === 'event' && selected) {
      const c = parseNaive(selected.peak_ts);
      return { from: Math.max(startMs, c - 3 * DAY), to: Math.min(endMs, c + 3 * DAY) };
    }
    if (win === 'all') return { from: startMs, to: endMs };
    const days = win === '30' ? 30 : 90;
    return { from: Math.max(startMs, endMs - days * DAY), to: endMs };
  }, [win, selected, endMs, startMs]);
  const readings = useApi(ready && id && winRange ? `an-read:${id}:${winRange.from}:${winRange.to}` : null, (signal) =>
    datasetApi.readingsHourly(id as number, { start: toApiTimestamp((winRange as { from: number }).from), end: toApiTimestamp((winRange as { to: number }).to), limit: 20000 }, { signal }),
  );
  const rows = useMemo(() => (readings.data ? readingsToRows(readings.data.points) : []), [readings.data]);
  const markers = useMemo<TsMarker[]>(
    () =>
      items
        .filter((e) => e.peak_value_kw !== null)
        .map((e) => ({
          id: e.id,
          t: parseNaive(e.peak_ts),
          v: e.peak_value_kw as number,
          shape: shapeFor(e.types),
          color: SEV_COLOR[e.severity] ?? SEV_COLOR.low,
          selected: e.id === selectedId,
          label: `${e.severity} ${e.types.join('/')} · ${formatTs(e.peak_ts)} · observed ${fmtNum(e.peak_value_kw)} kW${e.expected_kw !== null ? `, typical ${fmtNum(e.expected_kw)} kW` : ''}`,
        })),
    [items, selectedId],
  );

  if (dsLoading) return <Loading label="Loading datasets" />;
  if (!active) return (<><PageHeader title="Anomalies" /><NoDatasetState /></>);

  const job = activeJobs.find((j) => j.kind === 'anomaly' && j.dataset_id === active.id);
  const sum = summary.data && summary.data.run ? summary.data : null;

  const run = async () => {
    setRunning(true);
    setRunError(null);
    try {
      track(await anomalyApi.run(active.id, sensitivity));
      toast.push('Anomaly detection started.', 'info');
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Could not start detection.');
    } finally {
      setRunning(false);
    }
  };

  const toggleAck = async (e: AnomalyEvent) => {
    setAckBusy(e.id);
    try {
      await anomalyApi.acknowledge(e.id, !e.acknowledged);
      list.reload();
      summary.reload();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Could not update the event.', 'error');
    } finally {
      setAckBusy(null);
    }
  };

  const total = list.data?.total ?? 0;
  const pageItems = items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));

  const columns: Column<AnomalyEvent>[] = [
    { key: 'sev', header: 'Severity', render: (e) => <SeverityBadge severity={e.severity} /> },
    { key: 'type', header: 'Type', render: (e) => e.types.map((t) => TYPE_LABEL[t] ?? t).join(', ') },
    { key: 'when', header: 'Start (dataset clock)', render: (e) => <span>{formatTs(e.start_ts)}<span className="block text-xs text-muted">{fmtInt(e.hours)} h</span></span> },
    { key: 'peak', header: 'Peak vs typical', align: 'right', render: (e) => <span>{fmtNum(e.peak_value_kw)} kW<span className="block text-xs text-muted">typical {fmtNum(e.expected_kw)} kW</span></span> },
    { key: 'ex', header: 'Beyond usual range', align: 'right', render: (e) => (e.peak_excess_ratio === null ? '–' : `${fmtNum(e.peak_excess_ratio, 1)}×`) },
    { key: 'why', header: 'Why it was flagged', className: 'min-w-[16rem] max-w-md', render: (e) => <span className="text-xs text-ink-2">{e.explanation}</span> },
    {
      key: 'act',
      header: 'Status',
      render: (e) => (
        <div className="flex flex-col items-start gap-1">
          {e.acknowledged ? <Badge tone="good">✓ acknowledged</Badge> : <Badge>open</Badge>}
          <button type="button" className="btn-ghost !min-h-[28px] !px-1 text-xs" onClick={() => { setSelectedId(e.id); setWin('event'); }}>
            Show on timeline
          </button>
          <WriteOnly>
            <button type="button" className="btn-secondary !min-h-[28px] !px-2 text-xs" disabled={ackBusy === e.id} onClick={() => toggleAck(e)}>
              {e.acknowledged ? 'Unacknowledge' : 'Acknowledge'}
            </button>
          </WriteOnly>
        </div>
      ),
    },
  ];

  const legend: LegendItem[] = [
    { label: 'Hourly load (kW)', color: 'var(--s1)', kind: 'line' },
    { label: 'Spike', color: 'var(--ink-2)', kind: 'triangleUp' },
    { label: 'Drop', color: 'var(--ink-2)', kind: 'triangleDown' },
    { label: 'Flat run', color: 'var(--ink-2)', kind: 'diamond' },
    { label: 'Unusual pattern', color: 'var(--ink-2)', kind: 'circle' },
    { label: 'High severity', color: 'var(--sev-high)', kind: 'bar' },
    { label: 'Medium severity', color: 'var(--sev-medium)', kind: 'bar' },
    { label: 'Low severity', color: 'var(--sev-low)', kind: 'bar' },
  ];

  return (
    <>
      <PageHeader title="Anomalies" description={`Unusual hours in “${active.name}”, found without labels by comparing each hour with the same hour of earlier weeks.`} />
      <div className="space-y-6">
        <Notice tone="info" title="Unlabelled statistical findings">
          These events are unusual readings, not confirmed faults. There are no ground-truth anomaly labels, so no accuracy figure exists; how many hours are flagged is set by the sensitivity you choose. Unusual-but-legitimate use (guests, holidays) is flagged too.
        </Notice>

        <WriteOnly>
          <Card title="Run detection" description="Replaces the previous run for this dataset. Higher sensitivity flags more hours.">
            <div className="flex flex-wrap items-end gap-4">
              <Segmented hideLabel={false} label="Sensitivity" value={sensitivity} onChange={setSensitivity} options={[{ value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]} />
              <button type="button" className="btn-primary" onClick={run} disabled={running || !!job || !ready}>
                {(running || job) && <Spinner />}Run detection
              </button>
            </div>
            {runError && <div className="mt-3"><Notice tone="error" role="alert">{runError}</Notice></div>}
            {job && <div className="mt-4 max-w-md"><ProgressBar value={job.progress} label="Detection progress" message={job.message || job.status} /></div>}
          </Card>
        </WriteOnly>

        {!ready && <Notice tone="warn" title="This dataset is not ready">Detection needs a processed dataset (status: {active.status}).</Notice>}
        {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
        {summary.loading && !summary.data && ready && <Loading label="Loading summary" />}
        {summary.data && !sum && <EmptyState title="No detection run yet">Choose a sensitivity and run detection to see events. Detection needs several weeks of valid hours.</EmptyState>}

        {sum && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <KpiTile label="Events found" value={fmtInt(sum.summary.events)} sub={`${sum.run.sensitivity} sensitivity · run ${formatTs(sum.run.created_at)} (server clock)`} />
              <KpiTile label="High severity" value={fmtInt(sum.by_severity.high ?? 0)} tone={sum.by_severity.high ? 'bad' : undefined} />
              <KpiTile label="Medium severity" value={fmtInt(sum.by_severity.medium ?? 0)} />
              <KpiTile label="Low severity" value={fmtInt(sum.by_severity.low ?? 0)} />
              <KpiTile label="Open (not acknowledged)" value={fmtInt(sum.unacknowledged)} sub={`${fmtPct(sum.summary.flagged_pct_of_valid, 2)} of valid hours flagged`} />
            </div>
            <p className="text-sm text-ink-2">{sum.note}</p>
          </>
        )}

        {sum && (
          <>
            <Card title="Timeline" description="Hourly load with the peak hour of each event marked. Each marker’s hover text gives the observed and typical value.">
              <div className="mb-4 flex flex-wrap items-end gap-4">
                <SelectField label="Window" value={win} onChange={(e) => setWin(e.target.value as typeof win)} className="w-full sm:w-72">
                  <option value="30">Last 30 days</option>
                  <option value="90">Last 90 days</option>
                  <option value="all">Whole dataset</option>
                  <option value="event" disabled={!selected}>Around selected event (±3 days)</option>
                </SelectField>
                {selected && <p className="pb-2 text-sm text-ink-2">Selected: {selected.severity} event at {formatTs(selected.peak_ts)}</p>}
              </div>
              {readings.error && <ErrorState error={readings.error} onRetry={readings.reload} />}
              {readings.loading && !readings.data && <Loading label="Loading readings" />}
              {readings.data && (
                <ChartFrame
                  title="Load and anomaly events"
                  summary={`Line chart of hourly load with ${markers.filter((m) => winRange && m.t >= winRange.from && m.t <= winRange.to).length} anomaly event markers in the window. The event table below lists every event.`}
                  legend={legend}
                  table={<p className="text-sm text-ink-2">The event table below lists every event with its time, observed value and typical value.</p>}
                  footer="Markers sit at each event’s peak hour at the observed value. Typical values are the median of the same hour of the week in earlier weeks; the API gives them per event only, not as a continuous band."
                >
                  <TimeSeriesChart data={rows} lines={[{ key: 'actual', name: 'Load', color: 'var(--s1)' }]} markers={markers} zoomable height={320} onMarkerClick={(mid) => setSelectedId(mid)} />
                </ChartFrame>
              )}
            </Card>

            <Card title="Events" description={`${fmtInt(items.length)} shown${list.data && total > (list.data.items.length) ? ` (the API holds ${fmtInt(total)}; only the first ${fmtInt(list.data.items.length)} are loaded, narrow the filters to see others)` : ''}.`}>
              <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <SelectField label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value as '' | Severity)}>
                  <option value="">All</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </SelectField>
                <SelectField label="Status" value={ackFilter} onChange={(e) => setAckFilter(e.target.value as typeof ackFilter)}>
                  <option value="all">All</option>
                  <option value="open">Open</option>
                  <option value="acknowledged">Acknowledged</option>
                </SelectField>
                <SelectField label="Sort by" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
                  <option value="severity">Severity</option>
                  <option value="time">Newest first</option>
                </SelectField>
                <TextField label="Starts from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
                <TextField label="Starts until" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
              </div>
              {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
              {list.loading && !list.data && <Loading label="Loading events" />}
              {list.data && (
                <>
                  <Table columns={columns} rows={pageItems} rowKey={(e) => e.id} caption="Anomaly events" empty="No events match these filters." rowClassName={(e) => (e.id === selectedId ? 'bg-accent-soft' : '')} />
                  {pages > 1 && (
                    <div className="mt-3 flex items-center justify-between gap-3 text-sm">
                      <span className="text-ink-2">
                        Page {page + 1} of {pages}
                      </span>
                      <div className="flex gap-2">
                        <button type="button" className="btn-secondary" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
                          Previous
                        </button>
                        <button type="button" className="btn-secondary" onClick={() => setPage((p) => Math.min(pages - 1, p + 1))} disabled={page >= pages - 1}>
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </Card>
          </>
        )}
      </div>
    </>
  );
}

