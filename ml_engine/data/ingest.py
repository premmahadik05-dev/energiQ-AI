"""Generic, chunked CSV ingestion for electricity consumption data.

Used by both the web application (user uploads) and the benchmark, so the same
validation rules apply everywhere. Output is a regular hourly series in kW plus
a validation report with every issue counted (nothing is dropped silently).

Rules:
* Missing markers ("", "?", "NA", ...) become NaN; other non-numeric tokens become
  NaN and are counted as invalid.
* Negative consumption is invalid: set to NaN and counted.
* Duplicate timestamps keep the first row; unsorted input is sorted; both counted.
* Data coarser than hourly is rejected (hourly forecasting needs <= 1 h data).
* Sub-hourly data is averaged to hourly; an hour is valid only if at least
  ``min_valid_fraction`` of its expected readings exist (UCI: 45 of 60 minutes).
* Nothing is imputed.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .quality import quality_score

MISSING_TOKENS = frozenset({"", "?", "na", "n/a", "nan", "null", "none", "-", "--"})
POWER_UNITS = {"kw": 1.0, "w": 0.001, "mw": 1000.0}  # -> kW
ENERGY_UNITS = {"kwh": 1.0, "wh": 0.001, "mwh": 1000.0}  # energy per reading interval
MAX_UNPARSEABLE_TS_FRACTION = 0.20
MAX_NON_NUMERIC_FRACTION = 0.50
MIN_TRAIN_HOURS = 24 * 28  # four weeks of valid hourly values
RECOMMENDED_SPAN_DAYS = 360  # roughly one full seasonal cycle of calendar time


class IngestError(ValueError):
    """The file cannot be used; the message explains why."""


@dataclass
class IngestConfig:
    value_column: str
    unit: str = "kW"
    timestamp_column: str | None = None
    date_column: str | None = None
    time_column: str | None = None
    delimiter: str | None = None
    dayfirst: bool = False
    timestamp_format: str | None = None
    extra_columns: dict[str, str] = field(default_factory=dict)  # column -> unit
    min_valid_fraction: float = 0.75
    timezone_convention: str = "logger_clock"


UCI_CONFIG = IngestConfig(
    value_column="Global_active_power",
    unit="kW",
    date_column="Date",
    time_column="Time",
    delimiter=";",
    dayfirst=True,
    timestamp_format="%d/%m/%Y %H:%M:%S",
    extra_columns={"Sub_metering_1": "Wh", "Sub_metering_2": "Wh", "Sub_metering_3": "Wh"},
)


@dataclass
class IngestResult:
    hourly: pd.DataFrame  # index: hour start; columns: value_kw, valid_fraction, extras (kW)
    report: dict


def sniff_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        first = fh.readline()
    counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        raise IngestError("Could not detect a delimiter in the header line")
    return best


def _to_kw(values: np.ndarray, unit: str, step_hours: float) -> np.ndarray:
    u = unit.strip().lower()
    if u in POWER_UNITS:
        return values * POWER_UNITS[u]
    if u in ENERGY_UNITS:
        return values * ENERGY_UNITS[u] / step_hours
    raise IngestError(f"Unsupported unit '{unit}'. Use one of kW, W, MW, kWh, Wh, MWh.")


def _parse_numeric(col: pd.Series) -> tuple[pd.Series, int, int]:
    low = col.str.strip().str.lower()
    is_missing = low.isin(MISSING_TOKENS)
    num = pd.to_numeric(col.where(~is_missing), errors="coerce")
    non_numeric = int((num.isna() & ~is_missing).sum())
    return num.astype("float32"), int(is_missing.sum()), non_numeric


def _count_lines(path: Path) -> int:
    n = 0
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            n += block.count(b"\n")
    return n


def ingest_csv(path: str | Path, config: IngestConfig, chunksize: int = 200_000) -> IngestResult:
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise IngestError("The file is empty or does not exist")
    delimiter = config.delimiter or sniff_delimiter(path)

    ts_cols = [config.timestamp_column] if config.timestamp_column else [config.date_column, config.time_column]
    if not all(ts_cols):
        raise IngestError("Provide a timestamp column, or both a date column and a time column")
    needed = [*ts_cols, config.value_column, *config.extra_columns]

    reader = None
    try:
        reader = pd.read_csv(
            path,
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
            chunksize=chunksize,
            engine="c",
            encoding="utf-8-sig",
            encoding_errors="replace",
            on_bad_lines="skip",
        )
        ts_parts: list[np.ndarray] = []
        val_parts: list[np.ndarray] = []
        extra_parts: dict[str, list[np.ndarray]] = {c: [] for c in config.extra_columns}
        rows_read = unparseable_ts = non_numeric = missing_tokens = 0
        checked = False
        for chunk in reader:
            if not checked:
                absent = [c for c in needed if c not in chunk.columns]
                if absent:
                    raise IngestError(f"Missing expected column(s): {absent}. Found: {list(chunk.columns)[:12]}")
                checked = True
            rows_read += len(chunk)
            if config.timestamp_column:
                ts_str = chunk[config.timestamp_column]
            else:
                ts_str = chunk[config.date_column] + " " + chunk[config.time_column]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ts = pd.to_datetime(ts_str, format=config.timestamp_format, dayfirst=config.dayfirst, errors="coerce")
            ok = ts.notna().to_numpy()
            unparseable_ts += int((~ok).sum())
            val, miss, bad = _parse_numeric(chunk[config.value_column])
            missing_tokens += miss
            non_numeric += bad
            ts_parts.append(ts.to_numpy()[ok].astype("datetime64[ns]").astype("int64"))
            val_parts.append(val.to_numpy()[ok])
            for c in config.extra_columns:
                extra_parts[c].append(_parse_numeric(chunk[c])[0].to_numpy()[ok])
    except IngestError:
        raise
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError, ValueError) as exc:
        raise IngestError(f"The file could not be parsed as CSV: {exc}") from exc
    finally:
        if reader is not None:
            reader.close()  # release the file handle even when parsing fails part-way

    if rows_read == 0:
        raise IngestError("The file has a header but no data rows")
    skipped_lines = max(0, _count_lines(path) - 1 - rows_read)
    raw_rows = rows_read + skipped_lines
    if unparseable_ts / raw_rows > MAX_UNPARSEABLE_TS_FRACTION:
        raise IngestError(
            f"{unparseable_ts} of {raw_rows} rows have unparseable timestamps; check the timestamp column and format"
        )
    if non_numeric / rows_read > MAX_NON_NUMERIC_FRACTION:
        raise IngestError(f"{non_numeric} of {rows_read} values in '{config.value_column}' are not numeric")

    ts_ns = np.concatenate(ts_parts)
    vals = np.concatenate(val_parts)
    extras = {c: np.concatenate(p) for c, p in extra_parts.items()}
    if ts_ns.size == 0:
        raise IngestError("No row has a valid timestamp")

    inversions = int((np.diff(ts_ns) < 0).sum())
    if inversions:
        order = np.argsort(ts_ns, kind="stable")
        ts_ns, vals = ts_ns[order], vals[order]
        extras = {c: v[order] for c, v in extras.items()}
    keep = np.concatenate(([True], np.diff(ts_ns) > 0))
    duplicates = int((~keep).sum())
    ts_ns, vals = ts_ns[keep], vals[keep]
    extras = {c: v[keep] for c, v in extras.items()}

    negative = int((vals < 0).sum())
    vals = np.where(vals < 0, np.nan, vals)

    if ts_ns.size < 3:
        raise IngestError("Fewer than 3 distinct timestamps; cannot determine the sampling interval")
    diffs_s = np.diff(ts_ns) / 1e9
    step_s = float(np.median(diffs_s))
    if step_s <= 0:
        raise IngestError("Could not determine a positive sampling interval")
    if step_s > 3600 * 1.01:
        raise IngestError(
            f"Sampling interval is about {step_s / 3600:.1f} h; EnergiQ needs data at most hourly"
        )
    irregular = int((np.abs(diffs_s - step_s) > max(1.0, 0.01 * step_s)).sum())
    gaps = diffs_s[diffs_s > 1.5 * step_s]
    step_h = step_s / 3600.0

    kw = _to_kw(vals.astype("float64"), config.unit, step_h)
    index = pd.DatetimeIndex(ts_ns.astype("datetime64[ns]"), name="timestamp")
    main = pd.Series(kw, index=index)
    per_hour = max(1, int(round(3600.0 / step_s)))
    count = main.resample("1h").count()
    hourly = pd.DataFrame({"value_kw": main.resample("1h").mean(), "valid_fraction": (count / per_hour).clip(upper=1.0)})
    hourly.loc[hourly["valid_fraction"] < config.min_valid_fraction, "value_kw"] = np.nan
    for c, unit in config.extra_columns.items():
        s = pd.Series(_to_kw(extras[c].astype("float64"), unit, step_h), index=index)
        e = s.resample("1h").mean()
        e[(s.resample("1h").count() / per_hour) < config.min_valid_fraction] = np.nan
        hourly[c] = e

    valid_raw = int(np.isfinite(kw).sum())
    expected_slots = int(round((ts_ns[-1] - ts_ns[0]) / 1e9 / step_s)) + 1
    quality = quality_score(
        raw_rows=raw_rows,
        valid_values=valid_raw,
        expected_slots=expected_slots,
        duplicates=duplicates,
        non_numeric=non_numeric,
        negative=negative,
        unparseable_timestamps=unparseable_ts,
        irregular_steps=irregular,
        steps=int(diffs_s.size),
    )
    valid_hours = int(hourly["value_kw"].notna().sum())
    span_days = float((index[-1] - index[0]).total_seconds() / 86400)
    reasons: list[str] = []
    warnings_out: list[str] = []
    if valid_hours < MIN_TRAIN_HOURS:
        reasons.append(f"Only {valid_hours} valid hourly values; at least {MIN_TRAIN_HOURS} (4 weeks) are required")
    if span_days < RECOMMENDED_SPAN_DAYS:
        warnings_out.append("The data covers less than one year: yearly seasonality cannot be learned or evaluated")
    if irregular:
        warnings_out.append(f"{irregular} time steps differ from the dominant interval")
    if negative:
        warnings_out.append(f"{negative} negative readings were treated as invalid")
    if duplicates:
        warnings_out.append(f"{duplicates} duplicate timestamps were removed (first kept)")
    if inversions:
        warnings_out.append(f"The file was not in chronological order ({inversions} out-of-order steps); it was sorted")

    report = {
        "rows_read": int(rows_read),
        "skipped_malformed_lines": int(skipped_lines),
        "unparseable_timestamps": int(unparseable_ts),
        "missing_value_tokens": int(missing_tokens),
        "non_numeric_values": int(non_numeric),
        "negative_values": negative,
        "duplicate_timestamps": duplicates,
        "out_of_order_steps": inversions,
        "first_timestamp": str(index[0]),
        "last_timestamp": str(index[-1]),
        "span_days": round(span_days, 3),
        "sampling_interval_seconds": step_s,
        "irregular_steps": irregular,
        "gaps_longer_than_1_5_intervals": int(gaps.size),
        "largest_gap_minutes": round(float(gaps.max() / 60), 1) if gaps.size else 0.0,
        "expected_readings": expected_slots,
        "valid_readings": valid_raw,
        "hours_in_span": int(len(hourly)),
        "valid_hours": valid_hours,
        "min_valid_fraction": config.min_valid_fraction,
        "unit_declared": config.unit,
        "timezone_convention": config.timezone_convention,
        "quality": quality,
        "suitable_for_forecasting": not reasons,
        "unsuitable_reasons": reasons,
        "warnings": warnings_out,
        "value_summary_kw": {
            "min": float(np.nanmin(kw)) if valid_raw else None,
            "mean": float(np.nanmean(kw)) if valid_raw else None,
            "max": float(np.nanmax(kw)) if valid_raw else None,
        },
    }
    return IngestResult(hourly=hourly, report=report)
