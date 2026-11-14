import { useState } from 'react';
import { societyApi } from '../../api/endpoints';
import type { ReportKind, Resolution, SocietyReport, SocietySummary } from '../../api/societyTypes';
import { WriteOnly } from '../../auth/guards';
import { SocietyGate, SocietyHeader, TariffPicker } from '../../components/society/common';
import { Badge, Card, VisuallyHidden } from '../../components/ui/basic';
import { ErrorState, Loading, Notice, Spinner } from '../../components/ui/feedback';
import { SelectField, TextField } from '../../components/ui/forms';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { saveBlob } from '../../lib/download';
import { fmtBytes } from '../../lib/format';
import { formatDate, formatTs, parseNaive, toApiTimestamp } from '../../lib/time';
import { useSociety } from '../../state/SocietyContext';
import { useToast } from '../../state/ToastContext';

const KINDS: { value: ReportKind; label: string; format: 'pdf' | 'csv'; help: string }[] = [
  { value: 'monthly', label: 'Monthly society report (PDF)', format: 'pdf', help: 'Summary, charts, building table, alerts, cost estimate, peak analysis and forecast accuracy for the chosen period (default: the last calendar month of the data).' },
  { value: 'consumption', label: 'Consumption (CSV)', format: 'csv', help: 'Society energy and demand at hourly, daily, weekly or monthly resolution.' },
  { value: 'forecast', label: 'Forecast results (CSV)', format: 'csv', help: 'Held-out test-period predictions against measured demand for one horizon, with the 80% range and the baseline.' },
  { value: 'anomalies', label: 'Alerts (CSV)', format: 'csv', help: 'Every alert with time, severity, size and explanation.' },
  { value: 'cost', label: 'Cost estimate (CSV)', format: 'csv', help: 'Daily energy and estimated cost for the selected tariff. An estimate, not a bill.' },
  { value: 'buildings', label: 'Building comparison (CSV)', format: 'csv', help: 'Energy, share, intensity and peak demand per building.' },
];

function Reports({ society }: { society: SocietySummary }) {
  const { tariffId } = useSociety();
  const toast = useToast();
  const [kind, setKind] = useState<ReportKind>('monthly');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [resolution, setResolution] = useState<Resolution>('daily');
  const [horizon, setHorizon] = useState('24');
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const list = useApi(`soc-reports:${society.id}:${nonce}`, (signal) => societyApi.reports(society.id, { signal }));
  const def = KINDS.find((k) => k.value === kind) ?? (KINDS[0] as (typeof KINDS)[number]);

  const create = async () => {
    setError(null);
    const s = start ? parseNaive(start) : null;
    const e = end ? parseNaive(end) : null;
    if ((start && Number.isNaN(s)) || (end && Number.isNaN(e))) return setError('Enter valid dates.');
    if (s != null && e != null && s > e) return setError('The start date must not be after the end date.');
    setBusy(true);
    try {
      const r = await societyApi.createReport(society.id, {
        kind, format: def.format, tariff_id: tariffId,
        start: s != null ? toApiTimestamp(s) : undefined,
        end: e != null ? toApiTimestamp(e + 23 * 3_600_000) : undefined,
        resolution: kind === 'consumption' ? resolution : undefined,
        horizon: kind === 'forecast' ? Number(horizon) : undefined,
      });
      setNonce((n) => n + 1);
      toast.push(`${r.title} created.`, 'success');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the report.');
    } finally {
      setBusy(false);
    }
  };

  const download = async (r: SocietyReport) => {
    setDownloading(r.id);
    try {
      const res = await societyApi.downloadReport(society.id, r.id);
      saveBlob(res.blob, res.filename ?? r.filename);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Download failed.', 'error');
    } finally {
      setDownloading(null);
    }
  };

  const columns: Column<SocietyReport>[] = [
    { key: 't', header: 'Report', render: (r) => r.title },
    { key: 'f', header: 'Format', render: (r) => <Badge>{r.format.toUpperCase()}</Badge> },
    { key: 'p', header: 'Period', render: (r) => (r.period_start && r.period_end ? `${formatDate(r.period_start)} to ${formatDate(r.period_end)}` : '–') },
    { key: 'c', header: 'Created', render: (r) => formatTs(r.created_at) },
    { key: 's', header: 'Size', align: 'right', render: (r) => fmtBytes(r.size_bytes) },
    { key: 'd', header: <VisuallyHidden>Download</VisuallyHidden>, render: (r) => <button type="button" className="btn-secondary" onClick={() => void download(r)} disabled={downloading === r.id} aria-label={`Download ${r.title}`}>{downloading === r.id ? <Spinner /> : 'Download'}</button> },
  ];

  return (
    <div className="space-y-6">
      <WriteOnly>
        <Card title="Create a report" description={def.help} actions={kind === 'cost' || kind === 'monthly' ? <TariffPicker /> : undefined}>
          <form
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault();
              void create();
            }}
          >
            <SelectField label="Report" value={kind} onChange={(e) => setKind(e.target.value as ReportKind)} className="lg:col-span-2">
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </SelectField>
            <TextField label="From (optional)" type="date" value={start} min={society.start.slice(0, 10)} max={society.end.slice(0, 10)} onChange={(e) => setStart(e.target.value)} />
            <TextField label="To (optional)" type="date" value={end} min={society.start.slice(0, 10)} max={society.end.slice(0, 10)} onChange={(e) => setEnd(e.target.value)} />
            {kind === 'consumption' && (
              <SelectField label="Resolution" value={resolution} onChange={(e) => setResolution(e.target.value as Resolution)}>
                <option value="hourly">Hourly (up to 360 days)</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </SelectField>
            )}
            {kind === 'forecast' && (
              <SelectField label="Horizon" value={horizon} onChange={(e) => setHorizon(e.target.value)} hint="Held-out test period only">
                {['1', '6', '12', '24', '168'].map((h) => (
                  <option key={h} value={h}>{h === '168' ? '7 days' : `${h} h`}</option>
                ))}
              </SelectField>
            )}
            <div className="flex items-end">
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy && <Spinner />} Create report
              </button>
            </div>
          </form>
          {error && <div className="mt-3"><Notice tone="error">{error}</Notice></div>}
        </Card>
      </WriteOnly>
      <Card title="Reports" description="Saved reports of this society. Anyone signed in can download them." padded={false}>
        {list.error ? (
          <div className="p-4"><ErrorState error={list.error} onRetry={list.reload} /></div>
        ) : list.loading && !list.data ? (
          <div className="p-4"><Loading label="Loading reports" /></div>
        ) : (
          <Table columns={columns} rows={list.data ?? []} rowKey={(r) => r.id} caption="Saved reports" empty="No reports yet." dense />
        )}
      </Card>
      <Notice>Reports contain the same pseudonymous building codes as the pages. Cost figures are estimates from the chosen tariff, not bills.</Notice>
    </div>
  );
}

export function SocietyReportsPage() {
  return (
    <>
      <SocietyHeader title="Reports" description="Monthly PDF report and CSV exports of consumption, forecasts, alerts, cost and buildings." />
      <SocietyGate>{(s) => <Reports society={s} />}</SocietyGate>
    </>
  );
}
