import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { modelApi } from '../api/endpoints';
import type { ModelVersion, Monitoring } from '../api/types';
import { WriteOnly } from '../auth/guards';
import { BarsChart } from '../components/charts/CategoryCharts';
import { ChartFrame, type LegendItem } from '../components/charts/ChartFrame';
import { HoldoutNote, HoldoutTable, ModelBadge } from '../components/ModelMetrics';
import { Badge, Card, DescriptionList, PageHeader } from '../components/ui/basic';
import { ErrorState, Loading, Notice, ProgressBar, Spinner } from '../components/ui/feedback';
import { SelectField } from '../components/ui/forms';
import { ConfirmDialog } from '../components/ui/Modal';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { fmtInt, fmtNum, fmtPct, modelLabel, shortModelId } from '../lib/format';
import { headlineHorizon, sortedHorizons } from '../lib/models';
import { formatTs } from '../lib/time';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';
import { useToast } from '../state/ToastContext';
import { NoDatasetState } from './DashboardPage';

const METHOD_COLORS: Record<string, string> = { xgboost: 'var(--s1)', naive: 'var(--s2)', seasonal_naive_24: 'var(--s3)', seasonal_naive_168: 'var(--s4)' };

function MaeComparison({ model }: { model: ModelVersion }) {
  const hs = sortedHorizons(model.evaluation);
  if (hs.length === 0) return null;
  const methods = ['xgboost', ...Array.from(new Set(hs.flatMap(([, e]) => Object.keys(e.metrics)))).filter((m) => m !== 'xgboost')];
  const series = methods.map((m) => ({ key: m, name: modelLabel(m), color: METHOD_COLORS[m] ?? 'var(--s5)' }));
  const data: Record<string, string | number | null>[] = hs.map(([h, e]) => ({ horizon: `${h} h`, ...Object.fromEntries(methods.map((m) => [m, e.metrics[m]?.mae ?? null])) }));
  const legend: LegendItem[] = series.map((s) => ({ label: s.name, color: s.color, kind: 'bar' }));
  return (
    <ChartFrame
      title="Hold-out MAE by method and horizon"
      description="Mean absolute error in kW on the hold-out period. Lower is better."
      summary={`Grouped bar chart of hold-out mean absolute error for ${series.map((s) => s.name).join(', ')} at horizons ${hs.map(([h]) => h).join(', ')} hours. A table view lists the values.`}
      legend={legend}
      table={<Table caption="Hold-out MAE by method" rows={data} rowKey={(r) => String(r.horizon)} columns={[{ key: "h", header: "Horizon", render: (r) => String(r.horizon) }, ...series.map((s) => ({ key: s.key, header: `${s.name} (kW)`, align: 'right' as const, render: (r: (typeof data)[number]) => fmtNum(r[s.key] as number | null, 3) }))]} dense />}
    >
      <BarsChart data={data} xKey="horizon" series={series} unit="kW" digits={3} xLabel="Forecast horizon" />
    </ChartFrame>
  );
}

function MonitoringPanel({ model }: { model: ModelVersion }) {
  const [days, setDays] = useState(28);
  const mon = useApi<Monitoring>(`monitoring:${model.id}:${days}`, (signal) => modelApi.monitoring(model.id, days, { signal }));
  const m = mon.data;
  return (
    <Card title="Drift and error monitoring" description="Is the data the model sees now still like the data it was trained on, and are its saved forecasts still as accurate as expected?">
      <div className="space-y-5">
        <SelectField label="Recent window" value={String(days)} onChange={(e) => setDays(Number(e.target.value))} className="w-56">
          {[7, 14, 28, 56, 90, 180].map((d) => (
            <option key={d} value={d}>
              Last {d} days
            </option>
          ))}
        </SelectField>
        {mon.loading && !m && <Loading label="Computing monitoring" />}
        {mon.error && <ErrorState error={mon.error} onRetry={mon.reload} />}
        {m && (
          <>
            {m.retrain_recommended ? (
              <Notice tone="warn" title="The API recommends retraining this model">One of the checks below crossed its alert threshold.</Notice>
            ) : (
              <Notice tone="good" title="The API does not recommend retraining right now" />
            )}
            <div className="grid gap-6 lg:grid-cols-2">
              <section aria-labelledby="drift-h">
                <h3 id="drift-h" className="mb-2 text-sm">
                  Input drift <Badge tone={m.drift.status === 'stable' ? 'good' : m.drift.status === 'not enough data' ? 'neutral' : 'warn'}>{m.drift.status}</Badge>
                </h3>
                {m.drift.psi !== undefined ? (
                  <DescriptionList
                    columns={2}
                    items={[
                      { label: 'PSI (population stability index)', value: fmtNum(m.drift.psi, 3) },
                      { label: 'KS statistic', value: fmtNum(m.drift.ks_statistic, 3) },
                      { label: 'KS p-value', value: m.drift.ks_pvalue !== undefined && m.drift.ks_pvalue < 0.001 ? '< 0.001' : fmtNum(m.drift.ks_pvalue, 3) },
                      { label: 'Mean load, recent ÷ training', value: m.drift.mean_ratio_recent_to_reference != null ? `${fmtNum(m.drift.mean_ratio_recent_to_reference, 2)}×` : '–' },
                      { label: 'Training hours compared', value: fmtInt(m.drift.reference_hours ?? null) },
                      { label: 'Recent hours compared', value: `${fmtInt(m.drift.recent_hours ?? null)} (last ${m.drift.recent_days} days)` },
                    ]}
                  />
                ) : (
                  <p className="text-sm text-ink-2">There is not enough data to compare a recent window with the training data.</p>
                )}
                {!m.drift.new_data_since_training && (
                  <p className="mt-3 text-sm text-ink-2">
                    No data has arrived since this model was trained, so the “recent” window is the last days of the training data itself. A shift here reflects seasonal change inside the training period, not drift after deployment.
                  </p>
                )}
                <details className="mt-3 text-sm text-ink-2">
                  <summary className="cursor-pointer font-medium text-ink">How to read PSI and KS</summary>
                  <p className="mt-2">
                    PSI compares how recent load values are distributed against the training data. The API labels PSI below 0.1 as <em>stable</em>, from 0.1 to below 0.25 as <em>moderate shift</em>, and 0.25 or more as <em>significant shift</em>; only a significant shift triggers the retrain recommendation.
                  </p>
                  <p className="mt-2">
                    The KS statistic is the largest gap between the two cumulative distributions (0 means identical). With thousands of hourly values the p-value is almost always tiny, so it is shown for reference and does not drive the status.
                  </p>
                </details>
              </section>
              <section aria-labelledby="real-h">
                <h3 id="real-h" className="mb-2 text-sm">
                  Realised error of saved forecasts <Badge tone={m.realized_performance.status.startsWith('degraded') ? 'bad' : m.realized_performance.status === 'within expectation' ? 'good' : 'neutral'}>{m.realized_performance.status}</Badge>
                </h3>
                <DescriptionList
                  columns={2}
                  items={[
                    { label: 'Saved forecasts checked', value: fmtInt(m.realized_performance.forecasts_checked) },
                    { label: 'Forecast hours with an actual value', value: fmtInt(m.realized_performance.points_scored) },
                    { label: 'Realised MAE', value: m.realized_performance.realized_mae_kw != null ? `${fmtNum(m.realized_performance.realized_mae_kw, 3)} kW` : '–' },
                    { label: 'Hold-out MAE (mean of 1, 6, 24 h)', value: m.realized_performance.holdout_mae_kw_mean_over_1_6_24h != null ? `${fmtNum(m.realized_performance.holdout_mae_kw_mean_over_1_6_24h, 3)} kW` : '–' },
                    { label: 'Realised ÷ hold-out', value: m.realized_performance.ratio_realized_to_holdout != null ? `${fmtNum(m.realized_performance.ratio_realized_to_holdout, 2)}×` : '–' },
                    { label: 'Trained through', value: formatTs(m.trained_through) },
                    { label: 'Data through', value: formatTs(m.data_through) },
                  ]}
                />
                <p className="mt-3 text-sm text-ink-2">{m.realized_performance.note}</p>
                <p className="mt-2 text-sm text-ink-2">The API calls the model degraded when the realised error is more than 1.25× the hold-out error.</p>
              </section>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

export function ModelsPage() {
  const { active, loading: dsLoading } = useDatasets();
  const { settledSeq, track, active: activeJobs } = useJobs();
  const toast = useToast();
  const nav = useNavigate();
  const params = useParams();
  const id = active?.id ?? null;
  const [nonce, setNonce] = useState(0);
  const models = useApi<ModelVersion[]>(id ? `models:${id}:${settledSeq}:${nonce}` : null, (signal) => modelApi.list(id as number, { signal }));
  const [selectedId, setSelectedId] = useState<string | null>(params.modelId ?? null);
  const [training, setTraining] = useState(false);
  const [trainError, setTrainError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<ModelVersion | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);

  useEffect(() => {
    if (params.modelId) setSelectedId(params.modelId);
  }, [params.modelId]);

  if (dsLoading) return <Loading label="Loading datasets" />;
  if (!active) return (<><PageHeader title="Models" /><NoDatasetState /></>);

  const list = models.data ?? [];
  const selected = list.find((m) => m.id === selectedId) ?? list.find((m) => m.is_active) ?? list[0] ?? null;
  const trainJob = activeJobs.find((j) => j.kind === 'train' && j.dataset_id === active.id);

  const train = async () => {
    setTraining(true);
    setTrainError(null);
    try {
      const job = await modelApi.train(active.id, true);
      track(job);
      toast.push('Training started. It runs in the background.', 'info');
    } catch (e) {
      setTrainError(e instanceof Error ? e.message : 'Could not start training.');
    } finally {
      setTraining(false);
    }
  };
  const activate = async (m: ModelVersion) => {
    setActivating(m.id);
    try {
      await modelApi.activate(m.id);
      setNonce((n) => n + 1);
      toast.push('Model activated.', 'success');
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Could not activate the model.', 'error');
    } finally {
      setActivating(null);
    }
  };
  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await modelApi.remove(toDelete.id);
      if (selectedId === toDelete.id) setSelectedId(null);
      setToDelete(null);
      setNonce((n) => n + 1);
      toast.push('Model deleted.', 'success');
      if (params.modelId) nav('/models', { replace: true });
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed.');
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<ModelVersion>[] = [
    { key: 'id', header: 'Version', render: (m) => <span title={m.id} className="num font-medium">{shortModelId(m.id)}</span> },
    { key: 'st', header: 'Status', render: (m) => <ModelBadge model={m} /> },
    { key: 'train', header: 'Trained through', render: (m) => formatTs(m.train_end) },
    { key: 'rows', header: 'Training rows', align: 'right', render: (m) => fmtInt(m.train_rows) },
    {
      key: 'mae',
      header: 'Hold-out MAE vs best baseline',
      render: (m) => {
        const h = headlineHorizon(m.evaluation);
        if (!h) return '–';
        const base = h.data.metrics[h.data.best_baseline];
        return <span>{h.horizon} h: {fmtNum(h.data.metrics.xgboost?.mae, 3)} vs {fmtNum(base?.mae, 3)} kW ({fmtPct(h.data.mae_improvement_vs_best_baseline_pct)} lower)</span>;
      },
    },
    {
      key: 'a',
      header: 'Actions',
      render: (m) => (
        <div className="flex flex-wrap gap-1">
          <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => setSelectedId(m.id)} aria-pressed={selected?.id === m.id}>
            {selected?.id === m.id ? 'Showing' : 'Details'}
          </button>
          <WriteOnly>
            {!m.is_active && (
              <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => activate(m)} disabled={activating === m.id}>
                Activate
              </button>
            )}
            <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs text-bad" onClick={() => setToDelete(m)}>
              Delete
            </button>
          </WriteOnly>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Models"
        description={`Forecast model versions trained on “${active.name}”. Each version is scored on a chronological hold-out period before it is refitted on all the data.`}
        actions={
          <WriteOnly>
            <button type="button" className="btn-primary" onClick={train} disabled={training || !!trainJob || active.status !== 'ready'}>
              {(training || trainJob) && <Spinner />}Train a new model
            </button>
          </WriteOnly>
        }
      />
      <div className="space-y-6">
        {trainError && <Notice tone="error" role="alert">{trainError}</Notice>}
        {trainJob && (
          <Card title="Training in progress">
            <ProgressBar value={trainJob.progress} label="Training progress" message={trainJob.message || trainJob.status} />
          </Card>
        )}
        {active.status !== 'ready' && <Notice tone="warn" title="This dataset is not ready">Models can be trained once the dataset has been processed (status: {active.status}).</Notice>}
        {models.loading && !models.data && <Loading label="Loading models" />}
        {models.error && <ErrorState error={models.error} onRetry={models.reload} />}
        {models.data && list.length === 0 && (
          <Notice tone="info" title="No model trained for this dataset yet">
            Use “Train a new model” to fit one. Training evaluates the model on a hold-out period first, then fits the final model on all the data.
          </Notice>
        )}
        {list.length > 0 && (
          <Card title="Model versions" padded={false}>
            <div className="p-4 sm:p-5">
              <Table columns={columns} rows={list} rowKey={(m) => m.id} caption="Model versions" />
            </div>
          </Card>
        )}
        {selected && (
          <>
            <Card title={`Hold-out accuracy: ${shortModelId(selected.id)}`}>
              <div className="space-y-5">
                <HoldoutNote model={selected} />
                <DescriptionList
                  columns={3}
                  items={[
                    { label: 'Model family', value: modelLabel(selected.family) },
                    { label: 'Hold-out period', value: selected.evaluation.holdout_start ? `${formatTs(selected.evaluation.holdout_start)} to ${formatTs(selected.evaluation.holdout_end)}` : '–' },
                    { label: 'Trained through', value: formatTs(selected.train_end) },
                  ]}
                />
                <HoldoutTable model={selected} detailed />
                <MaeComparison model={selected} />
                {selected.evaluation.protocol && (
                  <details className="text-sm text-ink-2">
                    <summary className="cursor-pointer font-medium text-ink">Evaluation protocol</summary>
                    <p className="mt-2 max-w-prose">{selected.evaluation.protocol}</p>
                  </details>
                )}
              </div>
            </Card>
            <MonitoringPanel key={selected.id} model={selected} />
          </>
        )}
      </div>
      <ConfirmDialog open={!!toDelete} title="Delete this model version?" confirmLabel="Delete model" busy={deleting} error={deleteError} onConfirm={remove} onCancel={() => setToDelete(null)}>
        Version {toDelete ? shortModelId(toDelete.id) : ''} and its model files are removed. Saved forecasts keep their numbers, but this version can no longer produce new ones.
      </ConfirmDialog>
    </>
  );
}
