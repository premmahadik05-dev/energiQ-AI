"""Experiment pipeline: model selection by time-series CV, refit, test scoring.

Protocol (identical for the benchmark and for user datasets):

1. Build leak-free features per horizon (ml_engine.features.builder).
2. Select hyperparameters by expanding-window CV (benchmark) or by one validation
   block (user datasets). Training rows for any evaluation block are those whose
   TARGET time is strictly before the block starts.
3. Refit each chosen configuration on all rows with target before the test period.
4. Score every model, baselines included, on the same test rows.
5. Save tuned models as versioned artifacts with full metadata.

The test period is touched exactly once, in step 4.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml_engine.evaluation.metrics import evaluate
from ml_engine.evaluation.splits import Fold, SplitPlan, block_mask, train_mask
from ml_engine.features.builder import FeatureConfig, Supervised, common_eval_mask, make_features, make_supervised
from ml_engine.forecasting.models import RF_GRID, XGB_GRID, TreeModel, baselines
from ml_engine.forecasting.registry import save_tree_model, series_hash

FAMILY_GRIDS = {"random_forest": RF_GRID, "xgboost": XGB_GRID}


@dataclass
class ExperimentConfig:
    plan: SplitPlan
    horizons: tuple[int, ...] = (1, 6, 24)
    families: tuple[str, ...] = ("random_forest", "xgboost")
    grids: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: dict(FAMILY_GRIDS))
    seed: int = 42
    feature_cfg: FeatureConfig = field(default_factory=FeatureConfig)
    models_dir: Path | None = None
    log: Callable[[str], None] = print


def fit_before(sup: Supervised, family: str, params: dict, cutoff: pd.Timestamp, seed: int) -> TreeModel:
    """Fit using only rows whose target time is before ``cutoff``."""
    tr = train_mask(sup.target_time, cutoff) & sup.y.notna().to_numpy()
    return TreeModel(family, params, seed=seed).fit(sup.X[tr], sup.y[tr])


def _key(family: str, i: int) -> str:
    return f"{family}#{i}"


def _eval_block(model, sup: Supervised, evalm: np.ndarray, start, end) -> tuple[dict, np.ndarray]:
    blk = block_mask(sup.target_time, start, end) & evalm
    pred = model.predict(sup.X[blk])
    return evaluate(sup.y[blk], pred), blk


def run_experiment(series: pd.Series, cfg: ExperimentConfig) -> tuple[dict, dict[int, pd.DataFrame]]:
    plan = cfg.plan
    folds = list(plan.folds) or [Fold("validation", plan.val_start, plan.test_start - pd.Timedelta(hours=1))]
    data_hash = series_hash(series)
    results: dict[str, Any] = {}
    predictions: dict[int, pd.DataFrame] = {}
    for h in cfg.horizons:
        t0 = time.time()
        sup = make_supervised(series, h, cfg.feature_cfg)
        evalm = common_eval_mask(sup)
        res: dict[str, Any] = {"cv": {}, "chosen": {}, "test": {}}

        # ---- model selection on folds / validation block ----
        for base in baselines():
            res["cv"][base.name] = {}
            for f in folds:
                m, blk = _eval_block(base, sup, evalm, f.test_start, f.test_end)
                res["cv"][base.name][f.name] = m
        for fam in cfg.families:
            for i, params in enumerate(cfg.grids[fam]):
                key = _key(fam, i)
                res["cv"][key] = {}
                for f in folds:
                    model = fit_before(sup, fam, params, f.test_start, cfg.seed)
                    res["cv"][key][f.name], _ = _eval_block(model, sup, evalm, f.test_start, f.test_end)
        for per_fold in res["cv"].values():
            maes = [m["mae"] for m in per_fold.values() if m["mae"] is not None]
            per_fold["_summary"] = {"mean_fold_mae": float(np.mean(maes)) if maes else None, "folds": len(maes)}
        for fam in cfg.families:
            best = min(
                range(len(cfg.grids[fam])),
                key=lambda i: res["cv"][_key(fam, i)]["_summary"]["mean_fold_mae"],
            )
            res["chosen"][fam] = {"index": best, "params": cfg.grids[fam][best],
                                  "cv_mean_fold_mae": res["cv"][_key(fam, best)]["_summary"]["mean_fold_mae"]}

        # ---- final refit on everything before the test period, score once ----
        test_blk = block_mask(sup.target_time, plan.test_start, plan.test_end)
        scored = test_blk & evalm
        if scored.sum() == 0:
            raise ValueError("No test rows can be scored; the dataset is too short or too sparse")
        pred_df = pd.DataFrame({"y_true": sup.y[scored].to_numpy()}, index=sup.target_time[scored])
        pred_df.index.name = "target_time"
        for base in baselines():
            p = base.predict(sup.X[scored])
            pred_df[base.name] = p
            res["test"][base.name] = evaluate(pred_df["y_true"], p)
        for fam in cfg.families:
            params = res["chosen"][fam]["params"]
            model = fit_before(sup, fam, params, plan.test_start, cfg.seed)
            p = model.predict(sup.X[scored])
            pred_df[fam] = p
            res["test"][fam] = evaluate(pred_df["y_true"], p)
            if cfg.models_dir is not None:
                n_train = int((train_mask(sup.target_time, plan.test_start) & sup.y.notna().to_numpy()).sum())
                meta = {
                    "horizon": h,
                    "data_hash": data_hash,
                    "train_rows": n_train,
                    "train_target_before": str(plan.test_start),
                    "test_period": [str(plan.test_start), str(plan.test_end)],
                    "cv_mean_fold_mae": res["chosen"][fam]["cv_mean_fold_mae"],
                    "cv_folds": len(folds),
                    "test_metrics": res["test"][fam],
                    "unit": "kW",
                }
                res["chosen"][fam]["model_id"] = save_tree_model(cfg.models_dir, model, meta)
        res["counts"] = {
            "test_target_hours": int(test_blk.sum()),
            "test_rows_scored": int(scored.sum()),
            "test_rows_excluded": int(test_blk.sum() - scored.sum()),
        }
        results[str(h)] = res
        predictions[h] = pred_df
        cfg.log(f"[h={h}] done in {time.time() - t0:.0f}s | " + " | ".join(
            f"{k}: MAE {v['mae']:.4f}" for k, v in res["test"].items()))
    return results, predictions


def forecast_from_origin(model, series: pd.Series, horizon: int, origin: pd.Timestamp | None = None,
                         cfg: FeatureConfig = FeatureConfig()) -> dict:
    """Point forecast for ``origin + horizon`` using only data up to ``origin``."""
    X = make_features(series, horizon, cfg)
    origin = pd.Timestamp(origin) if origin is not None else X.index[-1]
    if origin not in X.index:
        raise ValueError(f"origin {origin} is outside the series")
    row = X.loc[[origin]]
    return {
        "origin": origin,
        "target_time": origin + pd.Timedelta(hours=horizon),
        "prediction_kw": float(model.predict(row)[0]),
        "origin_value_missing": bool(np.isnan(row["lag_0"].iloc[0])),
    }
