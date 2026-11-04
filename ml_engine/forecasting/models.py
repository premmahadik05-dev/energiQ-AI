"""Forecasting models: baselines, Random Forest and XGBoost.

All models share one interface over the feature matrix built by
``ml_engine.features.builder``:  fit(X, y) -> self,  predict(X) -> ndarray.
Baselines read a single feature column, so they use exactly the same inputs
(and the same evaluation rows) as the learned models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

RF_GRID: list[dict[str, Any]] = [
    {"n_estimators": 150, "max_depth": 12, "min_samples_leaf": 5, "max_features": 0.5},
    {"n_estimators": 150, "max_depth": None, "min_samples_leaf": 10, "max_features": 0.5},
]
XGB_GRID: list[dict[str, Any]] = [
    {"n_estimators": 300, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5},
    {"n_estimators": 400, "max_depth": 6, "learning_rate": 0.03, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5},
    {"n_estimators": 250, "max_depth": 3, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 10},
]


class BaselineModel:
    """Predicts the value found in one feature column (naive / seasonal naive)."""

    def __init__(self, name: str, column: str):
        self.name, self.column, self.family = name, column, "baseline"

    def fit(self, X: pd.DataFrame, y) -> BaselineModel:
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X[self.column].to_numpy(dtype="float64")


def baselines() -> list[BaselineModel]:
    return [
        BaselineModel("naive", "lag_0"),
        BaselineModel("seasonal_naive_24", "seasonal_24"),
        BaselineModel("seasonal_naive_168", "seasonal_168"),
    ]


@dataclass
class TreeModel:
    family: str  # "random_forest" | "xgboost"
    params: dict[str, Any]
    seed: int = 42
    name: str = ""
    model: Any = field(default=None, repr=False)

    def __post_init__(self):
        self.name = self.name or self.family

    def _build(self):
        if self.family == "random_forest":
            return RandomForestRegressor(random_state=self.seed, n_jobs=2, **self.params)
        if self.family == "xgboost":
            return XGBRegressor(tree_method="hist", random_state=self.seed, n_jobs=2, **self.params)
        raise ValueError(f"unknown family {self.family}")

    def fit(self, X: pd.DataFrame, y) -> TreeModel:
        y = np.asarray(y, dtype="float64")
        keep = np.isfinite(y)
        if keep.sum() < 50:
            raise ValueError("Insufficient training history: fewer than 50 labelled rows")
        self.model = self._build()
        self.model.fit(X.loc[keep].to_numpy(dtype="float32"), y[keep])
        self.columns = list(X.columns)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("model is not fitted")
        return np.asarray(self.model.predict(X[self.columns].to_numpy(dtype="float32")), dtype="float64")
