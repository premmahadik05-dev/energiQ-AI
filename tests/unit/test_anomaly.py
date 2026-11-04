"""Anomaly detector tests on synthetic data with known structure."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_engine.anomaly.detector import AnomalyConfig, detect, deviation_stats, flat_runs, inject_synthetic, injection_check


def _series(weeks=20, noise=0.05, seed=0):
    idx = pd.date_range("2022-01-03", periods=24 * 7 * weeks, freq="h")  # starts on a Monday
    rng = np.random.default_rng(seed)
    h = idx.hour.to_numpy()
    base = 0.6 + 0.9 * np.exp(-((h - 19) ** 2) / 8) + 0.3 * (idx.day_of_week.to_numpy() >= 5)
    return pd.Series(base + rng.normal(0, noise, len(idx)), index=idx)


def test_clean_series_has_low_flag_rate():
    res = detect(_series())
    assert res.summary["flagged_pct_of_valid"] < 2.0
    assert res.summary["hours_with_baseline"] > 0


def test_deviation_stats_are_causal():
    s = _series()
    cfg = AnomalyConfig()
    d1 = deviation_stats(s, cfg)
    s2 = s.copy()
    s2.iloc[-200:] = 40.0  # change only the last 200 hours
    d2 = deviation_stats(s2, cfg)
    cut = len(s) - 200
    for col in ("z", "q_hi", "q_lo", "expected_kw", "excess_ratio"):
        assert np.allclose(d1[col].iloc[:cut].fillna(-99), d2[col].iloc[:cut].fillna(-99)), col


def test_alert_rate_is_bounded_on_stationary_heavy_tailed_load():
    idx = pd.date_range("2022-01-03", periods=24 * 7 * 40, freq="h")
    rng = np.random.default_rng(3)
    base = 0.3 + 0.6 * np.exp(-((idx.hour.to_numpy() - 19) ** 2) / 8)
    bursts = (rng.random(len(idx)) < 0.08) * rng.lognormal(0.0, 0.8, len(idx))  # bursty appliance use
    # small meter noise: a noise-free series repeats identical night-time values, which the flat-run rule rightly flags
    res = detect(pd.Series(base + bursts + rng.normal(0, 0.02, len(idx)), index=idx))
    assert res.summary["hours_flagged_by"]["flat_run"] == 0
    assert res.summary["flagged_pct_of_valid"] < 2.5


def test_injected_spike_and_drop_are_found_with_severity_and_explanation():
    s = _series()
    t_spike, t_drop = s.index[24 * 7 * 14 + 30], s.index[24 * 7 * 17 + 60]
    s[t_spike] = s[t_spike] * 5 + 1
    s[t_drop] = 0.0
    res = detect(s)
    by_start = {e["start"]: e for e in res.events}
    assert str(t_spike) in by_start and "spike" in by_start[str(t_spike)]["types"]
    assert by_start[str(t_spike)]["severity"] in ("medium", "high")
    assert str(t_drop) in by_start and "drop" in by_start[str(t_drop)]["types"]
    assert "typical" in by_start[str(t_spike)]["explanation"] and "usual range" in by_start[str(t_spike)]["explanation"]


def test_flat_run_rule_needs_min_length_and_ignores_nan():
    idx = pd.date_range("2022-01-01", periods=30, freq="h")
    v = np.arange(30, dtype=float)
    v[5:11] = 0.36  # 6 identical hours
    v[15:19] = 0.5  # only 4 identical hours
    v[22:28] = np.nan  # gap, not a flat run
    fr = flat_runs(pd.Series(v, index=idx), 6)
    assert fr.iloc[5:11].all() and not fr.iloc[15:19].any() and not fr.iloc[22:28].any()
    s = _series()
    s.iloc[24 * 7 * 10: 24 * 7 * 10 + 30] = 0.36
    ev = [e for e in detect(s).events if "flat_run" in e["types"]]
    assert ev and ev[0]["severity"] == "high" and ev[0]["hours"] >= 30  # >= 24 identical hours is high


def test_missing_hours_are_never_flagged():
    s = _series()
    s.iloc[24 * 7 * 12: 24 * 7 * 12 + 20] = np.nan
    res = detect(s)
    assert not res.hourly.loc[s.isna(), "anomalous"].any()


def test_insufficient_history_raises():
    with pytest.raises(ValueError, match="Insufficient"):
        detect(_series(weeks=3))


def test_consecutive_flagged_hours_merge_into_one_event():
    s = _series()
    i = 24 * 7 * 13 + 40
    s.iloc[i: i + 3] = [6.0, 6.5, 6.2]
    res = detect(s)
    ev = [e for e in res.events if e["start"] == str(s.index[i])]
    assert len(ev) == 1 and ev[0]["flagged_hours"] == 3


def test_injection_check_is_labelled_synthetic_and_finds_large_faults():
    out = injection_check(_series(weeks=24), n=20, seed=1)
    assert out["synthetic"] is True
    assert out["kinds"]["spike_x3"]["recall_on_injected"] >= 0.9
    assert out["kinds"]["drop_to_5pct"]["recall_on_injected"] >= 0.5
    assert out["kinds"]["flat_8h"]["recall_on_injected"] >= 0.9
    for k in out["kinds"].values():
        assert k["flag_rate_untouched_pct"] < 3.0


def test_inject_synthetic_leaves_original_untouched():
    s = _series()
    before = s.copy()
    mod, marked = inject_synthetic(s, 5, "spike", seed=2)
    assert s.equals(before) and len(marked) == 5 and (mod[marked] != s[marked]).all()
