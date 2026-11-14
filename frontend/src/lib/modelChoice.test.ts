import { describe, expect, it } from 'vitest';
import type { HorizonResult } from '../api/societyTypes';
import { describeModelChoice } from './modelChoice';

// The three situations below occur in the bundled communities (values copied from their evaluation.json, 24 h horizon).
const base = { horizon: 24, test: {}, chosen: {}, chosen_baselines: {}, best_baseline_by_test: 'naive' } as const;

describe('describeModelChoice', () => {
  it('learned model selected and better than the baseline (Fox)', () => {
    const r = { ...base, best_overall_by_cv: 'random_forest', best_overall_is_baseline: false, best_model_by_cv: 'random_forest', best_baseline_by_cv: 'naive', mae_improvement_vs_best_baseline_pct: 20.68, learned_beats_best_baseline: true } as unknown as HorizonResult;
    const t = describeModelChoice(r);
    expect(t).toContain('selected model (Random forest)');
    expect(t).toContain('20.7% lower');
    expect(t).not.toContain('higher');
  });

  it('the baseline is the selected model although a learned model scored better on the test period (Eagle)', () => {
    const r = { ...base, best_overall_by_cv: 'naive', best_overall_is_baseline: true, best_model_by_cv: 'random_forest', best_baseline_by_cv: 'naive', mae_improvement_vs_best_baseline_pct: 8.19, learned_beats_best_baseline: true } as unknown as HorizonResult;
    const t = describeModelChoice(r);
    // must NOT claim that the selected model beat the baseline: the selected model IS the baseline
    expect(t.startsWith('A simple baseline (Naive (last value)) is the selected model')).toBe(true);
    expect(t).toContain('cross-validation on earlier data did not favour any learned model');
    expect(t).toContain('best learned model by cross-validation (Random forest)');
    expect(t).toContain('8.2% lower');
  });

  it('learned model selected by cross-validation but worse than the baseline on the test period (Peacock)', () => {
    const r = { ...base, best_overall_by_cv: 'random_forest', best_overall_is_baseline: false, best_model_by_cv: 'random_forest', best_baseline_by_cv: 'naive', mae_improvement_vs_best_baseline_pct: -6.47, learned_beats_best_baseline: false } as unknown as HorizonResult;
    const t = describeModelChoice(r);
    expect(t).toContain('did not beat the best simple baseline');
    expect(t).toContain('6.5% higher');
    expect(t).toContain('never used to change the choice');
    expect(t).not.toContain('is the selected model at this horizon'); // a learned model is not described as "a simple baseline"
  });
});
