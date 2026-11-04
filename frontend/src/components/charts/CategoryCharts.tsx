import { useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import { fmtNum } from '../../lib/format';
import { niceScale } from '../../lib/scale';
import { LegendSwatch } from './ChartFrame';

export interface Series {
  key: string;
  name: string;
  color: string;
  dashed?: boolean;
}

type Row = Record<string, string | number | null>;

function CatTooltip({ active, payload, label, unit, digits, series }: TooltipProps<number, string> & { unit: string; digits: number; series: Series[] }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="num mb-1 font-semibold text-ink">{String(label)}</p>
      {payload.map((p) => {
        const s = series.find((x) => x.key === p.dataKey);
        return (
          <p key={String(p.dataKey)} className="flex items-center gap-2 text-ink-2">
            <LegendSwatch kind={s?.dashed ? 'dash' : 'bar'} color={s?.color ?? 'var(--s1)'} />
            <span>{s?.name ?? String(p.name)}</span>
            <span className="num ml-auto pl-3 font-medium text-ink">
              {typeof p.value === 'number' ? fmtNum(p.value, digits) : '–'} {unit}
            </span>
          </p>
        );
      })}
    </div>
  );
}

function valueScale(data: Row[], series: Series[]) {
  let lo = 0;
  let hi = 0;
  for (const row of data) {
    for (const s of series) {
      const v = row[s.key];
      if (typeof v === 'number' && Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
  }
  return niceScale(lo, hi);
}

export function LinesChart({ data, xKey, series, unit, height = 260, digits = 2, step = false, xLabel, xTickFormatter }: { data: Row[]; xKey: string; series: Series[]; unit: string; height?: number; digits?: number; step?: boolean; xLabel?: string; xTickFormatter?: (v: string | number) => string }) {
  const scale = valueScale(data, series);
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 16, bottom: xLabel ? 18 : 4, left: 0 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey={xKey} stroke="var(--axis)" tickLine={false} tickFormatter={xTickFormatter} label={xLabel ? { value: xLabel, position: 'insideBottom', offset: -10 } : undefined} />
          <YAxis domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} width={52} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} label={{ value: unit, angle: -90, position: 'insideLeft', offset: 14, style: { textAnchor: 'middle' } }} />
          <Tooltip content={<CatTooltip unit={unit} digits={digits} series={series} />} cursor={{ stroke: 'var(--muted)' }} isAnimationActive={false} />
          {series.map((s) => (
            <Line key={s.key} dataKey={s.key} name={s.name} type={step ? 'stepAfter' : 'monotone'} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '6 4' : undefined} dot={false} activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }} isAnimationActive={false} connectNulls={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BarsChart({ data, xKey, series, unit, height = 260, digits = 2, horizontal = false, xLabel, yWidth }: { data: Row[]; xKey: string; series: Series[]; unit: string; height?: number; digits?: number; horizontal?: boolean; xLabel?: string; yWidth?: number }) {
  const scale = valueScale(data, series);
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 10, right: 16, bottom: xLabel ? 18 : 4, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} unit={unit === '%' ? '%' : undefined} />
              <YAxis type="category" dataKey={xKey} stroke="var(--axis)" tickLine={false} width={yWidth ?? 170} />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} stroke="var(--axis)" tickLine={false} label={xLabel ? { value: xLabel, position: 'insideBottom', offset: -10 } : undefined} />
              <YAxis domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} width={56} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} label={{ value: unit, angle: -90, position: 'insideLeft', offset: 14, style: { textAnchor: 'middle' } }} />
            </>
          )}
          <Tooltip content={<CatTooltip unit={unit} digits={digits} series={series} />} cursor={{ fill: 'var(--sunken)', opacity: 0.7 }} isAnimationActive={false} />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface WaterfallStep {
  name: string;
  lo: number;
  hi: number;
  /** signed contribution for deltas, absolute value for base/total */
  value: number;
  kind: 'base' | 'raises' | 'lowers' | 'total';
}

const KIND_COLOR: Record<WaterfallStep['kind'], string> = { base: 'var(--s1)', total: 'var(--s1)', raises: 'var(--s2)', lowers: 'var(--s3)' };
export const WATERFALL_COLORS = KIND_COLOR;

export function WaterfallChart({ steps, unit, digits = 2 }: { steps: WaterfallStep[]; unit: string; height?: number; digits?: number }) {
  const [narrow, setNarrow] = useState(false);
  const data = steps.map((s) => ({ ...s, range: [s.lo, s.hi] as [number, number] }));
  const scale = niceScale(Math.min(...steps.map((s) => s.lo)), Math.max(...steps.map((s) => s.hi)), 4);
  const height = steps.length * 38 + 64;
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer onResize={(w) => setNarrow(w < 520)}>
        <BarChart layout="vertical" data={data} margin={{ top: 6, right: narrow ? 44 : 56, bottom: 18, left: 0 }} barCategoryGap="22%">
          <CartesianGrid horizontal={false} />
          <XAxis type="number" domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} label={{ value: unit, position: 'insideBottomRight', offset: -4 }} />
          <YAxis type="category" dataKey="name" stroke="var(--axis)" tickLine={false} width={narrow ? 112 : 190} tick={{ fontSize: 12 }} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ fill: 'var(--sunken)', opacity: 0.7 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as (WaterfallStep & { range: [number, number] }) | undefined;
              if (!active || !p) return null;
              return (
                <div className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs shadow-lg">
                  <p className="mb-1 font-semibold text-ink">{p.name}</p>
                  <p className="num text-ink-2">
                    {p.kind === 'base' || p.kind === 'total' ? 'Value' : p.kind === 'raises' ? 'Raises forecast by' : 'Lowers forecast by'}{' '}
                    <span className="font-medium text-ink">
                      {p.kind === 'raises' ? '+' : p.kind === 'lowers' ? '−' : ''}
                      {fmtNum(Math.abs(p.value), digits)} {unit}
                    </span>
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="range" isAnimationActive={false} radius={[3, 3, 3, 3]} maxBarSize={26}>
            {data.map((d) => (
              <Cell key={d.name} fill={KIND_COLOR[d.kind]} />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              content={(props) => {
                const { x, y, width, height: h, index } = props as { x?: number; y?: number; width?: number; height?: number; index?: number };
                const d = index !== undefined ? data[index] : undefined;
                if (!d || x == null || y == null || width == null || h == null) return null;
                const txt = d.kind === 'raises' ? `+${fmtNum(d.value, digits)}` : d.kind === 'lowers' ? `−${fmtNum(Math.abs(d.value), digits)}` : fmtNum(d.value, digits);
                return (
                  <text x={x + width + 6} y={y + h / 2} dominantBaseline="central" fill="var(--ink)" fontSize={11} fontWeight={600}>
                    {txt}
                  </text>
                );
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
