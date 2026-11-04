import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { datasetApi, forecastApi, modelApi } from '../api/endpoints';
import type { Forecast, ModelVersion } from '../api/types';
import { WriteOnly } from '../auth/guards';
import { ForecastChart } from '../components/charts/ForecastChart';
import { HoldoutNote, HoldoutTable } from '../components/ModelMetrics';
import { Badge, Card, DescriptionList, PageHeader } from '../components/ui/basic';
import { ErrorState, Loading, Notice, Spinner } from '../components/ui/feedback';
import { SelectField, TextField } from '../components/ui/forms';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { saveBlob } from '../lib/download';
import { fmtKw, shortModelId } from '../lib/format';
import { forecastPeak } from '../lib/series';
import { DAY, HOUR, formatTs, parseNaive, toApiTimestamp, toDatetimeLocal } from '../lib/time';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';
import { useToast } from '../state/ToastContext';
import { NoDatasetState } from './DashboardPage';

export function ForecastPage() {
  const { active, loading: dsLoading } = useDatasets();
  const { settledSeq } = useJobs();
  const toast = useToast();
  const id = active?.id ?? null;
  const ready = active?.status === 'ready';

  const models = useApi<ModelVersion[]>(ready && id ? `fc-models:${id}:${settledSeq}` : null, (signal) => modelApi.list(id as number, { signal }));
  const [listNonce, setListNonce] = useState(0);
  const past = useApi<Forecast[]>(ready && id ? `fc-list:${id}:${listNonce}` : null, (signal) => forecastApi.list({ dataset_id: id as number, limit: 20 }, { signal }));

  const [modelId, setModelId] = useState('');
  const [origin, setOrigin] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Forecast | null>(null);
  const [exporting, setExporting] = useState<number | null>(null);

  // reset when the dataset changes
  useEffect(() => {
    setSelected(null);
    setModelId('');
    setOrigin('');
    setFormError(null);
  }, [id]);

  // default to the newest saved forecast
  useEffect(() => {
    if (!selected && past.data && past.data.length > 0) setSelected(past.data[0] ?? null);
  }, [past.data, selected]);

  const activeModel = models.data?.find((m) => m.is_active) ?? null;
  const selectedModel = selected ? (models.data?.find((m) => m.id === selected.model_id) ?? null) : null;

  const originMs = selected ? parseNaive(selected.origin) : null;
  const winStart = originMs !== null ? toApiTimestamp(originMs - 3 * DAY) : null;
  const winEnd = originMs !== null ? toApiTimestamp(originMs + 24 * HOUR) : null;
  const history = useApi(selected && id && winStart && winEnd ? `fc-hist:${id}:${selected.id}` : null, (signal) => datasetApi.readingsHourly(id as number, { start: winStart as string, end: winEnd as string, limit: 400 }, { signal }));

  if (dsLoading) return <Loading label="Loading datasets" />;
  if (!active) return (<><PageHeader title="Forecast" /><NoDatasetState /></>);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setBusy(true);
    setFormError(null);
    try {
      const fc = await forecastApi.create({ dataset_id: id, ...(modelId ? { model_id: modelId } : {}), ...(origin ? { origin: `${origin}:00`.slice(0, 19) } : {}) });
      setSelected(fc);
      setListNonce((n) => n + 1);
      toast.push('Forecast created and saved.', 'success');
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not create the forecast.');
    } finally {
      setBusy(false);
    }
  };

  const exportCsv = async (fc: Forecast) => {
    setExporting(fc.id);
    try {
      const res = await forecastApi.exportCsv(fc.id);
      saveBlob(res.blob, res.filename ?? `forecast_${fc.id}.csv`);
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Export failed.', 'error');
    } finally {
      setExporting(null);
    }
  };

  const pastColumns: Column<Forecast>[] = [
    { key: 'id', header: 'Forecast', render: (f) => `#${f.id}` },
    { key: 'origin', header: 'Origin (dataset clock)', render: (f) => formatTs(f.origin) },
    { key: 'model', header: 'Model version', render: (f) => <span title={f.model_id}>{shortModelId(f.model_id)}</span> },
    { key: 'peak', header: 'Peak', align: 'right', render: (f) => fmtKw(forecastPeak(f)?.kw) },
    { key: 'created', header: 'Saved (server clock)', render: (f) => formatTs(f.created_at) },
    {
      key: 'a',
      header: 'Actions',
      render: (f) => (
        <div className="flex gap-1">
          <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => setSelected(f)} aria-pressed={selected?.id === f.id}>
            {selected?.id === f.id ? 'Showing' : 'View'}
          </button>
          <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => exportCsv(f)} disabled={exporting === f.id}>
            {exporting === f.id ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      ),
    },
  ];

  const peak = selected ? forecastPeak(selected) : null;
  const dsStart = active.start_ts ? parseNaive(active.start_ts) : null;
  const dsEnd = active.end_ts ? parseNaive(active.end_ts) : null;
  const hasModel = (models.data?.length ?? 0) > 0;
  const noModelCard = ready && models.data && models.data.length === 0;

  return (
    <>
      <PageHeader title="Forecast" description={`Next 1 to 24 hours of load for “${active.name}”. Forecasts are saved so you can revisit and export them.`} />
      {!ready && <Notice tone="warn" title="This dataset is not ready">Forecasts need a processed dataset. Current status: {active.status}.</Notice>}
      {ready && (
        <div className="space-y-6">
          <Card title="Create a forecast">
            {noModelCard && (
              <Notice tone="warn" title="No trained model for this dataset">
                <Link to="/models" className="text-accent underline">Train a model</Link> first; forecasts need an active model.
              </Notice>
            )}
            {hasModel && (
              <WriteOnly>
                <form onSubmit={create} className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto]">
                  <SelectField label="Model version" value={modelId} onChange={(e) => setModelId(e.target.value)} hint="Default is the active model.">
                    <option value="">Active model{activeModel ? ` (${shortModelId(activeModel.id)})` : ''}</option>
                    {models.data?.map((m) => (
                      <option key={m.id} value={m.id}>
                        {shortModelId(m.id)}
                        {m.is_active ? ' (active)' : ''}
                      </option>
                    ))}
                  </SelectField>
                  <TextField
                    label="Forecast origin (optional)"
                    type="datetime-local"
                    value={origin}
                    min={dsStart !== null ? toDatetimeLocal(dsStart) : undefined}
                    max={dsEnd !== null ? toDatetimeLocal(dsEnd) : undefined}
                    onChange={(e) => setOrigin(e.target.value)}
                    hint={`Empty = latest data hour (${formatTs(active.end_ts)}). Earlier origins let you compare against what actually happened.`}
                  />
                  <div className="lg:pt-[26px]">
                    <button type="submit" className="btn-primary" disabled={busy}>
                      {busy && <Spinner />}Create forecast
                    </button>
                  </div>
                </form>
                {formError && <div className="mt-3"><Notice tone="error" role="alert">{formError}</Notice></div>}
              </WriteOnly>
            )}
            {models.error && <ErrorState error={models.error} onRetry={models.reload} />}
          </Card>

          {selected && (
            <Card
              title={`Forecast #${selected.id}`}
              description={`Origin ${formatTs(selected.origin)} (dataset clock) · saved ${formatTs(selected.created_at)} (server clock)`}
              actions={
                <button type="button" className="btn-secondary" onClick={() => exportCsv(selected)} disabled={exporting === selected.id}>
                  {exporting === selected.id && <Spinner />}Export CSV
                </button>
              }
            >
              <div className="space-y-5">
                {selected.origin_value_missing && (
                  <Notice tone="warn" title="The reading at the forecast origin is missing">
                    The model had no actual value for the last hour before this forecast, so its short-range accuracy may be lower than the hold-out figures suggest.
                  </Notice>
                )}
                <DescriptionList
                  columns={3}
                  items={[
                    { label: 'Forecast peak', value: peak ? `${fmtKw(peak.kw)} at ${formatTs(peak.ts)} (${peak.horizon} h ahead)` : '–' },
                    { label: 'Model version', value: <span title={selected.model_id}>{shortModelId(selected.model_id)} {selectedModel?.is_active ? <Badge tone="good">active</Badge> : null}</span> },
                    { label: 'Horizons', value: `${selected.points.length} hourly steps` },
                  ]}
                />
                {history.error && <ErrorState error={history.error} onRetry={history.reload} />}
                {history.loading && !history.data && <Loading label="Loading recent readings" />}
                {history.data && <ForecastChart actual={history.data.points} forecast={selected} />}
                <Notice tone="info" title="About the shaded band">
                  The band is built from the model’s hold-out errors (their 10th and 90th percentiles around each prediction, widened with the horizon). It is a rough guide to the likely range, not a guaranteed probability. Where actual readings after the origin exist, you can compare them with the forecast directly.
                </Notice>
                {selectedModel ? (
                  <>
                    <HoldoutNote model={selectedModel} />
                    <HoldoutTable model={selectedModel} />
                  </>
                ) : (
                  models.data && <Notice tone="warn">The model version behind this forecast is no longer available, so its hold-out accuracy cannot be shown.</Notice>
                )}
              </div>
            </Card>
          )}
          {!selected && !past.loading && hasModel && <Notice tone="info" title="No forecast saved yet">Create one above to see the chart and table.</Notice>}

          <Card title="Saved forecasts" description="The 20 most recent forecasts for this dataset.">
            {past.error && <ErrorState error={past.error} onRetry={past.reload} />}
            {past.loading && !past.data && <Loading label="Loading saved forecasts" />}
            {past.data && <Table columns={pastColumns} rows={past.data} rowKey={(f) => f.id} caption="Saved forecasts" empty="No forecasts have been saved for this dataset." />}
          </Card>
        </div>
      )}
    </>
  );
}

