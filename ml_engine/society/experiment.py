"""Society-level forecasting experiment: models, horizons, cross-validation, one-shot test scoring.

Protocol (same for every society, nothing tuned on the test period)
-------------------------------------------------------------------
* Series: society demand, hourly mean kW (= hourly kWh). Missing hours stay missing.
* Horizons: 1, 6, 12, 24 h and 168 h (7 days), forecast directly (one model per horizon).
* Models: naive baselines (persistence, same hour yesterday, same hour last week), linear regression,
  Random Forest, XGBoost, and XGBoost with observed weather at the forecast origin.
* Model selection: expanding-window cross-validation. Four consecutive 3-month blocks
  (2016-07 .. 2017-06); the training rows for a block are those whose TARGET time is before the block.
* Final: each family's CV-best configuration is refitted on all rows whose target is before
  ``test_start`` and scored once on the test period (2017-07 .. 2017-12). Every model, baselines
  included, is scored on exactly the same rows.
* The empirical 10-90 % residual band used for forecast ranges comes from the out-of-fold CV residuals,
  not from the test period; its coverage on the test period is then reported.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from ml_engine.evaluation.metrics import evaluate, paired_block_bootstrap
from ml_engine.evaluation.splits import Fold, SplitPlan, block_mask, expanding_folds, train_mask
from ml_engine.features.builder import FeatureConfig, Supervised, common_eval_mask, config_for_horizon, make_supervised
from ml_engine.forecasting.models import LINEAR_GRID, XGB_GRID, TreeModel, baselines

HORIZONS = (1, 6, 12, 24, 168)
WEATHER_COLUMNS = ("airTemperature", "dewTemperature", "windSpeed")
LEARNED = ("linear", "random_forest", "xgboost", "xgboost_weather")
# Leaner forests than the household benchmark's RF_GRID: nearly the same accuracy (measured on Fox: 1-3 % MAE difference)
# at 1-3 MB per saved model instead of 6-7 MB, which matters because 25 models are deployed per society.
SOCIETY_RF_GRID: list[dict[str, Any]] = [
    {"n_estimators": 100, "max_depth": 10, "min_samples_leaf": 12, "max_features": 0.5},
    {"n_estimators": 100, "max_depth": 8, "min_samples_leaf": 25, "max_features": 0.5},
]
GRIDS: dict[str, list[dict[str, Any]]] = {"linear": LINEAR_GRID, "random_forest": SOCIETY_RF_GRID, "xgboost": XGB_GRID, "xgboost_weather": XGB_GRID}
MAPE_EPS_KW = 1.0  # society demand is in the hundreds of kW; hours below 1 kW are excluded from MAPE (and counted)


def default_plan(series: pd.Series) -> SplitPlan:
    """Folds 2016-07..2017-06 (4 x 3 months), test 2017-07 to the end of the data."""
    end = series.dropna().index.max()
    return SplitPlan(test_start=pd.Timestamp("2017-07-01 00:00"), test_end=end, val_start=pd.Timestamp("2017-04-01 00:00"),
                     folds=tuple(expanding_folds("2016-07-01 00:00", "2017-06-30 23:00", 3)))


@dataclass
class SocietyExperiment:
    series: pd.Series
    weather: pd.DataFrame | None = None
    plan: SplitPlan | None = None
    horizons: tuple[int, ...] = HORIZONS
    families: tuple[str, ...] = LEARNED
    seed: int = 42
    base_cfg: FeatureConfig = field(default_factory=FeatureConfig)
    log: Callable[[str], None] = print


def _sup_for(exp: SocietyExperiment, h: int, weather: bool) -> Supervised:
    cfg = config_for_horizon(h, exp.base_cfg)
    if weather:
        cfg = replace(cfg, exog_columns=tuple(c for c in WEATHER_COLUMNS if exp.weather is not None and c in exp.weather.columns))
        return make_supervised(exp.series, h, cfg, exog=exp.weather)
    return make_supervised(exp.series, h, cfg)


def fit_before(sup: Supervised, family: str, params: dict, cutoff: pd.Timestamp, seed: int) -> TreeModel:
    fam = "xgboost" if family == "xgboost_weather" else family
    tr = train_mask(sup.target_time, cutoff) & sup.y.notna().to_numpy()
    return TreeModel(fam, params, seed=seed, name=family).fit(sup.X[tr], sup.y[tr])


def run_horizon(exp: SocietyExperiment, h: int) -> dict:
    plan = exp.plan or default_plan(exp.series)
    sups = {False: _sup_for(exp, h, False)}
    if exp.weather is not None and "xgboost_weather" in exp.families:
        sups[True] = _sup_for(exp, h, True)
    base_sup = sups[False]
    evalm = common_eval_mask(base_sup)
    folds = list(plan.folds) or [Fold("validation", plan.val_start, plan.test_start - pd.Timedelta(hours=1))]
    bl = baselines(h)

    cv: dict[str, dict] = {}
    oof: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}  # key -> [(y, pred)] over folds

    def blk(f: Fold) -> np.ndarray:
        return block_mask(base_sup.target_time, f.test_start, f.test_end) & evalm

    base_bands: dict[str, dict] = {}
    for b in bl:
        cv[b.name] = {f.name: evaluate(base_sup.y[blk(f)], b.predict(base_sup.X[blk(f)]), MAPE_EPS_KW) for f in folds}
        yy = np.concatenate([base_sup.y[blk(f)].to_numpy() for f in folds])
        pp = np.concatenate([b.predict(base_sup.X[blk(f)]) for f in folds])
        ok = np.isfinite(yy) & np.isfinite(pp)
        base_bands[b.name] = {"residual_q10": float(np.quantile(yy[ok] - pp[ok], 0.10)), "residual_q90": float(np.quantile(yy[ok] - pp[ok], 0.90)),
                              "oof_rows": int(ok.sum()), "column": b.column}
    for fam in exp.families:
        sup = sups.get(fam == "xgboost_weather", base_sup)
        if fam == "xgboost_weather" and True not in sups:
            continue
        for i, params in enumerate(GRIDS[fam]):
            key = f"{fam}#{i}"
            cv[key], oof[key] = {}, []
            for f in folds:
                m = blk(f)
                model = fit_before(sup, fam, params, f.test_start, exp.seed)
                pred = model.predict(sup.X[m])
                cv[key][f.name] = evaluate(sup.y[m], pred, MAPE_EPS_KW)
                oof[key].append((sup.y[m].to_numpy(), pred))
    for per in cv.values():
        maes = [v["mae"] for v in per.values() if v["mae"] is not None]
        per["_summary"] = {"mean_fold_mae": float(np.mean(maes)) if maes else None, "folds": len(maes)}

    chosen: dict[str, dict] = {}
    for fam in exp.families:
        if fam == "xgboost_weather" and True not in sups:
            continue
        i = min(range(len(GRIDS[fam])), key=lambda j: cv[f"{fam}#{j}"]["_summary"]["mean_fold_mae"])
        chosen[fam] = {"index": i, "params": GRIDS[fam][i], "cv_mean_fold_mae": cv[f"{fam}#{i}"]["_summary"]["mean_fold_mae"]}
        y_oof = np.concatenate([a for a, _ in oof[f"{fam}#{i}"]])
        p_oof = np.concatenate([b for _, b in oof[f"{fam}#{i}"]])
        resid = y_oof[np.isfinite(y_oof) & np.isfinite(p_oof)] - p_oof[np.isfinite(y_oof) & np.isfinite(p_oof)]
        chosen[fam]["residual_q10"] = float(np.quantile(resid, 0.10))
        chosen[fam]["residual_q90"] = float(np.quantile(resid, 0.90))
        chosen[fam]["oof_rows"] = int(resid.size)

    test_blk = block_mask(base_sup.target_time, plan.test_start, plan.test_end)
    scored = test_blk & evalm
    if scored.sum() == 0:
        raise ValueError("No test rows can be scored")
    pred_df = pd.DataFrame({"y_true": base_sup.y[scored].to_numpy()}, index=base_sup.target_time[scored])
    pred_df.index.name = "target_time"
    test: dict[str, dict] = {}
    models: dict[str, TreeModel] = {}
    for b in bl:
        pred_df[b.name] = b.predict(base_sup.X[scored])
        test[b.name] = evaluate(pred_df["y_true"], pred_df[b.name], MAPE_EPS_KW)
    for fam, c in chosen.items():
        sup = sups.get(fam == "xgboost_weather", base_sup)
        model = fit_before(sup, fam, c["params"], plan.test_start, exp.seed)
        models[fam] = model
        pred_df[fam] = model.predict(sup.X[scored])
        test[fam] = evaluate(pred_df["y_true"], pred_df[fam], MAPE_EPS_KW)
        lo, hi = c["residual_q10"], c["residual_q90"]
        inside = (pred_df["y_true"] >= pred_df[fam] + lo) & (pred_df["y_true"] <= pred_df[fam] + hi)
        test[fam]["band_80_coverage_pct"] = float(100 * inside.mean())

    best_learned = min(chosen, key=lambda k: chosen[k]["cv_mean_fold_mae"])
    for b in bl:
        lo, hi = base_bands[b.name]["residual_q10"], base_bands[b.name]["residual_q90"]
        inside = (pred_df["y_true"] >= pred_df[b.name] + lo) & (pred_df["y_true"] <= pred_df[b.name] + hi)
        test[b.name]["band_80_coverage_pct"] = float(100 * inside.mean())
    best_base_test = min((b.name for b in bl), key=lambda n: test[n]["mae"])
    best_base_cv = min((b.name for b in bl), key=lambda n: cv[b.name if False else n]["_summary"]["mean_fold_mae"])
    cv_mae = {k: v["_summary"]["mean_fold_mae"] for k, v in cv.items() if "#" not in k}
    cv_mae.update({fam: c["cv_mean_fold_mae"] for fam, c in chosen.items()})
    best_overall = min(cv_mae, key=cv_mae.get)
    boot = paired_block_bootstrap(pred_df["y_true"], pred_df[best_learned], pred_df[best_base_cv], pred_df.index, n_boot=1000, seed=exp.seed)
    train_rows = {fam: int((train_mask(sups.get(fam == "xgboost_weather", base_sup).target_time, plan.test_start)
                            & sups.get(fam == "xgboost_weather", base_sup).y.notna().to_numpy()).sum()) for fam in chosen}
    result = {
        "horizon": h,
        "cv": cv, "chosen": chosen, "chosen_baselines": base_bands, "test": test,
        "best_overall_by_cv": best_overall, "best_overall_is_baseline": best_overall not in chosen,
        "best_model_by_cv": best_learned, "best_baseline_by_cv": best_base_cv, "best_baseline_by_test": best_base_test,
        "mae_improvement_vs_best_baseline_pct": float(100 * (1 - test[best_learned]["mae"] / test[best_base_cv]["mae"])),
        "learned_beats_best_baseline": bool(test[best_learned]["mae"] < test[best_base_cv]["mae"]),
        "bootstrap_vs_best_baseline": {"model": best_learned, "baseline": best_base_cv, **boot},
        "counts": {"test_target_hours": int(test_blk.sum()), "test_rows_scored": int(scored.sum()),
                   "test_rows_excluded": int(test_blk.sum() - scored.sum()), "train_rows": train_rows},
        "test_best_by_test_mae": min(test, key=lambda k: test[k]["mae"]),
    }
    return {"result": result, "predictions": pred_df, "models": models, "sups": sups, "plan": plan}


def run_all(exp: SocietyExperiment) -> tuple[dict, dict[int, pd.DataFrame], dict[int, dict]]:
    """Run every horizon. Returns (results, test predictions, fitted test-protocol models and supervised sets)."""
    results: dict[str, Any] = {}
    preds: dict[int, pd.DataFrame] = {}
    keep: dict[int, dict] = {}
    for h in exp.horizons:
        t0 = time.time()
        out = run_horizon(exp, h)
        results[str(h)] = out["result"]
        preds[h] = out["predictions"]
        keep[h] = {"models": out["models"], "sups": out["sups"]}
        r = out["result"]
        exp.log(f"[h={h}] {time.time() - t0:.0f}s | " + " | ".join(f"{k}: {v['mae']:.1f}" for k, v in r["test"].items()))
    return results, preds, keep
