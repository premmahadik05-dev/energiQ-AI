import { useEffect, useMemo, useRef, useState } from 'react';
import { benchmarkApi } from '../api/endpoints';
import type { Benchmark, BenchmarkBootstrap } from '../api/types';
import { BarsChart } from '../components/charts/CategoryCharts';
import { ChartFrame } from '../components/charts/ChartFrame';
import { Badge, Card, DescriptionList, PageHeader } from '../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice } from '../components/ui/feedback';
import { SelectField } from '../components/ui/forms';
import { Modal } from '../components/ui/Modal';
import { Table, type Column } from '../components/ui/Table';
import { useApi } from '../hooks/useApi';
import { useBlobUrl } from '../hooks/useBlobUrl';
import { fmtInt, fmtNum, fmtPct, fmtSigned, humanize, modelLabel } from '../lib/format';
import { formatTs } from '../lib/time';

const METHOD_COLORS: Record<string, string> = { naive: 'var(--s2)', seasonal_naive_24: 'var(--s3)', seasonal_naive_168: 'var(--s4)', random_forest: 'var(--s5)', xgboost: 'var(--s1)', lstm: 'var(--s7)' };
const GROUP_LABEL: Record<string, string> = { evaluation: 'Forecast evaluation', anomaly: 'Anomaly detection', explain: 'Explainability', eda: 'Exploratory analysis' };

function figureTitle(name: string): string {
  return humanize(name.replace(/^fig_/, '').replace(/\.png$/, ''));
}

function useInView<T extends Element>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    if (seen || !ref.current) return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && setSeen(true), { rootMargin: '200px' });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [seen]);
  return [ref as React.RefObject<T>, seen];
}

function Figure({ group, name, caption }: { group: string; name: string; caption: string }) {
  const [ref, seen] = useInView<HTMLElement>();
  const [open, setOpen] = useState(false);
  const blob = useBlobUrl(seen ? `${group}/${name}` : null, () => benchmarkApi.figure(group, name));
  const title = figureTitle(name);
  return (
    <figure ref={ref} className="card m-0 flex flex-col p-3">
      <div className="flex min-h-[160px] items-center justify-center rounded bg-white">
        {blob.url ? (
          <button type="button" className="block w-full" onClick={() => setOpen(true)} aria-label={`Enlarge figure: ${title}`}>
            <img src={blob.url} alt={`${title}. ${caption}`} className="mx-auto h-auto max-h-[320px] w-full object-contain" loading="lazy" />
          </button>
        ) : blob.error ? (
          <p role="alert" className="p-4 text-sm text-bad">Could not load this figure: {blob.error.message}</p>
        ) : (
          <p role="status" className="p-4 text-sm text-muted">{seen ? 'Loading figure…' : 'The figure loads when it scrolls into view.'}</p>
        )}
      </div>
      <figcaption className="mt-2 text-xs text-ink-2">
        <strong className="text-ink">{title}.</strong> {caption}
      </figcaption>
      <Modal open={open} title={title} onClose={() => setOpen(false)} footer={<button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Close</button>}>
        {blob.url && <img src={blob.url} alt={`${title}. ${caption}`} className="max-h-[70vh] w-full rounded bg-white object-contain" />}
        <p className="mt-2 text-xs">{caption}</p>
      </Modal>
    </figure>
  );
}

const CI = (b: BenchmarkBootstrap) => `${fmtSigned(b.ci95_low, 3)} to ${fmtSigned(b.ci95_high, 3)}`;
const ciExcludesZero = (b: BenchmarkBootstrap) => b.ci95_low > 0 || b.ci95_high < 0;

function ForecastSection({ b }: { b: Benchmark }) {
  const ev = b.evaluation;
  const horizons = useMemo(() => Object.keys(ev?.horizons ?? {}).sort((a, c) => Number(a) - Number(c)), [ev]);
  const [hz, setHz] = useState('');
  if (!ev || horizons.length === 0) return <p className="text-sm text-ink-2">The server has no stored evaluation results.</p>;
  const h = hz && horizons.includes(hz) ? hz : (horizons[horizons.length - 1] as string);
  const data = ev.horizons?.[h];
  const methods = Object.keys(data?.metrics ?? {});
  const bestCv = ev.best_cv_baseline?.[h];
  const hind = data?.hindsight_best_baseline;

  type M = { method: string };
  const rows: M[] = methods.map((m) => ({ method: m }));
  const cols: Column<M>[] = [
    {
      key: 'm',
      header: 'Method',
      render: (r) => (
        <span>
          {modelLabel(r.method)}{' '}
          {r.method === bestCv && <Badge tone="accent" title="Chosen on cross-validation, before looking at the test period">best baseline (cross-validation)</Badge>}{' '}
          {r.method === hind && r.method !== bestCv && <Badge title="Best baseline in hindsight on the test period">best baseline in hindsight</Badge>}
        </span>
      ),
    },
    { key: 'mae', header: 'MAE (kW)', align: 'right', render: (r) => fmtNum(data?.metrics?.[r.method]?.mae, 3) },
    { key: 'rmse', header: 'RMSE (kW)', align: 'right', render: (r) => fmtNum(data?.metrics?.[r.method]?.rmse, 3) },
    { key: 'smape', header: 'sMAPE (%)', align: 'right', render: (r) => fmtNum(data?.metrics?.[r.method]?.smape_pct, 1) },
    { key: 'r2', header: 'R²', align: 'right', render: (r) => fmtNum(data?.metrics?.[r.method]?.r2, 3) },
  ];
  const boot = Object.entries(data?.bootstrap_mae_diff_vs_best_cv_baseline ?? {});
  const pair = Object.entries(data?.pairwise_mae_diff ?? {});

  const allMethods = Array.from(new Set(horizons.flatMap((x) => Object.keys(ev.horizons?.[x]?.metrics ?? {}))));
  const series = allMethods.map((m) => ({ key: m, name: modelLabel(m), color: METHOD_COLORS[m] ?? 'var(--s8)' }));
  const chart: Record<string, string | number | null>[] = horizons.map((x) => ({ horizon: `${x} h`, ...Object.fromEntries(allMethods.map((m) => [m, ev.horizons?.[x]?.metrics?.[m]?.mae ?? null])) }));

  return (
    <div className="space-y-6">
      <ChartFrame
        title="Test-period MAE by method and horizon"
        description="Mean absolute error in kW on the benchmark test period. Lower is better."
        summary={`Grouped bar chart of test-period mean absolute error for ${series.map((s) => s.name).join(', ')} at horizons ${horizons.join(', ')} hours. A table view lists the values.`}
        legend={series.map((s) => ({ label: s.name, color: s.color, kind: 'bar' as const }))}
        table={<Table caption="Test-period MAE by method" rows={chart} rowKey={(r) => String(r.horizon)} columns={[{ key: "h", header: "Horizon", render: (r) => String(r.horizon) }, ...series.map((s) => ({ key: s.key, header: `${s.name} (kW)`, align: 'right' as const, render: (r: (typeof chart)[number]) => fmtNum(r[s.key] as number | null, 3) }))]} dense />}
      >
        <BarsChart data={chart} xKey="horizon" series={series} unit="kW" digits={3} xLabel="Forecast horizon" />
      </ChartFrame>
      <div>
        <div className="mb-3 flex flex-wrap items-end gap-4">
          <h3 className="text-sm">All metrics at one horizon</h3>
          <SelectField label="Horizon" value={h} onChange={(e) => setHz(e.target.value)} className="w-40">
            {horizons.map((x) => (
              <option key={x} value={x}>
                {x} h ahead
              </option>
            ))}
          </SelectField>
        </div>
        <Table columns={cols} rows={rows} rowKey={(r) => r.method} caption={`Test-period metrics at ${h} h ahead`} />
        <p className="hint">{fmtInt(data?.n_rows_scored ?? null)} hours scored{data?.counts ? `, ${fmtInt(data.counts.test_rows_excluded ?? null)} excluded (missing data)` : ''}. Mean actual load {fmtNum(data?.mean_actual_kw, 3)} kW.</p>
      </div>
      {boot.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm">Difference from the best cross-validated baseline ({bestCv ? modelLabel(bestCv) : 'n/a'}), {h} h ahead</h3>
          <p className="mb-2 max-w-prose text-xs text-ink-2">Bootstrap over {fmtInt(boot[0]?.[1].days ?? null)} test days. A negative MAE difference means the method has lower error than the baseline; the interval is 95%.</p>
          <Table
            caption="Bootstrap MAE difference against the best baseline"
            rows={boot}
            rowKey={([m]) => m}
            columns={[
              { key: 'm', header: 'Method', render: ([m]) => modelLabel(m) },
              { key: 'd', header: 'MAE difference (kW)', align: 'right', render: ([, b]) => fmtSigned(b.mae_diff, 3) },
              { key: 'ci', header: '95% interval (kW)', align: 'right', render: ([, b]) => CI(b) },
              { key: 's', header: 'Interval excludes zero', render: ([, b]) => (ciExcludesZero(b) ? 'yes' : 'no') },
            ]}
            dense
          />
        </div>
      )}
      {pair.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm">Head-to-head, {h} h ahead</h3>
          <Table caption="Pairwise MAE differences" rows={pair} rowKey={([k]) => k} columns={[{ key: 'k', header: 'Comparison (first minus second)', render: ([k]) => k.split('_vs_').map(modelLabel).join(' − ') }, { key: 'd', header: 'MAE difference (kW)', align: 'right', render: ([, x]) => fmtSigned(x.mae_diff, 3) }, { key: 'ci', header: '95% interval (kW)', align: 'right', render: ([, x]) => CI(x) }, { key: 's', header: 'Interval excludes zero', render: ([, x]) => (ciExcludesZero(x) ? 'yes' : 'no') }]} dense />
        </div>
      )}
      {ev.lstm_seed_robustness && (
        <div>
          <h3 className="mb-2 text-sm">LSTM stability across random seeds (MAE, kW)</h3>
          <Table
            caption="LSTM seed robustness"
            rows={Object.entries(ev.lstm_seed_robustness)}
            rowKey={([s]) => s}
            columns={[
              { key: 's', header: 'Seed', render: ([s]) => <span>{s} {String(ev.lstm_headline_seed) === s && <Badge tone="accent">headline</Badge>}</span> },
              { key: 'h1', header: '1 h', align: 'right', render: ([, v]) => fmtNum(v.h1, 3) },
              { key: 'h6', header: '6 h', align: 'right', render: ([, v]) => fmtNum(v.h6, 3) },
              { key: 'h24', header: '24 h', align: 'right', render: ([, v]) => fmtNum(v.h24, 3) },
              { key: 'ep', header: 'Best epoch', align: 'right', render: ([, v]) => fmtNum(v.best_epochs, 0) },
            ]}
            dense
          />
        </div>
      )}
    </div>
  );
}

function ProtocolSection({ b }: { b: Benchmark }) {
  const p = b.evaluation?.protocol;
  if (!p) return null;
  return (
    <div className="space-y-4">
      <DescriptionList
        columns={2}
        items={[
          { label: 'Target', value: p.target ?? '–' },
          { label: 'Test period', value: p.test_period ? `${formatTs(p.test_period[0])} to ${formatTs(p.test_period[1])}` : '–' },
          { label: 'Random seed', value: p.seed ?? '–' },
          { label: 'Data fingerprint', value: p.data_hash ?? '–' },
        ]}
      />
      {p.cv_folds && p.cv_folds.length > 0 && (
        <Table caption="Cross-validation folds" rows={p.cv_folds} rowKey={(f) => f.name} columns={[{ key: 'n', header: 'Fold', render: (f) => f.name }, { key: 's', header: 'Validation start', render: (f) => formatTs(f.test_start) }, { key: 'e', header: 'Validation end', render: (f) => formatTs(f.test_end) }]} dense />
      )}
    </div>
  );
}

function AnomalySection({ b }: { b: Benchmark }) {
  const a = b.anomaly;
  const inj = b.anomaly_injection_check;
  if (!a && !inj) return <p className="text-sm text-ink-2">The server has no stored anomaly results.</p>;
  const s = a?.summary;
  return (
    <div className="space-y-6">
      <Notice tone="info" title="No ground-truth labels">The UCI data has no labelled anomalies, so there is no accuracy figure. The alert rate is a design setting of the detector.</Notice>
      {s && (
        <DescriptionList
          columns={3}
          items={[
            { label: 'Hours in series', value: fmtInt(s.hours_total) },
            { label: 'Valid hours', value: fmtInt(s.hours_valid) },
            { label: 'Hours flagged', value: `${fmtInt(s.hours_flagged)} (${fmtPct(s.flagged_pct_of_valid, 2)} of valid hours)` },
            { label: 'Events found', value: fmtInt(s.events) },
            { label: 'Events by severity', value: Object.entries(s.events_by_severity).map(([k, v]) => `${k} ${fmtInt(v)}`).join(' · ') },
            { label: 'Events by type', value: Object.entries(s.events_by_type).map(([k, v]) => `${humanize(k).toLowerCase()} ${fmtInt(v)}`).join(' · ') },
          ]}
        />
      )}
      {a?.top_events && a.top_events.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm">Highest-ranked events</h3>
          <Table
            caption="Highest-ranked benchmark anomaly events"
            rows={a.top_events}
            rowKey={(e) => `${e.start}-${e.end}`}
            columns={[
              { key: 's', header: 'Start', render: (e) => formatTs(e.start) },
              { key: 'h', header: 'Hours', align: 'right', render: (e) => fmtInt(e.hours) },
              { key: 't', header: 'Type', render: (e) => e.types.map((t) => humanize(t)).join(', ') },
              { key: 'sev', header: 'Severity', render: (e) => e.severity },
              { key: 'p', header: 'Peak vs typical (kW)', align: 'right', render: (e) => `${fmtNum(e.peak_value_kw)} vs ${fmtNum(e.expected_kw)}` },
            ]}
            dense
          />
        </div>
      )}
      {inj?.kinds && (
        <div>
          <h3 className="mb-1 text-sm">Synthetic injection check</h3>
          <p className="mb-2 max-w-prose text-xs text-ink-2">Faults were injected into a copy of the series on purpose ({fmtInt(inj.n_injected_per_kind ?? null)} of each kind). This is a sanity check of the detector, not accuracy on real faults.</p>
          <Table
            caption="Synthetic injection check"
            rows={Object.entries(inj.kinds)}
            rowKey={([k]) => k}
            columns={[
              { key: 'k', header: 'Injected fault', render: ([k]) => humanize(k) },
              { key: 'r', header: 'Share detected', align: 'right', render: ([, v]) => fmtPct(v.recall_on_injected * 100, 0) },
              { key: 'r1', header: 'Share detected where typical load ≥ 1 kW', align: 'right', render: ([, v]) => (v.recall_when_expected_ge_1kw == null ? '–' : fmtPct(v.recall_when_expected_ge_1kw * 100, 0)) },
              { key: 'u', header: 'Untouched hours flagged', align: 'right', render: ([, v]) => fmtPct(v.flag_rate_untouched_pct, 2) },
            ]}
            dense
          />
        </div>
      )}
    </div>
  );
}

function ShapSection({ b }: { b: Benchmark }) {
  const shap = b.shap;
  const hs = Object.keys(shap ?? {}).sort((a, c) => Number(a) - Number(c));
  const [hz, setHz] = useState('');
  if (!shap || hs.length === 0) return <p className="text-sm text-ink-2">The server has no stored explanation results.</p>;
  const h = hz && hs.includes(hz) ? hz : (hs[hs.length - 1] as string);
  const top = shap[h]?.top_features ?? [];
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-end gap-4">
        <h3 className="text-sm">Most important features of the benchmark XGBoost model</h3>
        <SelectField label="Horizon" value={h} onChange={(e) => setHz(e.target.value)} className="w-40">
          {hs.map((x) => (
            <option key={x} value={x}>
              {x} h ahead
            </option>
          ))}
        </SelectField>
      </div>
      <Table caption={`Benchmark top features at ${h} h ahead`} rows={top.slice(0, 10)} rowKey={(r) => r.feature} columns={[{ key: 'l', header: 'Feature', render: (r) => r.label }, { key: 'g', header: 'Group', render: (r) => r.group }, { key: 'm', header: 'Mean |SHAP| (kW)', align: 'right', render: (r) => fmtNum(r.mean_abs_shap_kw, 3) }, { key: 's', header: 'Share (%)', align: 'right', render: (r) => fmtNum(r.share_pct, 1) }]} dense />
      <p className="hint">Computed on {fmtInt(shap[h]?.rows_explained ?? null)} hold-out hours.</p>
    </div>
  );
}

export function BenchmarkPage() {
  const res = useApi<Benchmark>('benchmark', (signal) => benchmarkApi.get({ signal }));
  const b = res.data;
  const period = b?.evaluation?.protocol?.test_period;
  const periodText = period ? `${formatTs(period[0])} to ${formatTs(period[1])}` : null;

  return (
    <>
      <PageHeader title="Benchmark" description="How the forecasting methods compare on the public UCI household dataset. These are offline research results, not results for your own data." />
      {res.loading && !b && <Loading label="Loading benchmark" />}
      {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
      {b && (
        <div className="space-y-6">
          <Notice tone="info" title="Where these numbers come from">
            {b.dataset}. Forecast errors are measured on the benchmark’s hold-out period{periodText ? ` (${periodText})` : ''}, which no model was fitted or tuned on. The figures below are shown as stored by the server.
          </Notice>
          {!b.evaluation && !b.anomaly && !b.shap && <EmptyState title="No benchmark results are installed on this server" />}
          {b.evaluation && (
            <Card title="Forecast comparison">
              <ForecastSection b={b} />
            </Card>
          )}
          {b.evaluation?.protocol && (
            <Card title="Evaluation protocol">
              <ProtocolSection b={b} />
            </Card>
          )}
          {(b.anomaly || b.anomaly_injection_check) && (
            <Card title="Anomaly detection benchmark">
              <AnomalySection b={b} />
            </Card>
          )}
          {b.shap && (
            <Card title="Feature importance">
              <ShapSection b={b} />
            </Card>
          )}
          {Object.entries(b.figures).filter(([, names]) => names.length > 0).map(([group, names]) => (
            <Card key={group} title={`Figures: ${GROUP_LABEL[group] ?? humanize(group)}`}>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {names.map((n) => (
                  <Figure
                    key={n}
                    group={group}
                    name={n}
                    caption={
                      group === 'anomaly'
                        ? 'Benchmark run on the UCI household dataset; unsupervised detection over the whole series, so it is not a hold-out evaluation.'
                        : `Benchmark run on the UCI household dataset${periodText ? `, hold-out period ${periodText}` : ', hold-out period'}.`
                    }
                  />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
