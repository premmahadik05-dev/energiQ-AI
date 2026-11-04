"""Chronological splits and expanding-window cross-validation.

Everything is defined by TARGET time (origin + horizon): a training row is
usable only if its target lies strictly before the evaluation block starts, so
no label from the evaluation period can leak into training. There are no random
splits anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Fold:
    name: str
    test_start: pd.Timestamp
    test_end: pd.Timestamp  # inclusive


def expanding_folds(first_test_start: str, last_test_end: str, block_months: int = 3) -> list[Fold]:
    """Consecutive evaluation blocks; the training set grows before each block."""
    folds: list[Fold] = []
    start = pd.Timestamp(first_test_start)
    end_limit = pd.Timestamp(last_test_end)
    i = 1
    while start <= end_limit:
        end = min(start + pd.DateOffset(months=block_months) - pd.Timedelta(hours=1), end_limit)
        folds.append(Fold(f"fold{i}", start, end))
        start = start + pd.DateOffset(months=block_months)
        i += 1
    return folds


def train_mask(target_time: pd.DatetimeIndex, test_start: pd.Timestamp) -> np.ndarray:
    return np.asarray(target_time < test_start)


def block_mask(target_time: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> np.ndarray:
    return np.asarray((target_time >= start) & (target_time <= end))


@dataclass(frozen=True)
class SplitPlan:
    """Final protocol: select on folds/validation, refit on everything before test, score on test."""

    test_start: pd.Timestamp
    test_end: pd.Timestamp
    val_start: pd.Timestamp  # start of the validation block used for LSTM early stopping
    folds: tuple[Fold, ...] = ()


BENCHMARK_PLAN = SplitPlan(
    test_start=pd.Timestamp("2010-01-01 00:00"),
    test_end=pd.Timestamp("2010-11-26 23:00"),
    val_start=pd.Timestamp("2009-07-01 00:00"),
    folds=tuple(expanding_folds("2008-01-01 00:00", "2009-12-31 23:00", 3)),
)


def fractional_plan(valid_index: pd.DatetimeIndex, test_frac: float = 0.2, val_frac: float = 0.15) -> SplitPlan:
    """Plan for user datasets: last ``test_frac`` of the timeline is the test set."""
    if not 0 < test_frac < 0.5 or not 0 < val_frac < 0.5 or test_frac + val_frac >= 0.8:
        raise ValueError("invalid split fractions")
    t0, t1 = valid_index.min(), valid_index.max()
    span = t1 - t0
    test_start = (t0 + span * (1 - test_frac)).ceil("h")
    val_start = (t0 + span * (1 - test_frac - val_frac)).ceil("h")
    return SplitPlan(test_start=test_start, test_end=t1, val_start=val_start, folds=())
