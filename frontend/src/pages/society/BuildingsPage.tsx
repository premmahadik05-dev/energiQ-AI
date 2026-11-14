import { useMemo, useState } from 'react';
import { societyApi } from '../../api/endpoints';
import type { BuildingRow, SocietySummary } from '../../api/societyTypes';
import { BarsChart } from '../../components/charts/CategoryCharts';
import { RangePresets, SocietyGate, SocietyHeader } from '../../components/society/common';
import { useRange } from '../../components/society/useRange';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Card } from '../../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { Segmented, SelectField } from '../../components/ui/forms';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtNum, fmtPct } from '../../lib/format';
import { consumptionRows } from '../../lib/societySeries';
import { formatDate } from '../../lib/time';

type Measure = 'energy_kwh' | 'kwh_per_sqm' | 'peak_kw' | 'avg_kw';
const MEASURES: Record<Measure, { label: string; unit: string }> = {
  energy_kwh: { label: 'Energy', unit: 'kWh' },
  kwh_per_sqm: { label: 'Energy per m²', unit: 'kWh/m²' },
  avg_kw: { label: 'Average demand', unit: 'kW' },
  peak_kw: { label: 'Peak demand', unit: 'kW' },
};

function Buildings({ society }: { society: SocietySummary }) {
  const { preset, setPreset, range, key } = useRange(society, '1y');
  const [measure, setMeasure] = useState<Measure>('energy_kwh');
  const [selected, setSelected] = useState<number | null>(null);
  const data = useApi(`soc-b:${key}`, (signal) => societyApi.buildings(society.id, range, { signal }));
  const rows = useMemo(() => data.data?.buildings ?? [], [data.data]);
  const sel = rows.find((b) => b.id === selected) ?? rows[0] ?? null;
  const daily = useApi(sel ? `soc-bd:${society.id}:${sel.id}:${key}` : null, (signal) => societyApi.buildingConsumption(society.id, (sel as BuildingRow).id, { resolution: 'daily', ...range }, { signal }));
  const monthly = useApi(`soc-bm:${society.id}`, (signal) => societyApi.buildingsMonthly(society.id, { signal }));
  const isAdmin = rows.some((b) => b.source_id !== undefined);

  const chartRows = useMemo(
    () =>
      [...rows]
        .filter((b) => b[measure] != null)
        .sort((a, b) => (b[measure] ?? 0) - (a[measure] ?? 0))
        .map((b) => ({ building: b.code, value: Number((b[measure] ?? 0).toFixed(1)) })),
    [rows, measure],
  );
  const columns: Column<BuildingRow>[] = [
    { key: 'c', header: 'Building', render: (b) => <button type="button" className="font-medium text-accent underline" onClick={() => setSelected(b.id)} aria-label={`Show ${b.code} daily demand`}>{b.code}</button> },
    ...(isAdmin ? [{ key: 'src', header: 'Source id (admin)', render: (b: BuildingRow) => b.source_id ?? '' }] : []),
    { key: 'u', header: 'Use', render: (b) => b.sub_use || '–' },
    { key: 'a', header: 'Area (m²)', align: 'right', render: (b) => fmtInt(b.floor_area_sqm) },
    { key: 'e', header: 'Energy (kWh)', align: 'right', render: (b) => fmtInt(b.energy_kwh) },
    { key: 's', header: 'Share', align: 'right', render: (b) => fmtPct(b.share_pct, 1) },
    { key: 'i', header: 'kWh/m²', align: 'right', render: (b) => fmtNum(b.kwh_per_sqm, 1) },
    { key: 'p', header: 'Peak (kW)', align: 'right', render: (b) => fmtNum(b.peak_kw, 0) },
    { key: 'v', header: 'Valid hours', align: 'right', render: (b) => (b.expected_hours ? fmtPct((100 * b.valid_hours) / b.expected_hours, 1) : '–') },
  ];
  const monthlyRows = useMemo(() => {
    const b = monthly.data?.buildings.find((x) => x.code === sel?.code);
    return (b && monthly.data ? monthly.data.months.map((m, i) => ({ month: m.slice(0, 7), energy: b.energy_kwh[i] ?? null, valid: b.valid_hours[i] ?? 0 })) : []).map((r) => ({ month: r.month, energy: r.energy == null ? null : Number(r.energy.toFixed(0)) }));
  }, [monthly.data, sel]);

  return (
    <div className="space-y-6">
      <Notice>Each building is a real whole-building electricity meter of the dataset. Codes are pseudonymous labels; the dataset's own identifiers are visible to administrators only. Floor areas, where shown, come from the dataset's metadata.</Notice>
      <Card
        title="Building comparison"
        description="The same period for every building."
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <Segmented label="Measure" value={measure} onChange={setMeasure} options={(Object.keys(MEASURES) as Measure[]).map((k) => ({ value: k, label: MEASURES[k].label }))} />
          </div>
        }
      >
        <div className="mb-4">
          <RangePresets society={society} value={preset} onChange={(p) => setPreset(p)} presets={['90d', '1y', 'all']} />
        </div>
        {data.error ? (
          <ErrorState error={data.error} onRetry={data.reload} />
        ) : data.loading && !data.data ? (
          <Loading label="Loading buildings" />
        ) : rows.length === 0 ? (
          <EmptyState title="No buildings in this society" />
        ) : (
          <>
            <BarsChart data={chartRows} xKey="building" series={[{ key: 'value', name: MEASURES[measure].label, color: 'var(--s1)' }]} unit={MEASURES[measure].unit} horizontal yWidth={90} height={Math.max(240, rows.length * 34)} digits={measure === 'kwh_per_sqm' ? 1 : 0} />
            <p className="mt-2 text-xs text-ink-2">
              {formatDate(data.data?.start)} to {formatDate(data.data?.end)}. Energy counts only hours with a valid reading for that building, so buildings with more missing hours show lower totals; see the valid-hours column.
            </p>
          </>
        )}
      </Card>
      {rows.length > 0 && (
        <Card title="All buildings" padded={false}>
          <Table columns={columns} rows={rows} rowKey={(b) => b.id} caption="Buildings of the society with energy, share, intensity and peak demand" dense />
        </Card>
      )}
      {sel && (
        <Card
          title={`${sel.code}: daily energy`}
          actions={
            <SelectField label="Building" value={sel.id} onChange={(e) => setSelected(Number(e.target.value))}>
              {rows.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.code}
                </option>
              ))}
            </SelectField>
          }
        >
          {daily.error ? (
            <ErrorState error={daily.error} onRetry={daily.reload} />
          ) : daily.loading && !daily.data ? (
            <Loading label="Loading building demand" />
          ) : (
            <SeriesChart
              title={`${sel.code} daily energy`}
              summary={`Daily energy in kWh of building ${sel.code} from ${formatDate(range.start)} to ${formatDate(range.end)}. A table lists every value.`}
              rows={consumptionRows(daily.data?.points ?? [], 'energy_kwh')}
              lines={[{ key: 'v', name: 'Daily energy (kWh)', color: 'var(--s2)' }]}
              unit="kWh"
              digits={0}
              style="day"
              height={260}
            />
          )}
          {monthlyRows.length > 0 && (
            <div className="mt-6">
              <p className="mb-2 text-sm font-semibold">Monthly energy of {sel.code}</p>
              <BarsChart data={monthlyRows} xKey="month" series={[{ key: 'energy', name: 'Monthly energy', color: 'var(--s2)' }]} unit="kWh" height={240} digits={0} />
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export function BuildingsPage() {
  return (
    <>
      <SocietyHeader title="Buildings" description="Compare the buildings of the society: energy, share of the total, intensity per floor area and peak demand." />
      <SocietyGate>{(s) => <Buildings society={s} />}</SocietyGate>
    </>
  );
}
