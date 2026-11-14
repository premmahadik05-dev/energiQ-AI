import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { societyApi } from '../../api/endpoints';
import type { SocietySummary } from '../../api/societyTypes';
import type { TsRow } from '../../components/charts/TimeSeriesChart';
import { DataBasisNote, SocietyGate, SocietyHeader, TariffPicker } from '../../components/society/common';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Badge, Card, KpiTile } from '../../components/ui/basic';
import { ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtKw, fmtKwh, fmtMoney, fmtNum, fmtSigned } from '../../lib/format';
import { DAY, formatTs, parseNaive, toApiTimestamp } from '../../lib/time';
import { useJobs } from '../../state/JobsContext';
import { useSociety } from '../../state/SocietyContext';

function Overview({ society }: { society: SocietySummary }) {
  const { tariffId } = useSociety();
  const { settledSeq } = useJobs();
  const ov = useApi(`soc-ov:${society.id}:${tariffId}:${settledSeq}`, (signal) => societyApi.overview(society.id, tariffId, { signal }));
  const endMs = parseNaive(society.end);
  const hist = useApi(`soc-ov-hist:${society.id}:${settledSeq}`, (signal) =>
    societyApi.consumption(society.id, { resolution: 'hourly', start: toApiTimestamp(endMs - 6 * DAY), end: toApiTimestamp(endMs) }, { signal }),
  );
  const canForecast = ov.data?.forecast != null && !ov.data.forecast.error;
  const fc = useApi(canForecast ? `soc-ov-fc:${society.id}:${tariffId}:${settledSeq}` : null, (signal) => societyApi.forecast(society.id, { tariff_id: tariffId }, { signal }));

  const rows = useMemo<TsRow[]>(() => {
    const map = new Map<number, TsRow>();
    for (const p of hist.data?.points ?? []) map.set(parseNaive(p.ts), { t: parseNaive(p.ts), actual: p.avg_kw });
    for (const p of fc.data?.points ?? []) {
      const t = parseNaive(p.ts);
      const row = map.get(t) ?? ({ t, actual: null } as TsRow);
      row.forecast = p.kw;
      row.band = [p.lower_kw, p.upper_kw];
      map.set(t, row);
    }
    return [...map.values()].sort((a, b) => a.t - b.t);
  }, [hist.data, fc.data]);

  if (ov.loading && !ov.data) return <Loading label="Loading society overview" />;
  if (ov.error) return <ErrorState error={ov.error} onRetry={ov.reload} />;
  const o = ov.data;
  if (!o) return null;
  const f = o.forecast;
  const currency = o.tariff.currency;
  const attention = (o.anomalies.society.medium ?? 0) + (o.anomalies.society.high ?? 0);
  const week = o.windows.last_7d;
  const chg = o.windows.last_24h.change_vs_previous_pct;

  return (
    <div className="space-y-7">
      <DataBasisNote society={society} />

      <Card
        title="Last 7 days and the next 24 hours"
        description="Solid line: measured demand. Dashed line with dots and shaded band: forecast with its 80% range, made from the last hour of data."
      >
        {hist.error ? (
          <ErrorState error={hist.error} onRetry={hist.reload} />
        ) : hist.loading && !hist.data ? (
          <Loading label="Loading recent demand" />
        ) : (
          <SeriesChart
            title="Society demand: recent history and forecast"
            summary={`Hourly society demand for the last seven days up to ${formatTs(o.as_of)}${f?.peak_kw != null ? `, then a 24 hour forecast peaking near ${fmtNum(f.peak_kw, 0)} kW` : ''}. A table view lists every value.`}
            rows={rows}
            lines={[{ key: 'actual', name: 'Measured demand', color: 'var(--s1)' }, ...(fc.data ? [{ key: 'forecast', name: 'Forecast', color: 'var(--s2)', dashed: true, dots: true }] : [])]}
            band={fc.data ? { key: 'band', name: '80% range' } : undefined}
            refLines={fc.data ? [{ t: parseNaive(fc.data.origin), label: 'Forecast origin' }] : []}
            digits={0}
            height={340}
            footer={f?.note ?? o.as_of_note}
          />
        )}
        {fc.error && <Notice tone="warn" title="Forecast not shown">{fc.error.message}</Notice>}
      </Card>

      <section aria-labelledby="ov-measured" className="space-y-3">
        <h2 id="ov-measured" className="text-[16px]">Measured demand and energy</h2>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <KpiTile marker="measured" label="Latest demand" value={fmtNum(o.latest.demand_kw, 0)} unit="kW" sub={`Hour ending ${formatTs(o.latest.ts)} (last valid hour in the data)`} />
          <KpiTile marker="measured" label="Energy, last 24 h" value={fmtNum(o.windows.last_24h.energy_kwh, 0)} unit="kWh" sub={chg == null ? 'No previous day to compare' : `${fmtSigned(chg, 1)}% vs the 24 h before`} />
          <KpiTile marker="measured" label="Energy, last 7 days" value={fmtNum(week.energy_kwh, 0)} unit="kWh" sub={`Average ${fmtKw(week.avg_kw, 0)}, ${week.valid_hours} of ${week.hours} hours valid`} />
          <KpiTile marker="measured" label="Energy, last 30 days" value={fmtNum(o.windows.last_30d.energy_kwh, 0)} unit="kWh" sub={`Peak ${fmtKw(o.windows.last_30d.peak_kw, 0)}`} />
        </div>
      </section>

      <section aria-labelledby="ov-forecast" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h2 id="ov-forecast" className="text-[16px]">Forecast, cost and alerts</h2>
          <TariffPicker compact />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <KpiTile
            marker="forecast"
            label="Predicted next 24 h"
            value={f && f.next_24h_energy_kwh != null ? fmtNum(f.next_24h_energy_kwh, 0) : 'Not available'}
            unit={f && f.next_24h_energy_kwh != null ? 'kWh' : undefined}
            sub={f && f.next_24h_energy_range_kwh ? `80% range ${fmtNum(f.next_24h_energy_range_kwh[0], 0)} to ${fmtNum(f.next_24h_energy_range_kwh[1], 0)} kWh` : (f?.error ?? 'No trained model for this society')}
          />
          <KpiTile
            marker="forecast"
            label="Predicted peak demand"
            value={f && f.peak_kw != null ? fmtNum(f.peak_kw, 0) : 'Not available'}
            unit={f && f.peak_kw != null ? 'kW' : undefined}
            sub={f && f.peak_time ? `Around ${formatTs(f.peak_time)}${f.peak_range_kw ? `, range ${fmtNum(f.peak_range_kw[0], 0)} to ${fmtNum(f.peak_range_kw[1], 0)} kW` : ''}` : undefined}
          />
          <KpiTile
            label="Estimated cost, last 30 days"
            value={o.cost_last_30d ? fmtMoney(o.cost_last_30d.total_cost, currency, 0) : 'Not available'}
            sub={o.tariff.is_demo ? 'Demo tariff: an estimate with placeholder prices, not a bill' : `${o.tariff.name}: an estimate, not a bill`}
          />
          <KpiTile
            label="Alerts needing attention"
            value={fmtInt(attention)}
            tone={attention > 0 ? 'warn' : 'good'}
            sub={
              <>
                Medium or high severity on the whole society.{' '}
                <Link to="/alerts" className="text-accent underline">
                  Review alerts
                </Link>
              </>
            }
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Whole data period">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-ink-2">Total energy</dt><dd className="num">{fmtKwh(o.totals.energy_kwh, 0)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-2">Average demand</dt><dd className="num">{fmtKw(o.totals.avg_kw, 0)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-2">Peak hourly demand</dt><dd className="num">{fmtKw(o.totals.peak_kw, 0)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-2">Peak hour</dt><dd className="num">{formatTs(o.totals.peak_ts)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-2">Load factor</dt><dd className="num">{fmtNum(o.totals.load_factor, 2)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-2">Valid hours</dt><dd className="num">{fmtInt(o.totals.valid_hours)} of {fmtInt(o.totals.hours)}</dd></div>
          </dl>
        </Card>
        <Card title="Buildings and data">
          <p className="text-sm text-ink-2">
            {society.buildings} buildings{society.floor_area_sqm ? `, ${fmtInt(society.floor_area_sqm)} m² floor area` : ''}. Source: {society.source_name}. Licence: {society.license}.
          </p>
          <p className="mt-2 text-sm">
            <Link to="/buildings" className="text-accent underline">Compare buildings</Link> · <Link to="/facilities" className="text-accent underline">Facility meters</Link>
          </p>
        </Card>
        <Card title="Forecast model">
          <p className="text-sm text-ink-2">
            {society.has_model ? (society.forecast_ready === false ? 'Evaluation results are loaded, but the deployment models are not installed on this server.' : 'Models are trained on all data and evaluated on a held-out test period.') : 'No model has been trained for this society yet.'}
          </p>
          <p className="mt-2 flex flex-wrap gap-2 text-sm">
            {society.has_model && <Badge tone="good">Evaluated on held-out data</Badge>}
            <Link to="/forecasting" className="text-accent underline">Accuracy and model comparison</Link>
          </p>
        </Card>
      </div>
    </div>
  );
}

export function SocietyOverviewPage() {
  return (
    <>
      <SocietyHeader title="Society overview" description="Total electricity demand of the community, the next-24-hour forecast, cost estimate and alerts." />
      <SocietyGate>{(s) => <Overview society={s} />}</SocietyGate>
    </>
  );
}
