import { useState, type FormEvent } from 'react';
import { societyApi } from '../../api/endpoints';
import type { SocietySummary } from '../../api/societyTypes';
import { Badge, Card } from '../../components/ui/basic';
import { ConfirmDialog } from '../../components/ui/Modal';
import { ErrorState, Loading, Notice, Spinner } from '../../components/ui/feedback';
import { SelectField, TextField } from '../../components/ui/forms';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtPct } from '../../lib/format';
import { formatDate } from '../../lib/time';
import { useJobs } from '../../state/JobsContext';
import { useSociety } from '../../state/SocietyContext';
import { useToast } from '../../state/ToastContext';
import { SocietyHeader } from '../../components/society/common';

const MAX_MB = 40;
const MAX_MAPPING_MB = 2;

function SocietiesTable() {
  const { societies, loading, error, refresh } = useSociety();
  const { track, active } = useJobs();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<SocietySummary | null>(null);
  const [delError, setDelError] = useState<string | null>(null);
  const running = active.some((j) => j.kind.startsWith('society_'));

  const run = async (label: string, fn: () => Promise<Parameters<typeof track>[0] | void>) => {
    setBusy(label);
    try {
      const job = await fn();
      if (job) track(job);
      else refresh();
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'The request failed.', 'error');
    } finally {
      setBusy(null);
    }
  };

  const columns: Column<SocietySummary>[] = [
    { key: 'n', header: 'Society', render: (s) => <span className="font-medium">{s.name}</span> },
    { key: 'b', header: 'Buildings', align: 'right', render: (s) => fmtInt(s.buildings) },
    { key: 'p', header: 'Period', render: (s) => `${formatDate(s.start)} to ${formatDate(s.end)}` },
    { key: 'v', header: 'Valid hours', align: 'right', render: (s) => fmtPct((100 * s.valid_hours) / Math.max(1, s.hours), 1) },
    { key: 'm', header: 'Models', render: (s) => (!s.has_model ? <Badge>Not trained</Badge> : s.forecast_ready ? <Badge tone="good">Trained, forecasts ready</Badge> : <Badge tone="warn">Evaluated; models not installed</Badge>) },
    {
      key: 'a',
      header: 'Actions',
      render: (s) => (
        <span className="flex flex-wrap gap-2">
          <button type="button" className="btn-secondary" disabled={running || busy !== null} onClick={() => void run(`train${s.id}`, () => societyApi.train(s.id))} aria-label={`Train models for ${s.name}`}>
            {busy === `train${s.id}` ? <Spinner /> : 'Train models'}
          </button>
          <button type="button" className="btn-ghost text-bad" onClick={() => { setDelError(null); setConfirm(s); }} aria-label={`Delete ${s.name}`}>Delete</button>
        </span>
      ),
    },
  ];

  return (
    <Card
      title="Societies"
      description="Training evaluates the models on a chronological split and then refits them on all data; it takes a few minutes per society. It needs about nine months of valid hours."
      actions={
        <button type="button" className="btn-primary" disabled={running || busy !== null} onClick={() => void run('import', () => societyApi.importBundled())}>
          {busy === 'import' ? <Spinner /> : 'Import bundled communities'}
        </button>
      }
      padded={false}
    >
      {error ? (
        <div className="p-4"><ErrorState error={error} onRetry={refresh} /></div>
      ) : loading ? (
        <div className="p-4"><Loading label="Loading societies" /></div>
      ) : (
        <Table columns={columns} rows={societies} rowKey={(s) => s.id} caption="Societies with their data and model status" empty="No societies yet. Import the bundled real-data communities or upload your own meter CSV." />
      )}
      <ConfirmDialog
        open={confirm !== null}
        title="Delete this society?"
        confirmLabel="Delete society"
        error={delError ?? undefined}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (!confirm) return;
          try {
            await societyApi.remove(confirm.id);
            setConfirm(null);
            refresh();
            toast.push('Society deleted.', 'success');
          } catch (e) {
            setDelError(e instanceof Error ? e.message : 'Could not delete.');
          }
        }}
      >
        {confirm?.name} and all of its readings, forecasts, alerts and reports are removed from the database. Trained model files on disk and the processed source files are not touched.
      </ConfirmDialog>
    </Card>
  );
}

function UploadForm() {
  const { track } = useJobs();
  const toast = useToast();
  const [name, setName] = useState('');
  const [unit, setUnit] = useState<'kwh' | 'kw'>('kwh');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileKey, setFileKey] = useState(0);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (name.trim().length < 3) return setError('Give the society a name (at least 3 characters).');
    if (!file) return setError('Choose the meter CSV file.');
    for (const [f, limit] of [[file, MAX_MB], [mapping, MAX_MAPPING_MB]] as const) {
      if (f && f.size > limit * (1 << 20)) return setError(`${f.name} is larger than ${limit} MB.`);
      if (f && !/\.(csv|txt)$/i.test(f.name)) return setError(`${f.name} is not a .csv file.`);
    }
    setBusy(true);
    try {
      const job = await societyApi.upload({ name: name.trim(), unit, description: description.trim(), file, mapping });
      track(job);
      toast.push('Upload accepted; cleaning and storing the readings.', 'info');
      setName('');
      setDescription('');
      setFile(null);
      setMapping(null);
      setFileKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Upload a society" description="Real meter readings of your own community: one CSV with a timestamp column and one column per meter.">
      <form onSubmit={(e) => void submit(e)} className="grid grid-cols-1 gap-4 md:grid-cols-2" noValidate>
        <TextField label="Society name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
        <SelectField label="Values in the file are" value={unit} onChange={(e) => setUnit(e.target.value as 'kwh' | 'kw')} hint="kWh: energy per reading interval. kW: average power over the interval.">
          <option value="kwh">Energy (kWh per interval)</option>
          <option value="kw">Average power (kW)</option>
        </SelectField>
        <div>
          <label className="label" htmlFor="soc-file">Meter readings CSV</label>
          <input key={`f${fileKey}`} id="soc-file" type="file" accept=".csv,.txt,text/csv" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <p className="hint">First column: timestamp. Other columns: one per meter. Intervals of 1, 5, 10, 15, 30 or 60 minutes. Up to {MAX_MB} MB.</p>
        </div>
        <div>
          <label className="label" htmlFor="soc-map">Meter mapping CSV (optional)</label>
          <input key={`m${fileKey}`} id="soc-map" type="file" accept=".csv,.txt,text/csv" className="input" onChange={(e) => setMapping(e.target.files?.[0] ?? null)} />
          <p className="hint">Columns: meter_id, building, kind (building or facility), facility_category (lift, pump, streetlight, clubhouse, other), floor_area_sqm. Without it every column is one building.</p>
        </div>
        <TextField label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} className="md:col-span-2" />
        {error && <div className="md:col-span-2"><Notice tone="error">{error}</Notice></div>}
        <div className="md:col-span-2">
          <button type="submit" className="btn-primary" disabled={busy}>{busy && <Spinner />} Upload and process</button>
        </div>
      </form>
      <Notice title="What happens to the file">
        Readings are aggregated to hourly kWh, cleaned with the documented rules (negative, stuck, spike; exact zeros are invalid for buildings but valid for facility meters) and never filled. Meters below 90% valid hours are rejected and listed. Building codes are pseudonymous (for example GREEN-B01); your own meter names are visible to administrators only. After the upload, use Train models on the society to evaluate and deploy forecasters.
      </Notice>
    </Card>
  );
}

function MeterManagement() {
  const { societies } = useSociety();
  const toast = useToast();
  const [sid, setSid] = useState<number | null>(null);
  const id = sid ?? societies[0]?.id ?? null;
  const [nonce, setNonce] = useState(0);
  const meters = useApi(id ? `soc-meters:${id}:${nonce}` : null, (signal) => societyApi.meters(id as number, { signal }));
  const toggle = async (buildingId: number, active: boolean) => {
    try {
      await societyApi.patchBuilding(id as number, buildingId, active);
      setNonce((n) => n + 1);
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Could not update.', 'error');
    }
  };
  if (societies.length === 0) return null;
  return (
    <Card
      title="Buildings and meters"
      description="Hide a building from comparisons and alerts lists. The stored society total was computed when the data were loaded and is not recomputed."
      actions={
        <SelectField label="Society" value={id ?? ''} onChange={(e) => setSid(Number(e.target.value))}>
          {societies.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </SelectField>
      }
      padded={false}
    >
      {meters.error ? (
        <div className="p-4"><ErrorState error={meters.error} onRetry={meters.reload} /></div>
      ) : meters.loading && !meters.data ? (
        <div className="p-4"><Loading label="Loading meters" /></div>
      ) : (
        <Table
          dense
          caption="Meters of the society"
          rows={meters.data ?? []}
          rowKey={(m) => m.id}
          columns={[
            { key: 'c', header: 'Meter code', render: (m) => m.code },
            { key: 'k', header: 'Kind', render: (m) => (m.kind === 'facility' ? `Facility (${m.facility_category ?? 'other'})` : 'Building') },
            { key: 'u', header: 'Unit / interval', render: (m) => `${m.unit} / ${m.interval_minutes} min` },
            { key: 'v', header: 'Valid hours', align: 'right', render: (m) => fmtPct((m.valid_share ?? 0) * 100, 1) },
            {
              key: 'a',
              header: 'Shown',
              render: (m) =>
                m.building_id ? (
                  <button type="button" className="btn-secondary" onClick={() => void toggle(m.building_id as number, !m.is_active)} aria-label={`${m.is_active ? 'Hide' : 'Show'} ${m.code}`}>
                    {m.is_active ? 'Hide' : 'Show'}
                  </button>
                ) : (
                  <Badge>Always</Badge>
                ),
            },
            { key: 's', header: 'Status', render: (m) => (m.is_active ? <Badge tone="good">Active</Badge> : <Badge>Hidden</Badge>) },
          ]}
        />
      )}
    </Card>
  );
}

export function SocietyAdminPage() {
  return (
    <>
      <SocietyHeader title="Society administration" description="Import, upload, train and manage societies, buildings and meters." />
      <div className="space-y-6">
        <SocietiesTable />
        <UploadForm />
        <MeterManagement />
      </div>
    </>
  );
}
