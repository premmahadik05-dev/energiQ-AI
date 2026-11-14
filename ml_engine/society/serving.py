"""Serve forecasts from a saved society bundle (no database or web framework needed)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ml_engine.features.builder import make_features, regularize
from ml_engine.forecasting.registry import load_tree_model
from ml_engine.society.deploy import feature_cfg
from ml_engine.society.experiment import WEATHER_COLUMNS

TAIL_HOURS = 24 * 21  # enough for the 336 h seasonal offset and every rolling window


@lru_cache(maxsize=256)
def _model(models_dir: str, model_id: str):
    return load_tree_model(Path(models_dir), model_id)  # artifacts are immutable once written


def load_bundle(bundle_dir: Path) -> dict:
    p = Path(bundle_dir) / "bundle.json"
    if not p.is_file():
        raise FileNotFoundError(f"no bundle at {bundle_dir}")
    return json.loads(p.read_text())


def _row(series: pd.Series, weather: pd.DataFrame | None, origin: pd.Timestamp, h: int, use_weather: bool, cols: tuple[str, ...]):
    cfg = feature_cfg(h, use_weather, cols)
    s = regularize(series)
    tail = s[s.index <= origin].iloc[-TAIL_HOURS:]
    X = make_features(tail, h, cfg, exog=weather if use_weather else None)
    return X.loc[[origin]]


def forecast_from_bundle(bundle_dir: Path, series: pd.Series, weather: pd.DataFrame | None, origin: pd.Timestamp | None = None,
                         horizons: list[int] | None = None) -> dict:
    """Point forecasts and 80 % ranges for ``origin + h`` using only data up to ``origin``."""
    bundle = load_bundle(bundle_dir)
    s = regularize(series)
    origin = pd.Timestamp(origin).floor("h") if origin is not None else s.index.max()
    if origin not in s.index:
        raise ValueError("origin is outside the data range")
    cols = tuple(c for c in WEATHER_COLUMNS if weather is not None and c in weather.columns)
    pts = []
    for h in horizons or [int(k) for k in bundle["horizons"]]:
        e = bundle["horizons"].get(str(h))
        if e is None:
            raise ValueError(f"no model for horizon {h}")
        row = _row(s, weather, origin, h, e["weather"], cols)
        if e["family"] == "baseline":
            pred = float(row[e["column"]].iloc[0])
        else:
            model, _ = _model(str(Path(bundle_dir) / "models"), e["model_id"])
            pred = float(model.predict(row)[0])
        if not np.isfinite(pred):
            raise ValueError("model produced a non-finite value (inputs missing at the origin)")
        pts.append({"horizon": h, "ts": origin + pd.Timedelta(hours=h), "kw": max(pred, 0.0),
                    "lower_kw": max(pred + e["residual_q10"], 0.0), "upper_kw": max(pred + e["residual_q90"], 0.0), "family": e["family"]})
    return {"origin": origin, "origin_value_missing": bool(np.isnan(s.loc[origin])), "points": pts, "trained_through": bundle["trained_through"]}


def explain_from_bundle(bundle_dir: Path, series: pd.Series, weather: pd.DataFrame | None, horizon: int, origin: pd.Timestamp | None = None) -> dict:
    from ml_engine.explainability.shap_tree import explain_rows, narrative

    bundle = load_bundle(bundle_dir)
    e = bundle["horizons"].get(str(horizon))
    if e is None:
        raise ValueError(f"no model for horizon {horizon}")
    s = regularize(series)
    origin = pd.Timestamp(origin).floor("h") if origin is not None else s.index.max()
    cols = tuple(c for c in WEATHER_COLUMNS if weather is not None and c in weather.columns)
    if e["family"] == "baseline":
        raise ValueError(f"The model for {horizon} h is the baseline '{e['baseline']}' (it beat every learned model); it copies one past value, so there is nothing to explain with SHAP")
    model, _ = _model(str(Path(bundle_dir) / "models"), e["model_id"])
    exp = explain_rows(model, _row(s, weather, origin, horizon, e["weather"], cols))[0]
    exp["narrative"] = narrative(exp, horizon)
    exp["target_time"] = str(origin + pd.Timedelta(hours=horizon))
    exp["model_family"] = e["family"]
    return exp
