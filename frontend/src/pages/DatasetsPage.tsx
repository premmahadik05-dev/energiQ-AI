import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { datasetApi, type UploadFields } from '../api/endpoints';
import type { Dataset } from '../api/types';
import { WriteOnly, } from '../auth/guards';
import { useAuth } from '../auth/AuthContext';
import { Badge, Card, PageHeader, StatusBadge } from '../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice, Spinner } from '../components/ui/feedback';
import { CheckboxField, SelectField, Segmented, TextField } from '../components/ui/forms';
import { Table, type Column } from '../components/ui/Table';
import { fmtBytes, fmtInt, fmtNum } from '../lib/format';
import { MAX_UPLOAD_MB } from '../lib/config';
import { formatDate } from '../lib/time';
import { validateUploadFile, validateUploadForm, type UploadFormValues } from '../lib/validation';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';
import { useToast } from '../state/ToastContext';

function UploadCard() {
  const { track } = useJobs();
  const { refresh, setActiveId } = useDatasets();
  const toast = useToast();
  const nav = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [name, setName] = useState('');
  const [valueColumn, setValueColumn] = useState('');
  const [unit, setUnit] = useState('kW');
  const [mode, setMode] = useState<'single' | 'split'>('single');
  const [timestampColumn, setTimestampColumn] = useState('');
  const [dateColumn, setDateColumn] = useState('');
  const [timeColumn, setTimeColumn] = useState('');
  const [delimiter, setDelimiter] = useState('');
  const [dayfirst, setDayfirst] = useState(false);
  const [timestampFormat, setTimestampFormat] = useState('');
  const [tz, setTz] = useState('logger_clock');
  const [errors, setErrors] = useState<ReturnType<typeof validateUploadForm>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = (f: File | null) => {
    setFile(f);
    setFileError(f ? validateUploadFile(f, MAX_UPLOAD_MB) : null);
    if (f && !name) setName(f.name.replace(/\.[^.]+$/, ''));
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0] ?? null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const fe = validateUploadFile(file, MAX_UPLOAD_MB);
    const values: UploadFormValues = { name, valueColumn, mode, timestampColumn, dateColumn, timeColumn };
    const errs = validateUploadForm(values);
    setFileError(fe);
    setErrors(errs);
    if (fe || Object.keys(errs).length > 0 || !file) return;
    const fields: UploadFields = {
      name: name.trim(),
      value_column: valueColumn.trim(),
      unit,
      dayfirst,
      timezone_convention: tz,
      delimiter: delimiter || undefined,
      timestamp_format: timestampFormat.trim() || undefined,
      ...(mode === 'single' ? { timestamp_column: timestampColumn.trim() } : { date_column: dateColumn.trim(), time_column: timeColumn.trim() }),
    };
    setBusy(true);
    setServerError(null);
    try {
      const res = await datasetApi.upload(file, fields);
      track(res.job);
      setActiveId(res.dataset.id);
      refresh();
      toast.push(`Uploaded "${res.dataset.name}". Processing started.`, 'info');
      nav(`/datasets/${res.dataset.id}`);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Upload a CSV" description={`Hourly or finer readings. Accepted: .csv, .txt, .tsv up to ${MAX_UPLOAD_MB} MB (the server enforces its own limit).`}>
      <form onSubmit={submit} noValidate className="space-y-5">
        {serverError && <Notice tone="error" role="alert">{serverError}</Notice>}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`rounded-lg border-2 border-dashed p-5 text-center ${dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-sunken'}`}
        >
          <input ref={fileRef} id="upload-file" type="file" accept=".csv,.txt,.tsv,text/csv,text/plain" className="sr-only" onChange={(e) => pick(e.target.files?.[0] ?? null)} aria-describedby="upload-file-hint" />
          <label htmlFor="upload-file" className="btn-secondary cursor-pointer has-[:focus-visible]:outline">
            Choose file
          </label>
          <p id="upload-file-hint" className="mt-2 text-sm text-ink-2">
            {file ? (
              <>
                <strong className="text-ink">{file.name}</strong> · {fmtBytes(file.size)}
              </>
            ) : (
              'or drag a file here'
            )}
          </p>
          {fileError && <p role="alert" className="mt-1 text-sm font-medium text-bad">{fileError}</p>}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Dataset name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} maxLength={120} />
          <TextField label="Value column" value={valueColumn} onChange={(e) => setValueColumn(e.target.value)} error={errors.valueColumn} hint="The header of the column with the consumption values." />
          <SelectField label="Unit of the values" value={unit} onChange={(e) => setUnit(e.target.value)} hint="Power (kW, W, MW) or energy per reading interval (kWh, Wh, MWh).">
            {['kW', 'W', 'MW', 'kWh', 'Wh', 'MWh'].map((u) => (
              <option key={u}>{u}</option>
            ))}
          </SelectField>
          <SelectField label="Delimiter" value={delimiter} onChange={(e) => setDelimiter(e.target.value)} hint="Auto-detected from the header line when left on automatic.">
            <option value="">Automatic</option>
            <option value=",">Comma (,)</option>
            <option value=";">Semicolon (;)</option>
            <option value="tab">Tab</option>
            <option value="|">Pipe (|)</option>
          </SelectField>
        </div>

        <div>
          <Segmented hideLabel={false} label="Timestamp layout" value={mode} onChange={setMode} options={[{ value: 'single', label: 'One timestamp column' }, { value: 'split', label: 'Separate date and time columns' }]} />
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {mode === 'single' ? (
              <TextField label="Timestamp column" value={timestampColumn} onChange={(e) => setTimestampColumn(e.target.value)} error={errors.timestampColumn} />
            ) : (
              <>
                <TextField label="Date column" value={dateColumn} onChange={(e) => setDateColumn(e.target.value)} error={errors.dateColumn} />
                <TextField label="Time column" value={timeColumn} onChange={(e) => setTimeColumn(e.target.value)} error={errors.timeColumn} />
              </>
            )}
            <TextField label="Timestamp format (optional)" value={timestampFormat} onChange={(e) => setTimestampFormat(e.target.value)} hint="strptime pattern such as %d/%m/%Y %H:%M:%S. Leave empty to auto-detect." placeholder="%Y-%m-%d %H:%M:%S" maxLength={60} />
            <SelectField label="Time convention" value={tz} onChange={(e) => setTz(e.target.value)} hint="Timestamps are stored and shown exactly as in the file; nothing is converted.">
              <option value="logger_clock">Logger clock (as recorded)</option>
              <option value="utc">UTC</option>
              <option value="local_with_dst">Local time with daylight saving</option>
            </SelectField>
          </div>
          <div className="mt-3">
            <CheckboxField label="Day comes first in dates (31/12/2009)" checked={dayfirst} onChange={(e) => setDayfirst(e.target.checked)} />
          </div>
        </div>

        <button type="submit" className="btn-primary" disabled={busy}>
          {busy && <Spinner />}Upload and process
        </button>
      </form>
    </Card>
  );
}

function SampleCard() {
  const { track } = useJobs();
  const { refresh, setActiveId } = useDatasets();
  const toast = useToast();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await datasetApi.loadSample();
      track(res.job);
      setActiveId(res.dataset.id);
      refresh();
      toast.push('Loading the bundled sample dataset.', 'info');
      nav(`/datasets/${res.dataset.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not load the sample.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Bundled sample dataset" description="One year of hourly household readings from the public UCI dataset, ready to train on.">
      {err && <div className="mb-3"><Notice tone="error" role="alert">{err}</Notice></div>}
      <button type="button" className="btn-secondary" onClick={load} disabled={busy}>
        {busy && <Spinner />}Load bundled sample dataset
      </button>
    </Card>
  );
}

export function DatasetsPage() {
  const { datasets, loading, error, refresh, active, setActiveId } = useDatasets();
  const { canWrite } = useAuth();

  const columns: Column<Dataset>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (d) => (
        <div>
          <Link to={`/datasets/${d.id}`} className="font-medium text-accent underline">
            {d.name}
          </Link>
          <p className="text-xs text-muted">{d.original_filename}</p>
          {d.status === 'failed' && d.error && <p className="mt-1 text-xs text-bad">{d.error}</p>}
        </div>
      ),
    },
    { key: 'status', header: 'Status', render: (d) => <StatusBadge status={d.status} /> },
    { key: 'quality', header: 'Quality', align: 'right', render: (d) => (d.quality_score === null ? '–' : `${fmtNum(d.quality_score, 1)} / 100`) },
    { key: 'period', header: 'Period', render: (d) => (d.start_ts ? `${formatDate(d.start_ts)} to ${formatDate(d.end_ts)}` : '–') },
    { key: 'hours', header: 'Valid / total hours', align: 'right', render: (d) => (d.status === 'ready' ? `${fmtInt(d.valid_hours)} / ${fmtInt(d.hours)}` : '–') },
    {
      key: 'sel',
      header: 'Active',
      render: (d) =>
        active?.id === d.id ? (
          <Badge tone="accent">active</Badge>
        ) : (
          <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => setActiveId(d.id)} disabled={d.status !== 'ready'}>
            Use this
          </button>
        ),
    },
  ];

  return (
    <>
      <PageHeader title="Datasets" description="Your uploaded series. Everything else in the app works on the active dataset." />
      <div className="space-y-6">
        {!canWrite && <Notice tone="info" title="Read-only account">Viewer accounts cannot upload data or load the sample.</Notice>}
        <Card title="Your datasets" padded={false}>
          <div className="p-4 sm:p-5">
            {loading && <Loading label="Loading datasets" />}
            {error && <ErrorState error={error} onRetry={refresh} />}
            {!loading && !error && datasets.length === 0 && (
              <EmptyState title="No dataset yet">{canWrite ? 'Upload a CSV or load the bundled sample dataset below.' : 'There is nothing to show, and this account cannot upload.'}</EmptyState>
            )}
            {datasets.length > 0 && <Table columns={columns} rows={datasets} rowKey={(d) => d.id} caption="Your datasets" />}
          </div>
        </Card>
        <WriteOnly>
          <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
            <UploadCard />
            <SampleCard />
          </div>
        </WriteOnly>
      </div>
    </>
  );
}
