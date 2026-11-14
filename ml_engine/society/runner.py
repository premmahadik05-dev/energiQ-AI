"""Train, evaluate and (optionally) deploy the society forecasters for one real society series.

Shared by ``scripts/society_train.py`` (the bundled research communities) and by the API's train job
(a society uploaded by an admin), so both follow exactly the same protocol.
"""
from __future__ import annotations

import json
import platform
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import xgboost

from ml_engine.evaluation.splits import SplitPlan, expanding_folds
from ml_engine.explainability.shap_tree import global_importance
from ml_engine.society.experiment import HORIZONS, LEARNED, MAPE_EPS_KW, SocietyExperiment, run_all

MIN_VALID_HOURS = 24 * 270  # roughly nine months of valid hours: the least that still leaves two CV blocks and a test block
CV_BLOCK_MONTHS = 3
MIN_TRAIN_DAYS = 90  # training history required before the first CV block


class NotEnoughData(ValueError):
    """The series is too short for the chronological evaluation protocol."""


def plan_for(series: pd.Series) -> SplitPlan:
    """Chronological split derived from the data's own end.

    Test block = the last 6 whole months (3 if the history is short); the CV blocks are consecutive 3-month
    blocks directly before it (up to 4), each with at least 90 days of earlier training data. For the
    two-year BDG2 communities this reproduces the published protocol: CV 2016-07..2017-06, test 2017-07..2017-12.
    """
    valid = series.dropna()
    if len(valid) < MIN_VALID_HOURS:
        raise NotEnoughData(f"Only {len(valid)} valid hours ({len(valid) / 24:.0f} days); at least {MIN_VALID_HOURS // 24} days are needed for a leakage-free evaluation")
    start, end = valid.index.min(), valid.index.max()
    span_months = (end.year - start.year) * 12 + end.month - start.month
    test_months = 6 if span_months >= 20 else 3
    test_start = (end.floor("D") - pd.DateOffset(months=test_months - 1)).replace(day=1, hour=0)
    first_ok = (start + pd.Timedelta(days=MIN_TRAIN_DAYS)).ceil("D")
    n = 4
    while n >= 1:
        first = test_start - pd.DateOffset(months=CV_BLOCK_MONTHS * n)
        if first >= first_ok:
            break
        n -= 1
    if n < 2:
        raise NotEnoughData("The history is too short for two cross-validation blocks plus a test block; provide at least about 12 months of hourly data")
    first = test_start - pd.DateOffset(months=CV_BLOCK_MONTHS * n)
    folds = tuple(expanding_folds(str(first), str(test_start - pd.Timedelta(hours=1)), CV_BLOCK_MONTHS))
    return SplitPlan(test_start=test_start, test_end=end, val_start=folds[-1].test_start, folds=folds)


def peak_evaluation(preds_h24: pd.DataFrame, best: str, baseline: str, min_hours: int = 22) -> dict:
    """How well the 24-hour-ahead forecast finds each day's peak demand (held-out test days only).

    For each test day with at least ``min_hours`` scored hours, compare the day's highest *actual* hourly
    demand with the highest *forecast* hourly demand (both from forecasts issued 24 h ahead), and check whether
    the forecast peak falls in the right hour. The best simple baseline is scored the same way.
    """
    df = preds_h24.dropna(subset=["y_true", best, baseline])
    day = df.index.floor("D")
    rows = []
    for d, g in df.groupby(day):
        if len(g) < min_hours:
            continue
        a_i = g["y_true"].to_numpy().argmax()
        row = {"day": d, "actual_peak": float(g["y_true"].iloc[a_i]), "actual_hour": int(g.index[a_i].hour)}
        for name, col in (("model", best), ("baseline", baseline)):
            p_i = g[col].to_numpy().argmax()
            row[f"{name}_peak"] = float(g[col].iloc[p_i])
            row[f"{name}_hour"] = int(g.index[p_i].hour)
            row[f"{name}_at_actual_hour"] = float(g[col].iloc[a_i])
        rows.append(row)
    if not rows:
        return {"days": 0, "note": "No complete test days with forecasts"}
    r = pd.DataFrame(rows)
    # model / baseline are filled with the metrics below; the method names live under their own keys
    out: dict = {"days": int(len(r)), "model_name": best, "baseline_name": baseline, "horizon_h": 24,
                 "basis": "daily peak = highest hourly demand (kW) of the day; forecasts issued 24 h ahead; held-out test days only"}
    for name in ("model", "baseline"):
        err = r[f"{name}_peak"] - r["actual_peak"]
        diff = (r[f"{name}_hour"] - r["actual_hour"]).abs()
        diff = np.minimum(diff, 24 - diff)
        out[name] = {
            "peak_mae_kw": float(err.abs().mean()), "peak_mape_pct": float((err.abs() / r["actual_peak"]).mean() * 100),
            "peak_bias_kw": float(err.mean()),
            "peak_hour_exact_pct": float((diff == 0).mean() * 100), "peak_hour_within_1h_pct": float((diff <= 1).mean() * 100),
            "peak_hour_within_2h_pct": float((diff <= 2).mean() * 100),
        }
    out["mean_actual_peak_kw"] = float(r["actual_peak"].mean())
    out["mae_improvement_vs_baseline_pct"] = float((out["baseline"]["peak_mae_kw"] - out["model"]["peak_mae_kw"]) / out["baseline"]["peak_mae_kw"] * 100)
    return out


def evaluate(key: str, series: pd.Series, weather: pd.DataFrame | None, out_dir: Path, horizons: tuple[int, ...] = HORIZONS,
             plan: SplitPlan | None = None, log: Callable[[str], None] = print) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    has_weather = weather is not None and weather.notna().any().any()
    families = LEARNED if has_weather else tuple(f for f in LEARNED if f != "xgboost_weather")
    plan = plan or plan_for(series)
    exp = SocietyExperiment(series=series, weather=weather if has_weather else None, plan=plan, horizons=tuple(horizons), families=families, log=log)
    t0 = time.time()
    results, preds, keep = run_all(exp)
    shap: dict[str, dict] = {}
    for h, r in results.items():
        fam = r["best_model_by_cv"]
        model = keep[int(h)]["models"][fam]
        sup = keep[int(h)]["sups"][fam == "xgboost_weather"]
        mask = (sup.target_time >= plan.test_start) & (sup.target_time <= plan.test_end)
        X = sup.X[np.asarray(mask)].dropna(subset=["lag_0"])
        imp = global_importance(model, X, max_rows=1200)
        shap[h] = {"model": fam, "rows": int(min(len(X), 1200)),
                   "top_features": imp.head(12)[["feature", "label", "group", "mean_abs_shap_kw", "share_pct"]].to_dict("records"),
                   "group_share_pct": imp.groupby("group")["share_pct"].sum().sort_values(ascending=False).to_dict()}
    for h, df in preds.items():
        df.round(3).to_csv(out / f"predictions_h{h}.csv.gz", compression="gzip")
    if 24 in preds:
        r24 = results["24"]
        (out / "peak_evaluation.json").write_text(json.dumps(peak_evaluation(preds[24], r24["best_overall_by_cv"], r24["best_baseline_by_cv"]), indent=2), encoding="utf-8")
    meta = {
        "society": key, "unit": "kW (hourly mean demand, numerically equal to kWh per hour)",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "protocol": {
            "cv_folds": [{"name": f.name, "test_start": str(f.test_start), "test_end": str(f.test_end)} for f in plan.folds],
            "test_period": [str(plan.test_start), str(plan.test_end)],
            "selection": "lowest mean absolute error over the expanding-window CV folds, per horizon; the test period is scored once",
            "mape_excludes_actuals_below_kw": MAPE_EPS_KW, "seed": exp.seed,
            "weather": ("observed airTemperature, dewTemperature, windSpeed at the forecast origin and their 24 h mean (not a weather forecast)"
                        if has_weather else "no weather data supplied; weather models were not trained"),
        },
        "data": {"hours": int(len(series)), "valid_hours": int(series.notna().sum()), "first": str(series.index[0]), "last": str(series.index[-1])},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                     "scikit_learn": sklearn.__version__, "xgboost": xgboost.__version__},
        "runtime_seconds": round(time.time() - t0),
        "horizons": results,
    }
    (out / "evaluation.json").write_text(json.dumps(meta, indent=2, default=float), encoding="utf-8")
    (out / "shap_global.json").write_text(json.dumps({"society": key, "basis": "mean |SHAP| of the CV-selected model on the test rows", "horizons": shap}, indent=2, default=float), encoding="utf-8")
    return meta


def train(key: str, series: pd.Series, weather: pd.DataFrame | None, out_dir: Path, horizons: tuple[int, ...] = HORIZONS, deploy: bool = True,
          log: Callable[[str], None] = print) -> dict:
    from ml_engine.society.deploy import build_bundle

    meta = evaluate(key, series, weather, out_dir, horizons, log=log)
    if deploy:
        wx = weather if weather is not None and weather.notna().any().any() else pd.DataFrame(index=series.index)
        build_bundle(key, series, wx, Path(out_dir), log=log)
    return meta
