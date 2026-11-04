"""Versioned model artifacts on disk.

Layout:  <root>/<model_id>/metadata.json  +  model.joblib (random forest) or
model.json (xgboost). Metadata records everything needed to reproduce and audit
a run: parameters, feature names, training range, seed, library versions, a hash
of the training series, and metrics.

Security note: joblib files are pickles. Only load artifacts that this system
wrote itself; the backend never accepts model files from users.
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from xgboost import XGBRegressor

from .models import TreeModel


def series_hash(series: pd.Series) -> str:
    h = hashlib.sha256()
    h.update(str(series.index[0]).encode())
    h.update(np.ascontiguousarray(series.to_numpy(dtype="float64")).tobytes())
    return h.hexdigest()[:16]


def new_model_id(family: str, horizon: int) -> str:
    return f"{family}_h{horizon}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"


def save_tree_model(root: Path, model: TreeModel, meta: dict[str, Any]) -> str:
    model_id = meta.get("model_id") or new_model_id(model.family, meta["horizon"])
    folder = Path(root) / model_id
    folder.mkdir(parents=True, exist_ok=True)
    if model.family == "random_forest":
        joblib.dump(model.model, folder / "model.joblib", compress=3)
        artifact = "model.joblib"
    else:
        model.model.save_model(folder / "model.json")
        artifact = "model.json"
    full = {
        **meta,
        "model_id": model_id,
        "family": model.family,
        "params": model.params,
        "feature_names": model.columns,
        "seed": model.seed,
        "artifact": artifact,
        "created_at": datetime.now(UTC).isoformat(),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "xgboost": xgboost.__version__,
        },
    }
    (folder / "metadata.json").write_text(json.dumps(full, indent=2, default=str), encoding="utf-8")
    return model_id


def load_tree_model(root: Path, model_id: str) -> tuple[TreeModel, dict[str, Any]]:
    folder = Path(root) / model_id
    meta_path = folder / "metadata.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"model {model_id} not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    art = folder / meta["artifact"]
    if not art.is_file():
        raise FileNotFoundError(f"model artifact missing for {model_id}")
    tm = TreeModel(meta["family"], meta["params"], seed=meta.get("seed", 42))
    if meta["family"] == "random_forest":
        tm.model = joblib.load(art)
    else:
        booster = XGBRegressor()
        booster.load_model(art)
        tm.model = booster
    tm.columns = meta["feature_names"]
    return tm, meta
