"""Metrics, models, registry and pipeline tests (synthetic data with known structure)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_engine.evaluation.metrics import evaluate, paired_block_bootstrap
from ml_engine.evaluation.splits import SplitPlan, expanding_folds
from ml_engine.features.builder import make_supervised
from ml_engine.forecasting.models import BaselineModel, TreeModel, baselines
from ml_engine.forecasting.registry import load_tree_model, save_tree_model
from ml_engine.pipeline import ExperimentConfig, fit_before, forecast_from_origin, run_experiment

SMALL_GRIDS = {
    "random_forest": [{"n_estimators": 20, "max_depth": 8, "min_samples_leaf": 5, "max_features": 0.5}],
    "xgboost": [{"n_estimators": 40, "max_depth": 3, "learning_rate": 0.1},
                {"n_estimators": 40, "max_depth": 4, "learning_rate": 0.1}],
}


def _series(days=140, noise=0.1, seed=0, nan_frac=0.0):
    idx = pd.date_range("2022-01-01", periods=24 * days, freq="h")
    rng = np.random.default_rng(seed)
    h = idx.hour.to_numpy()
    v = 1.0 + 0.8 * np.exp(-((h - 19) ** 2) / 8) + 0.3 * (idx.day_of_week.to_numpy() >= 5) + rng.normal(0, noise, len(idx))
    s = pd.Series(v, index=idx)
    if nan_frac:
        s[rng.random(len(s)) < nan_frac] = np.nan
    return s


def test_metrics_known_values_and_safeguards():
    m = evaluate([1, 2, 3, 4], [1, 2, 3, 6])
    assert m["mae"] == 0.5 and m["rmse"] == 1.0 and m["n"] == 4
    assert m["r2"] == pytest.approx(1 - 4 / 5)
    z = evaluate([0.0, 0.0, 2.0], [0.1, 0.0, 2.0])  # zeros must not blow up MAPE / sMAPE
    assert z["mape_excluded"] == 2 and z["mape_pct"] == 0.0
    assert np.isfinite(z["smape_pct"])
    assert evaluate([np.nan], [1.0])["n"] == 0  # NaNs are dropped, not scored


def test_bootstrap_detects_real_difference_and_null():
    idx = pd.date_range("2022-01-01", periods=24 * 60, freq="h")
    rng = np.random.default_rng(1)
    y = rng.normal(1, 0.2, len(idx))
    good, bad = y + rng.normal(0, 0.05, len(idx)), y + rng.normal(0, 0.4, len(idx))
    d = paired_block_bootstrap(y, good, bad, idx, n_boot=300)
    assert d["mae_diff"] < 0 and d["ci95_high"] < 0
    same = paired_block_bootstrap(y, good, good, idx, n_boot=300)
    assert same["mae_diff"] == 0.0 and same["ci95_low"] == same["ci95_high"] == 0.0


def test_seasonal_naive_is_exact_on_periodic_series():
    idx = pd.date_range("2022-01-01", periods=24 * 30, freq="h")
    s = pd.Series(np.tile(np.arange(24, dtype=float), 30), index=idx)
    sup = make_supervised(s, 6)
    ok = sup.y.notna() & sup.X["seasonal_24"].notna()
    pred = BaselineModel("sn", "seasonal_24").predict(sup.X[ok])
    assert np.allclose(pred, sup.y[ok])
    assert [b.name for b in baselines()] == ["naive", "seasonal_naive_24", "seasonal_naive_168"]


@pytest.mark.parametrize("family,params", [("random_forest", SMALL_GRIDS["random_forest"][0]), ("xgboost", SMALL_GRIDS["xgboost"][0])])
def test_trees_beat_naive_on_structured_series(family, params):
    s = _series()
    sup = make_supervised(s, 6)
    cut = pd.Timestamp("2022-05-01")
    model = fit_before(sup, family, params, cut, seed=1)
    te = (sup.target_time >= cut) & sup.y.notna().to_numpy() & sup.X["lag_0"].notna().to_numpy()
    mae_model = evaluate(sup.y[te], model.predict(sup.X[te]))["mae"]
    mae_naive = evaluate(sup.y[te], sup.X.loc[te, "lag_0"])["mae"]
    assert mae_model < mae_naive


def test_insufficient_history_raises():
    s = _series(days=3)
    sup = make_supervised(s, 1)
    with pytest.raises(ValueError, match="Insufficient"):
        TreeModel("xgboost", SMALL_GRIDS["xgboost"][0]).fit(sup.X.iloc[:20], sup.y.iloc[:20])


@pytest.mark.parametrize("family", ["random_forest", "xgboost"])
def test_registry_roundtrip_gives_identical_predictions(tmp_path, family):
    s = _series(days=60)
    sup = make_supervised(s, 1)
    model = fit_before(sup, family, SMALL_GRIDS[family][0], pd.Timestamp("2022-02-15"), seed=3)
    mid = save_tree_model(tmp_path, model, {"horizon": 1, "data_hash": "x"})
    loaded, meta = load_tree_model(tmp_path, mid)
    X = sup.X.iloc[400:500]
    assert np.allclose(model.predict(X), loaded.predict(X))
    assert meta["feature_names"] == list(sup.X.columns) and meta["family"] == family
    with pytest.raises(FileNotFoundError):
        load_tree_model(tmp_path, "does_not_exist")


def test_training_never_sees_data_after_cutoff():
    """Leakage canary: changing every value after the cutoff must not change the fitted model."""
    s = _series(days=100)
    cutoff = pd.Timestamp("2022-03-15")
    a = fit_before(make_supervised(s, 6), "xgboost", SMALL_GRIDS["xgboost"][0], cutoff, seed=5)
    s2 = s.copy()
    s2[s2.index >= cutoff] = 50.0
    b = fit_before(make_supervised(s2, 6), "xgboost", SMALL_GRIDS["xgboost"][0], cutoff, seed=5)
    X = make_supervised(s, 6).X.iloc[300:600]
    assert np.allclose(a.predict(X), b.predict(X))


def test_run_experiment_with_folds_selects_and_scores(tmp_path):
    s = _series(days=150, nan_frac=0.02)
    plan = SplitPlan(
        test_start=pd.Timestamp("2022-05-01"), test_end=s.index[-1], val_start=pd.Timestamp("2022-04-01"),
        folds=tuple(expanding_folds("2022-03-01", "2022-04-30 23:00", 1)),
    )
    logs: list[str] = []
    res, preds = run_experiment(s, ExperimentConfig(plan=plan, horizons=(1, 24), grids=SMALL_GRIDS,
                                                    models_dir=tmp_path, log=logs.append))
    for h in ("1", "24"):
        r = res[h]
        assert set(r["chosen"]) == {"random_forest", "xgboost"}
        assert {"naive", "seasonal_naive_24", "seasonal_naive_168", "random_forest", "xgboost"} <= set(r["test"])
        assert r["counts"]["test_rows_scored"] > 0
        assert r["cv"]["xgboost#0"]["_summary"]["folds"] == 2
        assert (tmp_path / r["chosen"]["xgboost"]["model_id"] / "metadata.json").is_file()
    assert list(preds[1].columns[:2]) == ["y_true", "naive"]
    assert preds[1].index.min() >= plan.test_start
    assert res["24"]["test"]["xgboost"]["mae"] < res["24"]["test"]["naive"]["mae"]


def test_forecast_from_origin_uses_last_origin_by_default():
    s = _series(days=60)
    sup = make_supervised(s, 6)
    model = fit_before(sup, "xgboost", SMALL_GRIDS["xgboost"][0], pd.Timestamp("2022-02-10"), seed=1)
    out = forecast_from_origin(model, s, 6)
    assert out["origin"] == s.index[-1] and out["target_time"] == s.index[-1] + pd.Timedelta(hours=6)
    assert np.isfinite(out["prediction_kw"])
    with pytest.raises(ValueError):
        forecast_from_origin(model, s, 6, origin=pd.Timestamp("2030-01-01"))
