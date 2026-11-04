"""SHAP explanations, tariff/cost maths and recommendations (synthetic data with known structure)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_engine.explainability.shap_tree import explain_rows, global_importance, group_of, narrative
from ml_engine.features.builder import make_supervised
from ml_engine.optimization.recommendations import RecommendationConfig, cheapest_window, recommend
from ml_engine.optimization.tariff import DEMO_TARIFF, Tariff, TariffError, cost_of_series
from ml_engine.pipeline import fit_before

XGB = {"n_estimators": 60, "max_depth": 4, "learning_rate": 0.1}
RF = {"n_estimators": 20, "max_depth": 6, "min_samples_leaf": 5, "max_features": 0.5}


def _load(days=120, seed=0, evening=1.2, base=0.3, noise=0.05):
    idx = pd.date_range("2022-01-03", periods=24 * days, freq="h")  # Monday
    rng = np.random.default_rng(seed)
    h = idx.hour.to_numpy()
    v = base + evening * np.exp(-((h - 19) ** 2) / 6) + rng.normal(0, noise, len(idx))
    return pd.Series(np.clip(v, 0.05, None), index=idx)


# ------------------------------------------------------------------ SHAP
def test_shap_contributions_add_up_and_rank_sensible_features():
    s = _load(100)
    sup = make_supervised(s, 6)
    model = fit_before(sup, "xgboost", XGB, pd.Timestamp("2022-03-20"), seed=1)
    X = sup.X.dropna(subset=["lag_0"]).iloc[-48:]
    out = explain_rows(model, X)
    assert len(out) == 48
    for e in out:
        total = e["base_value_kw"] + sum(e["grouped_kw"].values())
        assert abs(total - e["prediction_kw"]) < 2e-3 and e["additivity_error_kw"] < 2e-3
        assert len(e["drivers"]) == 6
    imp = global_importance(model, sup.X.dropna(subset=["lag_0"]).iloc[-2000:])
    assert imp["share_pct"].sum() == pytest.approx(100.0)
    # the daily shape is carried by the hour / yesterday features, not by month (constant here)
    top = set(imp["feature"].head(5))
    assert top & {"hour", "hour_sin", "hour_cos", "seasonal_24", "lag_23"}
    assert imp.set_index("feature").loc["month", "share_pct"] < 5


def test_shap_rejects_random_forest_and_narrative_is_numeric():
    s = _load(60)
    sup = make_supervised(s, 1)
    rf = fit_before(sup, "random_forest", RF, pd.Timestamp("2022-02-10"), seed=1)
    with pytest.raises(ValueError, match="XGBoost"):
        explain_rows(rf, sup.X.iloc[-5:])
    xg = fit_before(sup, "xgboost", XGB, pd.Timestamp("2022-02-10"), seed=1)
    exp = explain_rows(xg, sup.X.dropna(subset=["lag_0"]).iloc[-1:])[0]
    text = narrative(exp, 1)
    assert f"{exp['prediction_kw']:.2f} kW" in text
    assert group_of("lag_5") == "Recent consumption" and group_of("seasonal_168").startswith("Same time")


# ------------------------------------------------------------------ tariff / cost
def test_tariff_validation():
    ok = [0.1] * 24
    with pytest.raises(TariffError):
        Tariff("x", "EUR", [0.1] * 23, ok)
    with pytest.raises(TariffError):
        Tariff("x", "EUR", ok, [-0.1] + [0.1] * 23)
    with pytest.raises(TariffError):
        Tariff("x", "EUR", ok, [float("nan")] + [0.1] * 23)
    with pytest.raises(TariffError):
        Tariff("x", "EUR", ok, ok, daily_fixed_charge=-1)
    with pytest.raises(TariffError):
        Tariff.from_dict({"name": "x"})
    assert Tariff.from_dict(DEMO_TARIFF.to_dict()) == DEMO_TARIFF and DEMO_TARIFF.is_demo


def test_cost_known_values_and_missing_hours_not_costed():
    idx = pd.date_range("2022-01-03", periods=24, freq="h")  # a Monday
    s = pd.Series(1.0, index=idx)
    c = cost_of_series(s, DEMO_TARIFF)
    assert c["energy_kwh"] == pytest.approx(24.0) and c["energy_cost"] == pytest.approx(sum(DEMO_TARIFF.weekday_rates))
    s2 = s.copy()
    s2.iloc[:6] = np.nan
    c2 = cost_of_series(s2, DEMO_TARIFF)
    assert c2["valid_hours"] == 18 and c2["energy_kwh"] == pytest.approx(18.0)
    fixed = Tariff("f", "EUR", [0.1] * 24, [0.1] * 24, daily_fixed_charge=0.5)
    assert cost_of_series(s, fixed)["total_cost"] == pytest.approx(2.4 + 0.5)
    assert cost_of_series(pd.Series(dtype=float, index=pd.DatetimeIndex([])), fixed)["total_cost"] == 0.0
    sat = pd.Series(1.0, index=pd.date_range("2022-01-08", periods=24, freq="h"))
    assert cost_of_series(sat, DEMO_TARIFF)["energy_cost"] == pytest.approx(sum(DEMO_TARIFF.weekend_rates))


# ------------------------------------------------------------------ recommendations
def test_peak_shift_recommendation_maths_matches_hand_calculation():
    s = _load(days=60)
    res = recommend(s, DEMO_TARIFF)
    rec = next(r for r in res["recommendations"] if r["id"] == "shift_peak_load")
    ev = rec["evidence"]
    assert 17 in ev["peak_hours"] and ev["dearest_rate_per_kwh"] == 0.30 and ev["cheapest_rate_per_kwh"] == 0.12
    days = res["window"]["days_covered"]
    expected = 0.10 * ev["peak_kwh_in_window"] * (30 / days) * (0.30 - 0.12)
    assert rec["scenario"]["saving_per_30d"] == pytest.approx(expected)
    assert any("DEMO" in c for c in rec["caveats"]) and "scenario" in rec["caveats"][0].lower()


def test_baseload_forecast_anomaly_and_gap_recommendations_trigger_only_when_justified():
    flat = _load(days=60, evening=0.05, base=1.0)  # high constant floor, no evening peak
    ids = {r["id"] for r in recommend(flat, DEMO_TARIFF)["recommendations"]}
    assert "reduce_baseload" in ids and "shift_peak_load" not in ids

    s = _load(days=60)
    fidx = pd.date_range(s.index[-1] + pd.Timedelta(hours=1), periods=24, freq="h")
    high = pd.Series(0.4, index=fidx)
    high[fidx[10]] = 5.0
    assert "forecast_peak" in {r["id"] for r in recommend(s, DEMO_TARIFF, forecast_kw=high)["recommendations"]}
    low = pd.Series(0.2, index=fidx)
    assert "forecast_peak" not in {r["id"] for r in recommend(s, DEMO_TARIFF, forecast_kw=low)["recommendations"]}

    end = s.index[-1]
    ev = [{"start": str(end - pd.Timedelta(days=2)), "end": str(end - pd.Timedelta(days=2)), "severity_level": 3, "peak_excess_ratio": 3.0, "explanation": "x"},
          {"start": str(end - pd.Timedelta(days=60)), "end": str(end - pd.Timedelta(days=60)), "severity_level": 3, "peak_excess_ratio": 9.0, "explanation": "old"}]
    rec = next(r for r in recommend(s, DEMO_TARIFF, anomaly_events=ev)["recommendations"] if r["id"] == "review_anomalies")
    assert rec["evidence"]["high_severity_events_30d"] == 1  # the 60-day-old event is ignored
    assert "review_anomalies" not in {r["id"] for r in recommend(s, DEMO_TARIFF, anomaly_events=[ev[1]])["recommendations"]}

    gappy = s.copy()
    gappy.iloc[-24 * 6:] = np.nan
    assert "data_gaps" in {r["id"] for r in recommend(gappy, DEMO_TARIFF)["recommendations"]}


def test_not_enough_data_returns_message_not_invented_advice():
    res = recommend(_load(days=5), DEMO_TARIFF)
    assert res["recommendations"] == [] and "at least" in res["message"]


def test_flat_tariff_has_no_load_shifting_advice():
    flat = Tariff("flat", "EUR", [0.2] * 24, [0.2] * 24)
    ids = {r["id"] for r in recommend(_load(days=60), flat)["recommendations"]}
    assert "shift_peak_load" not in ids


def test_cheapest_window_scheduler():
    r = cheapest_window(DEMO_TARIFF, pd.Timestamp("2022-01-03 16:30"), duration_h=3, power_kw=2.0)
    assert r["best_start"] == "2022-01-03 23:00:00"  # 23:00-02:00 is all off-peak; ties go to the earliest start
    assert r["cost"] == pytest.approx(2.0 * 3 * 0.12)
    assert r["saving_vs_first_hour"] > 0 and r["cost_at_worst_start"] >= r["cost_if_started_first_hour"] - 1e-9
    assert r["energy_kwh"] == 6.0 and r["is_demo_tariff"]
    with pytest.raises(ValueError):
        cheapest_window(DEMO_TARIFF, pd.Timestamp("2022-01-03"), duration_h=30, power_kw=1)
    with pytest.raises(ValueError):
        cheapest_window(DEMO_TARIFF, pd.Timestamp("2022-01-03"), duration_h=2, power_kw=0)
    cfg = RecommendationConfig()
    assert cfg.shift_fraction == 0.10
