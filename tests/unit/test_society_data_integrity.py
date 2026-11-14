"""Integrity of the PROCESSED real society data (all seven communities), checked independently of the code that built them.

Checks the contract the whole system relies on: society demand is exactly the sum of its building meters at each hour,
it is missing (never a partial sum) whenever any meter is missing, the hourly grid is complete, and the cleaning rules left no
negative, zero or long stuck readings behind. Skipped when the processed data are not present (scripts/society_prepare.py builds them).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "society" / "processed"
INDEX = PROCESSED / "societies.json"
pytestmark = pytest.mark.skipif(not INDEX.is_file(), reason="processed society data not present; run scripts/society_prepare.py")


def _keys() -> list[str]:
    return [s["key"] for s in json.loads(INDEX.read_text())["societies"]] if INDEX.is_file() else []


def _load(key: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    meters = pd.read_csv(PROCESSED / key / "meters_hourly_kwh.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    soc = pd.read_csv(PROCESSED / key / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    return meters, soc["society_kwh"], pd.read_csv(PROCESSED / key / "buildings.csv")


@pytest.mark.parametrize("key", _keys())
def test_society_total_is_the_exact_sum_of_its_meters_and_missing_otherwise(key):
    meters, total, buildings = _load(key)
    assert meters.shape[1] == len(buildings) >= 8
    all_valid = meters.notna().all(axis=1)
    expected = meters.sum(axis=1).where(all_valid)
    assert total.notna().equals(all_valid), "the total must exist exactly where every meter has a reading"
    # the files store 3 decimals for every meter and for the total, so the stored values can differ by rounding only
    tol = 0.0005 * (meters.shape[1] + 1)
    np.testing.assert_allclose(total[all_valid].to_numpy(), expected[all_valid].to_numpy(), rtol=0, atol=tol)


@pytest.mark.parametrize("key", _keys())
def test_hourly_grid_is_complete_sorted_and_unique(key):
    meters, total, _ = _load(key)
    assert meters.index.is_monotonic_increasing and meters.index.is_unique
    full = pd.date_range(meters.index[0], meters.index[-1], freq="1h")
    assert meters.index.equals(full), "no missing or duplicate timestamps"
    assert total.index.equals(meters.index)


@pytest.mark.parametrize("key", _keys())
def test_cleaning_rules_left_no_invalid_readings(key):
    meters, _, _ = _load(key)
    v = meters.to_numpy()
    assert not (v[~np.isnan(v)] <= 0).any(), "negative or exact-zero readings must have been removed"
    for c in meters.columns:  # no run of 48 or more identical readings
        s = meters[c]
        run = (s != s.shift()).cumsum()
        longest = s.groupby(run).transform("size").where(s.notna(), 0).max()
        assert longest < 48, f"{c}: {longest} identical consecutive readings"


@pytest.mark.parametrize("key", _keys())
def test_reported_valid_hours_match_the_data(key):
    entry = next(s for s in json.loads(INDEX.read_text())["societies"] if s["key"] == key)
    meters, total, _ = _load(key)
    assert entry["hours"] == len(meters) and entry["valid_hours"] == int(total.notna().sum()) and entry["buildings"] == meters.shape[1]
    assert abs(entry["mean_kw"] - float(total.mean())) < 0.01
