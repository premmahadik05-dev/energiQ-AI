import type { Recommendation } from '../../api/types';
import { evidenceLabel, evidenceValue } from '../../lib/evidence';
import { fmtMoney } from '../../lib/format';
import { Badge } from '../ui/basic';

const tone = (p: Recommendation['priority']) => (p === 'high' ? 'bad' : p === 'medium' ? 'warn' : 'neutral');

/** A recommendation with its measured evidence, any scenario (clearly an estimate) and caveats. */
export function RecommendationCard({ r }: { r: Recommendation }) {
  return (
    <li className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone(r.priority)}>{r.priority} priority</Badge>
        <Badge>{r.category}</Badge>
      </div>
      <h3 className="mt-2 text-base">{r.title}</h3>
      <p className="mt-1 text-sm">{r.explanation}</p>
      {Object.keys(r.evidence).length > 0 && (
        <>
          <h4 className="mt-3 text-xs font-semibold text-ink-2">Evidence from the data</h4>
          <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            {Object.entries(r.evidence).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-2">{evidenceLabel(k)}</dt>
                <dd className="num text-right">{evidenceValue(v)}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {r.scenario && (
        <div className="mt-3 rounded border border-line-strong bg-sunken p-3">
          <p className="flex items-center gap-2 text-xs font-semibold text-ink-2">
            Scenario <Badge tone="warn">estimate, not a measured saving</Badge>
          </p>
          <p className="mt-1 text-sm">{r.scenario.assumption}</p>
          <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            {Object.entries(r.scenario)
              .filter(([k]) => k !== 'assumption' && k !== 'currency')
              .map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-2">Estimated {evidenceLabel(k).toLowerCase()}</dt>
                  <dd className="num text-right font-medium">{k.includes('saving') && typeof v === 'number' ? fmtMoney(v, r.scenario?.currency ?? '') : evidenceValue(v)}</dd>
                </div>
              ))}
          </dl>
        </div>
      )}
      {r.caveats.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-ink-2">
          {r.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
