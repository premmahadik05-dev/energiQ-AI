"""Unit tests for ml_engine.data.loading (synthetic files only)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml_engine.data.loading import (
    NUMERIC_COLUMNS,
    DataFormatError,
    read_minute_data,
    to_hourly,
)

HEADER = (
    "Date;Time;Global_active_power;Global_reactive_power;Voltage;"
    "Global_intensity;Sub_metering_1;Sub_metering_2;Sub_metering_3"
)


def _row(t: datetime, value: str = "1.000") -> str:
    return f"{t:%d/%m/%Y};{t:%H:%M:%S};{value};0.100;240.000;4.200;0.000;1.000;2.000"


def _missing_row(t: datetime) -> str:
    # Matches the real file: "?" in six columns, empty trailing field.
    return f"{t:%d/%m/%Y};{t:%H:%M:%S};?;?;?;?;?;?;"


def _write(path: Path, rows: list[str], header: str = HEADER) -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


START = datetime(2008, 3, 1, 10, 0, 0)


def test_missing_markers_become_nan_in_all_columns(tmp_path):
    rows = [_row(START), _missing_row(START + timedelta(minutes=1)), _row(START + timedelta(minutes=2))]
    df = read_minute_data(_write(tmp_path / "a.txt", rows))
    assert len(df) == 3
    assert df.iloc[1].isna().all()
    assert df.iloc[[0, 2]].notna().all().all()
    assert all(df[c].dtype == np.float32 for c in NUMERIC_COLUMNS)


def test_chunk_size_does_not_change_result(tmp_path):
    rows = [
        _missing_row(START + timedelta(minutes=i)) if i % 7 == 0 else _row(START + timedelta(minutes=i), f"{1 + i / 10:.3f}")
        for i in range(50)
    ]
    path = _write(tmp_path / "a.txt", rows)
    pd.testing.assert_frame_equal(read_minute_data(path, chunksize=3), read_minute_data(path, chunksize=10_000))


def test_wrong_header_raises(tmp_path):
    path = _write(tmp_path / "a.txt", [_row(START)], header=HEADER.replace("Voltage", "Volts"))
    with pytest.raises(DataFormatError, match="header"):
        read_minute_data(path)


def test_unparseable_timestamp_raises(tmp_path):
    rows = [_row(START), "31/02/2008;10:01:00;1.0;0.1;240.0;4.0;0.0;1.0;2.0"]
    with pytest.raises(DataFormatError, match="timestamp"):
        read_minute_data(_write(tmp_path / "a.txt", rows))


def test_garbage_numeric_token_raises_instead_of_becoming_nan(tmp_path):
    rows = [_row(START), _row(START + timedelta(minutes=1), "abc")]
    with pytest.raises(DataFormatError, match="Global_active_power"):
        read_minute_data(_write(tmp_path / "a.txt", rows))


def test_header_only_file_returns_empty_frame(tmp_path):
    df = read_minute_data(_write(tmp_path / "a.txt", []))
    assert df.empty and list(df.columns) == list(NUMERIC_COLUMNS)


def _hour_frame(n_valid: int, value: float = 2.0) -> pd.DataFrame:
    idx = pd.date_range("2008-03-01 10:00", periods=60, freq="min", name="timestamp")
    vals = np.full(60, np.nan, dtype="float32")
    vals[:n_valid] = value
    return pd.DataFrame({"Global_active_power": vals}, index=idx)


@pytest.mark.parametrize("n_valid,expect_value", [(60, True), (45, True), (44, False), (0, False)])
def test_hourly_validity_threshold(n_valid, expect_value):
    out = to_hourly(_hour_frame(n_valid))
    assert len(out) == 1
    assert out["valid_minutes"].iloc[0] == n_valid
    if expect_value:
        assert out["value"].iloc[0] == pytest.approx(2.0)
    else:
        assert np.isnan(out["value"].iloc[0])


def test_hourly_mean_ignores_missing_minutes():
    df = _hour_frame(60)
    df.iloc[:30, 0] = 1.0
    df.iloc[30:50, 0] = 3.0
    df.iloc[50:, 0] = np.nan  # 10 missing, 50 valid
    out = to_hourly(df)
    assert out["valid_minutes"].iloc[0] == 50
    assert out["value"].iloc[0] == pytest.approx((30 * 1.0 + 20 * 3.0) / 50)


def test_hourly_grid_is_regular_across_a_gap():
    a = _hour_frame(60)
    b = _hour_frame(60)
    b.index = b.index + pd.Timedelta(hours=3)  # two hours with no rows at all
    out = to_hourly(pd.concat([a, b]))
    assert len(out) == 4
    assert out["valid_minutes"].tolist() == [60, 0, 0, 60]
    assert out["value"].isna().tolist() == [False, True, True, False]


def test_hourly_rejects_unsorted_and_duplicate_index():
    df = _hour_frame(60)
    with pytest.raises(ValueError, match="sorted"):
        to_hourly(df.iloc[::-1])
    duplicated_but_sorted = pd.concat([df, df]).sort_index(kind="stable")
    assert duplicated_but_sorted.index.is_monotonic_increasing
    with pytest.raises(ValueError, match="unique"):
        to_hourly(duplicated_but_sorted)


def test_hourly_rejects_bad_threshold_and_unknown_column():
    with pytest.raises(ValueError):
        to_hourly(_hour_frame(60), min_valid_minutes=61)
    with pytest.raises(KeyError):
        to_hourly(_hour_frame(60), column="nope")
