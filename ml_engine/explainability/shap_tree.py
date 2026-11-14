"""Additive feature explanations (SHAP) for the forecasters: XGBoost, Random Forest and linear regression.

Every explanation is a set of per-feature contributions plus a bias (the model's expected output) that
add up to the model prediction; ``explain_rows`` verifies this and raises if it does not hold.

* XGBoost       exact TreeSHAP from the booster's own ``pred_contribs`` (no extra dependency).
* Random Forest exact TreeSHAP from the ``shap`` package (``shap.TreeExplainer``).
* Linear model  closed form: coefficient x standardised (median-imputed) input, intercept as bias.

Features are also rolled up into a few human-readable groups for the dashboard.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb

from ml_engine.forecasting.models import TreeModel

GROUPS = {
    "Recent consumption": ("lag_",),
    "Same time yesterday / last week": ("seasonal_",),
    "Recent averages and variability": ("roll_",),
    "Time of day": ("hour", "hour_sin", "hour_cos"),
    "Day of week": ("dow", "is_weekend", "dow_sin", "dow_cos"),
    "Season": ("month", "month_sin", "month_cos"),
    "Weather at forecast time": ("wx_",),
}
NICE = {
    "lag_0": "usage in the latest hour", "lag_1": "usage 1 h earlier", "lag_2": "usage 2 h earlier",
    "lag_3": "usage 3 h earlier", "lag_5": "usage 5 h earlier", "lag_11": "usage 11 h earlier",
    "lag_23": "usage 23 h earlier", "lag_47": "usage 47 h earlier",
    "seasonal_24": "usage at the same time yesterday", "seasonal_168": "usage at the same time last week",
    "roll_mean_24": "average of the last 24 h", "roll_std_24": "variability over the last 24 h",
    "roll_mean_168": "average of the last 7 days", "roll_std_168": "variability over the last 7 days",
    "hour": "hour of day (number)", "dow": "day of week (number)", "month": "month (number)", "is_weekend": "weekend flag",
    "hour_sin": "hour of day (sine)", "hour_cos": "hour of day (cosine)", "dow_sin": "day of week (sine)", "dow_cos": "day of week (cosine)",
    "month_sin": "season (sine)", "month_cos": "season (cosine)",
    "seasonal_336": "usage at the same time two weeks ago",
    "wx_airTemperature": "outdoor temperature now", "wx_airTemperature_mean_24": "outdoor temperature, last 24 h average",
    "wx_dewTemperature": "dew point now", "wx_dewTemperature_mean_24": "dew point, last 24 h average",
    "wx_windSpeed": "wind speed now", "wx_windSpeed_mean_24": "wind speed, last 24 h average",
}


def group_of(feature: str) -> str:
    for g, prefixes in GROUPS.items():
        if any(feature == p or (p.endswith("_") and feature.startswith(p)) for p in prefixes):
            return g
    return "Other"


def contributions(model: TreeModel, X: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Per-feature contributions (same unit as the target) and the bias term for each row of X."""
    cols = model.columns
    arr = X[cols].to_numpy(dtype="float32")
    if model.family == "xgboost":
        raw = model.model.get_booster().predict(xgb.DMatrix(arr, feature_names=None), pred_contribs=True)
        return pd.DataFrame(raw[:, :-1], index=X.index, columns=cols), raw[:, -1]
    if model.family == "random_forest":
        import shap  # imported lazily: only needed to explain forests

        explainer = shap.TreeExplainer(model.model)
        vals = np.asarray(explainer.shap_values(arr, check_additivity=False))
        base = float(np.ravel(explainer.expected_value)[0])
        return pd.DataFrame(vals, index=X.index, columns=cols), np.full(len(X), base)
    if model.family == "linear":
        imputer, scaler, reg = (step for _, step in model.model.steps)
        xs = scaler.transform(imputer.transform(arr))
        return pd.DataFrame(xs * reg.coef_, index=X.index, columns=cols), np.full(len(X), float(reg.intercept_))
    raise ValueError(f"No explanation method for model family '{model.family}'")


def explain_rows(model: TreeModel, X: pd.DataFrame, top_k: int = 6) -> list[dict]:
    """Local explanation for every row: prediction, bias, top drivers and grouped totals."""
    contrib, bias = contributions(model, X)
    pred = model.predict(X)
    recon = contrib.sum(axis=1).to_numpy() + bias
    if not np.allclose(recon, pred, atol=2e-3 + 1e-5 * float(np.abs(pred).max())):
        raise AssertionError("SHAP contributions do not add up to the prediction")
    out = []
    for i, (ts, row) in enumerate(contrib.iterrows()):
        order = row.abs().sort_values(ascending=False).index[:top_k]
        drivers = [{
            "feature": f, "label": NICE.get(f, f), "value": None if pd.isna(X.iloc[i][f]) else float(X.iloc[i][f]),
            "contribution_kw": float(row[f]), "direction": "raises" if row[f] > 0 else "lowers",
        } for f in order]
        grouped: dict[str, float] = {}
        for f, v in row.items():
            grouped[group_of(f)] = grouped.get(group_of(f), 0.0) + float(v)
        out.append({
            "origin": str(ts), "prediction_kw": float(pred[i]), "base_value_kw": float(bias[i]),
            "drivers": drivers, "grouped_kw": dict(sorted(grouped.items(), key=lambda kv: -abs(kv[1]))),
            "additivity_error_kw": float(abs(recon[i] - pred[i])),
        })
    return out


def global_importance(model: TreeModel, X: pd.DataFrame, max_rows: int = 5000, seed: int = 0) -> pd.DataFrame:
    """Mean |SHAP| per feature and per group on a (sub)sample of rows, sorted descending."""
    if len(X) > max_rows:
        X = X.sample(max_rows, random_state=seed).sort_index()
    contrib, _ = contributions(model, X)
    imp = contrib.abs().mean().sort_values(ascending=False)
    df = pd.DataFrame({"feature": imp.index, "label": [NICE.get(f, f) for f in imp.index],
                       "group": [group_of(f) for f in imp.index], "mean_abs_shap_kw": imp.to_numpy()})
    df["share_pct"] = 100 * df["mean_abs_shap_kw"] / df["mean_abs_shap_kw"].sum()
    return df.reset_index(drop=True)


def narrative(exp: dict, horizon: int) -> str:
    """One plain-language sentence for a local explanation (numbers come from the contributions)."""
    pos = [d for d in exp["drivers"] if d["contribution_kw"] > 0][:2]
    neg = [d for d in exp["drivers"] if d["contribution_kw"] < 0][:2]
    parts = [f"The model forecasts {exp['prediction_kw']:.2f} kW for {horizon} h ahead (average-case baseline {exp['base_value_kw']:.2f} kW)."]
    if pos:
        parts.append("Pushing it up: " + "; ".join(f"{d['label']} (+{d['contribution_kw']:.2f} kW)" for d in pos) + ".")
    if neg:
        parts.append("Pulling it down: " + "; ".join(f"{d['label']} ({d['contribution_kw']:.2f} kW)" for d in neg) + ".")
    return " ".join(parts)
