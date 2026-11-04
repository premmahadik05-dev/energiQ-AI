import type { ModelVersion } from '../api/types';
import { fmtNum, fmtPct, modelLabel } from '../lib/format';
import { sortedHorizons } from '../lib/models';
import { formatTs } from '../lib/time';
import { Badge } from './ui/basic';
import { Notice } from './ui/feedback';
import { Table, type Column } from './ui/Table';

interface Row {
  horizon: string;
  model: number | undefined;
  base: number | undefined;
  baseName: string;
  improvement: number;
  rows: number;
  rmse: number | undefined;
  r2: number | undefined;
}

/** Per-horizon hold-out metrics: model against the best baseline, as stored with the model version. */
export function HoldoutTable({ model, detailed = false }: { model: ModelVersion; detailed?: boolean }) {
  const rows: Row[] = sortedHorizons(model.evaluation).map(([h, e]) => ({
    horizon: h,
    model: e.metrics.xgboost?.mae,
    base: e.metrics[e.best_baseline]?.mae,
    baseName: e.best_baseline,
    improvement: e.mae_improvement_vs_best_baseline_pct,
    rows: e.rows_scored,
    rmse: e.metrics.xgboost?.rmse,
    r2: e.metrics.xgboost?.r2,
  }));
  const columns: Column<Row>[] = [
    { key: 'h', header: 'Horizon', render: (r) => `${r.horizon} h ahead` },
    { key: 'm', header: 'Model MAE (kW)', align: 'right', render: (r) => fmtNum(r.model, 3) },
    { key: 'b', header: 'Best baseline MAE (kW)', align: 'right', render: (r) => fmtNum(r.base, 3) },
    { key: 'bn', header: 'Best baseline', render: (r) => modelLabel(r.baseName) },
    {
      key: 'i',
      header: 'Improvement vs best baseline',
      align: 'right',
      render: (r) => (
        <span className={r.improvement >= 0 ? 'text-good' : 'text-bad'}>
          <span aria-hidden="true">{r.improvement >= 0 ? '▼ ' : '▲ '}</span>
          {fmtPct(Math.abs(r.improvement))} {r.improvement >= 0 ? 'lower error' : 'higher error'}
        </span>
      ),
    },
    ...(detailed
      ? ([
          { key: 'rmse', header: 'Model RMSE (kW)', align: 'right', render: (r) => fmtNum(r.rmse, 3) },
          { key: 'r2', header: 'Model R²', align: 'right', render: (r) => fmtNum(r.r2, 3) },
          { key: 'n', header: 'Hours scored', align: 'right', render: (r) => fmtNum(r.rows, 0) },
        ] as Column<Row>[])
      : []),
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => r.horizon} caption="Hold-out error by forecast horizon" empty="This model version has no stored hold-out evaluation." />;
}

/** The sentence every forecast and model view must carry: what the accuracy figures are and are not. */
export function HoldoutNote({ model }: { model: ModelVersion }) {
  const ev = model.evaluation;
  return (
    <Notice tone="info" title="How accurate is this model?">
      Accuracy figures are measured on a hold-out period the model was not fitted on
      {ev.holdout_start && ev.holdout_end ? <> ({formatTs(ev.holdout_start)} to {formatTs(ev.holdout_end)})</> : null}, at selected horizons only (
      {Object.keys(ev.horizons ?? {}).join(', ')} h). They describe past performance on this dataset and are not a guarantee for future hours.
      {ev.caveat ? <span className="mt-1 block font-medium">{ev.caveat}</span> : null}
    </Notice>
  );
}

export function ModelBadge({ model }: { model: ModelVersion }) {
  return model.is_active ? <Badge tone="good">active</Badge> : <Badge>inactive</Badge>;
}

