import { useId, useMemo, useState, type PointerEvent } from 'react';
import { fmtInt } from '../../lib/format';
import { niceScale } from '../../lib/scale';
import { LOGIN_DEMAND as D } from './loginDemand';

/**
 * The figure on the sign-in page: one real week of measured demand and the forecast made 24 hours earlier, drawn as plain SVG so the sign-in page
 * does not load the charting library. The numbers come from scripts/make_login_chart_data.py (the Fox community's held-out test period); nothing
 * here is invented or smoothed. Hovering shows the two values for an hour; the SVG as a whole is described to assistive technology in words.
 */
const W = 560;
const H = 216;
const M = { top: 22, right: 12, bottom: 26, left: 46 };
const PW = W - M.left - M.right;
const PH = H - M.top - M.bottom;
const N = D.measured.length;
const START = Date.parse(`${D.weekStart}T00:00:00Z`);
const dayLabel = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', timeZone: 'UTC' });
const stampLabel = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' });
const weekLabel = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const at = (i: number) => new Date(START + i * 3_600_000);

const path = (values: readonly number[], x: (i: number) => number, y: (v: number) => number) => values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');

export function DemandForecastFigure() {
  const titleId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const geo = useMemo(() => {
    const all = [...D.measured, ...D.forecast];
    const scale = niceScale(Math.min(...all), Math.max(...all), 4, false);
    const x = (i: number) => M.left + (i / (N - 1)) * PW;
    const y = (v: number) => M.top + (1 - (v - scale.min) / (scale.max - scale.min)) * PH;
    let peak = 0;
    D.measured.forEach((v, i) => {
      if (v > (D.measured[peak] ?? 0)) peak = i;
    });
    return { scale, x, y, peak, measuredPath: path(D.measured, x, y), forecastPath: path(D.forecast, x, y) };
  }, []);

  const { scale, x, y, peak } = geo;
  const peakValue = D.measured[peak] ?? 0;
  const summary = `Line chart of one week of hourly electricity demand of the ${D.society}, in kilowatts. The measured demand peaks at ${fmtInt(peakValue)} kW on ${dayLabel.format(at(peak))}. The forecast made 24 hours ahead follows it closely: mean absolute error ${D.maeKw} kW, ${D.mapePct} percent.`;

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    setHover(Math.max(0, Math.min(N - 1, Math.round(((px - M.left) / PW) * (N - 1)))));
  };
  const hx = hover === null ? 0 : x(hover);
  const tipLeft = Math.max(20, Math.min(80, (hx / W) * 100));

  return (
    <figure className="m-0 rounded-lg border border-line bg-surface p-4 shadow-card sm:p-5" aria-labelledby={titleId}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <figcaption id={titleId} className="text-[14px] font-semibold text-ink">
            Society demand: measured and 24 h-ahead forecast
          </figcaption>
          <p className="mt-0.5 text-[12.5px] text-muted">Hourly demand in kW, a typical week of the held-out test period</p>
        </div>
        <ul className="flex items-center gap-4 text-[12.5px] text-ink-2" aria-label="Chart legend">
          <li className="flex items-center gap-2">
            <svg width="18" height="10" viewBox="0 0 18 10" aria-hidden="true">
              <line x1="1" y1="5" x2="17" y2="5" stroke="var(--blue)" strokeWidth="2.25" strokeLinecap="round" />
            </svg>
            Measured
          </li>
          <li className="flex items-center gap-2">
            <svg width="18" height="10" viewBox="0 0 18 10" aria-hidden="true">
              <line x1="1" y1="5" x2="17" y2="5" stroke="var(--brand)" strokeWidth="2.25" strokeDasharray="4 3" strokeLinecap="round" />
            </svg>
            Forecast
          </li>
        </ul>
      </div>

      <div className="relative mt-3">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary} className="block h-auto w-full touch-pan-y" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {scale.ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth="1" />
              <text x={M.left - 8} y={y(t)} textAnchor="end" dominantBaseline="central" fontSize="11" fill="var(--axis-text)">
                {fmtInt(t)}
              </text>
            </g>
          ))}
          {Array.from({ length: 7 }, (_, d) => (
            <g key={d}>
              {d > 0 && <line x1={x(d * 24)} x2={x(d * 24)} y1={M.top} y2={M.top + PH} stroke="var(--grid)" strokeWidth="1" strokeDasharray="2 4" />}
              <text x={x(d * 24 + 12)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--axis-text)">
                {dayLabel.format(at(d * 24))}
              </text>
            </g>
          ))}
          <text x={M.left - 8} y={9} textAnchor="end" fontSize="11" fill="var(--axis-text)">
            kW
          </text>

          <path d={`${geo.measuredPath} L${x(N - 1).toFixed(1)} ${y(scale.min)} L${x(0).toFixed(1)} ${y(scale.min)} Z`} fill="var(--blue)" fillOpacity="0.06" />
          <path d={geo.measuredPath} fill="none" stroke="var(--blue)" strokeWidth="2" strokeLinejoin="round" />
          <path d={geo.forecastPath} fill="none" stroke="var(--brand)" strokeWidth="2" strokeDasharray="5 4" strokeLinejoin="round" />

          <g aria-hidden="true">
            <circle cx={x(peak)} cy={y(peakValue)} r="4" fill="var(--surface)" stroke="var(--blue)" strokeWidth="2" />
            <text x={x(peak)} y={y(peakValue) - 10} textAnchor={x(peak) > W - 90 ? 'end' : 'middle'} fontSize="11" fontWeight="600" fill="var(--ink)">
              Peak {fmtInt(peakValue)} kW
            </text>
            {hover !== null && (
              <g>
                <line x1={hx} x2={hx} y1={M.top} y2={M.top + PH} stroke="var(--muted)" strokeWidth="1" />
                <circle cx={hx} cy={y(D.measured[hover] ?? 0)} r="4" fill="var(--blue)" stroke="var(--surface)" strokeWidth="2" />
                <circle cx={hx} cy={y(D.forecast[hover] ?? 0)} r="4" fill="var(--brand)" stroke="var(--surface)" strokeWidth="2" />
              </g>
            )}
          </g>
        </svg>
        {hover !== null && (
          <div aria-hidden="true" className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-md border border-line-strong bg-surface px-3 py-2 text-[12px] shadow-lg" style={{ left: `${tipLeft}%` }}>
            <p className="num mb-1 font-semibold text-ink">{stampLabel.format(at(hover))}</p>
            <p className="flex items-center justify-between gap-4 text-ink-2">
              <span>Measured</span>
              <span className="num font-medium text-ink">{fmtInt(D.measured[hover])} kW</span>
            </p>
            <p className="flex items-center justify-between gap-4 text-ink-2">
              <span>Forecast</span>
              <span className="num font-medium text-ink">{fmtInt(D.forecast[hover])} kW</span>
            </p>
          </div>
        )}
      </div>

      <p className="mt-3 text-[12px] leading-relaxed text-muted">
        Real data: {D.society}, week of {weekLabel.format(at(0))} (median error of {D.candidateWeeks} test weeks). {D.model.charAt(0).toUpperCase() + D.model.slice(1)} forecast made {D.horizonHours} hours ahead, mean absolute error {D.maeKw} kW ({D.mapePct} %). {D.source}.
      </p>
    </figure>
  );
}
