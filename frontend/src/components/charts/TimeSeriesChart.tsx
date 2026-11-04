import { useCallback, useMemo, useState } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import { formatMs, niceTimeTicks } from '../../lib/time';
import { fmtNum } from '../../lib/format';
import { niceScale } from '../../lib/scale';
import { LegendSwatch, type LegendKind } from './ChartFrame';

export type TsRow = { t: number } & Record<string, number | null | [number, number]>;

export interface TsLine {
  key: string;
  name: string;
  color: string;
  dashed?: boolean;
  /** draw small dots (sparse series such as a 24-point forecast) */
  dots?: boolean;
}

export interface TsMarker {
  id: number | string;
  t: number;
  v: number;
  shape: Extract<LegendKind, 'triangleUp' | 'triangleDown' | 'diamond' | 'circle'>;
  color: string;
  label: string;
  selected?: boolean;
}

export interface TsRef {
  t: number;
  label: string;
}

interface Props {
  data: TsRow[];
  lines: TsLine[];
  band?: { key: string; name: string };
  markers?: TsMarker[];
  refLines?: TsRef[];
  unit?: string;
  height?: number;
  zoomable?: boolean;
  digits?: number;
  onMarkerClick?: (id: number | string) => void;
}

function MarkerShape(props: { cx?: number; cy?: number; payload?: TsMarker }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload) return <g />;
  const r = payload.selected ? 8 : 6;
  const common = { fill: payload.color, stroke: 'var(--ink)', strokeWidth: payload.selected ? 2.5 : 1.5 };
  let shape;
  if (payload.shape === 'triangleUp') shape = <path d={`M${cx} ${cy - r} L${cx + r} ${cy + r * 0.8} H${cx - r} Z`} {...common} />;
  else if (payload.shape === 'triangleDown') shape = <path d={`M${cx} ${cy + r} L${cx + r} ${cy - r * 0.8} H${cx - r} Z`} {...common} />;
  else if (payload.shape === 'diamond') shape = <path d={`M${cx} ${cy - r} L${cx + r} ${cy} L${cx} ${cy + r} L${cx - r} ${cy} Z`} {...common} />;
  else shape = <circle cx={cx} cy={cy} r={r * 0.85} {...common} />;
  return (
    <g style={{ cursor: 'pointer' }}>
      <title>{payload.label}</title>
      <circle cx={cx} cy={cy} r={13} fill="transparent" />
      {shape}
    </g>
  );
}

function TsTooltip({ active, payload, label, lines, band, unit, digits }: TooltipProps<number, string> & { lines: TsLine[]; band?: { key: string; name: string }; unit: string; digits: number }) {
  if (!active || !payload || payload.length === 0 || typeof label !== 'number') return null;
  const byKey = new Map(payload.map((p) => [String(p.dataKey), p]));
  const rows: { key: string; name: string; color: string; text: string; kind: LegendKind }[] = [];
  for (const l of lines) {
    const p = byKey.get(l.key);
    if (p && typeof p.value === 'number') rows.push({ key: l.key, name: l.name, color: l.color, text: `${fmtNum(p.value, digits)} ${unit}`, kind: l.dashed ? 'dash' : 'line' });
  }
  if (band) {
    const p = byKey.get(band.key);
    const v = p?.value as unknown;
    if (Array.isArray(v) && v.length === 2) rows.push({ key: band.key, name: band.name, color: 'var(--s2)', text: `${fmtNum(Number(v[0]), digits)} to ${fmtNum(Number(v[1]), digits)} ${unit}`, kind: 'area' });
  }
  return (
    <div className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="num mb-1 font-semibold text-ink">{formatMs(label)}</p>
      {rows.length === 0 && <p className="text-ink-2">No reading (gap)</p>}
      {rows.map((r) => (
        <p key={r.key} className="flex items-center gap-2 text-ink-2">
          <LegendSwatch kind={r.kind} color={r.color} />
          <span>{r.name}</span>
          <span className="num ml-auto pl-3 font-medium text-ink">{r.text}</span>
        </p>
      ))}
    </div>
  );
}

/**
 * Time-series line chart for naive local timestamps (x = ms "as if UTC", see lib/time).
 * Lines break at null samples (gaps stay gaps). Optional uncertainty band, event markers and reference lines.
 * Zoom: drag on the chart, or use the buttons (keyboard accessible).
 */
export function TimeSeriesChart({ data, lines, band, markers = [], refLines = [], unit = 'kW', height = 300, zoomable = false, digits = 2, onMarkerClick }: Props) {
  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const [drag, setDrag] = useState<{ from: number; to: number | null } | null>(null);

  const full = useMemo<[number, number]>(() => {
    if (data.length === 0) return [0, 1];
    return [(data[0] as TsRow).t, (data[data.length - 1] as TsRow).t];
  }, [data]);
  const [lo, hi] = zoom ?? full;
  const visible = useMemo(() => (zoom ? data.filter((d) => d.t >= lo && d.t <= hi) : data), [data, zoom, lo, hi]);
  const visibleMarkers = useMemo(() => markers.filter((m) => m.t >= lo && m.t <= hi), [markers, lo, hi]);
  const span = Math.max(hi - lo, 1);
  const [width, setWidth] = useState(800);
  const axis = useMemo(() => niceTimeTicks(lo, hi, Math.max(3, Math.min(7, Math.floor(width / 85)))), [lo, hi, width]);

  const setClamped = useCallback(
    (a: number, b: number) => {
      const minSpan = 6 * 3600_000;
      let l = Math.max(full[0], Math.min(a, b));
      let r = Math.min(full[1], Math.max(a, b));
      if (r - l < minSpan) r = Math.min(full[1], l + minSpan);
      if (r - l < minSpan) l = Math.max(full[0], r - minSpan);
      setZoom(l <= full[0] && r >= full[1] ? null : [l, r]);
    },
    [full],
  );

  const zoomBy = (factor: number) => {
    const c = (lo + hi) / 2;
    const half = (span * factor) / 2;
    setClamped(c - half, c + half);
  };
  const pan = (dir: -1 | 1) => {
    const shift = span * 0.5 * dir;
    let l = lo + shift;
    let r = hi + shift;
    if (l < full[0]) {
      r += full[0] - l;
      l = full[0];
    }
    if (r > full[1]) {
      l -= r - full[1];
      r = full[1];
    }
    setClamped(l, r);
  };

  const yScale = useMemo(() => {
    let lowest = 0;
    let highest = 0;
    const take = (v: unknown) => {
      if (typeof v === 'number' && Number.isFinite(v)) {
        lowest = Math.min(lowest, v);
        highest = Math.max(highest, v);
      }
    };
    for (const row of visible) {
      for (const l of lines) take(row[l.key]);
      if (band) {
        const b = row[band.key];
        if (Array.isArray(b)) b.forEach(take);
      }
    }
    for (const m of visibleMarkers) take(m.v);
    return niceScale(lowest, highest);
  }, [visible, visibleMarkers, lines, band]);
  const canZoom = zoomable && data.length > 2;

  return (
    <div>
      {canZoom && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-secondary !min-h-[30px] !px-2 text-xs" onClick={() => zoomBy(0.5)} disabled={span <= 6 * 3600_000}>
            Zoom in
          </button>
          <button type="button" className="btn-secondary !min-h-[30px] !px-2 text-xs" onClick={() => zoomBy(2)} disabled={!zoom}>
            Zoom out
          </button>
          <button type="button" className="btn-secondary !min-h-[30px] !px-2 text-xs" onClick={() => pan(-1)} disabled={!zoom || lo <= full[0]}>
            Earlier
          </button>
          <button type="button" className="btn-secondary !min-h-[30px] !px-2 text-xs" onClick={() => pan(1)} disabled={!zoom || hi >= full[1]}>
            Later
          </button>
          <button type="button" className="btn-ghost !min-h-[30px] !px-2 text-xs" onClick={() => setZoom(null)} disabled={!zoom}>
            Reset zoom
          </button>
          <span className="text-xs text-muted">{zoom ? `Showing ${formatMs(lo)} to ${formatMs(hi)}` : 'Drag across the chart to zoom'}</span>
        </div>
      )}
      <div style={{ width: '100%', height, userSelect: drag ? 'none' : undefined }}>
        <ResponsiveContainer width="100%" height="100%" onResize={(w) => setWidth(Math.round(w))}>
          <ComposedChart
            data={visible}
            margin={{ top: 10, right: 16, bottom: 4, left: 0 }}
            onMouseDown={canZoom ? (e) => typeof e?.activeLabel === 'number' && setDrag({ from: e.activeLabel, to: null }) : undefined}
            onMouseMove={canZoom ? (e) => drag && typeof e?.activeLabel === 'number' && setDrag({ from: drag.from, to: e.activeLabel }) : undefined}
            onMouseUp={
              canZoom
                ? () => {
                    if (drag && drag.to !== null && Math.abs(drag.to - drag.from) > 0) setClamped(drag.from, drag.to);
                    setDrag(null);
                  }
                : undefined
            }
            onMouseLeave={canZoom ? () => setDrag(null) : undefined}
          >
            <CartesianGrid strokeDasharray="0" vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={[lo, hi]} allowDataOverflow ticks={axis.ticks} tickFormatter={axis.format} stroke="var(--axis)" tickLine={false} interval={0} />
            <YAxis domain={[yScale.min, yScale.max]} ticks={yScale.ticks} stroke="var(--axis)" tickLine={false} width={52} tickFormatter={(v: number) => fmtNum(v, yScale.decimals)} label={{ value: unit, angle: -90, position: 'insideLeft', offset: 14, style: { textAnchor: 'middle' } }} />
            <Tooltip content={<TsTooltip lines={lines} band={band} unit={unit} digits={digits} />} cursor={{ stroke: 'var(--muted)', strokeWidth: 1 }} isAnimationActive={false} />
            {band && <Area dataKey={band.key} name={band.name} type="monotone" stroke="none" fill="var(--s2)" fillOpacity={0.18} isAnimationActive={false} activeDot={false} connectNulls={false} />}
            {lines.map((l) => (
              <Line key={l.key} dataKey={l.key} name={l.name} type="linear" stroke={l.color} strokeWidth={2} strokeDasharray={l.dashed ? '6 4' : undefined} dot={l.dots ? { r: 2.5, fill: l.color, stroke: 'var(--surface)', strokeWidth: 1 } : false} activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} />
            ))}
            {refLines.map((r) => (
              <ReferenceLine key={`${r.t}-${r.label}`} x={r.t} stroke="var(--muted)" strokeDasharray="2 3" label={{ value: r.label, position: 'insideTopRight', fill: 'var(--ink-2)', fontSize: 11 }} />
            ))}
            {visibleMarkers.length > 0 && <Scatter data={visibleMarkers} dataKey="v" xAxisId={0} yAxisId={0} shape={<MarkerShape />} isAnimationActive={false} onClick={(d: unknown) => onMarkerClick?.((d as TsMarker).id)} legendType="none" />}
            {drag && drag.to !== null && <ReferenceArea x1={drag.from} x2={drag.to} fill="var(--accent)" fillOpacity={0.15} stroke="var(--accent)" strokeOpacity={0.5} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
