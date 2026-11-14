import { useMemo, useState } from 'react';
import { societyApi } from '../../api/endpoints';
import type { SocietySummary } from '../../api/societyTypes';
import { BarsChart, LinesChart } from '../../components/charts/CategoryCharts';
import { RangePresets, SocietyGate, SocietyHeader, TariffPicker } from '../../components/society/common';
import { TariffManager } from '../../components/society/TariffManager';
import { useRange } from '../../components/society/useRange';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Card, KpiTile } from '../../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { Tabs } from '../../components/ui/Tabs';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtKw, fmtKwh, fmtMoney, fmtNum, fmtPct, modelLabel } from '../../lib/format';
import { formatTs, parseNaive } from '../../lib/time';
import { useSociety } from '../../state/SocietyContext';

function CostTab({ society }: { society: SocietySummary }) {
  const { tariffId, tariff } = useSociety();
  const { preset, setPreset, range, key } = useRange(society, '90d');
  const cost = useApi(`soc-cost:${key}:${tariffId}`, (signal) => societyApi.cost(society.id, { tariff_id: tariffId, ...range }, { signal }));
  const monthly = useMemo(() => {
    const m = new Map<string, { month: string; kwh: number; cost: number }>();
    for (const d of cost.data?.daily ?? []) {
      const k = d.ts.slice(0, 7);
      const row = m.get(k) ?? { month: k, kwh: 0, cost: 0 };
      row.kwh += d.energy_kwh;
      row.cost += d.total_cost;
      m.set(k, row);
    }
    return [...m.values()];
  }, [cost.data]);
  const c = cost.data?.total;
  const currency = c?.currency ?? tariff?.currency ?? '';
  const monthlyCols: Column<(typeof monthly)[number]>[] = [
    { key: 'm', header: 'Month', render: (r) => r.month },
    { key: 'e', header: 'Energy (kWh)', align: 'right', render: (r) => fmtInt(r.kwh) },
    { key: 'c', header: `Estimated cost (${currency})`, align: 'right', render: (r) => fmtNum(r.cost, 0) },
    { key: 'a', header: `Per kWh (${currency})`, align: 'right', render: (r) => (r.kwh > 0 ? fmtNum(r.cost / r.kwh, 3) : '–') },
  ];
  return (
    <div className="space-y-6">
      <Notice tone="warn" title="An estimate, not a bill">
        Cost is the metered energy multiplied by the tariff you choose (time-of-day rates for weekdays and weekends, plus an optional daily fixed charge). There are no real utility prices in this project: the built-in tariff is a placeholder, and demand charges, taxes and fuel adjustments are not modelled.
      </Notice>
      <Card title="Cost estimate" actions={<TariffPicker />}>
        <div className="mb-4">
          <RangePresets society={society} value={preset} onChange={(p) => setPreset(p)} presets={['30d', '90d', '1y', 'all']} />
        </div>
        {cost.error ? (
          <ErrorState error={cost.error} onRetry={cost.reload} />
        ) : cost.loading && !cost.data ? (
          <Loading label="Calculating cost" />
        ) : c ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <KpiTile label="Estimated cost" value={fmtMoney(c.total_cost, c.currency, 0)} sub={c.is_demo_tariff ? 'Demo tariff' : tariff?.name} />
              <KpiTile label="Energy" value={fmtKwh(c.energy_kwh, 0)} sub={`${fmtInt(c.valid_hours)} valid hours`} />
              <KpiTile label="Average price" value={c.avg_cost_per_kwh != null ? `${fmtNum(c.avg_cost_per_kwh, 3)} ${c.currency}/kWh` : '–'} sub="Energy cost over energy" />
              <KpiTile label="Fixed charges" value={fmtMoney(c.fixed_cost, c.currency, 0)} />
            </div>
            <div className="mt-6">
              <SeriesChart
                title="Estimated daily cost"
                summary={`Estimated electricity cost per day in ${c.currency} from ${range.start.slice(0, 10)} to ${range.end.slice(0, 10)}. A table lists every value.`}
                rows={(cost.data?.daily ?? []).map((d) => ({ t: parseNaive(d.ts), v: d.valid_hours > 0 ? d.total_cost : null }))}
                lines={[{ key: 'v', name: `Daily cost (${c.currency})`, color: 'var(--s4)' }]}
                unit={c.currency}
                digits={0}
                style="day"
                height={260}
              />
            </div>
            {monthly.length > 1 && (
              <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div>
                  <p className="mb-2 text-sm font-semibold">Estimated monthly cost</p>
                  <BarsChart data={monthly.map((m) => ({ month: m.month, cost: Number(m.cost.toFixed(0)) }))} xKey="month" series={[{ key: 'cost', name: 'Estimated cost', color: 'var(--s4)' }]} unit={c.currency} height={260} digits={0} />
                </div>
                <Table columns={monthlyCols} rows={monthly} rowKey={(r) => r.month} caption="Monthly energy and estimated cost" dense />
              </div>
            )}
            <p className="mt-3 text-xs text-ink-2">Partial months at the edges of the range, and hours without a valid reading, make the first and last months lower than a full month.</p>
          </>
        ) : null}
      </Card>
      <TariffManager />
    </div>
  );
}

function PeaksTab({ society }: { society: SocietySummary }) {
  const { preset, setPreset, range, key } = useRange(society, '1y');
  const pk = useApi(`soc-peaks:${key}`, (signal) => societyApi.peaks(society.id, range, { signal }));
  const p = pk.data;
  const ev = p?.forecast_evaluation;
  const m = ev?.model ?? null;
  const b = ev?.baseline ?? null;
  const topCols: Column<{ ts: string; kw: number }>[] = [
    { key: 't', header: 'Hour', render: (r) => formatTs(r.ts) },
    { key: 'k', header: 'Demand (kW)', align: 'right', render: (r) => fmtNum(r.kw, 0) },
  ];
  return (
    <div className="space-y-6">
      <Notice>Peak demand here is the highest hourly average kW. A short spike inside an hour can be higher than the hourly average, and the data cannot show it.</Notice>
      <Card title="Peak demand analysis">
        <div className="mb-4">
          <RangePresets society={society} value={preset} onChange={(v) => setPreset(v)} presets={['30d', '90d', '1y', 'all']} />
        </div>
        {pk.error ? (
          <ErrorState error={pk.error} onRetry={pk.reload} />
        ) : pk.loading && !pk.data ? (
          <Loading label="Analysing peaks" />
        ) : p ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <KpiTile label="Peak hourly demand" value={fmtKw(p.overall.peak_kw, 0)} sub={`Top hour ${formatTs(p.top_hours[0]?.ts)}`} />
              <KpiTile label="Load factor" value={fmtNum(p.overall.load_factor, 2)} sub="Average demand over peak demand" />
              <KpiTile label="Peak to average" value={fmtNum(p.overall.peak_to_average, 2)} />
              <KpiTile label="95th percentile" value={fmtKw(p.overall.p95_kw, 0)} sub={`99th ${fmtNum(p.overall.p99_kw, 0)} kW`} />
            </div>
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-sm font-semibold">Average demand by hour of day</p>
                <LinesChart
                  data={p.profile.map((r) => ({ hour: String(r.hour).padStart(2, '0'), weekday: Number(r.weekday_mean_kw.toFixed(1)), weekend: Number(r.weekend_mean_kw.toFixed(1)), p95: Number(r.p95_kw.toFixed(1)) }))}
                  xKey="hour"
                  series={[{ key: 'weekday', name: 'Weekday average', color: 'var(--s1)' }, { key: 'weekend', name: 'Weekend average', color: 'var(--s3)' }, { key: 'p95', name: '95th percentile (all days)', color: 'var(--s2)', dashed: true }]}
                  unit="kW"
                  digits={0}
                  xLabel="Hour of day"
                  height={280}
                />
              </div>
              <div>
                <p className="mb-2 text-sm font-semibold">When does the daily peak happen? (days per hour)</p>
                <BarsChart data={p.peak_hour_histogram.map((r) => ({ hour: String(r.hour).padStart(2, '0'), days: r.days }))} xKey="hour" series={[{ key: 'days', name: 'Days with the peak in this hour', color: 'var(--s1)' }]} unit="days" digits={0} xLabel="Hour of day" height={280} />
              </div>
            </div>
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <p className="mb-1 text-sm font-semibold">Load duration curve</p>
                <p className="mb-2 text-xs text-ink-2">Every valid hour sorted from the highest demand to the lowest. A steep left edge means a few very high hours drive the peak.</p>
                {p.load_duration.length > 1 ? (
                  <LinesChart
                    data={p.load_duration.map((r) => ({ pct: `${fmtNum(r.percent_of_time, 0)}%`, kw: Number(r.kw.toFixed(1)) }))}
                    xKey="pct"
                    series={[{ key: 'kw', name: 'Demand exceeded for this share of hours', color: 'var(--s1)' }]}
                    unit="kW"
                    digits={0}
                    xLabel="Share of hours with demand at or above this level (%)"
                    xInterval={9}
                    height={280}
                  />
                ) : (
                  <EmptyState title="No data">There are no valid hours in this range.</EmptyState>
                )}
              </div>
              <div>
                <p className="mb-1 text-sm font-semibold">Distribution of hourly demand</p>
                <p className="mb-2 text-xs text-ink-2">How many hours fall in each demand band across the selected range.</p>
                {p.distribution.length > 0 ? (
                  <BarsChart
                    data={p.distribution.map((r) => ({ band: fmtNum((r.from_kw + r.to_kw) / 2, 0), hours: r.hours }))}
                    xKey="band"
                    series={[{ key: 'hours', name: 'Hours in this demand band', color: 'var(--s2)' }]}
                    unit="hours"
                    digits={0}
                    xLabel="Hourly demand, middle of each band (kW)"
                    height={280}
                  />
                ) : (
                  <EmptyState title="No data">There are no valid hours in this range.</EmptyState>
                )}
              </div>
            </div>
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-sm font-semibold">Monthly average and peak demand</p>
                <BarsChart data={p.monthly.map((r) => ({ month: r.month, average: Number(r.mean_kw.toFixed(0)), peak: Number(r.peak_kw.toFixed(0)) }))} xKey="month" series={[{ key: 'average', name: 'Average', color: 'var(--s1)' }, { key: 'peak', name: 'Peak', color: 'var(--s2)' }]} unit="kW" digits={0} height={280} />
              </div>
              <div>
                <p className="mb-2 text-sm font-semibold">Ten highest hours</p>
                <Table columns={topCols} rows={p.top_hours} rowKey={(r) => r.ts} caption="Ten highest hourly demands" dense />
              </div>
            </div>
          </>
        ) : null}
      </Card>
      <Card title="How well is the daily peak forecast?" description="24-hour-ahead forecasts on held-out test days: the day's highest predicted hour against the day's highest measured hour.">
        {!ev || ev.days === 0 || !m || !b ? (
          <EmptyState title="Not evaluated">{ev?.note ?? 'No peak evaluation is stored for this society.'}</EmptyState>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <KpiTile label="Peak size error (MAE)" value={`${fmtNum(m.peak_mae_kw, 1)} kW`} sub={ev.model_name ? `${modelLabel(ev.model_name)}; mean daily peak ${fmtNum(ev.mean_actual_peak_kw, 0)} kW` : `Mean daily peak ${fmtNum(ev.mean_actual_peak_kw, 0)} kW`} />
              <KpiTile label="Baseline MAE" value={`${fmtNum(b.peak_mae_kw, 1)} kW`} sub={ev.baseline_name ? modelLabel(ev.baseline_name) : 'Simple baseline'} />
              <KpiTile label="Peak hour within 1 h" value={fmtPct(m.peak_hour_within_1h_pct, 0)} sub={`Baseline ${fmtPct(b.peak_hour_within_1h_pct, 0)}`} />
              <KpiTile label="Peak hour within 2 h" value={fmtPct(m.peak_hour_within_2h_pct, 0)} sub={`Baseline ${fmtPct(b.peak_hour_within_2h_pct, 0)}; ${ev.days} test days`} />
            </div>
            <p className="mt-3 text-xs text-ink-2">{ev.basis}. Exact-hour hits: model {fmtPct(m.peak_hour_exact_pct, 0)}, baseline {fmtPct(b.peak_hour_exact_pct, 0)}. A modest gain over the baseline is the honest finding where the numbers are close.</p>
          </>
        )}
      </Card>
    </div>
  );
}

function PeaksCost({ society }: { society: SocietySummary }) {
  const [tab, setTab] = useState<'cost' | 'peaks'>('cost');
  return (
    <Tabs label="Cost and peaks" value={tab} onChange={setTab} tabs={[{ id: 'cost', label: 'Cost' }, { id: 'peaks', label: 'Peak demand' }]}>
      {tab === 'cost' ? <CostTab society={society} /> : <PeaksTab society={society} />}
    </Tabs>
  );
}

export function PeaksCostPage() {
  return (
    <>
      <SocietyHeader title="Cost and peak demand" description="Configurable cost estimate and the shape of peak demand, including how well the daily peak is forecast." />
      <SocietyGate>{(s) => <PeaksCost society={s} />}</SocietyGate>
    </>
  );
}
