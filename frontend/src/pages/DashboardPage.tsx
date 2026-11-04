import { Link } from 'react-router-dom';
import { anomalyApi, datasetApi, forecastApi, modelApi, notificationApi } from '../api/endpoints';
import type { ReadingPoint } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { ForecastChart } from '../components/charts/ForecastChart';
import { Card, KpiTile, PageHeader, StatusBadge } from '../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice, ProgressBar } from '../components/ui/feedback';
import { useApi } from '../hooks/useApi';
import { fmtInt, fmtKw, fmtNum, fmtPct, jobKindLabel, modelLabel } from '../lib/format';
import { headlineHorizon } from '../lib/models';
import { forecastPeak } from '../lib/series';
import { DAY, HOUR, formatDate, formatTs, parseNaive, toApiTimestamp } from '../lib/time';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';

export function NoDatasetState() {
  const { canWrite } = useAuth();
  return (
    <EmptyState
      title="No dataset yet"
      action={
        canWrite ? (
          <Link to="/datasets" className="btn-primary">
            Upload a CSV or load the bundled sample
          </Link>
        ) : undefined
      }
    >
      {canWrite ? 'Upload a CSV of hourly or sub-hourly electricity readings, or load the bundled sample dataset, to start forecasting.' : 'Datasets belong to the account that uploaded them, and your viewer account is read-only, so it cannot upload one.'}
    </EmptyState>
  );
}

export function DashboardPage() {
  const { datasets, active, loading, error, refresh } = useDatasets();
  const { active: running, settledSeq } = useJobs();
  const id = active?.id ?? null;
  const ready = active?.status === 'ready';

  const models = useApi(ready && id ? `dash-models:${id}:${settledSeq}` : null, (signal) => modelApi.list(id as number, { signal }));
  const anomalies = useApi(ready && id ? `dash-anom:${id}:${settledSeq}` : null, (signal) => anomalyApi.summary(id as number, { signal }));
  const forecasts = useApi(ready && id ? `dash-fc:${id}:${settledSeq}` : null, (signal) => forecastApi.list({ dataset_id: id as number, limit: 1 }, { signal }));
  const unread = useApi(`dash-unread:${settledSeq}`, (signal) => notificationApi.list({ unread_only: true, limit: 5 }, { signal }));

  const latestForecast = forecasts.data?.[0] ?? null;
  const originMs = latestForecast ? parseNaive(latestForecast.origin) : null;
  const endMs = active?.end_ts ? parseNaive(active.end_ts) : null;
  // History window: 72 h before the forecast origin through the end of the forecast; else the last 7 days of data.
  const win = ready && id && !forecasts.loading ? (originMs !== null ? { start: originMs - 3 * DAY, end: originMs + 24 * HOUR } : endMs !== null ? { start: endMs - 7 * DAY, end: endMs } : null) : null;
  const history = useApi(win && id ? `dash-hist:${id}:${win.start}:${win.end}` : null, (signal) => datasetApi.readingsHourly(id as number, { start: toApiTimestamp((win as { start: number }).start), end: toApiTimestamp((win as { end: number }).end), limit: 400 }, { signal }));

  if (loading) return <Loading label="Loading your datasets" />;
  if (error) return <ErrorState error={error} onRetry={refresh} title="Could not load datasets" />;
  if (datasets.length === 0 || !active) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <NoDatasetState />
      </>
    );
  }

  const activeModel = models.data?.find((m) => m.is_active) ?? null;
  const head = headlineHorizon(activeModel?.evaluation);
  const base = head ? head.data.metrics[head.data.best_baseline] : undefined;
  const modelMetrics = head?.data.metrics.xgboost;
  const anomSummary = anomalies.data && anomalies.data.run ? anomalies.data : null;
  const peak = latestForecast ? forecastPeak(latestForecast) : null;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={
          <>
            {active.name} · <StatusBadge status={active.status} />
          </>
        }
      />
      {active.status === 'processing' && <Notice tone="info" title="This dataset is still being processed">Figures appear when processing finishes.</Notice>}
      {active.status === 'failed' && (
        <Notice tone="error" title="Processing this dataset failed">
          {active.error ?? 'No reason was recorded.'}
        </Notice>
      )}

      {ready && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <KpiTile label="Data quality score" value={active.quality_score === null ? '–' : `${fmtNum(active.quality_score, 1)} / 100`} sub={<Link to={`/datasets/${active.id}`} className="text-accent underline">Quality report</Link>} />
            <KpiTile label="Valid hours" value={fmtInt(active.valid_hours)} sub={`of ${fmtInt(active.hours)} hours · ${formatDate(active.start_ts)} to ${formatDate(active.end_ts)}`} />
            <KpiTile
              label={head ? `Active model: ${head.horizon} h hold-out MAE` : 'Active model'}
              value={models.loading && !models.data ? '…' : modelMetrics ? fmtKw(modelMetrics.mae, 3) : 'None'}
              sub={
                modelMetrics && base ? (
                  <>
                    Best baseline ({modelLabel(head?.data.best_baseline ?? '')}) {fmtKw(base.mae, 3)} · {fmtPct(head?.data.mae_improvement_vs_best_baseline_pct)} lower error
                  </>
                ) : (
                  <Link to="/models" className="text-accent underline">
                    Train a model
                  </Link>
                )
              }
            />
            <KpiTile
              label="Open anomalies"
              value={anomalies.loading && !anomalies.data ? '…' : anomSummary ? fmtInt(anomSummary.unacknowledged) : 'No run'}
              sub={
                anomSummary ? (
                  <>
                    of {fmtInt(anomSummary.summary.events)} events · high {fmtInt(anomSummary.by_severity.high ?? 0)}, medium {fmtInt(anomSummary.by_severity.medium ?? 0)}, low {fmtInt(anomSummary.by_severity.low ?? 0)}
                  </>
                ) : (
                  <Link to="/anomalies" className="text-accent underline">
                    Run detection
                  </Link>
                )
              }
            />
            <KpiTile
              label="Latest forecast peak"
              value={forecasts.loading && !forecasts.data ? '…' : peak ? fmtKw(peak.kw) : 'None'}
              sub={peak && latestForecast ? <>at {formatTs(peak.ts)} · origin {formatTs(latestForecast.origin)}</> : <Link to="/forecast" className="text-accent underline">Create a forecast</Link>}
            />
          </div>

          <Card title="Recent history and latest forecast" description={latestForecast ? 'The most recently saved forecast, with the actual readings around its origin.' : 'No forecast has been saved for this dataset yet, so only recent readings are shown.'}>
            {history.error && <ErrorState error={history.error} onRetry={history.reload} />}
            {!history.error && (history.loading || forecasts.loading) && !history.data && <Loading label="Loading readings" />}
            {history.data && <ForecastChart actual={history.data.points as ReadingPoint[]} forecast={latestForecast} height={300} zoomable={false} />}
            {history.data && history.data.points.length === 0 && <p className="mt-2 text-sm text-ink-2">The dataset has no readings in this window.</p>}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Unread notifications" actions={<Link to="/notifications" className="text-sm text-accent underline">View all</Link>}>
              {unread.error && <ErrorState error={unread.error} onRetry={unread.reload} />}
              {!unread.error && unread.data && unread.data.length === 0 && <p className="text-sm text-ink-2">Nothing unread.</p>}
              <ul className="divide-y divide-line">
                {(unread.data ?? []).map((n) => (
                  <li key={n.id} className="py-2 text-sm">
                    <p>{n.message}</p>
                    <p className="num text-xs text-muted">{formatTs(n.created_at)}</p>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Running jobs" actions={<Link to="/jobs" className="text-sm text-accent underline">All jobs</Link>}>
              {running.length === 0 && <p className="text-sm text-ink-2">No background job is running.</p>}
              <ul className="space-y-4">
                {running.map((j) => (
                  <li key={j.id}>
                    <p className="mb-1 text-sm font-medium">{jobKindLabel(j.kind)}</p>
                    <ProgressBar value={j.progress} label={`${jobKindLabel(j.kind)} progress`} message={j.message || j.status} />
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
