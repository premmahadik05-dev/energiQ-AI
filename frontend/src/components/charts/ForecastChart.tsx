import { useMemo } from 'react';
import type { Forecast, ReadingPoint } from '../../api/types';
import { fmtNum } from '../../lib/format';
import { forecastPeak, forecastRows } from '../../lib/series';
import { formatMs, formatTs, parseNaive } from '../../lib/time';
import { Table, type Column } from '../ui/Table';
import { ChartFrame, type LegendItem } from './ChartFrame';
import { TimeSeriesChart, type TsRow } from './TimeSeriesChart';

type Num = number | null;
interface Row {
  t: number;
  actual: Num;
  forecast: Num;
  lo: Num;
  hi: Num;
}

const num = (v: unknown): Num => (typeof v === 'number' ? v : null);

/** Recent actuals + saved forecast + the uncertainty band, with a table alternative. */
export function ForecastChart({ actual, forecast, title = 'Actual load and forecast', height = 320, zoomable = true }: { actual: ReadingPoint[]; forecast: Forecast | null; title?: string; height?: number; zoomable?: boolean }) {
  const rows = useMemo(() => forecastRows(actual, forecast), [actual, forecast]);
  const originMs = forecast ? parseNaive(forecast.origin) : null;
  const tableRows = useMemo<Row[]>(
    () =>
      rows
        .filter((r) => r.actual != null || r.forecast != null)
        .map((r: TsRow) => {
          const b = r.band;
          return { t: r.t, actual: num(r.actual), forecast: num(r.forecast), lo: Array.isArray(b) ? (b[0] ?? null) : null, hi: Array.isArray(b) ? (b[1] ?? null) : null };
        }),
    [rows],
  );
  const columns: Column<Row>[] = [
    { key: 't', header: 'Time (dataset clock)', render: (r) => formatMs(r.t) },
    { key: 'a', header: 'Actual (kW)', align: 'right', render: (r) => fmtNum(r.actual) },
    ...(forecast
      ? ([
          { key: 'f', header: 'Forecast (kW)', align: 'right', render: (r) => fmtNum(r.forecast) },
          { key: 'lo', header: 'Lower (kW)', align: 'right', render: (r) => fmtNum(r.lo) },
          { key: 'hi', header: 'Upper (kW)', align: 'right', render: (r) => fmtNum(r.hi) },
        ] as Column<Row>[])
      : []),
  ];
  const legend: LegendItem[] = [{ label: 'Actual load (kW)', color: 'var(--s1)', kind: 'line' }];
  if (forecast) {
    legend.push({ label: 'Forecast (kW)', color: 'var(--s2)', kind: 'dash' }, { label: 'Interval band (lower to upper)', color: 'var(--s2)', kind: 'area' });
  }
  const peak = forecast ? forecastPeak(forecast) : null;
  const summary = forecast
    ? `Line chart of hourly load around the forecast origin ${formatTs(forecast.origin)} with a ${forecast.points.length}-hour forecast${peak ? `, peaking at ${fmtNum(peak.kw)} kW at ${formatTs(peak.ts)}` : ''}. A table view has every value.`
    : `Line chart of recent hourly load with ${tableRows.length} readings. A table view has every value.`;

  return (
    <ChartFrame title={title} summary={summary} legend={legend} table={<Table columns={columns} rows={tableRows} rowKey={(r) => r.t} caption={`${title}: values by hour`} dense />}>
      <TimeSeriesChart
        data={rows}
        height={height}
        zoomable={zoomable}
        lines={[
          { key: 'actual', name: 'Actual load', color: 'var(--s1)' },
          ...(forecast ? [{ key: 'forecast', name: 'Forecast', color: 'var(--s2)', dashed: true, dots: true }] : []),
        ]}
        band={forecast ? { key: 'band', name: 'Interval' } : undefined}
        refLines={originMs !== null && forecast ? [{ t: originMs, label: 'Forecast origin' }] : []}
      />
    </ChartFrame>
  );
}
