import { useMemo, useState } from 'react';
import { societyApi } from '../../api/endpoints';
import type { Backtest, ErrorAnalysis, HorizonResult, ModelsResponse, SocietySummary } from '../../api/societyTypes';
import { BarsChart } from '../../components/charts/CategoryCharts';
import type { TsRow } from '../../components/charts/TimeSeriesChart';
import { DataBasisNote, SocietyGate, SocietyHeader } from '../../components/society/common';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Badge, Card, DescriptionList, KpiTile } from '../../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { Segmented, TextField } from '../../components/ui/forms';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtNum, fmtPct, fmtSigned, modelLabel } from '../../lib/format';
import { describeModelChoice } from '../../lib/modelChoice';
import { DAY, formatTs, parseNaive, toApiTimestamp } from '../../lib/time';
import { useSociety } from '../../state/SocietyContext';
import { useJobs } from '../../state/JobsContext';

const HORIZON_LABEL: Record<string, string> = { '1': '1 hour', '6': '6 hours', '12': '12 hours', '24': '24 hours', '168': '7 days' };
const WINDOWS = { '7': '7 days', '14': '14 days', '30': '30 days' } as const;
type Win = keyof typeof WINDOWS;
const LEARNED = ['linear', 'random_forest', 'xgboost', 'xgboost_weather'];

interface CompareRow {
  model: string;
  mae: number;
  rmse: number;
  mape: number | null;
  r2: number | null;
  cvMae: number | null;
  tags: string[];
}

function compareRows(r: HorizonResult): CompareRow[] {
  return Object.entries(r.test)
    .map(([m, t]) => {
      const tags: string[] = [];
      if (m === r.best_overall_by_cv) tags.push('Selected (lowest CV error)');
      if (!LEARNED.includes(m)) tags.push('Baseline');
      return { model: m, mae: t.mae, rmse: t.rmse, mape: t.mape_pct, r2: t.r2, cvMae: r.chosen[m]?.cv_mean_fold_mae ?? r.cv?.[m]?._summary?.mean_fold_mae ?? null, tags };
    })
    .sort((a, b) => a.mae - b.mae);
}

function ModelComparison({ models, horizon }: { models: ModelsResponse; horizon: string }) {
  const r = models.horizons[horizon];
  if (!r) return null;
  const rows = compareRows(r);
  const columns: Column<CompareRow>[] = [
    { key: 'm', header: 'Model', render: (x) => <span className={x.tags[0]?.startsWith('Selected') ? 'font-semibold' : ''}>{modelLabel(x.model)}</span> },
    { key: 'cv', header: 'CV MAE (kW)', align: 'right', render: (x) => (x.cvMae == null ? '–' : fmtNum(x.cvMae, 1)) },
    { key: 'mae', header: 'Test MAE (kW)', align: 'right', render: (x) => fmtNum(x.mae, 1) },
    { key: 'rmse', header: 'Test RMSE (kW)', align: 'right', render: (x) => fmtNum(x.rmse, 1) },
    { key: 'mape', header: 'Test MAPE', align: 'right', render: (x) => fmtPct(x.mape, 2) },
    { key: 'r2', header: 'Test R²', align: 'right', render: (x) => fmtNum(x.r2, 3) },
    { key: 'tag', header: 'Note', render: (x) => x.tags.map((t) => <Badge key={t} tone={t.startsWith('Selected') ? 'good' : 'neutral'}>{t}</Badge>) },
  ];
  const boot = r.bootstrap_vs_best_baseline;
  return (
    <Card
      title={`Model comparison, ${HORIZON_LABEL[horizon]} ahead`}
      description="Every model scored once on the same held-out test period. The model is chosen by cross-validated error on earlier data, never by looking at the test period."
    >
      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <div>
          <p className="text-sm font-semibold">Test mean absolute error (kW, lower is better)</p>
          <p className="mb-2 text-xs text-ink-2">The darker bar is the model selected by cross-validation.</p>
          <BarsChart
            data={rows.map((x) => ({ model: modelLabel(x.model), mae: Number(x.mae.toFixed(2)), selected: x.tags.some((t) => t.startsWith('Selected')) ? 1 : 0 }))}
            xKey="model"
            series={[{ key: 'mae', name: 'Test MAE', color: 'var(--s1)' }]}
            colorOf={(row) => (row.selected === 1 ? 'var(--s1)' : 'var(--s1-muted)')}
            unit="kW"
            horizontal
            yWidth={170}
            height={Math.max(220, rows.length * 38)}
            digits={1}
          />
        </div>
        <Table columns={columns} rows={rows} rowKey={(x) => x.model} caption="Model comparison on the held-out test period" dense />
      </div>
      <p className="mt-3 text-xs text-ink-2">
        {describeModelChoice(r)}{' '}
        {boot && `A paired bootstrap over ${boot.days} test days gives a 95% interval of ${fmtNum(boot.ci95_low, 1)} to ${fmtNum(boot.ci95_high, 1)} kW for the MAE difference (${modelLabel(boot.model)} minus ${modelLabel(boot.baseline)}); an interval that includes zero means the two are not clearly different.`}
      </p>
    </Card>
  );
}

function BacktestSection({ society, models, horizon }: { society: SocietySummary; models: ModelsResponse; horizon: string }) {
  const [win, setWin] = useState<Win>('14');
  const testEnd = parseNaive(models.model?.protocol.test_period[1] ?? society.end);
  const testStart = parseNaive(models.model?.protocol.test_period[0] ?? society.start);
  const start = Math.max(testStart, testEnd - Number(win) * DAY + 3_600_000);
  const bt = useApi<Backtest>(`soc-bt:${society.id}:${horizon}:${win}`, (signal) => societyApi.backtest(society.id, { horizon: Number(horizon), start: toApiTimestamp(start), end: toApiTimestamp(testEnd), limit: 1000 }, { signal }));
  const rows = useMemo<TsRow[]>(
    () => (bt.data?.points ?? []).map((p) => ({ t: parseNaive(p.ts), actual: p.actual_kw, predicted: p.predicted_kw, baseline: p.baseline_kw, band: p.lower_kw != null && p.upper_kw != null ? [p.lower_kw, p.upper_kw] : null }) as TsRow),
    [bt.data],
  );
  const r = models.horizons[horizon];
  const m = r?.test[r.best_overall_by_cv];
  const base = r?.test[r.best_baseline_by_cv];
  return (
    <Card
      title={`Actual and predicted, ${HORIZON_LABEL[horizon]} ahead`}
      description="Held-out test period only: each prediction was made the stated time before the hour it predicts, using data up to that moment. Nothing here was seen in training."
      actions={<Segmented label="Window" value={win} onChange={setWin} options={(Object.keys(WINDOWS) as Win[]).map((k) => ({ value: k, label: `Last ${WINDOWS[k]}` }))} />}
    >
      {m && r && (
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <KpiTile label="MAE" value={`${fmtNum(m.mae, 1)} kW`} sub={`Whole test period, ${modelLabel(r.best_overall_by_cv)}`} />
          <KpiTile label="RMSE" value={`${fmtNum(m.rmse, 1)} kW`} />
          <KpiTile label="MAPE" value={fmtPct(m.mape_pct, 2)} sub={m.mape_excluded > 0 ? `${m.mape_excluded} near-zero hours excluded` : undefined} />
          <KpiTile label="R²" value={fmtNum(m.r2, 3)} />
          <KpiTile label="Best baseline MAE" value={base ? `${fmtNum(base.mae, 1)} kW` : '–'} sub={modelLabel(r.best_baseline_by_cv)} />
        </div>
      )}
      {bt.error ? (
        <ErrorState error={bt.error} onRetry={bt.reload} />
      ) : bt.loading && !bt.data ? (
        <Loading label="Loading held-out predictions" />
      ) : (
        <SeriesChart
          title={`Measured and predicted demand (${HORIZON_LABEL[horizon]} ahead, held-out period)`}
          summary={`Measured demand against predictions made ${HORIZON_LABEL[horizon]} ahead, from ${formatTs(bt.data?.points[0]?.ts)} to ${formatTs(bt.data?.points[bt.data.points.length - 1]?.ts)}, with an 80% range. A table lists every value.`}
          rows={rows}
          lines={[
            { key: 'actual', name: 'Measured', color: 'var(--s1)' },
            { key: 'predicted', name: `Predicted (${modelLabel(bt.data?.model ?? '')})`, color: 'var(--s2)', dashed: true },
            { key: 'baseline', name: `Baseline (${modelLabel(bt.data?.baseline ?? '')})`, color: 'var(--s3)', dashed: true },
          ]}
          band={{ key: 'band', name: '80% range' }}
          digits={0}
          height={340}
          footer={bt.data ? `Range coverage over the whole test period: ${fmtNum(bt.data.metrics.band_80_coverage_pct ?? Number.NaN, 0)}% of hours fell inside the 80% range (target 80%).` : undefined}
        />
      )}
    </Card>
  );
}

function ErrorAnalysisSection({ society, horizon }: { society: SocietySummary; horizon: string }) {
  const ea = useApi(`soc-ea:${society.id}:${horizon}`, (signal) => societyApi.errorAnalysis(society.id, Number(horizon), { signal }));
  const e = ea.data;
  const worstCols: Column<ErrorAnalysis['worst'][number]>[] = [
    { key: 't', header: 'Hour', render: (r) => formatTs(r.ts) },
    { key: 'a', header: 'Measured (kW)', align: 'right', render: (r) => fmtNum(r.actual_kw, 0) },
    { key: 'p', header: 'Predicted (kW)', align: 'right', render: (r) => fmtNum(r.predicted_kw, 0) },
    { key: 'e', header: 'Error (kW)', align: 'right', render: (r) => fmtSigned(r.error_kw, 0) },
  ];
  return (
    <Card
      title={`Forecast error analysis, ${HORIZON_LABEL[horizon]} ahead`}
      description="Error is predicted minus measured demand on the held-out test period, which the model never saw during training. Positive means the forecast was too high."
    >
      {ea.error ? (
        <ErrorState error={ea.error} onRetry={ea.reload} title="Could not load the error analysis" />
      ) : ea.loading && !e ? (
        <Loading label="Analysing forecast errors" />
      ) : e ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile label="Average error (bias)" value={`${fmtSigned(e.bias_kw, 1)} kW`} sub={e.bias_kw > 0 ? 'Too high on average' : e.bias_kw < 0 ? 'Too low on average' : 'No average bias'} />
            <KpiTile label="Mean absolute error" value={`${fmtNum(e.mae_kw, 1)} kW`} sub={e.baseline_mae_kw != null ? `${modelLabel(e.baseline)} baseline ${fmtNum(e.baseline_mae_kw, 1)} kW` : modelLabel(e.model)} />
            <KpiTile label="Typical and bad hours" value={`${fmtNum(e.abs_error_percentiles_kw.p50, 0)} / ${fmtNum(e.abs_error_percentiles_kw.p95, 0)} kW`} sub="Median and 95th percentile of the absolute error" />
            <KpiTile label="Inside the prediction band" value={fmtPct(e.interval_coverage_pct, 0)} sub="The band is nominally 80%" />
          </div>
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-semibold">How large are the errors?</p>
              <p className="mb-2 text-xs text-ink-2">Hours per error size. A narrow bar group centred on zero is a forecast that is rarely far off.</p>
              <BarsChart
                data={e.histogram.map((r) => ({ band: fmtNum((r.from_kw + r.to_kw) / 2, 0), hours: r.hours }))}
                xKey="band"
                series={[{ key: 'hours', name: 'Hours with this error', color: 'var(--s1)' }]}
                unit="hours"
                digits={0}
                xLabel="Forecast error, middle of each band (kW)"
                height={280}
              />
              {e.histogram_note && <p className="mt-1 text-xs text-ink-2">{e.histogram_note}</p>}
            </div>
            <div>
              <p className="mb-1 text-sm font-semibold">Which hours of the day are hardest?</p>
              <p className="mb-2 text-xs text-ink-2">Mean absolute error by hour of the day being forecast, against the simple baseline.</p>
              <BarsChart
                data={e.by_hour.map((r) => ({ hour: String(r.hour).padStart(2, '0'), model: Number(r.mae_kw.toFixed(1)), baseline: r.baseline_mae_kw != null ? Number(r.baseline_mae_kw.toFixed(1)) : null }))}
                xKey="hour"
                series={[{ key: 'model', name: modelLabel(e.model), color: 'var(--s1)' }, { key: 'baseline', name: `${modelLabel(e.baseline)} baseline`, color: 'var(--s3)' }]}
                unit="kW"
                digits={1}
                xLabel="Hour of day"
                height={280}
              />
            </div>
          </div>
          <div className="mt-6">
            <p className="mb-2 text-sm font-semibold">The {e.worst.length} largest errors</p>
            <Table columns={worstCols} rows={e.worst} rowKey={(r) => r.ts} caption="The largest forecast errors with measured and predicted demand" dense />
          </div>
          <p className="mt-3 text-xs text-ink-2">
            {fmtInt(e.hours)} test hours from {formatTs(e.test_period[0])} to {formatTs(e.test_period[1])}. {e.note}
          </p>
        </>
      ) : null}
    </Card>
  );
}

function LiveForecast({ society }: { society: SocietySummary }) {
  const { tariffId } = useSociety();
  const { settledSeq } = useJobs();
  const [origin, setOrigin] = useState('');
  const [applied, setApplied] = useState('');
  const [originError, setOriginError] = useState<string | null>(null);
  const fc = useApi(`soc-fc:${society.id}:${applied}:${tariffId}:${settledSeq}`, (signal) =>
    societyApi.forecast(society.id, { origin: applied || undefined, horizons: [...Array.from({ length: 24 }, (_, i) => i + 1), 168].join(','), tariff_id: tariffId }, { signal }),
  );
  const originMs = fc.data ? parseNaive(fc.data.origin) : null;
  const hist = useApi(originMs ? `soc-fc-hist:${society.id}:${originMs}` : null, (signal) =>
    societyApi.consumption(society.id, { resolution: 'hourly', start: toApiTimestamp((originMs as number) - 3 * DAY), end: toApiTimestamp((originMs as number) + 24 * 3_600_000) }, { signal }),
  );
  const rows = useMemo<TsRow[]>(() => {
    const map = new Map<number, TsRow>();
    for (const p of hist.data?.points ?? []) map.set(parseNaive(p.ts), { t: parseNaive(p.ts), actual: p.avg_kw });
    for (const p of fc.data?.points ?? []) {
      if (p.horizon > 24) continue;
      const t = parseNaive(p.ts);
      const row = map.get(t) ?? ({ t, actual: null } as TsRow);
      row.forecast = p.kw;
      row.band = [p.lower_kw, p.upper_kw];
      map.set(t, row);
    }
    return [...map.values()].sort((a, b) => a.t - b.t);
  }, [hist.data, fc.data]);
  const week = fc.data?.points.find((p) => p.horizon === 168);

  const apply = () => {
    if (origin === '') {
      setApplied('');
      setOriginError(null);
      return;
    }
    const ms = parseNaive(origin);
    if (Number.isNaN(ms) || ms < parseNaive(society.start) || ms > parseNaive(society.end)) {
      setOriginError(`Choose a time between ${formatTs(society.start)} and ${formatTs(society.end)}.`);
      return;
    }
    setOriginError(null);
    setApplied(toApiTimestamp(ms));
  };

  return (
    <Card
      title="Forecast from a chosen hour"
      description="History (solid) and forecast (dashed, shaded range) on one axis. The default origin is the last hour of data; an earlier origin gives a retrospective forecast that uses only data up to that hour, shown next to what actually happened."
    >
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          apply();
        }}
      >
        <TextField label="Forecast origin" type="datetime-local" value={origin} onChange={(e) => setOrigin(e.target.value)} error={originError ?? undefined} hint="Leave empty for the last hour of data" />
        <button type="submit" className="btn-secondary">Run forecast</button>
      </form>
      {fc.error ? (
        <ErrorState error={fc.error} onRetry={fc.reload} title="Forecast not available" />
      ) : fc.loading && !fc.data ? (
        <Loading label="Forecasting" />
      ) : fc.data ? (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile label="Origin" value={formatTs(fc.data.origin)} sub="Data up to this hour were used" />
            <KpiTile label="Next 24 h energy" value={fc.data.summary.next_24h_energy_kwh != null ? `${fmtNum(fc.data.summary.next_24h_energy_kwh, 0)} kWh` : '–'} sub={fc.data.summary.next_24h_energy_range_kwh ? `80% range ${fmtNum(fc.data.summary.next_24h_energy_range_kwh[0], 0)} to ${fmtNum(fc.data.summary.next_24h_energy_range_kwh[1], 0)}` : undefined} />
            <KpiTile label="Predicted peak" value={fc.data.summary.peak_kw != null ? `${fmtNum(fc.data.summary.peak_kw, 0)} kW` : '–'} sub={fc.data.summary.peak_time ? formatTs(fc.data.summary.peak_time) : undefined} />
            <KpiTile label="7 days ahead" value={week ? `${fmtNum(week.kw, 0)} kW` : '–'} sub={week ? `${formatTs(week.ts)}, range ${fmtNum(week.lower_kw, 0)} to ${fmtNum(week.upper_kw, 0)}` : undefined} />
          </div>
          <SeriesChart
            title="History and 24-hour forecast"
            summary={`Hourly demand for three days before ${formatTs(fc.data.origin)} and a 24 hour forecast with an 80% range. A table lists every value.`}
            rows={rows}
            lines={[{ key: 'actual', name: 'Measured', color: 'var(--s1)' }, { key: 'forecast', name: 'Forecast', color: 'var(--s2)', dashed: true, dots: true }]}
            band={{ key: 'band', name: '80% range' }}
            refLines={[{ t: parseNaive(fc.data.origin), label: 'Forecast origin' }]}
            digits={0}
            height={320}
            footer={fc.data.note}
          />
        </>
      ) : null}
    </Card>
  );
}

function Explanations({ society, models, horizon }: { society: SocietySummary; models: ModelsResponse; horizon: string }) {
  const g = useApi(`soc-shap:${society.id}`, (signal) => societyApi.explainGlobal(society.id, { signal }));
  const [local, setLocal] = useState<{ key: string; busy: boolean; error: Error | null; data: Awaited<ReturnType<typeof societyApi.explainLocal>> | null }>({ key: '', busy: false, error: null, data: null });
  const h = g.data?.horizons[horizon];
  const deployed = models.deployed[horizon];
  const key = `${society.id}:${horizon}`;
  const run = () => {
    setLocal({ key, busy: true, error: null, data: null });
    societyApi.explainLocal(society.id, { horizon: Number(horizon) }).then(
      (data) => setLocal({ key, busy: false, error: null, data }),
      (error: Error) => setLocal({ key, busy: false, error, data: null }),
    );
  };
  return (
    <Card title={`What drives the ${HORIZON_LABEL[horizon]}-ahead forecast`} description="SHAP values of the selected model: how many kW each input moves a prediction, on average (global) or for one forecast (local). Baselines have no model to explain.">
      {g.error ? (
        <ErrorState error={g.error} onRetry={g.reload} />
      ) : !h ? (
        <EmptyState title="No explanation for this horizon">{g.loading ? 'Loading.' : 'The selected method at this horizon is a baseline, or no explanation was saved.'}</EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-semibold">Global: average impact on a prediction ({modelLabel(h.model)}, {h.rows} test hours)</p>
            <BarsChart data={h.top_features.slice(0, 10).map((f) => ({ feature: f.label, impact: Number(f.mean_abs_shap_kw.toFixed(1)) }))} xKey="feature" series={[{ key: 'impact', name: 'Mean |SHAP|', color: 'var(--s1)' }]} unit="kW" horizontal yWidth={210} height={330} digits={1} />
          </div>
          <div>
            <p className="mb-2 text-sm font-semibold">Share of impact by input group</p>
            <ul className="space-y-1 text-sm">
              {Object.entries(h.group_share_pct).map(([k, v]) => (
                <li key={k} className="flex justify-between gap-3">
                  <span>{k}</span>
                  <span className="num">{fmtNum(v, 1)}%</span>
                </li>
              ))}
            </ul>
            <div className="mt-4">
              <button type="button" className="btn-secondary" onClick={run} disabled={local.busy || !deployed || deployed.family === 'baseline'}>
                {local.busy ? 'Explaining' : 'Explain the latest forecast'}
              </button>
              {deployed?.family === 'baseline' && <p className="mt-2 text-xs text-ink-2">The deployed method here is a baseline ({modelLabel(deployed.baseline ?? 'baseline')}), which has nothing to explain.</p>}
            </div>
            {local.key === key && local.error && <div className="mt-3"><Notice tone="error">{local.error.message}</Notice></div>}
            {local.key === key && local.data && (
              <div className="mt-3">
                <p className="text-sm">
                  Forecast {fmtNum(local.data.prediction_kw, 0)} kW for the hour {HORIZON_LABEL[horizon]} after {formatTs(local.data.origin)}; the average prediction is {fmtNum(local.data.base_value_kw, 0)} kW.
                </p>
                <ul className="mt-2 space-y-1 text-sm">
                  {local.data.drivers.slice(0, 6).map((d) => (
                    <li key={d.feature} className="flex justify-between gap-3">
                      <span>{d.label}{d.value != null ? ` (${fmtNum(d.value, 1)})` : ''}</span>
                      <span className="num">{d.contribution_kw >= 0 ? '+' : ''}{fmtNum(d.contribution_kw, 1)} kW</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function Forecasting({ society }: { society: SocietySummary }) {
  const models = useApi(`soc-models:${society.id}`, (signal) => societyApi.models(society.id, { signal }));
  const [horizon, setHorizon] = useState('24');
  if (models.error) return <ErrorState error={models.error} onRetry={models.reload} />;
  if (models.loading && !models.data) return <Loading label="Loading model results" />;
  const m = models.data;
  if (!m || !m.model) return <EmptyState title="No trained model for this society">{m?.message ?? 'An administrator can train models from the society admin page.'}</EmptyState>;
  const horizons = Object.keys(m.horizons).sort((a, b) => Number(a) - Number(b));
  const deployed = m.deployed[horizon];
  return (
    <div className="space-y-6">
      <DataBasisNote society={society} />
      <Card
        title="Forecast horizon"
        description="Each horizon has its own model, evaluated separately. The 7-day horizon is the weekly forecast."
        actions={<Segmented label="Horizon" value={horizon} onChange={setHorizon} options={horizons.map((h) => ({ value: h, label: HORIZON_LABEL[h] ?? `${h} h` }))} />}
      >
        <DescriptionList
          columns={3}
          items={[
            { label: 'Test period (scored once)', value: `${formatTs(m.model.protocol.test_period[0])} to ${formatTs(m.model.protocol.test_period[1])}` },
            { label: 'Selection rule', value: 'Lowest mean absolute error over expanding-window cross-validation blocks before the test period' },
            { label: 'Deployed for live forecasts', value: deployed ? (deployed.family === 'baseline' ? `Baseline: ${modelLabel(deployed.baseline ?? '')}` : modelLabel(deployed.family)) : 'Not deployed' },
            { label: 'Weather input', value: m.model.protocol.weather },
            { label: 'Models trained through', value: formatTs(m.model.trained_through) },
            { label: 'MAPE', value: `Hours with demand below ${m.model.protocol.mape_excludes_actuals_below_kw} kW are excluded and counted` },
          ]}
        />
      </Card>
      <BacktestSection society={society} models={m} horizon={horizon} />
      <ErrorAnalysisSection society={society} horizon={horizon} />
      <ModelComparison models={m} horizon={horizon} />
      <LiveForecast society={society} />
      <Explanations society={society} models={m} horizon={horizon} />
      {m.note && <Notice>{m.note}</Notice>}
    </div>
  );
}

export function SocietyForecastPage() {
  return (
    <>
      <SocietyHeader title="Forecasting" description="Total society demand 1, 6, 12 and 24 hours and 7 days ahead, with honest out-of-sample accuracy and a model comparison." />
      <SocietyGate>{(s) => <Forecasting society={s} />}</SocietyGate>
    </>
  );
}
