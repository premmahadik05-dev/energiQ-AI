import { societyApi } from '../../api/endpoints';
import type { SocietySummary } from '../../api/societyTypes';
import { RecommendationCard } from '../../components/society/RecommendationCard';
import { SocietyGate, SocietyHeader, TariffPicker } from '../../components/society/common';
import { Card } from '../../components/ui/basic';
import { EmptyState, ErrorState, Loading, Notice } from '../../components/ui/feedback';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtMoney, fmtNum } from '../../lib/format';
import { formatTs } from '../../lib/time';
import { useJobs } from '../../state/JobsContext';
import { useSociety } from '../../state/SocietyContext';

function Recommendations({ society }: { society: SocietySummary }) {
  const { tariffId } = useSociety();
  const { settledSeq } = useJobs();
  const rec = useApi(`soc-rec:${society.id}:${tariffId}:${settledSeq}`, (signal) => societyApi.recommendations(society.id, tariffId, { signal }));
  const d = rec.data;
  return (
    <div className="space-y-6">
      <Notice title="How to read these">
        Each recommendation comes from a rule applied to the measured data; the evidence it used is listed. Where a cost figure appears it is a stated what-if scenario, not a forecast of savings, because the data cannot show what actually causes the load.
      </Notice>
      <Card title="Recommendations" description="Based on the most recent months of the dataset." actions={<TariffPicker />}>
        {rec.error ? (
          <ErrorState error={rec.error} onRetry={rec.reload} />
        ) : rec.loading && !d ? (
          <Loading label="Analysing demand" />
        ) : d ? (
          <>
            {d.window && (
              <p className="mb-3 text-sm text-ink-2">
                Window analysed: {formatTs(d.window.start)} to {formatTs(d.window.end)} ({fmtNum(d.window.days_covered, 1)} days, {fmtInt(d.window.valid_hours)} valid hours).
                {d.baseline_cost ? ` Estimated energy cost in the window: ${fmtMoney(d.baseline_cost.total_cost, d.baseline_cost.currency, 0)}${d.baseline_cost.is_demo_tariff ? ' (demo tariff)' : ''}.` : ''}
              </p>
            )}
            {d.message && <Notice tone="warn">{d.message}</Notice>}
            {d.recommendations.length === 0 && !d.message ? (
              <EmptyState title="No recommendations apply">None of the rules found something worth flagging in this window.</EmptyState>
            ) : (
              <ul className="grid gap-4 lg:grid-cols-2">
                {d.recommendations.map((r) => (
                  <RecommendationCard key={r.id} r={r} />
                ))}
              </ul>
            )}
          </>
        ) : null}
      </Card>
    </div>
  );
}

export function SocietyRecommendationsPage() {
  return (
    <>
      <SocietyHeader title="Recommendations" description="Evidence-based observations about the society's demand, with no unverified savings claims." />
      <SocietyGate>{(s) => <Recommendations society={s} />}</SocietyGate>
    </>
  );
}
