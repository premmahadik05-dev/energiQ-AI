import { societyApi } from '../../api/endpoints';
import type { SocietyDetail, SocietySummary } from '../../api/societyTypes';
import { SocietyGate, SocietyHeader } from '../../components/society/common';
import { Card, DescriptionList } from '../../components/ui/basic';
import { ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtPct } from '../../lib/format';
import { formatTs } from '../../lib/time';

const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '–' : String(v));

function Card_({ d }: { d: SocietyDetail }) {
  const src = (d.data_card.source ?? {}) as Record<string, unknown>;
  const upload = src.kind === 'upload';
  const rule = (d.data_card.rule ?? {}) as Record<string, unknown>;
  const clean = (d.data_card.cleaning ?? {}) as Record<string, unknown>;
  const t = d.data_card.cleaning_totals ?? {};
  const rep = (d.data_card.cleaning_report ?? {}) as Record<string, unknown>;
  const url = upload ? '' : d.source_url;
  const readings = t.readings ?? 0;
  return (
    <Card title="Data card" description="Where the data come from and exactly what was done to them.">
      <DescriptionList
        columns={2}
        items={[
          { label: 'Dataset', value: d.source_name },
          { label: 'Official URL', value: url ? <a className="text-accent underline" href={url} target="_blank" rel="noreferrer">{url}</a> : 'Uploaded by an administrator' },
          { label: 'Publisher', value: str(src.publisher ?? 'The uploading administrator') },
          { label: 'Reference', value: src.paper ? `${str(src.paper)}${src.paper_doi ? ` doi:${str(src.paper_doi)}` : ''}` : '–' },
          { label: 'Licence', value: d.license },
          { label: 'Downloaded / loaded', value: str(d.data_card.downloaded_at ?? (src.kind === 'upload' ? 'At upload time' : '–')) },
          { label: 'Buildings (meters) kept', value: `${d.buildings} real whole-building meters${d.data_card.excluded_count ? `; ${d.data_card.excluded_count} more were rejected by the validity rule` : ''}` },
          { label: 'Period and frequency', value: `${formatTs(d.start)} to ${formatTs(d.end)}, hourly (${fmtInt(d.hours)} hours)` },
          { label: 'Units', value: 'Energy: kWh per hour per meter. Demand: kW, the hourly mean (numerically equal to that hour\'s kWh). Peak demand is the highest hourly mean.' },
          { label: 'Time convention', value: str(src.timestamp_convention ?? `${d.timezone}; stored as given`) },
          { label: 'Missing values', value: `${fmtInt(d.hours - d.valid_hours)} of ${fmtInt(d.hours)} hours (${fmtPct((100 * (d.hours - d.valid_hours)) / d.hours, 2)}) have no valid society total; they stay missing and are never filled or interpolated` },
          { label: 'Aggregation method', value: 'Society kWh = sum of the retained building meters at each hour, defined only when every retained meter has a valid reading at that hour.' },
        ]}
      />
      <h3 className="mt-5 text-sm font-semibold">Preprocessing applied to every meter</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
        <li>Duplicate timestamps dropped (first kept) and the series reindexed to a complete hourly grid; missing hours stay missing.</li>
        <li>Negative readings are invalid (whole-building consumption cannot be negative).</li>
        <li>{clean.zero_is_invalid ? 'Exact zero readings are invalid for building meters: occupied buildings do not draw exactly 0 kWh, and the source has long dead-meter stretches.' : 'Zero readings are kept as valid.'}</li>
        <li>Stuck sensor: the same non-zero value for {str(clean.stuck_min_hours)} or more hours is invalid.</li>
        <li>Spike: a value above {str(clean.spike_factor)} times the meter's own {fmtPct(Number(clean.spike_quantile) * 100, 1)} percentile is invalid.</li>
        <li>
          Meter kept only if at least {fmtPct(Number(rule.min_meter_valid_share) * 100, 0)} of its hours are valid
          {rule.min_buildings ? `, and a society needs at least ${str(rule.min_buildings)} meters` : ''}
          {rule.min_society_valid_share ? ` with a valid total in at least ${fmtPct(Number(rule.min_society_valid_share) * 100, 0)} of hours` : ''}.
        </li>
      </ul>
      {readings > 0 && (
        <>
          <h3 className="mt-5 text-sm font-semibold">What the rules removed (retained meters, all hours)</h3>
          <DescriptionList
            columns={3}
            items={[
              { label: 'Readings examined', value: fmtInt(readings) },
              { label: 'Missing in the source', value: fmtInt(t.missing_in_source) },
              { label: 'Negative', value: fmtInt(t.negative) },
              { label: 'Zero (long runs / short)', value: `${fmtInt(t.zero_long_runs)} / ${fmtInt(t.zero_short)}` },
              { label: 'Stuck sensor', value: fmtInt(t.stuck_sensor) },
              { label: 'Spike', value: fmtInt(t.spike) },
              { label: 'Valid readings left', value: `${fmtInt(t.valid_out)} (${fmtPct((100 * (t.valid_out ?? 0)) / readings, 2)})` },
            ]}
          />
        </>
      )}
      {typeof rep.society_valid_share === 'number' && <p className="mt-3 text-xs text-ink-2">Society total valid in {fmtPct(rep.society_valid_share * 100, 2)} of hours.</p>}
    </Card>
  );
}

function Detail({ society }: { society: SocietySummary }) {
  const d = useApi(`soc-detail:${society.id}`, (signal) => societyApi.detail(society.id, { signal }));
  if (d.error) return <ErrorState error={d.error} onRetry={d.reload} />;
  if (d.loading && !d.data) return <Loading label="Loading data card" />;
  if (!d.data) return null;
  const src = d.data.data_card.source as Record<string, unknown> | undefined;
  return (
    <div className="space-y-6">
      <Notice title="What these societies are">
        {src?.kind === 'upload'
          ? 'This society was built from meter readings uploaded by an administrator.'
          : 'No open dataset of a registered housing society with per-building meters was available, so each society here is a research-based representative community: the real residential-use buildings (student residence halls) of one site of a public building-energy dataset, summed per hour. It is not a registered housing society. The data are real measurements; the grouping is the project\'s construction.'}
        {src?.note ? ` ${str(src.note)}` : ''}
      </Notice>
      <Card_ d={d.data} />
    </div>
  );
}

export function DataSourcesPage() {
  return (
    <>
      <SocietyHeader title="Data sources" description="Provenance, licence, cleaning rules and aggregation method of the selected society's data." />
      <SocietyGate>{(s) => <Detail society={s} />}</SocietyGate>
    </>
  );
}
