import { useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { datasetApi } from '../api/endpoints';
import type { Dataset, DatasetDetail, DatasetProfile, ReadingPoint } from '../api/types';
import { WriteOnly } from '../auth/guards';
import { BarsChart, LinesChart } from '../components/charts/CategoryCharts';
import { ChartFrame } from '../components/charts/ChartFrame';
import { TimeSeriesChart } from '../components/charts/TimeSeriesChart';
import { Badge, Card, DescriptionList, PageHeader, StatusBadge } from '../components/ui/basic';
import { ErrorState, Loading, Notice, ProgressBar, Spinner } from '../components/ui/feedback';
import { SelectField, TextField } from '../components/ui/forms';
import { ConfirmDialog } from '../components/ui/Modal';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { saveBlob } from '../lib/download';
import { fmtFractionPct, fmtInt, fmtNum, humanize } from '../lib/format';
import { dailyToRows, readingsToRows } from '../lib/series';
import { DAY, HOUR, formatMs, formatTs, parseNaive, toApiTimestamp, toDatetimeLocal } from '../lib/time';
import { MAX_UPLOAD_MB } from '../lib/config';
import { validateUploadFile } from '../lib/validation';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';
import { useToast } from '../state/ToastContext';


// ------------------------------------------------------------------ readings explorer
type Preset = '7' | '30' | '90' | 'all' | 'custom';

function ReadingsExplorer({ ds }: { ds: Dataset }) {
  const startMs = ds.start_ts ? parseNaive(ds.start_ts) : null;
  const endMs = ds.end_ts ? parseNaive(ds.end_ts) : null;
  const [preset, setPreset] = useState<Preset>('30');
  const [cStart, setCStart] = useState('');
  const [cEnd, setCEnd] = useState('');

  const range = useMemo(() => {
    if (startMs === null || endMs === null) return null;
    if (preset === 'all') return { from: startMs, to: endMs };
    if (preset === 'custom') {
      const a = cStart ? parseNaive(cStart) : startMs;
      const b = cEnd ? parseNaive(cEnd) : endMs;
      return Number.isNaN(a) || Number.isNaN(b) || a > b ? null : { from: a, to: b };
    }
    return { from: Math.max(startMs, endMs - Number(preset) * DAY), to: endMs };
  }, [preset, cStart, cEnd, startMs, endMs]);

  const hours = range ? Math.round((range.to - range.from) / HOUR) + 1 : 0;
  const daily = hours > 20000;
  const key = range ? `readings:${ds.id}:${range.from}:${range.to}:${daily ? 'd' : 'h'}` : null;
  const res = useApi(key, async (signal) => {
    const q = { start: toApiTimestamp((range as { from: number }).from), end: toApiTimestamp((range as { to: number }).to), limit: 20000 };
    return daily ? { kind: 'daily' as const, r: await datasetApi.readingsDaily(ds.id, q, { signal }) } : { kind: 'hourly' as const, r: await datasetApi.readingsHourly(ds.id, q, { signal }) };
  });

  const rows = useMemo(() => {
    if (!res.data) return [];
    return res.data.kind === 'daily' ? dailyToRows(res.data.r.points) : readingsToRows(res.data.r.points);
  }, [res.data]);

  const stats = useMemo(() => {
    if (!res.data || res.data.kind !== 'hourly') return null;
    const pts: ReadingPoint[] = res.data.r.points;
    const first = pts[0] ? parseNaive(pts[0].ts) : null;
    const last = pts.length ? parseNaive((pts[pts.length - 1] as ReadingPoint).ts) : null;
    const expected = first !== null && last !== null ? Math.round((last - first) / HOUR) + 1 : 0;
    const valid = pts.filter((p) => p.kw !== null).length;
    return { expected, valid, missing: Math.max(0, expected - valid) };
  }, [res.data]);

  if (startMs === null || endMs === null) return <p className="text-sm text-ink-2">This dataset has no readings yet.</p>;

  const tableRows = rows.filter((r) => r.actual != null);
  const shown = tableRows.slice(0, 500);
  const columns: Column<(typeof shown)[number]>[] = [
    { key: 't', header: daily ? 'Day' : 'Hour starting (dataset clock)', render: (r) => formatMs(r.t, daily ? 'date' : 'full') },
    { key: 'v', header: daily ? 'Mean power (kW)' : 'Power (kW)', align: 'right', render: (r) => fmtNum(r.actual as number, 3) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField label="Range" value={preset} onChange={(e) => setPreset(e.target.value as Preset)} className="w-48">
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="90">Last 90 days</option>
          <option value="all">Whole dataset</option>
          <option value="custom">Custom range</option>
        </SelectField>
        {preset === 'custom' && (
          <>
            <TextField label="From" type="datetime-local" value={cStart} min={toDatetimeLocal(startMs)} max={toDatetimeLocal(endMs)} onChange={(e) => setCStart(e.target.value)} />
            <TextField label="To" type="datetime-local" value={cEnd} min={toDatetimeLocal(startMs)} max={toDatetimeLocal(endMs)} onChange={(e) => setCEnd(e.target.value)} />
          </>
        )}
      </div>
      {preset === 'custom' && !range && <Notice tone="warn" role="alert">Choose a valid range: the start must not be after the end.</Notice>}
      {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
      {res.loading && !res.data && <Loading label="Loading readings" />}
      {res.data && (
        <ChartFrame
          title={daily ? 'Daily mean power' : 'Hourly power'}
          description={daily ? 'The range is longer than 20,000 hours, so the API returns daily means.' : undefined}
          summary={`Line chart of ${daily ? 'daily mean' : 'hourly'} power in kW between ${range ? formatMs(range.from) : ''} and ${range ? formatMs(range.to) : ''}. Hours without a valid reading appear as gaps. A table view lists the values.`}
          table={
            <>
              <Table columns={columns} rows={shown} rowKey={(r) => r.t} caption="Readings" dense />
              {tableRows.length > shown.length && <p className="mt-2 text-xs text-ink-2">Showing the first {shown.length} of {fmtInt(tableRows.length)} readings. Narrow the range to see the rest.</p>}
            </>
          }
          footer={
            stats ? (
              <>
                {fmtInt(stats.valid)} valid hours in this range; {fmtInt(stats.missing)} missing hours are shown as gaps (nothing is interpolated).
              </>
            ) : (
              'Days without any valid hour are shown as gaps.'
            )
          }
        >
          <TimeSeriesChart data={rows} lines={[{ key: 'actual', name: daily ? 'Mean power' : 'Power', color: 'var(--s1)' }]} zoomable height={320} digits={3} />
        </ChartFrame>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ profile
function ProfileCharts({ id, refreshKey }: { id: number; refreshKey: number }) {
  const prof = useApi<DatasetProfile>(`profile:${id}:${refreshKey}`, (signal) => datasetApi.profile(id, { signal }));
  if (prof.loading && !prof.data) return <Loading label="Loading data profile" />;
  if (prof.error) return <ErrorState error={prof.error} onRetry={prof.reload} />;
  const p = prof.data;
  if (!p || p.hourly_profile.length === 0) return <p className="text-sm text-ink-2">There are no valid readings to profile yet.</p>;
  const hourTick = (v: string | number) => `${String(v).padStart(2, '0')}`;
  const hourRows = p.hourly_profile.map((h) => ({ hour: h.hour, mean_kw: h.mean_kw }));
  return (
    <div className="grid gap-8 xl:grid-cols-2">
      <ChartFrame
        title="Average load by hour of day"
        description="Mean of all valid readings for each hour of the day."
        summary={`Average load by hour of day in kW. Highest at ${hourRows.reduce((a, b) => ((b.mean_kw ?? 0) > (a.mean_kw ?? 0) ? b : a)).hour}:00. A table view lists all 24 values.`}
        table={<Table caption="Average load by hour of day" rows={hourRows} rowKey={(r) => r.hour} columns={[{ key: 'h', header: 'Hour of day', render: (r) => `${String(r.hour).padStart(2, '0')}:00` }, { key: 'm', header: 'Mean load (kW)', align: 'right', render: (r) => fmtNum(r.mean_kw, 3) }]} dense />}
      >
        <LinesChart data={hourRows} xKey="hour" series={[{ key: 'mean_kw', name: 'Mean load', color: 'var(--s1)' }]} unit="kW" xLabel="Hour of day" xTickFormatter={hourTick} digits={3} />
      </ChartFrame>
      <ChartFrame
        title="Weekday versus weekend"
        description="Average load by hour of day, weekdays against weekends."
        summary="Two lines of average load by hour of day: weekdays and weekends. A table view lists both."
        legend={[{ label: 'Weekday', color: 'var(--s1)', kind: 'line' }, { label: 'Weekend', color: 'var(--s2)', kind: 'dash' }]}
        table={<Table caption="Weekday versus weekend load" rows={p.weekday_vs_weekend} rowKey={(r) => r.hour} columns={[{ key: 'h', header: 'Hour of day', render: (r) => `${String(r.hour).padStart(2, '0')}:00` }, { key: 'wd', header: 'Weekday (kW)', align: 'right', render: (r) => fmtNum(r.weekday_kw, 3) }, { key: 'we', header: 'Weekend (kW)', align: 'right', render: (r) => fmtNum(r.weekend_kw, 3) }]} dense />}
      >
        <LinesChart data={p.weekday_vs_weekend} xKey="hour" series={[{ key: 'weekday_kw', name: 'Weekday', color: 'var(--s1)' }, { key: 'weekend_kw', name: 'Weekend', color: 'var(--s2)', dashed: true }]} unit="kW" xLabel="Hour of day" xTickFormatter={hourTick} digits={3} />
      </ChartFrame>
      <div className="xl:col-span-2">
        <ChartFrame
          title="Monthly mean load"
          summary={`Bar chart of mean load for each of ${p.monthly_mean_kw.length} months. A table view lists the values.`}
          table={<Table caption="Monthly mean load" rows={p.monthly_mean_kw} rowKey={(r) => r.month} columns={[{ key: 'm', header: 'Month', render: (r) => r.month }, { key: 'v', header: 'Mean load (kW)', align: 'right', render: (r) => fmtNum(r.mean_kw, 3) }]} dense />}
          footer={`Based on ${fmtInt(p.valid_hours ?? null)} valid hours. At least ${fmtInt(p.min_hours_needed_for_forecasting ?? null)} valid hours are needed for forecasting.`}
        >
          <BarsChart data={p.monthly_mean_kw} xKey="month" series={[{ key: 'mean_kw', name: 'Mean load', color: 'var(--s1)' }]} unit="kW" digits={3} />
        </ChartFrame>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ quality report
function QualityReport({ ds }: { ds: DatasetDetail }) {
  const r = ds.report;
  const q = r.quality;
  const counts: [string, number | undefined][] = [
    ['Rows read', r.rows_read],
    ['Missing-value markers', r.missing_value_tokens],
    ['Non-numeric values', r.non_numeric_values],
    ['Negative values (invalid)', r.negative_values],
    ['Duplicate timestamps', r.duplicate_timestamps],
    ['Out-of-order steps', r.out_of_order_steps],
    ['Unparseable timestamps', r.unparseable_timestamps],
    ['Skipped malformed lines', r.skipped_malformed_lines],
    ['Irregular steps', r.irregular_steps],
    ['Gaps longer than 1.5 intervals', r.gaps_longer_than_1_5_intervals],
  ];
  return (
    <div className="space-y-5">
      {(r.warnings?.length ?? 0) > 0 && (
        <Notice tone="warn" title="Warnings from the data check">
          <ul className="list-disc pl-5">
            {r.warnings?.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Notice>
      )}
      {r.suitable_for_forecasting === false && (
        <Notice tone="error" title="Not suitable for forecasting">
          <ul className="list-disc pl-5">
            {(r.unsuitable_reasons ?? []).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Notice>
      )}
      {(r.warnings?.length ?? 0) === 0 && r.suitable_for_forecasting !== false && <Notice tone="good" title="The data check reported no warnings" />}
      <DescriptionList
        columns={3}
        items={[
          { label: 'Quality score', value: q ? `${fmtNum(q.score, 2)} / 100 (${q.grade})` : '–' },
          { label: 'Completeness', value: fmtFractionPct(q?.completeness, 2) },
          { label: 'Regularity', value: fmtFractionPct(q?.regularity, 2) },
          { label: 'Invalid fraction', value: fmtFractionPct(q?.invalid_fraction, 2) },
          { label: 'Valid hours / hours in span', value: `${fmtInt(r.valid_hours)} / ${fmtInt(r.hours_in_span)}` },
          { label: 'Span', value: r.span_days != null ? `${fmtNum(r.span_days, 1)} days` : '–' },
          { label: 'Unit declared', value: r.unit_declared ?? '–' },
          { label: 'Time convention', value: r.timezone_convention ? `${humanize(r.timezone_convention)} (timestamps shown as recorded, not converted)` : '–' },
          { label: 'Sampling interval', value: r.sampling_interval_seconds != null ? `${fmtNum(r.sampling_interval_seconds / 60, 0)} min` : '–' },
          { label: 'Min / mean / max load', value: r.value_summary_kw ? `${fmtNum(r.value_summary_kw.min, 2)} / ${fmtNum(r.value_summary_kw.mean, 2)} / ${fmtNum(r.value_summary_kw.max, 2)} kW` : '–' },
          { label: 'Min valid fraction per hour', value: fmtFractionPct(r.min_valid_fraction, 0) },
          { label: 'Largest gap', value: r.largest_gap_minutes != null ? `${fmtNum(r.largest_gap_minutes, 0)} min` : '–' },
        ]}
      />
      <details className="rounded-lg border border-line">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium">Row-level checks</summary>
        <div className="p-4 pt-0">
          <Table caption="Row-level data checks" rows={counts.filter(([, v]) => v !== undefined)} rowKey={([k]) => k} columns={[{ key: 'k', header: 'Check', render: ([k]) => k }, { key: 'v', header: 'Count', align: 'right', render: ([, v]) => fmtInt(v ?? null) }]} dense />
        </div>
      </details>
      {(r.appends?.length ?? 0) > 0 && (
        <div>
          <h3 className="mb-2 text-sm">Appended data</h3>
          <Table
            caption="Appended data history"
            rows={r.appends ?? []}
            rowKey={(a) => a.at}
            columns={[
              { key: 'at', header: 'Appended at (server clock)', render: (a) => formatTs(a.at) },
              { key: 'rows', header: 'Rows read', align: 'right', render: (a) => fmtInt(a.rows_read) },
              { key: 'range', header: 'Range', render: (a) => `${formatTs(a.range[0])} to ${formatTs(a.range[1])}` },
              { key: 'w', header: 'Warnings', render: (a) => (a.warnings.length ? a.warnings.join('; ') : 'None') },
            ]}
            dense
          />
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ page
export function DatasetDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const nav = useNavigate();
  const { settledSeq, track, active: runningJobs } = useJobs();
  const { refresh, setActiveId, active: activeDs } = useDatasets();
  const toast = useToast();
  const detail = useApi<DatasetDetail>(Number.isInteger(id) ? `dataset:${id}:${settledSeq}` : null, (signal) => datasetApi.detail(id, { signal }));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [reporting, setReporting] = useState(false);
  const [appendBusy, setAppendBusy] = useState(false);
  const [appendError, setAppendError] = useState<string | null>(null);
  const appendRef = useRef<HTMLInputElement>(null);

  if (!Number.isInteger(id)) return <ErrorState error={new Error('That dataset id is not valid.')} title="Dataset not found" />;
  if (detail.loading && !detail.data) return <Loading label="Loading dataset" />;
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} title="Could not load this dataset" />;
  const ds = detail.data;
  if (!ds) return null;
  const ingestJob = runningJobs.find((j) => j.dataset_id === ds.id && j.kind === 'ingest');

  const download = async () => {
    setReporting(true);
    try {
      const res = await datasetApi.report(ds.id);
      saveBlob(res.blob, res.filename ?? `energiq_report_${ds.id}.html`);
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Could not download the report.', 'error');
    } finally {
      setReporting(false);
    }
  };

  const onAppend = async (f: File | null) => {
    if (!f) return;
    const err = validateUploadFile(f, MAX_UPLOAD_MB);
    setAppendError(err);
    if (err) return;
    setAppendBusy(true);
    try {
      const res = await datasetApi.append(ds.id, f);
      track(res.job);
      toast.push('Appending data. Only hours that have a value in the new file are replaced; the rest keep their stored readings.', 'info');
    } catch (e) {
      setAppendError(e instanceof Error ? e.message : 'Append failed.');
    } finally {
      setAppendBusy(false);
      if (appendRef.current) appendRef.current.value = '';
    }
  };

  const remove = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await datasetApi.remove(ds.id);
      if (activeDs?.id === ds.id) setActiveId(null);
      refresh();
      toast.push(`Deleted "${ds.name}" with its models, forecasts and anomalies.`, 'success');
      nav('/datasets', { replace: true });
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed.');
    } finally {
      setDeleting(false);
    }
  };

  const ready = ds.status === 'ready';
  return (
    <>
      <PageHeader
        title={ds.name}
        description={
          <>
            <Link to="/datasets" className="text-accent underline">
              Datasets
            </Link>{' '}
            · {ds.original_filename} · uploaded {formatTs(ds.created_at)} (server clock)
          </>
        }
        actions={
          <>
            {activeDs?.id !== ds.id && ready && (
              <button type="button" className="btn-secondary" onClick={() => setActiveId(ds.id)}>
                Use as active dataset
              </button>
            )}
            {activeDs?.id === ds.id && <Badge tone="accent">Active dataset</Badge>}
            <button type="button" className="btn-secondary" onClick={download} disabled={reporting}>
              {reporting && <Spinner />}Download HTML report
            </button>
            <WriteOnly>
              <button type="button" className="btn-danger" onClick={() => setConfirmDelete(true)}>
                Delete
              </button>
            </WriteOnly>
          </>
        }
      />
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={ds.status} />
          {ready && <span className="text-sm text-ink-2">{fmtInt(ds.valid_hours)} valid of {fmtInt(ds.hours)} hours · {formatTs(ds.start_ts)} to {formatTs(ds.end_ts)}</span>}
        </div>
        {ds.status === 'processing' && (
          <Notice tone="info" title="Processing" role="status">
            {ingestJob ? <ProgressBar value={ingestJob.progress} label="Dataset processing progress" message={ingestJob.message || ingestJob.status} /> : 'The file is being validated and aggregated to hourly values.'}
          </Notice>
        )}
        {ds.status === 'failed' && (
          <Notice tone="error" title="Processing failed">
            {ds.error ?? 'No reason was recorded.'}
          </Notice>
        )}

        {ready && (
          <>
            <Card title="Data quality report" description="Produced when the file was processed. Nothing is imputed: missing hours stay missing.">
              <QualityReport ds={ds} />
            </Card>
            <Card title="Data profile" description="Patterns computed from the stored valid hours.">
              <ProfileCharts id={ds.id} refreshKey={settledSeq} />
            </Card>
            <Card title="Readings explorer" description="Pick a range, drag across the chart to zoom, or use the zoom buttons.">
              <ReadingsExplorer key={`${ds.id}:${ds.end_ts}`} ds={ds} />
            </Card>
            <WriteOnly>
              <Card title="Append newer data" description="Upload another file with the same columns. An existing hour is replaced only when the new file has a value for it; hours that are missing or blank in the new file keep the stored reading.">
                {appendError && <div className="mb-3"><Notice tone="error" role="alert">{appendError}</Notice></div>}
                <input ref={appendRef} id="append-file" type="file" accept=".csv,.txt,.tsv,text/csv,text/plain" className="sr-only" onChange={(e) => onAppend(e.target.files?.[0] ?? null)} />
                <label htmlFor="append-file" className={`btn-secondary cursor-pointer has-[:focus-visible]:outline ${appendBusy ? 'pointer-events-none opacity-50' : ''}`}>
                  {appendBusy && <Spinner />}Choose a file to append
                </label>
                <p className="hint">Column mapping and unit are reused from the original upload ({ds.config.value_column ?? 'value column'}, {ds.config.unit ?? 'kW'}).</p>
              </Card>
            </WriteOnly>
          </>
        )}
      </div>
      <ConfirmDialog open={confirmDelete} title={`Delete "${ds.name}"?`} confirmLabel="Delete dataset" busy={deleting} error={deleteError} onConfirm={remove} onCancel={() => setConfirmDelete(false)}>
        This permanently removes the dataset together with its readings, trained models, saved forecasts and anomaly events. It cannot be undone.
      </ConfirmDialog>
    </>
  );
}

