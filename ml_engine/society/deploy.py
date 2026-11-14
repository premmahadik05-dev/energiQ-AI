"""Deployment bundle: the models the API uses for live society forecasts.

For every hourly horizon 1..24 and for 168 h, one model is refitted on *all* valid history (the
evaluation protocol in ``experiment.py`` has already measured the configuration's out-of-sample error)
and saved with the versioned registry. Which configuration is used:

* Accuracy was measured at 1, 6, 12, 24 and 168 h. For an evaluated horizon the model with the lowest
  cross-validated error is used, *baselines included*: if "same hour last week" beats every learned model
  (it does at some 7-day horizons), the bundle serves that baseline instead of a worse learned model. For the other hours (2-5, 7-11, 13-23) the configuration of the nearest evaluated
  horizon is reused (ties go to the shorter one); their accuracy is not separately measured.
* The forecast range is ``prediction + q10 .. prediction + q90`` of the out-of-fold CV residuals,
  linearly interpolated between evaluated horizons. It is an empirical 80 % band, not a guarantee.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from ml_engine.features.builder import FeatureConfig, config_for_horizon, make_supervised
from ml_engine.forecasting.registry import save_tree_model, series_hash
from ml_engine.society.experiment import WEATHER_COLUMNS, fit_before

BUNDLE_HORIZONS: tuple[int, ...] = (*range(1, 25), 168)


def _pick(r: dict) -> dict:
    name = r["best_overall_by_cv"]
    if r["best_overall_is_baseline"]:
        b = r["chosen_baselines"][name]
        return {"family": "baseline", "baseline": name, "column": b["column"], "params": {}, "q10": b["residual_q10"], "q90": b["residual_q90"]}
    c = r["chosen"][name]
    return {"family": name, "params": c["params"], "q10": c["residual_q10"], "q90": c["residual_q90"]}


def nearest(evaluated: list[int], h: int) -> int:
    return min(evaluated, key=lambda e: (abs(e - h), e))


def feature_cfg(h: int, weather: bool, weather_cols: tuple[str, ...] = WEATHER_COLUMNS) -> FeatureConfig:
    cfg = config_for_horizon(h, FeatureConfig())
    return replace(cfg, exog_columns=tuple(weather_cols)) if weather else cfg


def build_bundle(key: str, series: pd.Series, weather: pd.DataFrame, out_dir: Path, log=print) -> dict:
    out_dir = Path(out_dir)
    ev = json.loads((out_dir / "evaluation.json").read_text())
    horizons = ev["horizons"]
    short = sorted(int(h) for h in horizons if int(h) <= 24)
    if not short:
        raise ValueError("evaluation.json has no horizon up to 24 h")
    pick: dict[int, dict] = {}
    for h in short:
        pick[h] = _pick(horizons[str(h)])
    cutoff = series.index.max().floor("h") + pd.Timedelta(hours=1)
    data_hash = series_hash(series)
    models_dir = out_dir / "models"
    entries: dict[str, dict] = {}
    for h in BUNDLE_HORIZONS:
        if h == 168:
            if "168" not in horizons:
                continue
            conf = _pick(horizons["168"])
            src = 168
        else:
            src = nearest(short, h)
            conf = dict(pick[src])
            conf["q10"] = float(np.interp(h, short, [pick[e]["q10"] for e in short]))
            conf["q90"] = float(np.interp(h, short, [pick[e]["q90"] for e in short]))
        if conf["family"] == "baseline":
            entries[str(h)] = {"model_id": None, "family": "baseline", "baseline": conf["baseline"], "column": conf["column"], "weather": False,
                               "selected_from_horizon": src, "residual_q10": conf["q10"], "residual_q90": conf["q90"]}
            if h in (1, 24, 168):
                log(f"deployed h={h}: baseline {conf['baseline']}")
            continue
        use_weather = conf["family"] == "xgboost_weather"
        cfg = feature_cfg(h, use_weather, tuple(c for c in WEATHER_COLUMNS if c in weather.columns))
        sup = make_supervised(series, h, cfg, exog=weather if use_weather else None)
        model = fit_before(sup, conf["family"], conf["params"], cutoff, seed=42)
        meta = {"horizon": h, "society": key, "data_hash": data_hash, "train_target_before": str(cutoff), "unit": "kW",
                "selected_from_horizon": src, "weather": use_weather, "weather_columns": list(cfg.exog_columns),
                "train_rows": int((sup.y.notna() & np.asarray(sup.target_time < cutoff)).sum())}
        mid = save_tree_model(models_dir, model, meta)
        entries[str(h)] = {"model_id": mid, "family": conf["family"], "weather": use_weather, "selected_from_horizon": src,
                           "residual_q10": conf["q10"], "residual_q90": conf["q90"]}
        if h in (1, 24, 168):
            log(f"deployed h={h}: {conf['family']} ({mid})")
    bundle = {"society": key, "trained_through": str(series.index.max()), "data_hash": data_hash, "horizons": entries,
              "evaluated_horizons": sorted(int(h) for h in horizons),
              "note": "Accuracy was measured at the evaluated horizons only; other hours reuse the nearest evaluated configuration."}
    (out_dir / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle
