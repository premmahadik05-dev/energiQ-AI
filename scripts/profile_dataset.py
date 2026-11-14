"""Phase 1 dataset profiler for EnergiQ AI.

Read-only on the raw file. Reads in chunks (RAM-safe for an 8 GB machine),
keeps only compact float32 arrays, and writes a JSON profile.

Usage (Windows or Linux):
    python scripts/profile_dataset.py ^
        --input data/raw/uci_household_power/household_power_consumption.txt ^
        --output artifacts/reports/dataset_profile.json
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

NUMERIC = [
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
]
EXPECTED_COLUMNS = ["Date", "Time", *NUMERIC]
TS_FORMAT = "%d/%m/%Y %H:%M:%S"


def peak_rss_mb() -> float | None:
    """Peak resident memory in MB, or None if it cannot be measured.

    Linux/macOS use the stdlib `resource` module (absent on Windows).
    On Windows, psutil's peak working set is used when psutil is installed.
    """
    try:
        import resource  # POSIX only

        # ru_maxrss is KB on Linux, bytes on macOS.
        import sys

        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor, 1)
    except ImportError:
        try:
            import psutil

            info = psutil.Process().memory_info()
            return round(getattr(info, "peak_wset", info.rss) / (1024 * 1024), 1)
        except ImportError:
            return None


def field_count_distribution(path: Path) -> dict[str, int]:
    """Count semicolons per physical line to detect malformed rows."""
    counter: Counter[int] = Counter()
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            counter[line.rstrip("\r\n").count(";") + 1] += 1
    return {str(k): int(v) for k, v in sorted(counter.items())}


def run_lengths(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start indices and lengths of consecutive True runs."""
    if mask.size == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    padded = np.concatenate(([0], mask.astype(np.int8), [0]))
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return starts, ends - starts


def describe(series: pd.Series) -> dict:
    s = series.dropna()
    if s.empty:
        return {}
    q = s.quantile([0.001, 0.01, 0.25, 0.5, 0.75, 0.99, 0.999])
    return {
        "count": int(s.size),
        "min": float(s.min()),
        "max": float(s.max()),
        "mean": float(s.mean()),
        "std": float(s.std()),
        "q0.1%": float(q.loc[0.001]),
        "q1%": float(q.loc[0.01]),
        "q25%": float(q.loc[0.25]),
        "median": float(q.loc[0.5]),
        "q75%": float(q.loc[0.75]),
        "q99%": float(q.loc[0.99]),
        "q99.9%": float(q.loc[0.999]),
        "negative_count": int((s < 0).sum()),
        "zero_count": int((s == 0).sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--chunksize", type=int, default=200_000)
    args = ap.parse_args()

    t0 = time.time()
    path: Path = args.input
    report: dict = {"file": {"name": path.name, "size_bytes": path.stat().st_size}}

    # ---- structural check -------------------------------------------------
    fc = field_count_distribution(path)
    report["file"]["fields_per_line_distribution"] = fc  # includes header line

    # ---- chunked read -----------------------------------------------------
    raw_tokens = {c: {"question_mark": 0, "empty": 0, "other_non_numeric": 0} for c in NUMERIC}
    bad_ts = 0
    ts_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    header_cols: list[str] | None = None
    n_rows = 0

    reader = pd.read_csv(
        path,
        sep=";",
        dtype=str,
        keep_default_na=False,
        chunksize=args.chunksize,
        engine="c",
    )
    for chunk in reader:
        if header_cols is None:
            header_cols = list(chunk.columns)
        n_rows += len(chunk)
        for c in NUMERIC:
            col = chunk[c]
            q = int((col == "?").sum())
            e = int((col == "").sum())
            num = pd.to_numeric(col.where(~col.isin(["?", ""])), errors="coerce")
            other = int((num.isna() & ~col.isin(["?", ""])).sum())
            raw_tokens[c]["question_mark"] += q
            raw_tokens[c]["empty"] += e
            raw_tokens[c]["other_non_numeric"] += other
            chunk[c] = num.astype("float32")
        ts = pd.to_datetime(chunk["Date"] + " " + chunk["Time"], format=TS_FORMAT, errors="coerce")
        bad_ts += int(ts.isna().sum())
        ts_parts.append(ts.values)
        val_parts.append(chunk[NUMERIC].to_numpy(dtype=np.float32))

    ts_all = np.concatenate(ts_parts)
    vals = np.concatenate(val_parts)
    del ts_parts, val_parts
    df = pd.DataFrame(vals, columns=NUMERIC)
    df.insert(0, "ts", ts_all)
    del vals

    report["structure"] = {
        "rows": int(n_rows),
        "columns": len(header_cols or []),
        "column_names": header_cols,
        "header_matches_expected": header_cols == EXPECTED_COLUMNS,
        "unparseable_timestamps": bad_ts,
        "raw_token_issues": raw_tokens,
    }

    # ---- time axis --------------------------------------------------------
    ts = df["ts"]
    valid_ts = ts.notna()
    ts_v = ts[valid_ts]
    diffs = np.diff(ts_v.values).astype("timedelta64[s]").astype(np.int64)
    gap_mask = diffs > 60
    gap_idx = np.flatnonzero(gap_mask)
    top = np.argsort(diffs[gap_idx])[::-1][:10]
    top_gaps = []
    for i in gap_idx[top]:
        top_gaps.append(
            {
                "after": str(ts_v.iloc[i]),
                "next_reading": str(ts_v.iloc[i + 1]),
                "missing_minutes": int(diffs[i] // 60 - 1),
            }
        )
    span_minutes = int((ts_v.max() - ts_v.min()).total_seconds() // 60) + 1
    diff_counts = Counter(diffs.tolist())
    report["time_axis"] = {
        "first_timestamp": str(ts_v.min()),
        "last_timestamp": str(ts_v.max()),
        "is_chronologically_sorted": bool(ts_v.is_monotonic_increasing),
        "duplicate_timestamps": int(ts_v.duplicated().sum()),
        "step_seconds_top5": {str(k): int(v) for k, v in diff_counts.most_common(5)},
        "dominant_step_seconds": int(diff_counts.most_common(1)[0][0]),
        "expected_minutes_in_span": span_minutes,
        "rows_present": int(valid_ts.sum()),
        "coverage_fraction_of_span": round(float(valid_ts.sum()) / span_minutes, 6),
        "rows_missing_from_span_(absent_timestamps)": int(span_minutes - valid_ts.sum()),
        "gaps_longer_than_1_min": int(gap_mask.sum()),
        "largest_gaps": top_gaps,
    }

    # ---- missing values ---------------------------------------------------
    miss = df[NUMERIC].isna()
    gap_col = miss["Global_active_power"].to_numpy()
    starts, lens = run_lengths(gap_col)
    long_idx = np.argsort(lens)[::-1][:8]
    ts_arr = df["ts"].reset_index(drop=True)
    longest_blocks = [
        {
            "start": str(ts_arr.iloc[starts[i]]),
            "minutes": int(lens[i]),
        }
        for i in long_idx
    ]
    per_year = (
        df.assign(year=df["ts"].dt.year, miss=miss["Global_active_power"])
        .groupby("year")["miss"]
        .agg(["sum", "size"])
    )
    report["missing_values"] = {
        "per_column_nan_count": {c: int(miss[c].sum()) for c in NUMERIC},
        "per_column_nan_pct": {c: round(float(miss[c].mean() * 100), 4) for c in NUMERIC},
        "rows_with_any_missing": int(miss.any(axis=1).sum()),
        "rows_with_all_missing": int(miss.all(axis=1).sum()),
        "missing_is_all_or_nothing_per_row": bool(
            int(miss.any(axis=1).sum()) == int(miss.all(axis=1).sum())
        ),
        "global_active_power_missing_blocks": int(starts.size),
        "block_length_minutes": {
            "median": float(np.median(lens)) if lens.size else 0.0,
            "p95": float(np.percentile(lens, 95)) if lens.size else 0.0,
            "max": int(lens.max()) if lens.size else 0,
            "blocks_longer_than_60_min": int((lens > 60).sum()),
            "blocks_longer_than_1440_min": int((lens > 1440).sum()),
        },
        "longest_blocks": longest_blocks,
        "missing_pct_by_year": {
            str(int(y)): round(float(r["sum"] / r["size"] * 100), 3) for y, r in per_year.iterrows()
        },
    }

    # ---- value ranges and outliers ---------------------------------------
    report["value_statistics"] = {c: describe(df[c]) for c in NUMERIC}
    gap = df["Global_active_power"].dropna()
    q1, q3 = gap.quantile(0.25), gap.quantile(0.75)
    iqr = q3 - q1
    report["outlier_screen_global_active_power"] = {
        "iqr_1.5_upper_fence": float(q3 + 1.5 * iqr),
        "count_above_1.5_fence": int((gap > q3 + 1.5 * iqr).sum()),
        "iqr_3.0_upper_fence": float(q3 + 3.0 * iqr),
        "count_above_3.0_fence": int((gap > q3 + 3.0 * iqr).sum()),
        "max_value": float(gap.max()),
        "note": "Screening only. High values here can be genuine appliance use, not errors.",
    }
    sm_cols = ["Sub_metering_1", "Sub_metering_2", "Sub_metering_3"]
    sm = df[sm_cols].dropna()
    report["sub_metering_integrality"] = {
        c: bool(np.all(np.mod(sm[c].to_numpy(), 1) == 0)) for c in sm_cols
    }

    # Active energy per minute in Wh = kW * 1000 / 60. Unmetered = that - sum(sub-meters).
    ok = df[["Global_active_power", *sm_cols]].dropna()
    unmetered = ok["Global_active_power"] * 1000 / 60 - ok[sm_cols].sum(axis=1)
    report["unmetered_energy_wh_per_min"] = {
        "formula": "Global_active_power*1000/60 - (Sub_metering_1+2+3)",
        "rows": int(unmetered.size),
        "negative_count": int((unmetered < 0).sum()),
        "negative_pct": round(float((unmetered < 0).mean() * 100), 4),
        "mean": float(unmetered.mean()),
        "median": float(unmetered.median()),
    }

    # ---- resampling viability --------------------------------------------
    series = df.dropna(subset=["ts"]).drop_duplicates("ts").set_index("ts")["Global_active_power"]
    hourly_n = series.resample("1h").count()
    daily_n = series.resample("1D").count()
    full_hours_idx = hourly_n.index
    report["resampling_viability"] = {
        "hours_in_span": int(len(full_hours_idx)),
        "hours_with_60_valid_minutes": int((hourly_n == 60).sum()),
        "hours_with_at_least_45_valid_minutes": int((hourly_n >= 45).sum()),
        "hours_with_zero_valid_minutes": int((hourly_n == 0).sum()),
        "days_in_span": int(len(daily_n)),
        "days_with_at_least_1380_valid_minutes_(95%)": int((daily_n >= 1380).sum()),
        "days_with_zero_valid_minutes": int((daily_n == 0).sum()),
    }

    report["run"] = {
        "chunksize": args.chunksize,
        "seconds": round(time.time() - t0, 1),
        "peak_rss_mb": peak_rss_mb(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
