"""Lightweight CPU LSTM that predicts 1 h, 6 h and 24 h ahead in one network.

Sized for an 8 GB laptop: one LSTM layer (hidden 32), a 168-hour lookback and a
small head. Leak-free by construction:

* the scaler (mean/std) and the hour-of-week fill values come from rows whose
  target is before the cutoff only;
* the loss uses only targets whose time is before the cutoff;
* missing inputs are filled with the training hour-of-week mean and flagged with
  a "missing" channel; missing TARGETS are never filled, they are masked out of
  the loss and of the scoring.

torch is imported lazily so the rest of ml_engine works without it.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ml_engine.features.builder import regularize

HORIZONS = (1, 6, 24)


@dataclass
class LSTMConfig:
    lookback: int = 168
    hidden: int = 32
    batch_size: int = 256
    max_epochs: int = 12
    patience: int = 3
    lr: float = 2e-3
    seed: int = 42
    threads: int = 2


def _torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyTorch is not installed; the LSTM model is unavailable") from exc
    return torch


def _make_net(torch, n_in: int, hidden: int, n_cal: int, n_out: int):
    nn = torch.nn

    class LoadLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(n_in, hidden, 1, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden + n_cal, 32), nn.ReLU(), nn.Linear(32, n_out))

        def forward(self, x, cal):
            out, _ = self.lstm(x)
            return self.head(torch.cat([out[:, -1], cal], dim=1))

    return LoadLSTM()


def _cal(ts: pd.DatetimeIndex) -> np.ndarray:
    return np.stack(
        [np.sin(2 * np.pi * ts.hour / 24), np.cos(2 * np.pi * ts.hour / 24),
         np.sin(2 * np.pi * ts.day_of_week / 7), np.cos(2 * np.pi * ts.day_of_week / 7)], axis=1
    ).astype("float32")


class LSTMForecaster:
    def __init__(self, cfg: LSTMConfig | None = None):
        self.cfg = cfg or LSTMConfig()
        self.net = None
        self.mean = self.std = None
        self.how_mean: np.ndarray | None = None
        self.trained_epochs = 0

    # ---- data preparation -------------------------------------------------
    def _fit_stats(self, s: pd.Series, cutoff: pd.Timestamp) -> None:
        past = s[s.index < cutoff].dropna()
        if len(past) < 24 * 14:
            raise ValueError("Insufficient training history: fewer than 14 days of valid hours")
        self.mean, self.std = float(past.mean()), float(past.std() or 1.0)
        how = past.index.day_of_week * 24 + past.index.hour
        table = pd.Series(past.to_numpy()).groupby(np.asarray(how)).mean().reindex(range(168))
        self.how_mean = table.fillna(self.mean).to_numpy()

    def _matrices(self, series: pd.Series):
        s = regularize(series)
        idx, n = s.index, len(s)
        v = s.to_numpy(dtype="float64")
        how = np.asarray(idx.day_of_week * 24 + idx.hour)
        filled = np.where(np.isnan(v), self.how_mean[how], v)
        feats = np.concatenate(
            [(((filled - self.mean) / self.std)[:, None]).astype("float32"),
             np.isnan(v).astype("float32")[:, None], _cal(idx)], axis=1)
        y = np.full((n, len(HORIZONS)), np.nan, dtype="float32")
        for j, h in enumerate(HORIZONS):
            y[: n - h, j] = (v[h:] - self.mean) / self.std
        cal = np.concatenate([_cal(idx + pd.Timedelta(hours=h)) for h in HORIZONS], axis=1)
        return idx, feats, y, cal

    def _windows(self, feats: np.ndarray):
        return np.lib.stride_tricks.sliding_window_view(feats, self.cfg.lookback, axis=0)  # (P, C, L)

    def _batch(self, torch, win, cal, pos):
        x = torch.from_numpy(np.ascontiguousarray(win[pos].transpose(0, 2, 1)))
        c = torch.from_numpy(cal[pos + self.cfg.lookback - 1])
        return x, c

    # ---- training ---------------------------------------------------------
    def fit(self, series: pd.Series, cutoff: pd.Timestamp,
            val_range: tuple[pd.Timestamp, pd.Timestamp] | None = None, epochs: int | None = None,
            log=None) -> dict:
        torch = _torch()
        cfg = self.cfg
        torch.set_num_threads(cfg.threads)
        torch.manual_seed(cfg.seed)
        rng = np.random.default_rng(cfg.seed)
        self._fit_stats(regularize(series), pd.Timestamp(cutoff))
        idx, feats, y, cal = self._matrices(series)
        L = cfg.lookback
        horizon_td = [pd.Timedelta(hours=h) for h in HORIZONS]
        y_train = y.copy()
        for j, td in enumerate(horizon_td):
            y_train[~np.asarray((idx + td) < cutoff), j] = np.nan
        win = self._windows(feats)
        pos_all = np.arange(win.shape[0])
        origin_rows = pos_all + L - 1
        train_pos = pos_all[~np.isnan(y_train[origin_rows]).all(axis=1)]
        if len(train_pos) < 200:
            raise ValueError("Insufficient training history: fewer than 200 usable training windows")
        val_pos = y_val = None
        if val_range is not None:
            y_val = y.copy()
            for j, td in enumerate(horizon_td):
                t = idx + td
                y_val[~np.asarray((t >= val_range[0]) & (t < val_range[1])), j] = np.nan
            val_pos = pos_all[~np.isnan(y_val[origin_rows]).all(axis=1)]

        self.net = _make_net(torch, feats.shape[1], cfg.hidden, cal.shape[1], len(HORIZONS))
        opt = torch.optim.Adam(self.net.parameters(), lr=cfg.lr)
        huber = torch.nn.SmoothL1Loss(reduction="none")
        history, best, best_state, bad = [], np.inf, None, 0
        n_epochs = epochs if epochs is not None else cfg.max_epochs
        for epoch in range(1, n_epochs + 1):
            self.net.train()
            order = rng.permutation(train_pos)
            total, count = 0.0, 0
            for i in range(0, len(order), cfg.batch_size):
                pos = order[i: i + cfg.batch_size]
                x, c = self._batch(torch, win, cal, pos)
                target = torch.from_numpy(y_train[pos + L - 1])
                mask = ~torch.isnan(target)
                pred = self.net(x, c)
                loss = (huber(pred, torch.nan_to_num(target)) * mask).sum() / mask.sum().clamp(min=1)
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                opt.step()
                total += float(loss.detach()) * len(pos)
                count += len(pos)
            rec = {"epoch": epoch, "train_loss": total / count}
            if val_pos is not None and len(val_pos):
                maes = self._val_mae_kw(torch, win, cal, y_val, val_pos)
                rec["val_mae_kw"] = {f"h{h}": maes[j] for j, h in enumerate(HORIZONS)}
                score = float(np.mean(maes))
                rec["val_mae_mean_kw"] = score
                if score < best - 1e-6:
                    best, bad = score, 0
                    best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                    rec["best"] = True
                else:
                    bad += 1
            history.append(rec)
            if log is not None:
                log(rec)
            if epochs is None and val_pos is not None and bad >= cfg.patience:
                break
        if best_state is not None and epochs is None:
            self.net.load_state_dict(best_state)
            self.trained_epochs = 1 + int(np.argmin([r.get("val_mae_mean_kw", np.inf) for r in history]))
        else:
            self.trained_epochs = len(history)
        return {"history": history, "best_epoch": self.trained_epochs, "train_windows": int(len(train_pos)),
                "val_windows": int(len(val_pos)) if val_pos is not None else 0}

    def _val_mae_kw(self, torch, win, cal, y_val, val_pos) -> list[float]:
        self.net.eval()
        preds = []
        with torch.no_grad():
            for i in range(0, len(val_pos), 1024):
                pos = val_pos[i: i + 1024]
                x, c = self._batch(torch, win, cal, pos)
                preds.append(self.net(x, c).numpy())
        p = np.concatenate(preds)
        t = y_val[val_pos + self.cfg.lookback - 1]
        out = []
        for j in range(len(HORIZONS)):
            ok = ~np.isnan(t[:, j])
            out.append(float(np.abs(p[ok, j] - t[ok, j]).mean() * self.std) if ok.any() else float("nan"))
        return out

    # ---- inference --------------------------------------------------------
    def predict(self, series: pd.Series, origins: pd.DatetimeIndex | None = None) -> pd.DataFrame:
        """Predictions in kW, one row per origin, columns h1, h6, h24."""
        if self.net is None:
            raise RuntimeError("model is not fitted")
        torch = _torch()
        torch.set_num_threads(self.cfg.threads)
        idx, feats, _, cal = self._matrices(series)
        L = self.cfg.lookback
        win = self._windows(feats)
        valid_origins = idx[L - 1:]
        pos = np.arange(win.shape[0])
        if origins is not None:
            pos = valid_origins.get_indexer(pd.DatetimeIndex(origins))
            if (pos < 0).any():
                raise ValueError("some origins lack a full lookback window")
        self.net.eval()
        out = []
        with torch.no_grad():
            for i in range(0, len(pos), 1024):
                x, c = self._batch(torch, win, cal, pos[i: i + 1024])
                out.append(self.net(x, c).numpy())
        arr = np.concatenate(out) * self.std + self.mean if out else np.empty((0, len(HORIZONS)))
        return pd.DataFrame(arr, index=valid_origins[pos], columns=[f"h{h}" for h in HORIZONS])

    # ---- persistence ------------------------------------------------------
    def save(self, folder: Path, meta: dict) -> None:
        torch = _torch()
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        torch.save(self.net.state_dict(), folder / "model.pt")
        (folder / "metadata.json").write_text(json.dumps({
            **meta, "config": asdict(self.cfg), "mean": self.mean, "std": self.std,
            "how_mean": self.how_mean.tolist(), "trained_epochs": self.trained_epochs,
            "horizons": list(HORIZONS), "family": "lstm",
        }, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, folder: Path) -> LSTMForecaster:
        torch = _torch()
        folder = Path(folder)
        meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        obj = cls(LSTMConfig(**meta["config"]))
        obj.mean, obj.std = meta["mean"], meta["std"]
        obj.how_mean = np.asarray(meta["how_mean"])
        obj.trained_epochs = meta["trained_epochs"]
        obj.net = _make_net(torch, 6, obj.cfg.hidden, 4 * len(HORIZONS), len(HORIZONS))
        obj.net.load_state_dict(torch.load(folder / "model.pt", map_location="cpu", weights_only=True))
        return obj
