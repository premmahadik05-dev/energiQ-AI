"""Forecast accuracy metrics with zero-value safeguards, plus a paired block bootstrap."""
from __future__ import annotations

import numpy as np
import pandas as pd

MAPE_EPS_KW = 0.05  # actuals below this are excluded from MAPE (and counted)


def evaluate(y_true, y_pred, mape_eps: float = MAPE_EPS_KW) -> dict:
    y = np.asarray(y_true, dtype="float64")
    p = np.asarray(y_pred, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    n = int(y.size)
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "mape_pct": None, "mape_excluded": 0, "smape_pct": None, "r2": None}
    err = p - y
    big = np.abs(y) >= mape_eps
    denom = np.abs(y) + np.abs(p)
    sm_ok = denom > 0
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "n": n,
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "mape_pct": float(100 * np.mean(np.abs(err[big]) / np.abs(y[big]))) if big.any() else None,
        "mape_excluded": int((~big).sum()),
        "smape_pct": float(100 * np.mean(2 * np.abs(err[sm_ok]) / denom[sm_ok])) if sm_ok.any() else None,
        "r2": float(1 - (err**2).sum() / ss_tot) if ss_tot > 0 else None,
    }


def paired_block_bootstrap(
    y_true, pred_a, pred_b, times: pd.DatetimeIndex, n_boot: int = 2000, seed: int = 0
) -> dict:
    """95% CI of MAE(a) - MAE(b), resampling whole days (errors are autocorrelated).

    A negative difference means model ``a`` has the lower error. If the interval
    excludes 0 the difference is unlikely to be sampling noise at the day level.
    """
    y, a, b = (np.asarray(v, dtype="float64") for v in (y_true, pred_a, pred_b))
    ok = np.isfinite(y) & np.isfinite(a) & np.isfinite(b)
    diff = np.abs(a - y)[ok] - np.abs(b - y)[ok]
    days = pd.DatetimeIndex(times)[ok].normalize()
    frame = pd.DataFrame({"d": diff, "day": days}).groupby("day")["d"].agg(["sum", "count"])
    sums, counts = frame["sum"].to_numpy(), frame["count"].to_numpy()
    rng = np.random.default_rng(seed)
    k = len(sums)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, k, k)
        boots[i] = sums[pick].sum() / counts[pick].sum()
    return {
        "mae_diff": float(diff.mean()),
        "ci95_low": float(np.percentile(boots, 2.5)),
        "ci95_high": float(np.percentile(boots, 97.5)),
        "days": int(k),
    }
