import { useMemo, useState, type FormEvent } from 'react';
import { explainApi, modelApi } from '../api/endpoints';
import type { LocalExplanation, ModelVersion } from '../api/types';
import { BarsChart, WaterfallChart, WATERFALL_COLORS, type WaterfallStep } from '../components/charts/CategoryCharts';
import { ChartFrame, type LegendItem } from '../components/charts/ChartFrame';
import { Card, DescriptionList, PageHeader } from '../components/ui/basic';
import { ErrorState, Loading, Notice, Spinner } from '../components/ui/feedback';
import { SelectField, TextField } from '../components/ui/forms';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { fmtKw, fmtNum, fmtSigned, shortModelId } from '../lib/format';
import { formatTs, parseNaive, toDatetimeLocal } from '../lib/time';
import { useDatasets } from '../state/DatasetContext';
import { useJobs } from '../state/JobsContext';
import { NoDatasetState } from './DashboardPage';

const HORIZON_COLORS = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)'];

function GlobalPanel({ modelId }: { modelId: string }) {
  const g = useApi(`explain-global:${modelId}`, (signal) => explainApi.global(modelId, { signal }));
  const [hz, setHz] = useState('');
  const horizons = useMemo(() => Object.keys(g.data?.horizons ?? {}).sort((a, b) => Number(a) - Number(b)), [g.data]);
  if (g.loading && !g.data) return <Loading label="Loading global importance" />;
  if (g.error) return <ErrorState error={g.error} onRetry={g.reload} />;
  if (!g.data || horizons.length === 0) return <p className="text-sm text-ink-2">This model version has no stored explanation.</p>;

  const first = g.data.horizons[horizons[horizons.length - 1] as string];
  const groups = Object.keys(first?.group_share_pct ?? {});
  for (const h of horizons) for (const k of Object.keys(g.data.horizons[h]?.group_share_pct ?? {})) if (!groups.includes(k)) groups.push(k);
  groups.sort((a, b) => (first?.group_share_pct[b] ?? 0) - (first?.group_share_pct[a] ?? 0));
  const series = horizons.map((h, i) => ({ key: `h${h}`, name: `${h} h ahead`, color: HORIZON_COLORS[i % HORIZON_COLORS.length] as string }));
  const data: Record<string, string | number | null>[] = groups.map((grp) => ({ group: grp, ...Object.fromEntries(horizons.map((h) => [`h${h}`, g.data?.horizons[h]?.group_share_pct[grp] ?? 0])) }));
  const legend: LegendItem[] = series.map((s) => ({ label: s.name, color: s.color, kind: 'bar' }));
  const chosen = hz && horizons.includes(hz) ? hz : (horizons[horizons.length - 1] as string);
  const top = g.data.horizons[chosen]?.top_features ?? [];

  return (
    <div className="space-y-6">
      <Notice tone="info" title="What this shows">
        {g.data.basis}. Each bar is the share of the model’s total attribution that comes from a group of input features. It describes how the model behaves, not what causes consumption.
      </Notice>
      <ChartFrame
        title="Share of importance by feature group"
        description="Percentage of total mean |SHAP|, per forecast horizon."
        summary={`Grouped bar chart of the share of model importance per feature group at horizons ${horizons.join(', ')} hours. Largest group at the longest horizon: ${groups[0] ?? 'none'}. A table view lists the values.`}
        legend={legend}
        table={<Table caption="Feature-group importance (%)" rows={data} rowKey={(r) => String(r.group)} columns={[{ key: "g", header: "Feature group", render: (r) => String(r.group) }, ...series.map((s) => ({ key: s.key, header: `${s.name} (%)`, align: 'right' as const, render: (r: (typeof data)[number]) => fmtNum(r[s.key] as number, 1) }))]} dense />}
      >
        <BarsChart data={data} xKey="group" series={series} unit="%" digits={1} horizontal height={Math.max(260, groups.length * 30 * horizons.length + 40)} yWidth={190} />
      </ChartFrame>
      <div>
        <div className="mb-3 flex flex-wrap items-end gap-4">
          <h3 className="text-sm">Most important individual features</h3>
          <SelectField label="Horizon" value={chosen} onChange={(e) => setHz(e.target.value)} className="w-40">
            {horizons.map((h) => (
              <option key={h} value={h}>
                {h} h ahead
              </option>
            ))}
          </SelectField>
        </div>
        <Table
          caption={`Top features at ${chosen} h ahead`}
          rows={top}
          rowKey={(r) => r.feature}
          columns={[
            { key: 'l', header: 'Feature', render: (r) => <span>{r.label}<span className="block text-xs text-muted">{r.feature}</span></span> },
            { key: 'g', header: 'Group', render: (r) => r.group },
            { key: 'm', header: 'Mean |SHAP| (kW)', align: 'right', render: (r) => fmtNum(r.mean_abs_shap_kw, 3) },
            { key: 's', header: 'Share (%)', align: 'right', render: (r) => fmtNum(r.share_pct, 1) },
          ]}
          dense
        />
      </div>
    </div>
  );
}

function waterfallSteps(e: LocalExplanation): WaterfallStep[] {
  const steps: WaterfallStep[] = [{ name: 'Average-case baseline', lo: Math.min(0, e.base_value_kw), hi: Math.max(0, e.base_value_kw), value: e.base_value_kw, kind: 'base' }];
  let cum = e.base_value_kw;
  for (const [name, v] of Object.entries(e.grouped_kw)) {
    steps.push({ name, lo: Math.min(cum, cum + v), hi: Math.max(cum, cum + v), value: v, kind: v >= 0 ? 'raises' : 'lowers' });
    cum += v;
  }
  steps.push({ name: 'Forecast', lo: Math.min(0, e.prediction_kw), hi: Math.max(0, e.prediction_kw), value: e.prediction_kw, kind: 'total' });
  return steps;
}

function LocalPanel({ model, defaultOrigin, minOrigin, maxOrigin }: { model: ModelVersion; defaultOrigin: string | null; minOrigin: number | null; maxOrigin: number | null }) {
  const [horizon, setHorizon] = useState('6');
  const [origin, setOrigin] = useState('');
  const [submitted, setSubmitted] = useState<{ horizon: number; origin: string }>({ horizon: 6, origin: '' });
  const res = useApi<LocalExplanation>(`explain-local:${model.id}:${submitted.horizon}:${submitted.origin}`, (signal) =>
    explainApi.local({ model_id: model.id, horizon: submitted.horizon, ...(submitted.origin ? { origin: submitted.origin } : {}) }, { signal }),
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted({ horizon: Number(horizon), origin: origin ? `${origin}:00`.slice(0, 19) : '' });
  };
  const e = res.data;
  const steps = useMemo(() => (e ? waterfallSteps(e) : []), [e]);
  const legend: LegendItem[] = [
    { label: 'Baseline and forecast', color: WATERFALL_COLORS.base, kind: 'bar' },
    { label: 'Group raises the forecast', color: WATERFALL_COLORS.raises, kind: 'bar' },
    { label: 'Group lowers the forecast', color: WATERFALL_COLORS.lowers, kind: 'bar' },
  ];
  const maxAbs = e ? Math.max(...e.drivers.map((d) => Math.abs(d.contribution_kw)), 1e-9) : 1;
  const driverCols: Column<LocalExplanation['drivers'][number]>[] = [
    { key: 'l', header: 'Input', render: (d) => d.label },
    { key: 'v', header: 'Value', align: 'right', render: (d) => fmtNum(d.value, 2) },
    {
      key: 'c',
      header: 'Effect on the forecast',
      render: (d) => (
        <div className="flex items-center gap-3">
          <span className="num w-20 shrink-0 text-right font-medium">{fmtSigned(d.contribution_kw, 3)} kW</span>
          <span className="flex h-3 w-40 items-center" aria-hidden="true">
            <span className="flex h-full w-1/2 justify-end">{d.contribution_kw < 0 && <span className="h-full rounded-l bg-[var(--s3)]" style={{ width: `${(Math.abs(d.contribution_kw) / maxAbs) * 100}%` }} />}</span>
            <span className="h-full w-px bg-line-strong" />
            <span className="flex h-full w-1/2">{d.contribution_kw > 0 && <span className="h-full rounded-r bg-[var(--s2)]" style={{ width: `${(Math.abs(d.contribution_kw) / maxAbs) * 100}%` }} />}</span>
          </span>
          <span className="text-xs text-ink-2">{d.direction}</span>
        </div>
      ),
    },
  ];
  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-[12rem_1fr_auto]">
        <SelectField label="Horizon" value={horizon} onChange={(ev) => setHorizon(ev.target.value)}>
          {Array.from({ length: 24 }, (_, i) => i + 1).map((h) => (
            <option key={h} value={h}>
              {h} h ahead
            </option>
          ))}
        </SelectField>
        <TextField
          label="Forecast origin (optional)"
          type="datetime-local"
          value={origin}
          min={minOrigin !== null ? toDatetimeLocal(minOrigin) : undefined}
          max={maxOrigin !== null ? toDatetimeLocal(maxOrigin) : undefined}
          onChange={(ev) => setOrigin(ev.target.value)}
          hint={defaultOrigin ? `Empty = latest data hour (${formatTs(defaultOrigin)}).` : undefined}
        />
        <button type="submit" className="btn-primary" disabled={res.loading}>
          {res.loading && <Spinner />}Explain this forecast
        </button>
      </form>
      {res.error && <ErrorState error={res.error} onRetry={res.reload} title="Could not explain this forecast" />}
      {res.loading && !e && <Loading label="Computing explanation" />}
      {e && (
        <>
          <DescriptionList
            columns={3}
            items={[
              { label: 'Forecast origin', value: formatTs(e.origin) },
              { label: 'Target hour', value: formatTs(e.target_time) },
              { label: 'Forecast', value: fmtKw(e.prediction_kw, 3) },
              { label: 'Average-case baseline', value: fmtKw(e.base_value_kw, 3) },
              { label: 'Additivity check', value: `contributions add up to the forecast within ${e.additivity_error_kw.toExponential(1)} kW` },
            ]}
          />
          <p className="max-w-prose text-sm">{e.narrative}</p>
          <ChartFrame
            title="From baseline to forecast, by feature group"
            description="Each bar shows how much a group of inputs moves the forecast away from the average-case baseline."
            summary={`Waterfall from a baseline of ${fmtNum(e.base_value_kw)} kW to a forecast of ${fmtNum(e.prediction_kw)} kW through ${Object.keys(e.grouped_kw).length} feature groups. A table view lists each group’s effect.`}
            legend={legend}
            table={<Table caption="Feature-group effects on this forecast" rows={Object.entries(e.grouped_kw)} rowKey={([k]) => k} columns={[{ key: 'g', header: 'Feature group', render: ([k]) => k }, { key: 'v', header: 'Effect (kW)', align: 'right', render: ([, v]) => fmtSigned(v, 3) }]} dense />}
          >
            <WaterfallChart steps={steps} unit="kW" digits={2} />
          </ChartFrame>
          <div>
            <h3 className="mb-2 text-sm">Largest individual drivers</h3>
            <Table columns={driverCols} rows={e.drivers} rowKey={(d) => d.feature} caption="Largest individual drivers of this forecast" dense />
            <p className="hint">Only the strongest drivers are listed, so they do not sum to the full forecast; the group chart above does.</p>
          </div>
        </>
      )}
    </div>
  );
}

export function ExplainPage() {
  const { active, loading: dsLoading } = useDatasets();
  const { settledSeq } = useJobs();
  const id = active?.id ?? null;
  const models = useApi<ModelVersion[]>(id ? `ex-models:${id}:${settledSeq}` : null, (signal) => modelApi.list(id as number, { signal }));
  const [pick, setPick] = useState('');
  if (dsLoading) return <Loading label="Loading datasets" />;
  if (!active) return (<><PageHeader title="Explainability" /><NoDatasetState /></>);
  const list = models.data ?? [];
  const model = list.find((m) => m.id === pick) ?? list.find((m) => m.is_active) ?? list[0] ?? null;
  const minO = active.start_ts ? parseNaive(active.start_ts) : null;
  const maxO = active.end_ts ? parseNaive(active.end_ts) : null;

  return (
    <>
      <PageHeader title="Explainability" description="Why the model forecasts what it does. Explanations use exact tree SHAP values of the XGBoost forecaster." />
      <div className="space-y-6">
        {models.loading && !models.data && <Loading label="Loading models" />}
        {models.error && <ErrorState error={models.error} onRetry={models.reload} />}
        {models.data && list.length === 0 && <Notice tone="info" title="No trained model">Train a model for this dataset first.</Notice>}
        {model && (
          <>
            <SelectField label="Model version" value={model.id} onChange={(e) => setPick(e.target.value)} className="max-w-sm">
              {list.map((m) => (
                <option key={m.id} value={m.id}>
                  {shortModelId(m.id)}
                  {m.is_active ? ' (active)' : ''}
                </option>
              ))}
            </SelectField>
            <Card title="Global importance" description="Which inputs matter most across the hold-out period.">
              <GlobalPanel key={model.id} modelId={model.id} />
            </Card>
            <Card title="Local explanation" description="Break one specific forecast down into the inputs that pushed it up or down.">
              <LocalPanel key={model.id} model={model} defaultOrigin={active.end_ts} minOrigin={minO} maxOrigin={maxO} />
            </Card>
          </>
        )}
      </div>
    </>
  );
}
