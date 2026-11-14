import { useMemo } from 'react';
import { fmtNum } from '../../lib/format';
import { formatMs } from '../../lib/time';
import { ChartFrame, type LegendItem } from '../charts/ChartFrame';
import { TimeSeriesChart, type TsLine, type TsMarker, type TsRef, type TsRow } from '../charts/TimeSeriesChart';
import { Table, type Column } from '../ui/Table';

const MAX_TABLE_ROWS = 1500;

/**
 * A time-series chart with its legend, plain-language summary and table view, for the society pages.
 * Lines break at null samples; history and forecast are drawn as different line styles so they cannot be confused.
 */
export function SeriesChart({
  title, description, summary, rows, lines, band, markers, refLines, unit = 'kW', height = 300, zoomable = true, digits = 1, style = 'hour', footer, onMarkerClick,
}: {
  title: string;
  description?: string;
  summary: string;
  rows: TsRow[];
  lines: TsLine[];
  band?: { key: string; name: string };
  markers?: TsMarker[];
  refLines?: TsRef[];
  unit?: string;
  height?: number;
  zoomable?: boolean;
  digits?: number;
  /** "day" shows dates only in the table */
  style?: 'hour' | 'day';
  footer?: string;
  onMarkerClick?: (id: number | string) => void;
}) {
  const legend = useMemo<LegendItem[]>(
    () => [...lines.map((l) => ({ label: l.name, color: l.color, kind: (l.dashed ? 'dash' : 'line') as LegendItem['kind'] })), ...(band ? [{ label: band.name, color: 'var(--s2)', kind: 'area' as const }] : [])],
    [lines, band],
  );
  const columns = useMemo<Column<TsRow>[]>(
    () => [
      { key: 't', header: style === 'day' ? 'Date' : 'Time', render: (r) => formatMs(r.t, style === 'day' ? 'date' : 'full') },
      ...lines.map((l) => ({ key: l.key, header: `${l.name} (${unit})`, align: 'right' as const, render: (r: TsRow) => (typeof r[l.key] === 'number' ? fmtNum(r[l.key] as number, digits) : '–') })),
      ...(band
        ? [{ key: band.key, header: `${band.name} (${unit})`, align: 'right' as const, render: (r: TsRow) => { const b = r[band.key]; return Array.isArray(b) ? `${fmtNum(b[0], digits)} to ${fmtNum(b[1], digits)}` : '–'; } }]
        : []),
    ],
    [lines, band, unit, digits, style],
  );
  const tableRows = useMemo(() => rows.filter((r) => lines.some((l) => typeof r[l.key] === 'number') || (band && Array.isArray(r[band.key]))).slice(0, MAX_TABLE_ROWS), [rows, lines, band]);
  return (
    <ChartFrame
      title={title}
      description={description}
      summary={summary}
      legend={legend}
      footer={footer}
      table={<Table columns={columns} rows={tableRows} rowKey={(r) => r.t} caption={`${title}: values`} dense empty="No data in this range." />}
    >
      <TimeSeriesChart data={rows} lines={lines} band={band} markers={markers} refLines={refLines} unit={unit} height={height} zoomable={zoomable} digits={digits} onMarkerClick={onMarkerClick} />
    </ChartFrame>
  );
}
