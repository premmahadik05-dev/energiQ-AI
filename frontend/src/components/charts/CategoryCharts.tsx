import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import { fmtNum } from '../../lib/format';
import { niceScale } from '../../lib/scale';
import { ChartSurface, LegendSwatch } from './ChartFrame';

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

function valueScale(data: Row[], series: Series[], includeZero = true) {
  let lo = includeZero ? 0 : Number.POSITIVE_INFINITY;
  let hi = includeZero ? 0 : Number.NEGATIVE_INFINITY;
  for (const row of data) {
    for (const s of series) {
      const v = row[s.key];
      if (typeof v === 'number' && Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return niceScale(0, 1);
  return niceScale(lo, hi, 5, includeZero);
}

export function LinesChart({ data, xKey, series, unit, height = 260, digits = 2, step = false, xLabel, xTickFormatter, xInterval, zero = false }: { data: Row[]; xKey: string; series: Series[]; unit: string; height?: number; digits?: number; step?: boolean; xLabel?: string; xInterval?: number | 'preserveStartEnd' | 'equidistantPreserveStart'; /** start the value axis at zero (for quantities where the size of the level matters, such as a price) */ zero?: boolean; xTickFormatter?: (v: string | number) => string }) {
  const scale = valueScale(data, series, zero);
  return (
    <ChartSurface style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 28, right: 16, bottom: xLabel ? 18 : 4, left: 0 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey={xKey} stroke="var(--axis)" tickLine={false} interval={xInterval} tickFormatter={xTickFormatter} label={xLabel ? { value: xLabel, position: 'insideBottom', offset: -10 } : undefined} />
          <YAxis domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} width={52} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} label={{ value: unit, position: 'top', offset: 12, style: { textAnchor: 'middle' } }} />
          <Tooltip content={<CatTooltip unit={unit} digits={digits} series={series} />} cursor={{ stroke: 'var(--muted)' }} isAnimationActive={false} />
          {series.map((s) => (
            <Line key={s.key} dataKey={s.key} name={s.name} type={step ? 'stepAfter' : 'monotone'} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '6 4' : undefined} dot={false} activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }} isAnimationActive={false} connectNulls={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartSurface>
  );
}

export function BarsChart({ data, xKey, series, unit, height = 260, digits = 2, horizontal = false, xLabel, yWidth, colorOf }: { data: Row[]; xKey: string; series: Series[]; unit: string; height?: number; digits?: number; horizontal?: boolean; xLabel?: string; yWidth?: number; /** colour a single bar differently (for example the selected model); return undefined for the series colour */ colorOf?: (row: Row) => string | undefined }) {
  const scale = valueScale(data, series);
  // horizontal bars put the value axis along the bottom: title it with the unit (a % already shows on the ticks)
  const axisLabel = horizontal ? (xLabel ?? (unit === '%' ? undefined : unit)) : xLabel;
  return (
    <ChartSurface style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: horizontal ? 10 : 28, right: 16, bottom: axisLabel ? 18 : 4, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} unit={unit === '%' ? '%' : undefined} label={axisLabel ? { value: axisLabel, position: 'insideBottom', offset: -10 } : undefined} />
              <YAxis type="category" dataKey={xKey} stroke="var(--axis)" tickLine={false} width={yWidth ?? 170} />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} stroke="var(--axis)" tickLine={false} label={axisLabel ? { value: axisLabel, position: 'insideBottom', offset: -10 } : undefined} />
              <YAxis domain={[scale.min, scale.max]} ticks={scale.ticks} stroke="var(--axis)" tickLine={false} width={56} tickFormatter={(v: number) => fmtNum(v, scale.decimals)} label={{ value: unit, position: 'top', offset: 12, style: { textAnchor: 'middle' } }} />
            </>
          )}
          <Tooltip content={<CatTooltip unit={unit} digits={digits} series={series} />} cursor={{ fill: 'var(--sunken)', opacity: 0.7 }} isAnimationActive={false} />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false}>
              {colorOf && data.map((row, i) => <Cell key={i} fill={colorOf(row) ?? s.color} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartSurface>
  );
}
