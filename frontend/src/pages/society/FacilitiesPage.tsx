import { Link } from 'react-router-dom';
import { societyApi } from '../../api/endpoints';
import type { FacilityCategory, SocietySummary } from '../../api/societyTypes';
import { useAuth } from '../../auth/AuthContext';
import { RangePresets, SocietyGate, SocietyHeader } from '../../components/society/common';
import { useRange } from '../../components/society/useRange';
import { SeriesChart } from '../../components/society/SeriesChart';
import { Badge, Card } from '../../components/ui/basic';
import { ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { useApi } from '../../hooks/useApi';
import { fmtKwh } from '../../lib/format';
import { consumptionRows } from '../../lib/societySeries';

function CategoryCard({ c, start, end }: { c: FacilityCategory; start: string; end: string }) {
  const series = c.series ?? [];
  const total = series.reduce((a, p) => a + (p.energy_kwh ?? 0), 0);
  return (
    <Card title={c.label} actions={c.measured ? <Badge tone="good">Measured</Badge> : <Badge tone="neutral">Not measured in this dataset</Badge>}>
      {c.measured ? (
        <>
          <p className="mb-3 text-sm text-ink-2">{fmtKwh(total, 0)} in the selected period from {c.meters.length} meter(s).</p>
          <SeriesChart
            title={`${c.label}: daily energy`}
            summary={`Daily energy of ${c.label.toLowerCase()} from ${start.slice(0, 10)} to ${end.slice(0, 10)}. A table lists every value.`}
            rows={consumptionRows(series, 'energy_kwh')}
            lines={[{ key: 'v', name: 'Daily energy (kWh)', color: 'var(--s3)' }]}
            unit="kWh"
            digits={0}
            style="day"
            height={220}
          />
        </>
      ) : (
        <p className="text-sm text-ink-2">No separate meter exists for this in the data, so no consumption is shown. Nothing is estimated or inferred from the building totals.</p>
      )}
    </Card>
  );
}

function Facilities({ society }: { society: SocietySummary }) {
  const { preset, setPreset, range, key } = useRange(society, '90d');
  const { hasRole } = useAuth();
  const data = useApi(`soc-fac:${key}`, (signal) => societyApi.facilities(society.id, { ...range, resolution: 'daily' }, { signal }));
  if (data.error) return <ErrorState error={data.error} onRetry={data.reload} />;
  if (data.loading && !data.data) return <Loading label="Loading facilities" />;
  const d = data.data;
  if (!d) return null;
  return (
    <div className="space-y-6">
      {!d.available && (
        <Notice tone="warn" title="Facility consumption is unavailable for this society">
          {d.message}{' '}
          {hasRole('admin') && (
            <>
              Administrators can upload a society whose meter file includes lift, pump, street-light or clubhouse meters (mapped on the <Link to="/society-admin" className="underline">society admin page</Link>); those then appear here.
            </>
          )}
        </Notice>
      )}
      {d.available && (
        <div>
          <RangePresets society={society} value={preset} onChange={(p) => setPreset(p)} presets={['30d', '90d', '1y', 'all']} />
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {d.categories.map((c) => (
          <CategoryCard key={c.category} c={c} start={range.start} end={range.end} />
        ))}
      </div>
    </div>
  );
}

export function FacilitiesPage() {
  return (
    <>
      <SocietyHeader title="Facilities" description="Lifts, water pumps, street lighting and the clubhouse: shown only where the data contain a separate meter." />
      <SocietyGate>{(s) => <Facilities society={s} />}</SocietyGate>
    </>
  );
}
