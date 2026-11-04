"""Feature leakage and split tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_engine.evaluation.splits import BENCHMARK_PLAN, block_mask, expanding_folds, fractional_plan, train_mask
from ml_engine.features.builder import common_eval_mask, feature_names, make_features, make_supervised

IDX = pd.date_range("2022-01-01", periods=24 * 60, freq="h")


def _series(seed=0, nan_frac=0.0):
    rng = np.random.default_rng(seed)
    v = 1 + 0.5 * np.sin(np.arange(len(IDX)) * 2 * np.pi / 24) + rng.normal(0, 0.1, len(IDX))
    s = pd.Series(v, index=IDX)
    if nan_frac:
        s[rng.random(len(s)) < nan_frac] = np.nan
    return s


@pytest.mark.parametrize("h", [1, 6, 24])
def test_target_alignment(h):
    s = _series()
    sup = make_supervised(s, h)
    t = IDX[500]
    assert sup.y.loc[t] == s.loc[t + pd.Timedelta(hours=h)]
    assert sup.target_time[500] == t + pd.Timedelta(hours=h)
    assert sup.y.iloc[-h:].isna().all()  # origins whose target is in the future


@pytest.mark.parametrize("h", [1, 6, 24])
def test_features_do_not_use_future_values(h):
    s = _series()
    origin = IDX[800]
    base = make_features(s, h).loc[origin]
    tampered = s.copy()
    tampered[tampered.index > origin] = 999.0  # change every future value
    after = make_features(tampered, h).loc[origin]
    pd.testing.assert_series_equal(base, after)


def test_seasonal_features_point_at_target_minus_offset():
    s = _series()
    h, origin = 6, IDX[700]
    X = make_features(s, h)
    tgt = origin + pd.Timedelta(hours=h)
    assert X.loc[origin, "seasonal_24"] == s.loc[tgt - pd.Timedelta(hours=24)]
    assert X.loc[origin, "seasonal_168"] == s.loc[tgt - pd.Timedelta(hours=168)]
    assert X.loc[origin, "lag_3"] == s.loc[origin - pd.Timedelta(hours=3)]


def test_calendar_features_describe_target_time():
    X = make_features(_series(), 6)
    origin = IDX[300]
    tgt = origin + pd.Timedelta(hours=6)
    assert X.loc[origin, "hour"] == tgt.hour and X.loc[origin, "dow"] == tgt.day_of_week
    assert X.loc[origin, "is_weekend"] == int(tgt.day_of_week >= 5)


def test_horizon_above_seasonal_offset_rejected():
    with pytest.raises(ValueError):
        make_features(_series(), 25)
    with pytest.raises(ValueError):
        make_features(_series(), 0)


def test_columns_and_common_mask_with_missing_data():
    sup = make_supervised(_series(nan_frac=0.1), 1)
    assert list(sup.X.columns) == feature_names()
    m = common_eval_mask(sup)
    assert m.sum() < len(m)
    assert sup.y[m].notna().all() and sup.X.loc[m, "lag_0"].notna().all()


def test_expanding_folds_never_leak_and_cover_benchmark_period():
    folds = BENCHMARK_PLAN.folds
    assert len(folds) == 8
    assert folds[0].test_start == pd.Timestamp("2008-01-01") and folds[-1].test_end == pd.Timestamp("2009-12-31 23:00")
    tt = pd.date_range("2006-12-16", "2010-11-26", freq="h")
    for a, b in zip(folds, folds[1:]):
        assert a.test_end < b.test_start  # blocks do not overlap
    for f in folds:
        tr, te = train_mask(tt, f.test_start), block_mask(tt, f.test_start, f.test_end)
        assert not (tr & te).any()
        assert tt[tr].max() < f.test_start <= tt[te].min()
    assert BENCHMARK_PLAN.test_start > folds[-1].test_end  # final test is after all CV data


def test_expanding_folds_generic():
    f = expanding_folds("2020-01-01", "2020-12-31 23:00", 4)
    assert [x.test_start.month for x in f] == [1, 5, 9]


def test_fractional_plan_orders_boundaries():
    p = fractional_plan(pd.date_range("2022-01-01", periods=24 * 200, freq="h"))
    assert p.val_start < p.test_start <= p.test_end
    with pytest.raises(ValueError):
        fractional_plan(IDX, test_frac=0.6)
