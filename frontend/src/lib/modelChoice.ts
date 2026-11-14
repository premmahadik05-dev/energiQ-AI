import type { HorizonResult } from '../api/societyTypes';
import { fmtNum, modelLabel } from './format';

/**
 * Plain-language statement of which model is deployed at one horizon and how it did on the held-out test period.
 *
 * Three different facts are involved and they must not be mixed up:
 *  - the DEPLOYED model is chosen by cross-validated error on earlier data only (`best_overall_by_cv`, baselines included);
 *  - `mae_improvement_vs_best_baseline_pct` / `learned_beats_best_baseline` compare the best LEARNED model by
 *    cross-validation (`best_model_by_cv`) with the best simple baseline, on the test period;
 *  - the deployed model can therefore be the baseline itself (cross-validation preferred it), or a learned model that
 *    later did worse than the baseline on the test period. Both happen in the bundled communities and are reported as measured.
 */
export function describeModelChoice(r: HorizonResult): string {
  const learned = modelLabel(r.best_model_by_cv);
  const baseline = modelLabel(r.best_baseline_by_cv);
  const pct = r.mae_improvement_vs_best_baseline_pct;
  const compare = `On the held-out test period the best learned model by cross-validation (${learned}) had a mean absolute error ${fmtNum(Math.abs(pct), 1)}% ${pct >= 0 ? 'lower' : 'higher'} than the best simple baseline (${baseline}).`;
  if (r.best_overall_is_baseline) {
    return `A simple baseline (${modelLabel(r.best_overall_by_cv)}) is the selected model at this horizon: cross-validation on earlier data did not favour any learned model, and the system deploys what that evidence supports. ${compare}`;
  }
  if (r.learned_beats_best_baseline) {
    return `The selected model (${modelLabel(r.best_overall_by_cv)}) has a test error ${fmtNum(pct, 1)}% lower than the best simple baseline (${baseline}).`;
  }
  return `The selected model (${modelLabel(r.best_overall_by_cv)}) was chosen by cross-validation, but on the held-out test period it did not beat the best simple baseline (${baseline}): its error was ${fmtNum(Math.abs(pct), 1)}% higher. The test period is never used to change the choice, so this is reported as measured.`;
}
