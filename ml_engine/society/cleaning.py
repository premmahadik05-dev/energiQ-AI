"""Meter-level cleaning for hourly whole-building electricity readings (kWh per hour).

Every rule marks a reading as *invalid* (NaN) and counts it. Nothing is ever filled, interpolated or
replaced, so a society total exists only for hours where every retained meter has a real reading.

Rules (all parameters are in ``CleaningConfig`` and are recorded in every report):

1. Negative reading           - whole-building consumption cannot be negative.
2. Exact zero                 - an occupied residential building does not draw exactly 0 kWh for an
                                hour; in BDG2 zeros appear as long dead-meter stretches. Counted
                                separately for "short" (< ``long_zero_hours``) and "long" runs.
3. Stuck sensor               - the same non-zero value repeated for ``stuck_min_hours`` or more.
4. Isolated spike             - a value above ``spike_factor`` times the meter's own 99.5th percentile.
5. Missing timestamps / duplicates are handled when the table is built (``regularise_hourly``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class CleaningConfig:
    zero_is_invalid: bool = True
    long_zero_hours: int = 24
    stuck_min_hours: int = 48
    spike_factor: float = 4.0
    spike_quantile: float = 0.995

    def to_dict(self) -> dict:
        return asdict(self)


def regularise_hourly(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Sort, drop duplicate timestamps (keep first) and reindex to a complete hourly grid."""
    report = {"rows_in": int(len(df))}
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("index must be a DatetimeIndex")
    out = df.sort_index()
    dup = int(out.index.duplicated().sum())
    out = out[~out.index.duplicated(keep="first")]
    full = pd.date_range(out.index.min().floor("h"), out.index.max().ceil("h"), freq="1h")
    missing_ts = int(len(full.difference(out.index)))
    out = out.reindex(full)
    out.index.name = "timestamp"
    report.update({"duplicate_timestamps": dup, "missing_timestamps": missing_ts, "rows_out": int(len(out)),
                   "first": str(out.index[0]), "last": str(out.index[-1])})
    return out, report


def _run_lengths(mask: pd.Series) -> pd.Series:
    """Length of the run of equal values each position belongs to."""
    grp = (mask != mask.shift()).cumsum()
    return mask.groupby(grp).transform("size")


def clean_meter(raw: pd.Series, cfg: CleaningConfig = CleaningConfig()) -> tuple[pd.Series, dict]:
    """Return the cleaned series (invalid -> NaN) and a count of what each rule removed."""
    x = raw.astype("float64")
    valid_in = x.notna()
    counts = {"readings": int(len(x)), "missing_in_source": int((~valid_in).sum())}

    neg = (x < 0).fillna(False)
    zero = (x == 0).fillna(False)
    zero_run = _run_lengths(zero) * zero
    long_zero = zero & (zero_run >= cfg.long_zero_hours)
    short_zero = zero & ~long_zero

    positive = x.where(x > 0)
    stuck = pd.Series(False, index=x.index)
    if cfg.stuck_min_hours > 1:
        same_run = _run_lengths(positive.where(positive.notna(), -1.0).astype(float))
        stuck = (same_run >= cfg.stuck_min_hours) & positive.notna()

    spike = pd.Series(False, index=x.index)
    if positive.notna().sum() >= 100:
        limit = cfg.spike_factor * float(positive.quantile(cfg.spike_quantile))
        spike = (x > limit).fillna(False)

    invalid = neg | stuck | spike
    if cfg.zero_is_invalid:
        invalid = invalid | zero
    counts.update({
        "negative": int(neg.sum()),
        "zero_long_runs": int(long_zero.sum()) if cfg.zero_is_invalid else 0,
        "zero_short": int(short_zero.sum()) if cfg.zero_is_invalid else 0,
        "stuck_sensor": int((stuck & ~neg).sum()),
        "spike": int((spike & ~neg & ~stuck).sum()),
    })
    cleaned = x.mask(invalid)
    counts["valid_out"] = int(cleaned.notna().sum())
    counts["valid_share"] = float(cleaned.notna().mean()) if len(cleaned) else 0.0
    return cleaned, counts
