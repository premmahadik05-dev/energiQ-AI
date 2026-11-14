import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { societyApi } from '../../api/endpoints';
import type { CommunityRow } from '../../api/societyTypes';
import { BarsChart } from '../../components/charts/CategoryCharts';
import { Badge, Card, PageHeader } from '../../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { Table, type Column } from '../../components/ui/Table';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtNum, modelLabel } from '../../lib/format';
import { useSociety } from '../../state/SocietyContext';

/** "Bull" for the bundled key "bull"; uploaded communities keep their own name. */
const shortName = (c: CommunityRow): string => (c.key.length <= 12 ? c.key.charAt(0).toUpperCase() + c.key.slice(1) : c.name);

type Metric = (c: CommunityRow) => number | null;

function RankChart({ rows, activeId, metric, name, unit, axis, digits, height }: { rows: CommunityRow[]; activeId: number | null; metric: Metric; name: string; unit: string; axis: string; digits: number; height?: number }) {
  const data = rows
    .map((c) => ({ community: shortName(c), value: metric(c), selected: c.id === activeId ? 1 : 0 }))
    .filter((d): d is { community: string; value: number; selected: number } => d.value != null && Number.isFinite(d.value))
    .sort((a, b) => b.value - a.value)
    .map((d) => ({ ...d, value: Number(d.value.toFixed(digits + 1)) }));
  if (data.length === 0) return <EmptyState title="No data">None of the communities has this figure.</EmptyState>;
  return (
    <>
      <BarsChart
        data={data}
        xKey="community"
        series={[{ key: 'value', name, color: 'var(--s1)' }]}
        colorOf={(row) => (row.selected === 1 ? 'var(--s1)' : 'var(--s1-muted)')}
        unit={unit}
        xLabel={axis}
        horizontal
        yWidth={92}
        digits={digits}
        height={height ?? Math.max(200, data.length * 40 + 30)}
      />
      {data.length < rows.length && <p className="mt-1 text-xs text-ink-2">{rows.length - data.length} of {rows.length} communities have no value for this figure (no floor area was recorded) and are left out.</p>}
    </>
  );
}

export function CompareCommunitiesPage() {
  const { active, setActiveId } = useSociety();
  const navigate = useNavigate();
  const cmp = useApi('soc-compare', (signal) => societyApi.compare({ signal }));
  const rows = useMemo(() => cmp.data?.communities ?? [], [cmp.data]);

  const columns: Column<CommunityRow>[] = [
    {
      key: 'n',
      header: 'Community',
      render: (c) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{shortName(c)}</span>
          {c.id === active?.id && <Badge tone="good">Selected</Badge>}
        </span>
      ),
    },
    { key: 'b', header: 'Buildings', align: 'right', render: (c) => fmtInt(c.buildings) },
    { key: 'a', header: 'Floor area (m²)', align: 'right', render: (c) => (c.floor_area_sqm != null ? fmtInt(c.floor_area_sqm) : '–') },
    { key: 'p', header: 'Period', className: 'whitespace-nowrap', render: (c) => `${c.period_start.slice(0, 7)} to ${c.period_end.slice(0, 7)}` },
    { key: 'e', header: 'Energy (GWh)', align: 'right', render: (c) => fmtNum(c.energy_kwh / 1e6, 1) },
    { key: 'k', header: 'Average (kW)', align: 'right', render: (c) => fmtNum(c.avg_kw, 0) },
    { key: 'pk', header: 'Peak (kW)', align: 'right', render: (c) => fmtNum(c.peak_kw, 0) },
    { key: 'lf', header: 'Load factor', align: 'right', render: (c) => fmtNum(c.load_factor, 2) },
    { key: 'ey', header: 'kWh/m² per year', align: 'right', render: (c) => fmtNum(c.kwh_per_sqm_year, 1) },
    { key: 'm', header: '24 h error (% of average)', align: 'right', render: (c) => (c.accuracy_24h?.mae_pct_of_average != null ? `${fmtNum(c.accuracy_24h.mae_pct_of_average, 1)}%` : '–') },
    { key: 'g', header: 'Gain over baseline', align: 'right', render: (c) => (c.accuracy_24h?.gain_vs_baseline_pct != null ? `${fmtNum(c.accuracy_24h.gain_vs_baseline_pct, 1)}%` : '–') },
    { key: 'mo', header: '24 h model', render: (c) => (c.accuracy_24h ? modelLabel(c.accuracy_24h.model) : 'Not evaluated') },
    {
      key: 'o',
      header: 'Open',
      render: (c) => (
        <button
          type="button"
          className="btn-ghost text-xs"
          aria-label={`Open ${shortName(c)} in the society overview`}
          onClick={() => {
            setActiveId(c.id);
            navigate('/');
          }}
        >
          Open
        </button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Compare communities" description="Size-independent figures for every community in the database, computed from the same measured hourly data used everywhere else in EnergiQ." />
      {cmp.error ? (
        <ErrorState error={cmp.error} onRetry={cmp.reload} />
      ) : cmp.loading && !cmp.data ? (
        <Loading label="Comparing communities" />
      ) : rows.length < 2 ? (
        <EmptyState title="Nothing to compare yet">{rows.length === 0 ? 'No community has finished importing.' : 'Only one community is available.'} Import the bundled communities from the society admin page to compare several.</EmptyState>
      ) : (
        <div className="space-y-6">
          <Notice title="Read these figures with care">
            {(cmp.data?.notes ?? []).join(' ')} The bundled communities are research datasets, not registered housing societies, and they cover different years and climates.
          </Notice>
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Card title="Energy use per floor area" description="Annual energy per square metre of floor area (kWh per m² per year). The selected community is the darker bar.">
              <RankChart rows={rows} activeId={active?.id ?? null} metric={(c) => c.kwh_per_sqm_year} name="Energy per m² per year" unit="kWh/m²/yr" axis="Energy per floor area (kWh per m² per year)" digits={1} />
            </Card>
            <Card title="Load factor" description="Average demand divided by peak demand. Nearer 1 means a flatter load; lower means a few peak hours set the size of the supply.">
              <RankChart rows={rows} activeId={active?.id ?? null} metric={(c) => c.load_factor} name="Load factor" unit="ratio" axis="Load factor (average demand ÷ peak demand)" digits={2} />
            </Card>
            <Card title="Peak demand per floor area" description="Highest hourly demand in watts per square metre of floor area (W per m²).">
              <RankChart rows={rows} activeId={active?.id ?? null} metric={(c) => c.peak_w_per_sqm} name="Peak demand per m²" unit="W/m²" axis="Peak hourly demand per floor area (W per m²)" digits={1} />
            </Card>
            <Card title="24-hour forecast error" description="Mean absolute error on the held-out test period as a share of the community's average demand (%). Lower is better.">
              <RankChart rows={rows} activeId={active?.id ?? null} metric={(c) => c.accuracy_24h?.mae_pct_of_average ?? null} name="24 h forecast error" unit="%" axis="Mean absolute error (% of average demand)" digits={1} />
            </Card>
          </div>
          <Card title="All figures" padded={false}>
            <Table columns={columns} rows={rows} rowKey={(c) => c.id} caption="Side-by-side figures for every community" dense rowClassName={(c) => (c.id === active?.id ? 'bg-accent-soft' : '')} />
          </Card>
          <p className="text-xs text-ink-2">
            Forecast errors are the held-out test results saved when each community&apos;s models were trained; nothing on this page is re-fitted or tuned. The 24 h model is whichever method cross-validation selected for that community, and a simple baseline can win.
          </p>
        </div>
      )}
    </>
  );
}
