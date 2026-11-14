"""Leak-free feature construction for direct multi-horizon forecasting.

For an origin hour ``t`` (the last hour whose value is known) and horizon ``h``:

* target            y[t + h]
* lag features      value[t - k]                       (known at t)
* seasonal features value[t + h - s] for s in (24, 168) (needs s >= h, so h <= 24)
* rolling features  mean/std over windows ending at t
* calendar features of the TARGET time t + h (calendar is known in advance)
* optional exogenous (weather) features: the observed value at the origin ``t`` and its mean over the
  last 24 h. These are *observed* weather, not a weather forecast for the target hour, so they carry no
  information from after ``t``.

Horizons up to 24 h use seasonal offsets of 24 h and 168 h; horizons up to 168 h use 168 h and 336 h
(``config_for_horizon``). A seasonal offset must be at least the horizon, otherwise the feature would
read the future.

No feature uses any value after ``t``. tests/unit/test_features.py checks this by
changing all future values and confirming the features do not move.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureConfig:
    lags: tuple[int, ...] = (0, 1, 2, 3, 5, 11, 23, 47)
    seasonal_offsets: tuple[int, ...] = (24, 168)
    roll_windows: tuple[int, ...] = (24, 168)
    exog_columns: tuple[str, ...] = ()  # names of columns of the ``exog`` frame to use (e.g. weather)
    exog_roll: int = 24


WEEKLY_SEASONAL_OFFSETS = (168, 336)


def config_for_horizon(horizon: int, base: FeatureConfig | None = None) -> FeatureConfig:
    """Feature configuration valid for ``horizon``: hourly-lag set up to 24 h, weekly offsets beyond."""
    from dataclasses import replace

    base = base or FeatureConfig()
    if horizon <= min(base.seasonal_offsets):
        return base
    if horizon > min(WEEKLY_SEASONAL_OFFSETS):
        raise ValueError(f"horizon {horizon} exceeds the weekly seasonal offset {min(WEEKLY_SEASONAL_OFFSETS)}")
    return replace(base, seasonal_offsets=WEEKLY_SEASONAL_OFFSETS)


@dataclass
class Supervised:
    X: pd.DataFrame  # indexed by origin time
    y: pd.Series  # target value at origin + horizon (NaN if missing / in the future)
    target_time: pd.DatetimeIndex
    horizon: int


def regularize(series: pd.Series) -> pd.Series:
    """Reindex to a complete hourly grid (missing hours become NaN)."""
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("series must have a DatetimeIndex")
    full = pd.date_range(series.index.min().floor("h"), series.index.max().floor("h"), freq="1h")
    return series.astype("float64").reindex(full)


def feature_names(cfg: FeatureConfig = FeatureConfig()) -> list[str]:
    names = [f"lag_{k}" for k in cfg.lags]
    names += [f"seasonal_{s}" for s in cfg.seasonal_offsets]
    for w in cfg.roll_windows:
        names += [f"roll_mean_{w}", f"roll_std_{w}"]
    names += [
        "hour", "dow", "month", "is_weekend",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos",
    ]
    for c in cfg.exog_columns:
        names += [f"wx_{c}", f"wx_{c}_mean_{cfg.exog_roll}"]
    return names


def make_features(series: pd.Series, horizon: int, cfg: FeatureConfig = FeatureConfig(),
                  exog: pd.DataFrame | None = None) -> pd.DataFrame:
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if horizon > min(cfg.seasonal_offsets):
        raise ValueError(f"horizon {horizon} exceeds the smallest seasonal offset {min(cfg.seasonal_offsets)}")
    s = regularize(series)
    cols: dict[str, pd.Series] = {}
    for k in cfg.lags:
        cols[f"lag_{k}"] = s.shift(k)
    for off in cfg.seasonal_offsets:
        cols[f"seasonal_{off}"] = s.shift(off - horizon)  # value at t + h - off
    for w in cfg.roll_windows:
        roll = s.rolling(w, min_periods=max(2, w // 2))
        cols[f"roll_mean_{w}"] = roll.mean()
        cols[f"roll_std_{w}"] = roll.std()
    X = pd.DataFrame(cols)
    tt = X.index + pd.Timedelta(hours=horizon)
    X["hour"] = tt.hour
    X["dow"] = tt.day_of_week
    X["month"] = tt.month
    X["is_weekend"] = (tt.day_of_week >= 5).astype(int)
    X["hour_sin"] = np.sin(2 * np.pi * tt.hour / 24)
    X["hour_cos"] = np.cos(2 * np.pi * tt.hour / 24)
    X["dow_sin"] = np.sin(2 * np.pi * tt.day_of_week / 7)
    X["dow_cos"] = np.cos(2 * np.pi * tt.day_of_week / 7)
    X["month_sin"] = np.sin(2 * np.pi * (tt.month - 1) / 12)
    X["month_cos"] = np.cos(2 * np.pi * (tt.month - 1) / 12)
    if cfg.exog_columns:
        if exog is None:
            raise ValueError("exog_columns are configured but no exog frame was given")
        ex = exog.reindex(s.index)
        for c in cfg.exog_columns:
            col = ex[c].astype("float64")
            X[f"wx_{c}"] = col  # value at the origin hour
            X[f"wx_{c}_mean_{cfg.exog_roll}"] = col.rolling(cfg.exog_roll, min_periods=cfg.exog_roll // 2).mean()
    return X[feature_names(cfg)]


def make_supervised(series: pd.Series, horizon: int, cfg: FeatureConfig = FeatureConfig(),
                    exog: pd.DataFrame | None = None) -> Supervised:
    s = regularize(series)
    X = make_features(s, horizon, cfg, exog)
    y = s.shift(-horizon)
    y.name = f"y_t_plus_{horizon}"
    return Supervised(X=X, y=y, target_time=X.index + pd.Timedelta(hours=horizon), horizon=horizon)


def common_eval_mask(sup: Supervised) -> np.ndarray:
    """Rows where the target exists and every baseline has its input.

    All models are scored on this same set so comparisons are fair. Tree models
    could also predict on rows with missing inputs; those rows are excluded from
    scoring (and counted in the report), never filled.
    """
    cols = ["lag_0", *[c for c in sup.X.columns if c.startswith("seasonal_")]]
    return (sup.y.notna() & sup.X[cols].notna().all(axis=1)).to_numpy()
