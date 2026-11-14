"""The forecast range must be wider on the side where the errors are larger (regression test for a flipped sign)."""
from __future__ import annotations

import numpy as np

from backend.app.services.ml import residual_band


def _skewed_case(n=20000, seed=0):
    rng = np.random.default_rng(seed)
    pred = rng.uniform(0.5, 2.0, n)
    y = pred + rng.exponential(0.6, n) - 0.4   # actual load spikes ABOVE the prediction more often than below
    return y, pred


def test_band_is_wider_above_when_actuals_spike_upwards():
    y, pred = _skewed_case()
    lo, hi = residual_band(y, pred)
    assert hi > -lo, "upper side must be wider than the lower side for upward-skewed errors"
    assert lo < 0 < hi


def test_band_covers_about_80_percent_of_actuals():
    y, pred = _skewed_case()
    lo, hi = residual_band(y, pred)
    inside = np.mean((y >= pred + lo) & (y <= pred + hi))
    assert abs(inside - 0.80) < 0.01


def test_band_on_unseen_data_from_same_process_keeps_coverage():
    y, pred = _skewed_case(seed=1)
    lo, hi = residual_band(y, pred)
    y2, pred2 = _skewed_case(seed=2)
    assert abs(np.mean((y2 >= pred2 + lo) & (y2 <= pred2 + hi)) - 0.80) < 0.02


def test_a_perfect_model_gives_a_zero_width_band():
    pred = np.linspace(0.5, 2, 100)
    assert residual_band(pred, pred) == (0.0, 0.0)
