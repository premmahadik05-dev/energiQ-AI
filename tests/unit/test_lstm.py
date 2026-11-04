"""LSTM tests on small synthetic data (skipped automatically if PyTorch is missing)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from ml_engine.forecasting.lstm import HORIZONS, LSTMConfig, LSTMForecaster  # noqa: E402

CFG = LSTMConfig(lookback=48, hidden=16, batch_size=128, max_epochs=6, patience=2, lr=5e-3, seed=7, threads=1)


def _series(days=90, noise=0.08, seed=0, nan_frac=0.0):
    idx = pd.date_range("2022-01-01", periods=24 * days, freq="h")
    rng = np.random.default_rng(seed)
    h = idx.hour.to_numpy()
    v = 1.0 + 0.8 * np.exp(-((h - 19) ** 2) / 8) + 0.3 * (idx.day_of_week.to_numpy() >= 5) + rng.normal(0, noise, len(idx))
    s = pd.Series(v, index=idx)
    if nan_frac:
        s[rng.random(len(s)) < nan_frac] = np.nan
    return s


def test_fit_predict_shapes_and_learns_daily_pattern():
    s = _series(nan_frac=0.02)
    cut = pd.Timestamp("2022-03-01")
    m = LSTMForecaster(CFG)
    info = m.fit(s, cut, val_range=(cut, cut + pd.Timedelta(days=14)))
    assert info["train_windows"] > 1000 and 1 <= info["best_epoch"] <= CFG.max_epochs
    assert all(np.isfinite(r["train_loss"]) for r in info["history"])
    pred = m.predict(s)
    assert list(pred.columns) == ["h1", "h6", "h24"] and np.isfinite(pred.to_numpy()).all()
    assert pred.index[0] == s.index[CFG.lookback - 1]
    # h=24 forecast on held-out days must beat a constant-mean forecast (the series has a strong daily shape)
    test_origins = pred.index[(pred.index >= cut + pd.Timedelta(days=14)) & (pred.index + pd.Timedelta(hours=24) <= s.index[-1])]
    y = s.reindex(test_origins + pd.Timedelta(hours=24)).to_numpy()
    ok = ~np.isnan(y)
    mae_model = np.abs(pred.loc[test_origins, "h24"].to_numpy()[ok] - y[ok]).mean()
    mae_mean = np.abs(s[s.index < cut].mean() - y[ok]).mean()
    assert mae_model < mae_mean


def test_leakage_canary_future_values_do_not_change_model():
    s = _series(days=60)
    cut = pd.Timestamp("2022-02-10")
    a = LSTMForecaster(CFG)
    a.fit(s, cut, epochs=2)
    s2 = s.copy()
    s2[s2.index >= cut] = 99.0
    b = LSTMForecaster(CFG)
    b.fit(s2, cut, epochs=2)
    for (ka, va), (kb, vb) in zip(a.net.state_dict().items(), b.net.state_dict().items()):
        assert ka == kb and torch.equal(va, vb), f"weights differ in {ka}: future data leaked into training"
    assert a.mean == b.mean and a.std == b.std and np.array_equal(a.how_mean, b.how_mean)


def test_save_load_roundtrip_gives_identical_predictions(tmp_path):
    s = _series(days=45)
    m = LSTMForecaster(CFG)
    m.fit(s, pd.Timestamp("2022-02-01"), epochs=2)
    m.save(tmp_path / "lstm1", {"model_id": "lstm1", "unit": "kW"})
    loaded = LSTMForecaster.load(tmp_path / "lstm1")
    assert np.allclose(m.predict(s).to_numpy(), loaded.predict(s).to_numpy(), atol=1e-6)
    assert loaded.trained_epochs == m.trained_epochs


def test_insufficient_history_and_unfitted_errors():
    s = _series(days=60)
    with pytest.raises(ValueError, match="Insufficient"):
        LSTMForecaster(CFG).fit(s, pd.Timestamp("2022-01-05"), epochs=1)
    with pytest.raises(RuntimeError, match="not fitted"):
        LSTMForecaster(CFG).predict(s)


def test_predict_rejects_origins_without_full_lookback():
    s = _series(days=45)
    m = LSTMForecaster(CFG)
    m.fit(s, pd.Timestamp("2022-02-01"), epochs=1)
    with pytest.raises(ValueError, match="lookback"):
        m.predict(s, origins=pd.DatetimeIndex([s.index[5]]))
    out = m.predict(s, origins=pd.DatetimeIndex([s.index[100], s.index[200]]))
    assert len(out) == 2 and HORIZONS == (1, 6, 24)
