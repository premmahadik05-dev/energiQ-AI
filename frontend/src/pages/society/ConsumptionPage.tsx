import { useMemo, useState } from 'react';
import { societyApi } from '../../api/endpoints';
import type { Resolution, SocietySummary } from '../../api/societyTypes';
import { DataBasisNote, RangePresets, SocietyGate, SocietyHeader } from '../../components/society/common';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Card, KpiTile } from '../../components/ui/basic';
import { ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { Segmented } from '../../components/ui/forms';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtKw, fmtKwh } from '../../lib/format';
import { consumptionRows, presetRange, type RangePreset } from '../../lib/societySeries';
import { formatDate } from '../../lib/time';

type Metric = 'energy_kwh' | 'avg_kw' | 'peak_kw';
const RES_LABEL: Record<Resolution, string> = { hourly: 'Hourly', daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly' };
const METRIC_LABEL: Record<Metric, { name: string; unit: string }> = {
  energy_kwh: { name: 'Energy', unit: 'kWh' },
  avg_kw: { name: 'Average demand', unit: 'kW' },
  peak_kw: { name: 'Peak hourly demand', unit: 'kW' },
};

function Consumption({ society }: { society: SocietySummary }) {
  const [resolution, setResolution] = useState<Resolution>('daily');
  const [metric, setMetric] = useState<Metric>('energy_kwh');
  const [preset, setPreset] = useState<RangePreset>('90d');
  // hourly requests are limited to 120 days by the API, so the long presets are not offered for them
  const effectivePreset: RangePreset = resolution === 'hourly' && (preset === '1y' || preset === 'all') ? '90d' : preset;
  const range = presetRange(effectivePreset, society.start, society.end);
  const m: Metric = resolution === 'hourly' && metric === 'energy_kwh' ? 'avg_kw' : metric;
  const data = useApi(`soc-cons:${society.id}:${resolution}:${range.start}:${range.end}`, (signal) => societyApi.consumption(society.id, { resolution, ...range }, { signal }));

  const points = useMemo(() => data.data?.points ?? [], [data.data]);
  const rows = useMemo(() => consumptionRows(points, m), [points, m]);
  const totals = useMemo(() => {
    const valid = points.filter((p) => p.energy_kwh != null);
    return {
      energy: valid.reduce((a, p) => a + (p.energy_kwh ?? 0), 0),
      peak: Math.max(0, ...points.map((p) => p.peak_kw ?? 0)),
      incomplete: points.filter((p) => !p.complete).length,
    };
  }, [points]);
  const label = METRIC_LABEL[m];

  return (
    <div className="space-y-6">
      <DataBasisNote society={society} />
      <Card
        title="Total society consumption"
        description="Sum of every building meter per hour. Hours where any meter has no valid reading are gaps, never zero or an estimate."
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <Segmented label="Resolution" value={resolution} onChange={setResolution} options={(Object.keys(RES_LABEL) as Resolution[]).map((r) => ({ value: r, label: RES_LABEL[r] }))} />
            {resolution !== 'hourly' && (
              <Segmented label="Measure" value={metric} onChange={setMetric} options={(Object.keys(METRIC_LABEL) as Metric[]).map((k) => ({ value: k, label: METRIC_LABEL[k].name }))} />
            )}
          </div>
        }
      >
        <div className="mb-4">
          <RangePresets society={society} value={effectivePreset} onChange={(p) => setPreset(p)} presets={resolution === 'hourly' ? ['7d', '30d', '90d'] : ['30d', '90d', '1y', 'all']} />
        </div>
        {data.error ? (
          <ErrorState error={data.error} onRetry={data.reload} />
        ) : data.loading && !data.data ? (
          <Loading label="Loading consumption" />
        ) : (
          <>
            <SeriesChart
              title={`${RES_LABEL[resolution]} ${label.name.toLowerCase()} of the society`}
              summary={`${RES_LABEL[resolution]} ${label.name.toLowerCase()} in ${label.unit} from ${formatDate(data.data?.start)} to ${formatDate(data.data?.end)}: ${points.length} points. A table view lists every value.`}
              rows={rows}
              lines={[{ key: 'v', name: `${label.name} (${label.unit})`, color: 'var(--s1)' }]}
              unit={label.unit}
              digits={resolution === 'hourly' ? 0 : 0}
              style={resolution === 'hourly' ? 'hour' : 'day'}
              height={320}
            />
            {totals.incomplete > 0 && resolution !== 'hourly' && (
              <p className="mt-3 text-xs text-ink-2">
                {totals.incomplete} of {points.length} {resolution === 'weekly' ? 'weeks' : resolution === 'monthly' ? 'months' : 'days'} contain hours without valid data (or are partial at the edge of the range), so their energy is a lower bound.
              </p>
            )}
          </>
        )}
      </Card>
      {data.data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <KpiTile label="Energy in range" value={fmtKwh(totals.energy, 0)} sub="Valid hours only" />
          <KpiTile label="Highest hourly demand in range" value={fmtKw(totals.peak, 0)} />
          <KpiTile label="Points shown" value={fmtInt(points.length)} sub={`${RES_LABEL[resolution].toLowerCase()} resolution`} />
        </div>
      )}
      {resolution === 'weekly' && <Notice>Weeks start on Monday. Energy (kWh) is summed over the valid hours of each week; demand (kW) is the hourly mean.</Notice>}
    </div>
  );
}

export function ConsumptionPage() {
  return (
    <>
      <SocietyHeader title="Consumption" description="Total electricity use of the society over time at hourly, daily, weekly and monthly resolution." />
      <SocietyGate>{(s) => <Consumption society={s} />}</SocietyGate>
    </>
  );
}
