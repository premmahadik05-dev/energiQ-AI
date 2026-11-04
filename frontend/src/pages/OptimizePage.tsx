import { useMemo, useState, type FormEvent } from 'react';
import { optimizeApi } from '../api/endpoints';
import type { RecommendationsResponse, Tariff } from '../api/types';
import { WriteOnly } from '../auth/guards';
import { BarsChart, LinesChart } from '../components/charts/CategoryCharts';
import { ChartFrame } from '../components/charts/ChartFrame';
import { Badge, Card, DescriptionList, KpiTile, PageHeader } from '../components/ui/basic';
import { ErrorState, Loading, Notice, Spinner } from '../components/ui/feedback';
import { SelectField, TextField } from '../components/ui/forms';
import { ConfirmDialog } from '../components/ui/Modal';
import { Table, type Column } from '../components/ui/Table';
import { Tabs } from '../components/ui/Tabs';
import { useAuth } from '../auth/AuthContext';
import { useApi } from '../hooks/useApi';
import { evidenceLabel, evidenceValue } from '../lib/evidence';
import { fmtInt, fmtKwh, fmtMoney, fmtNum } from '../lib/format';
import { formatDate, formatTs } from '../lib/time';
import { parseTariffForm, validateSchedule } from '../lib/validation';
import { useDatasets } from '../state/DatasetContext';
import { useToast } from '../state/ToastContext';
import { NoDatasetState } from './DashboardPage';

type TabId = 'tariffs' | 'cost' | 'recommendations' | 'schedule';
const TABS: { id: TabId; label: string }[] = [
  { id: 'tariffs', label: 'Tariffs' },
  { id: 'cost', label: 'Cost analysis' },
  { id: 'recommendations', label: 'Recommendations' },
  { id: 'schedule', label: 'Cheapest-window scheduler' },
];

const DemoBadge = ({ t }: { t: Pick<Tariff, 'is_demo'> }) => (t.is_demo ? <Badge tone="warn">DEMO – illustrative prices</Badge> : null);

function TariffSelect({ tariffs, value, onChange, label = 'Tariff' }: { tariffs: Tariff[]; value: string; onChange: (v: string) => void; label?: string }) {
  return (
    <SelectField label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {tariffs.map((t) => (
        <option key={String(t.id)} value={String(t.id)}>
          {t.is_demo ? 'DEMO – ' : ''}
          {t.name} ({t.currency})
        </option>
      ))}
    </SelectField>
  );
}

// ------------------------------------------------------------------ tariffs
const HOURS = Array.from({ length: 24 }, (_, h) => h);

function TariffForm({ onCreated }: { onCreated: () => void }) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('');
  const [fixed, setFixed] = useState('0');
  const [wd, setWd] = useState<string[]>(() => HOURS.map(() => ''));
  const [we, setWe] = useState<string[]>(() => HOURS.map(() => ''));
  const [fillValue, setFillValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const parsed = parseTariffForm({ name, currency, dailyFixed: fixed, weekday: wd, weekend: we });
    if ('error' in parsed) return setError(parsed.error);
    setBusy(true);
    setError(null);
    try {
      await optimizeApi.createTariff(parsed.value);
      toast.push(`Tariff “${parsed.value.name}” saved.`, 'success');
      setName('');
      setWd(HOURS.map(() => ''));
      setWe(HOURS.map(() => ''));
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the tariff.');
    } finally {
      setBusy(false);
    }
  };
  const set = (arr: string[], setter: (v: string[]) => void, h: number, v: string) => setter(arr.map((x, i) => (i === h ? v : x)));

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {error && <Notice tone="error" role="alert">{error}</Notice>}
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField label="Tariff name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
        <TextField label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)} maxLength={8} hint="Code or symbol, for example EUR or $." />
        <TextField label="Daily fixed charge" type="number" min="0" step="any" value={fixed} onChange={(e) => setFixed(e.target.value)} hint="Per day, in the same currency." />
      </div>
      <fieldset>
        <legend className="label">Price per kWh for each hour of the day</legend>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <TextField label="Fill every hour with" type="number" min="0" step="any" value={fillValue} onChange={(e) => setFillValue(e.target.value)} className="w-40" />
          <button type="button" className="btn-secondary" onClick={() => { setWd(HOURS.map(() => fillValue)); setWe(HOURS.map(() => fillValue)); }} disabled={fillValue === ''}>
            Fill both columns
          </button>
          <button type="button" className="btn-secondary" onClick={() => setWe([...wd])}>
            Copy weekday to weekend
          </button>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
          {HOURS.map((h) => (
            <div key={h} className="rounded border border-line p-2">
              <p className="num mb-1 text-xs font-semibold text-ink-2">{String(h).padStart(2, '0')}:00</p>
              <div className="flex gap-2">
                <label className="min-w-0 flex-1 text-xs text-ink-2">
                  Weekday
                  <input className="input !min-h-[32px] mt-0.5 px-2" type="number" inputMode="decimal" min="0" step="any" value={wd[h]} onChange={(e) => set(wd, setWd, h, e.target.value)} aria-label={`Weekday rate at ${String(h).padStart(2, '0')}:00`} />
                </label>
                <label className="min-w-0 flex-1 text-xs text-ink-2">
                  Weekend
                  <input className="input !min-h-[32px] mt-0.5 px-2" type="number" inputMode="decimal" min="0" step="any" value={we[h]} onChange={(e) => set(we, setWe, h, e.target.value)} aria-label={`Weekend rate at ${String(h).padStart(2, '0')}:00`} />
                </label>
              </div>
            </div>
          ))}
        </div>
      </fieldset>
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy && <Spinner />}Save tariff
      </button>
    </form>
  );
}

function TariffsTab({ tariffs, reload }: { tariffs: Tariff[]; reload: () => void }) {
  const toast = useToast();
  const [shown, setShown] = useState<string>('demo');
  const [toDelete, setToDelete] = useState<Tariff | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);
  const t = tariffs.find((x) => String(x.id) === shown) ?? tariffs[0];

  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    setDelError(null);
    try {
      await optimizeApi.deleteTariff(Number(toDelete.id));
      toast.push('Tariff deleted.', 'success');
      setToDelete(null);
      setShown('demo');
      reload();
    } catch (e) {
      setDelError(e instanceof Error ? e.message : 'Delete failed.');
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<Tariff>[] = [
    { key: 'n', header: 'Name', render: (x) => <span className="font-medium">{x.name} <DemoBadge t={x} /></span> },
    { key: 'c', header: 'Currency', render: (x) => x.currency },
    { key: 'f', header: 'Daily fixed charge', align: 'right', render: (x) => fmtMoney(x.daily_fixed_charge, x.currency) },
    { key: 'r', header: 'Rate range per kWh', align: 'right', render: (x) => { const all = [...x.weekday_rates, ...x.weekend_rates]; return `${fmtNum(Math.min(...all), 3)} to ${fmtNum(Math.max(...all), 3)}`; } },
    {
      key: 'a',
      header: 'Actions',
      render: (x) => (
        <div className="flex gap-1">
          <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => setShown(String(x.id))} aria-pressed={t?.id === x.id}>
            {t?.id === x.id ? 'Showing' : 'View rates'}
          </button>
          {!x.is_demo && (
            <WriteOnly>
              <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs text-bad" onClick={() => setToDelete(x)}>
                Delete
              </button>
            </WriteOnly>
          )}
        </div>
      ),
    },
  ];
  const rateRows = HOURS.map((h) => ({ hour: h, weekday: t?.weekday_rates[h] ?? null, weekend: t?.weekend_rates[h] ?? null }));

  return (
    <div className="space-y-6">
      <Card title="Your tariffs" padded={false}>
        <div className="p-4 sm:p-5">
          <Table columns={columns} rows={tariffs} rowKey={(x) => String(x.id)} caption="Tariffs" />
          {tariffs.some((x) => x.is_demo) && <p className="mt-3 text-sm text-ink-2">{tariffs.find((x) => x.is_demo)?.note}</p>}
        </div>
      </Card>
      {t && (
        <Card title={`Hourly rates: ${t.name}`} description={t.is_demo ? t.note : undefined}>
          <ChartFrame
            title="Price per kWh by hour of day"
            summary={`Step chart of price per kWh in ${t.currency} for each hour, weekdays and weekends. A table view lists the 24 hourly rates.`}
            legend={[{ label: 'Weekday', color: 'var(--s1)', kind: 'line' }, { label: 'Weekend', color: 'var(--s2)', kind: 'dash' }]}
            table={<Table caption="Hourly rates" rows={rateRows} rowKey={(r) => r.hour} columns={[{ key: 'h', header: 'Hour', render: (r) => `${String(r.hour).padStart(2, '0')}:00` }, { key: 'wd', header: `Weekday (${t.currency}/kWh)`, align: 'right', render: (r) => fmtNum(r.weekday, 3) }, { key: 'we', header: `Weekend (${t.currency}/kWh)`, align: 'right', render: (r) => fmtNum(r.weekend, 3) }]} dense />}
          >
            <LinesChart data={rateRows} xKey="hour" step series={[{ key: 'weekday', name: 'Weekday', color: 'var(--s1)' }, { key: 'weekend', name: 'Weekend', color: 'var(--s2)', dashed: true }]} unit={`${t.currency}/kWh`} digits={3} xLabel="Hour of day" xTickFormatter={(v) => String(v).padStart(2, '0')} />
          </ChartFrame>
        </Card>
      )}
      <WriteOnly>
        <Card title="Add a tariff" description="24 weekday and 24 weekend prices per kWh, plus an optional fixed charge per day.">
          <TariffForm onCreated={reload} />
        </Card>
      </WriteOnly>
      <ConfirmDialog open={!!toDelete} title={`Delete “${toDelete?.name ?? ''}”?`} confirmLabel="Delete tariff" busy={deleting} error={delError} onConfirm={remove} onCancel={() => setToDelete(null)}>
        The tariff is removed. Analyses you run later must use another tariff.
      </ConfirmDialog>
    </div>
  );
}

// ------------------------------------------------------------------ cost
function CostTab({ tariffs, datasetId, start, end }: { tariffs: Tariff[]; datasetId: number; start: string | null; end: string | null }) {
  const [tariffId, setTariffId] = useState('demo');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const key = `cost:${datasetId}:${tariffId}:${from}:${to}`;
  const res = useApi(key, (signal) => optimizeApi.cost({ dataset_id: datasetId, tariff_id: tariffId === 'demo' ? 'demo' : Number(tariffId), ...(from ? { start: `${from}T00:00:00` } : {}), ...(to ? { end: `${to}T23:59:59` } : {}) }, { signal }));
  const c = res.data;
  const cur = c?.total.currency ?? '';
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <TariffSelect tariffs={tariffs} value={tariffId} onChange={setTariffId} />
        <TextField label="From (optional)" type="date" value={from} min={start ? formatDate(start) : undefined} max={end ? formatDate(end) : undefined} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="To (optional)" type="date" value={to} min={start ? formatDate(start) : undefined} max={end ? formatDate(end) : undefined} onChange={(e) => setTo(e.target.value)} />
      </div>
      {res.loading && !c && <Loading label="Calculating cost" />}
      {res.error && <ErrorState error={res.error} onRetry={res.reload} title="Could not calculate the cost" />}
      {c && (
        <>
          {c.total.is_demo_tariff && <Notice tone="warn" title="DEMO tariff">The prices used here are illustrative, not any utility’s real price list. Add your own tariff before relying on a cost figure.</Notice>}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile label="Total cost" value={fmtMoney(c.total.total_cost, cur)} sub={c.tariff.name} />
            <KpiTile label="Energy" value={fmtKwh(c.total.energy_kwh, 0)} sub={`${fmtInt(c.total.valid_hours)} valid hours costed`} />
            <KpiTile label="Energy charges" value={fmtMoney(c.total.energy_cost, cur)} sub={`Fixed charges ${fmtMoney(c.total.fixed_cost, cur)}`} />
            <KpiTile label="Average cost per kWh" value={c.total.avg_cost_per_kwh != null ? fmtMoney(c.total.avg_cost_per_kwh, cur, 3) : '–'} sub={`Range ${formatTs(c.range[0])} to ${formatTs(c.range[1])}`} />
          </div>
          <p className="text-sm text-ink-2">Only hours with a valid reading are costed; missing hours are not estimated.</p>
          <ChartFrame
            title="Cost by month"
            summary={`Bar chart of total cost in ${cur} for each of ${c.monthly.length} months. A table view lists cost, energy and valid hours per month.`}
            table={<Table caption="Monthly cost" rows={c.monthly} rowKey={(m) => m.month} columns={[{ key: 'm', header: 'Month', render: (m) => m.month }, { key: 'h', header: 'Valid hours', align: 'right', render: (m) => fmtInt(m.valid_hours) }, { key: 'e', header: 'Energy (kWh)', align: 'right', render: (m) => fmtNum(m.energy_kwh, 1) }, { key: 'c', header: `Cost (${cur})`, align: 'right', render: (m) => fmtNum(m.total_cost, 2) }]} dense />}
            footer="Months with fewer valid hours cost less simply because less data was counted; compare the valid hours column."
          >
            <BarsChart data={c.monthly} xKey="month" series={[{ key: 'total_cost', name: 'Total cost', color: 'var(--s1)' }]} unit={cur} digits={2} />
          </ChartFrame>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ recommendations
function RecommendationsTab({ tariffs, datasetId }: { tariffs: Tariff[]; datasetId: number }) {
  const { canWrite } = useAuth();
  const [tariffId, setTariffId] = useState('demo');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [out, setOut] = useState<RecommendationsResponse | null>(null);
  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setOut(await optimizeApi.recommendations({ dataset_id: datasetId, tariff_id: tariffId === 'demo' ? 'demo' : Number(tariffId) }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not generate recommendations.');
    } finally {
      setBusy(false);
    }
  };
  const tone = (p: string) => (p === 'high' ? 'bad' : p === 'medium' ? 'warn' : 'neutral');
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <TariffSelect tariffs={tariffs} value={tariffId} onChange={(v) => { setTariffId(v); setOut(null); }} />
        <button type="button" className="btn-primary" onClick={run} disabled={busy || !canWrite}>
          {busy && <Spinner />}Generate recommendations
        </button>
        {!canWrite && <p className="pb-2 text-sm text-ink-2">Viewer accounts cannot generate recommendations (each run is saved).</p>}
      </div>
      <p className="max-w-prose text-sm text-ink-2">Rule-based suggestions from your own history, the latest forecast, the tariff and recent anomalies. Cost figures are scenario estimates under a stated assumption, not predictions of savings.</p>
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      {out && (
        <>
          {out.window && <p className="text-sm text-ink-2">Based on {fmtInt(out.window.valid_hours)} valid hours from {formatTs(out.window.start)} to {formatTs(out.window.end)} ({fmtNum(out.window.days_covered, 0)} days).</p>}
          {out.message && <Notice tone="info">{out.message}</Notice>}
          {out.recommendations.length === 0 && !out.message && <Notice tone="info" title="No recommendations apply">None of the rules found something worth flagging in this window.</Notice>}
          <ul className="grid gap-4 lg:grid-cols-2">
            {out.recommendations.map((r) => (
              <li key={r.id} className="card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={tone(r.priority)}>{r.priority} priority</Badge>
                  <Badge>{r.category}</Badge>
                </div>
                <h3 className="mt-2 text-base">{r.title}</h3>
                <p className="mt-1 text-sm">{r.explanation}</p>
                {Object.keys(r.evidence).length > 0 && (
                  <>
                    <h4 className="mt-3 text-xs font-semibold text-ink-2">Evidence</h4>
                    <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
                      {Object.entries(r.evidence).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-ink-2">{evidenceLabel(k)}</dt>
                          <dd className="num text-right">{evidenceValue(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
                {r.scenario && (
                  <div className="mt-3 rounded border border-line-strong bg-sunken p-3">
                    <p className="flex items-center gap-2 text-xs font-semibold text-ink-2">
                      Scenario <Badge tone="warn">estimate</Badge>
                    </p>
                    <p className="mt-1 text-sm">{r.scenario.assumption}</p>
                    <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
                      {Object.entries(r.scenario)
                        .filter(([k]) => k !== 'assumption' && k !== 'currency')
                        .map(([k, v]) => (
                          <div key={k} className="contents">
                            <dt className="text-ink-2">Estimated {evidenceLabel(k).toLowerCase()}</dt>
                            <dd className="num text-right font-medium">{k.includes('saving') && typeof v === 'number' ? fmtMoney(v, r.scenario?.currency ?? '') : evidenceValue(v)}</dd>
                          </div>
                        ))}
                    </dl>
                  </div>
                )}
                {r.caveats.length > 0 && (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-ink-2">
                    {r.caveats.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ scheduler
function ScheduleTab({ tariffs, datasetId, datasetEnd }: { tariffs: Tariff[]; datasetId: number; datasetEnd: string | null }) {
  const [tariffId, setTariffId] = useState('demo');
  const [duration, setDuration] = useState('3');
  const [power, setPower] = useState('2');
  const [startAfter, setStartAfter] = useState('');
  const [useForecast, setUseForecast] = useState(true);
  const [errors, setErrors] = useState<{ duration_h?: string; power_kw?: string }>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [out, setOut] = useState<Awaited<ReturnType<typeof optimizeApi.schedule>> | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = validateSchedule(duration, power);
    setErrors(v);
    if (v.duration_h || v.power_kw) return;
    setBusy(true);
    setErr(null);
    try {
      setOut(await optimizeApi.schedule({ ...(useForecast ? { dataset_id: datasetId } : {}), tariff_id: tariffId === 'demo' ? 'demo' : Number(tariffId), duration_h: Number(duration), power_kw: Number(power), ...(startAfter ? { start_after: `${startAfter}:00`.slice(0, 19) } : {}) }));
    } catch (error) {
      setErr(error instanceof Error ? error.message : 'Could not find a window.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={submit} noValidate className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <TariffSelect tariffs={tariffs} value={tariffId} onChange={setTariffId} />
        <TextField label="Run time (hours)" type="number" min="1" max="24" step="1" value={duration} onChange={(e) => setDuration(e.target.value)} error={errors.duration_h} />
        <TextField label="Power draw (kW)" type="number" min="0" step="any" value={power} onChange={(e) => setPower(e.target.value)} error={errors.power_kw} />
        <TextField label="Start no earlier than (optional)" type="datetime-local" value={startAfter} onChange={(e) => setStartAfter(e.target.value)} hint={datasetEnd ? `Empty = the hour after the dataset ends (${formatTs(datasetEnd)}).` : 'Empty = now (server clock).'} />
        <div className="flex items-center gap-2 sm:col-span-2 lg:col-span-1 lg:pt-7">
          <input id="use-forecast" type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={useForecast} onChange={(e) => setUseForecast(e.target.checked)} />
          <label htmlFor="use-forecast" className="text-sm">Break ties toward hours when the active model forecasts lower demand</label>
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy && <Spinner />}Find the cheapest window
          </button>
        </div>
      </form>
      <p className="max-w-prose text-sm text-ink-2">Searches the 24 hours from the start time for the start that makes a continuous run cost least (price × power, summed over the run).</p>
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      {out && (
        <Card title="Cheapest window">
          <div className="space-y-4">
            {out.is_demo_tariff && <Notice tone="warn" title="DEMO tariff">The prices are illustrative, not a real utility price list.</Notice>}
            <p className="text-lg">
              Start at <strong className="num">{formatTs(out.best_start)}</strong>, finish at <strong className="num">{formatTs(out.best_end)}</strong>
            </p>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <KpiTile label="Cost of this window" value={fmtMoney(out.cost, out.currency)} sub={`${fmtKwh(out.energy_kwh, 1)} of energy`} />
              <KpiTile label="Cost if started in the first hour" value={fmtMoney(out.cost_if_started_first_hour, out.currency)} />
              <KpiTile label="Saving vs first hour" value={fmtMoney(out.saving_vs_first_hour, out.currency)} sub="Zero when the first hour is already cheapest" />
              <KpiTile label="Dearest start in the window" value={fmtMoney(out.cost_at_worst_start, out.currency)} sub={`Starting ${formatTs(out.worst_start)}`} />
            </div>
            <DescriptionList items={[{ label: 'Energy', value: fmtKwh(out.energy_kwh, 1) }, { label: 'Currency', value: out.currency }]} />
          </div>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ page
export function OptimizePage() {
  const { active, loading: dsLoading } = useDatasets();
  const [tab, setTab] = useState<TabId>('tariffs');
  const tariffs = useApi<Tariff[]>('tariffs', (signal) => optimizeApi.tariffs({ signal }));
  const list = useMemo(() => tariffs.data ?? [], [tariffs.data]);
  const needsData = tab !== 'tariffs';

  if (dsLoading) return <Loading label="Loading datasets" />;
  return (
    <>
      <PageHeader title="Optimisation" description="Electricity cost for your data under a tariff, ideas for saving, and the cheapest time to run a flexible load." />
      {tariffs.loading && !tariffs.data && <Loading label="Loading tariffs" />}
      {tariffs.error && <ErrorState error={tariffs.error} onRetry={tariffs.reload} />}
      {tariffs.data && (
        <Tabs tabs={TABS} value={tab} onChange={setTab} label="Optimisation sections">
          {tab === 'tariffs' && <TariffsTab tariffs={list} reload={tariffs.reload} />}
          {needsData && !active && <NoDatasetState />}
          {needsData && active && active.status !== 'ready' && <Notice tone="warn" title="This dataset is not ready">Status: {active.status}.</Notice>}
          {needsData && active?.status === 'ready' && (
            <>
              <p className="mb-4 text-sm text-ink-2">Dataset: <strong className="text-ink">{active.name}</strong></p>
              {tab === 'cost' && <CostTab key={active.id} tariffs={list} datasetId={active.id} start={active.start_ts} end={active.end_ts} />}
              {tab === 'recommendations' && <RecommendationsTab key={active.id} tariffs={list} datasetId={active.id} />}
              {tab === 'schedule' && <ScheduleTab key={active.id} tariffs={list} datasetId={active.id} datasetEnd={active.end_ts} />}
            </>
          )}
        </Tabs>
      )}
    </>
  );
}

