"""Chunked loading and hourly aggregation for the UCI household power file.

Design rules (see docs/01_dataset_suitability.md):

* Memory-safe: the file is read in chunks and stored as float32.
* Both missing-value markers seen in the real file ("?" and an empty field)
  become NaN. Any *other* non-numeric token raises, so bad data is never
  silently turned into NaN.
* Nothing is imputed here. Hourly values with too few valid minutes stay NaN.

Phase 3 builds the user-upload validator (soft handling, quality score) on top
of these primitives.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

NUMERIC_COLUMNS: tuple[str, ...] = (
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
)
EXPECTED_COLUMNS: tuple[str, ...] = ("Date", "Time", *NUMERIC_COLUMNS)
MISSING_TOKENS: tuple[str, ...] = ("?", "")
TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M:%S"
DEFAULT_MIN_VALID_MINUTES = 45


class DataFormatError(ValueError):
    """The input file does not match the expected household-power format."""


def read_minute_data(path: str | Path, chunksize: int = 200_000) -> pd.DataFrame:
    """Read the 1-minute file into a timestamp-indexed float32 DataFrame.

    Raises DataFormatError on a wrong header, an unparseable timestamp, or a
    numeric token that is neither a number nor a known missing marker.
    """
    path = Path(path)
    parts: list[pd.DataFrame] = []
    header_checked = False
    with pd.read_csv(  # the context manager closes the file even when validation raises part-way
        path,
        sep=";",
        dtype=str,
        keep_default_na=False,
        chunksize=chunksize,
        engine="c",
    ) as reader:
        for chunk in reader:
            if not header_checked:
                if tuple(chunk.columns) != EXPECTED_COLUMNS:
                    raise DataFormatError(
                        f"Unexpected header {list(chunk.columns)}; expected {list(EXPECTED_COLUMNS)}"
                    )
                header_checked = True

            ts = pd.to_datetime(chunk["Date"] + " " + chunk["Time"], format=TIMESTAMP_FORMAT, errors="coerce")
            n_bad_ts = int(ts.isna().sum())
            if n_bad_ts:
                raise DataFormatError(f"{n_bad_ts} unparseable timestamp(s) in {path.name}")

            values: dict[str, pd.Series] = {}
            for col in NUMERIC_COLUMNS:
                raw = chunk[col]
                is_missing = raw.isin(MISSING_TOKENS)
                numeric = pd.to_numeric(raw.where(~is_missing), errors="coerce")
                n_bad = int((numeric.isna() & ~is_missing).sum())
                if n_bad:
                    raise DataFormatError(f"{n_bad} non-numeric value(s) in column {col}")
                values[col] = numeric.astype("float32")

            frame = pd.DataFrame(values)
            frame.index = pd.DatetimeIndex(ts.to_numpy(), name="timestamp")
            parts.append(frame)

    if not parts:
        empty = pd.DataFrame({c: pd.Series(dtype="float32") for c in NUMERIC_COLUMNS})
        empty.index = pd.DatetimeIndex([], name="timestamp")
        return empty
    return pd.concat(parts)


def to_hourly(
    minute_df: pd.DataFrame,
    column: str = "Global_active_power",
    min_valid_minutes: int = DEFAULT_MIN_VALID_MINUTES,
) -> pd.DataFrame:
    """Hourly mean of one column, NaN where fewer than ``min_valid_minutes`` are valid.

    Returns a DataFrame indexed by hour start with columns:
      * ``value``         hourly mean (same unit as the input column)
      * ``valid_minutes`` number of non-missing minute readings in that hour

    Hours with no rows at all appear with valid_minutes == 0 and NaN value, so
    the hourly grid is regular. The input must be sorted with unique timestamps.
    """
    if not 1 <= min_valid_minutes <= 60:
        raise ValueError("min_valid_minutes must be between 1 and 60")
    if column not in minute_df.columns:
        raise KeyError(column)
    idx = minute_df.index
    if not idx.is_monotonic_increasing:
        raise ValueError("Timestamps must be sorted in increasing order")
    if idx.has_duplicates:
        raise ValueError("Timestamps must be unique")

    series = minute_df[column].astype("float64")
    grouped = series.resample("1h")
    out = pd.DataFrame(
        {
            "value": grouped.mean(),
            "valid_minutes": grouped.count().astype("int64"),
        }
    )
    out.loc[out["valid_minutes"] < min_valid_minutes, "value"] = np.nan
    return out
