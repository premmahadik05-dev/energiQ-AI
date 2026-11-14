"""Read a society's real meter data from an uploaded wide CSV and build the community series.

Input format (one file, one row per timestamp, one column per meter)::

    timestamp,B01,B02,Lift_A,Pump_1
    2024-01-01 00:00,41.2,38.0,2.1,0.0
    ...

* ``unit="kwh"``: each value is the energy used in the interval ending/starting at the timestamp.
* ``unit="kw"``:  each value is the average power over the interval.
* The interval may be 1, 5, 10, 15, 30 or 60 minutes. It is aggregated to hourly kWh (energy summed, power
  averaged). An hour needs every sub-interval for kWh and at least 75 % of them for kW, otherwise it is missing.
* An optional mapping CSV (``meter_id,building,kind,facility_category,floor_area_sqm``) says which meters are
  buildings and which are common-area facilities (lift, pump, streetlight, clubhouse). Without it every column
  is one building.

Nothing is ever filled in. Readings failing the validity rules (cleaning.py) become missing, the society
total exists only at hours where every retained meter is valid, and all counts are reported.
"""
from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .cleaning import CleaningConfig, clean_meter, regularise_hourly

FACILITY_CATEGORIES = ("lift", "pump", "streetlight", "clubhouse", "other")
ALLOWED_INTERVALS = (1, 5, 10, 15, 30, 60)
MAX_METERS = 200
MAX_ROWS = 24 * 366 * 6 * 4  # six years of 15-minute data
# Database column widths (backend/app/models.py: Building.code / Meter.code and source_id). SQLite does not enforce them, PostgreSQL does,
# so they are enforced here, where the values are made; tests/unit/test_society_db_limits.py ties these numbers to the models.
CODE_MAX_CHARS = 24
METER_ID_MAX_CHARS = 120


class IngestError(ValueError):
    """The uploaded file cannot be turned into a valid society."""


@dataclass(frozen=True)
class UploadRule:
    min_meter_valid_share: float = 0.90
    min_meters: int = 2
    min_society_valid_share: float = 0.80

    def to_dict(self) -> dict:
        return asdict(self)


def slugify(text: str, fallback: str = "society") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:24] or fallback


def _read(source) -> pd.DataFrame:
    try:
        if isinstance(source, (bytes, bytearray)):
            return pd.read_csv(io.BytesIO(source), dtype=str, keep_default_na=False)
        return pd.read_csv(Path(source), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise IngestError(f"The file is not a readable CSV: {exc}") from exc


def read_wide_csv(source, unit: str = "kwh", timestamp_column: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Return (hourly kWh per meter on a complete hourly grid, import report)."""
    if unit not in ("kwh", "kw"):
        raise IngestError("unit must be 'kwh' or 'kw'")
    raw = _read(source)
    if raw.shape[1] < 2 or len(raw) < 24:
        raise IngestError("Need a timestamp column, at least one meter column and at least 24 rows")
    if len(raw) > MAX_ROWS:
        raise IngestError(f"At most {MAX_ROWS:,} rows are accepted")
    tcol = timestamp_column or raw.columns[0]
    if tcol not in raw.columns:
        raise IngestError(f"Timestamp column '{tcol}' not found")
    ts = pd.to_datetime(raw[tcol].str.strip(), errors="coerce", format="mixed")
    bad_ts = int(ts.isna().sum())
    if bad_ts > 0.02 * len(raw):
        raise IngestError(f"{bad_ts} of {len(raw)} timestamps could not be parsed; use ISO format, e.g. 2024-01-31 14:00")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)  # stored as UTC clock time when the file carries offsets
    meters = raw.drop(columns=[tcol])
    if meters.shape[1] > MAX_METERS:
        raise IngestError(f"At most {MAX_METERS} meter columns are accepted")
    names = [c.strip() for c in meters.columns]
    if len(set(names)) != len(names):
        raise IngestError("Meter column names must be unique")
    if any(not n for n in names):
        raise IngestError("Meter column names must not be empty")
    too_long = [n for n in names if len(n) > METER_ID_MAX_CHARS]
    if too_long:
        raise IngestError(f"Meter column names may have at most {METER_ID_MAX_CHARS} characters; {len(too_long)} are longer (first: '{too_long[0][:30]}...')")
    meters.columns = names
    non_numeric = 0
    num = {}
    for c in names:
        col = pd.to_numeric(meters[c].str.replace(",", "", regex=False).str.strip(), errors="coerce")
        non_numeric += int(((col.isna()) & (meters[c].str.strip() != "")).sum())
        num[c] = col
    df = pd.DataFrame(num)
    df.index = ts
    df = df[df.index.notna()]
    all_nan = [c for c in names if df[c].notna().sum() == 0]
    df = df.drop(columns=all_nan)
    if df.shape[1] == 0:
        raise IngestError("No meter column contains numeric readings")

    df = df.sort_index()
    dup = int(df.index.duplicated().sum())
    df = df[~df.index.duplicated(keep="first")]
    diffs = df.index.to_series().diff().dropna()
    if diffs.empty:
        raise IngestError("Need at least two distinct timestamps")
    step = int(round(diffs.median().total_seconds() / 60))
    if step not in ALLOWED_INTERVALS:
        raise IngestError(f"Reading interval looks like {step} minutes; supported intervals are {', '.join(map(str, ALLOWED_INTERVALS))} minutes")
    per_hour = 60 // step
    if step < 60:
        hour = df.index.floor("h")
        grp = df.groupby(hour)
        cnt = grp.count()
        if unit == "kwh":
            hourly = grp.sum(min_count=1).where(cnt >= per_hour)
        else:
            hourly = grp.mean().where(cnt >= 0.75 * per_hour)
        hourly.index.name = "timestamp"
    else:
        hourly = df
        hourly.index = hourly.index.floor("h")
        hourly = hourly[~hourly.index.duplicated(keep="first")]
    hourly, ts_report = regularise_hourly(hourly)
    report = {"unit": unit, "interval_minutes": step, "rows_in": int(len(raw)), "unparseable_timestamps": bad_ts, "non_numeric_cells": non_numeric,
              "duplicate_timestamps": dup, "empty_meter_columns_dropped": all_nan, "hourly_rows": int(len(hourly)), "first": str(hourly.index[0]), "last": str(hourly.index[-1]),
              "timestamps": ts_report,
              "aggregation": ("hourly kWh = sum of the sub-hourly kWh values (all of them required)" if step < 60 and unit == "kwh" else
                              "hourly kWh = mean of the sub-hourly kW values (at least 75 % required)" if step < 60 else
                              "values are hourly; kW (average power) is read as kWh for the hour" if unit == "kw" else "values are hourly kWh")}
    return hourly, report


def read_mapping_csv(source, meter_ids: list[str]) -> pd.DataFrame:
    """Mapping with columns meter_id, building, kind, facility_category, floor_area_sqm (all but meter_id optional)."""
    cols = ["meter_id", "building", "kind", "facility_category", "floor_area_sqm"]
    if source is None:
        return pd.DataFrame({"meter_id": meter_ids, "building": meter_ids, "kind": "building", "facility_category": "", "floor_area_sqm": np.nan})
    m = _read(source)
    m.columns = [c.strip().lower() for c in m.columns]
    if "meter_id" not in m.columns:
        raise IngestError("The mapping file needs a 'meter_id' column")
    for c in cols:
        if c not in m.columns:
            m[c] = ""
    m = m[cols].copy()
    for c in ("meter_id", "building", "kind", "facility_category"):
        m[c] = m[c].str.strip()
    m["kind"] = m["kind"].str.lower().replace("", "building")
    m["facility_category"] = m["facility_category"].str.lower()
    if m["meter_id"].duplicated().any():
        raise IngestError("The mapping file lists a meter_id more than once")
    unknown = sorted(set(m["meter_id"]) - set(meter_ids))
    if unknown:
        raise IngestError(f"Mapping refers to meters that are not columns of the data file: {', '.join(unknown[:5])}")
    if (~m["kind"].isin(["building", "facility"])).any():
        raise IngestError("Mapping 'kind' must be 'building' or 'facility'")
    fac = m["kind"] == "facility"
    bad_cat = ~m.loc[fac, "facility_category"].isin(FACILITY_CATEGORIES)
    if bad_cat.any():
        raise IngestError(f"Facility meters need facility_category in {', '.join(FACILITY_CATEGORIES)}")
    m["floor_area_sqm"] = pd.to_numeric(m["floor_area_sqm"], errors="coerce")
    missing = [c for c in meter_ids if c not in set(m["meter_id"])]
    if missing:  # unlisted columns default to one building each
        add = pd.DataFrame({"meter_id": missing, "building": missing, "kind": "building", "facility_category": "", "floor_area_sqm": np.nan})
        m = pd.concat([m, add], ignore_index=True)
    m["building"] = m["building"].where(m["building"] != "", m["meter_id"])
    return m.set_index("meter_id").loc[meter_ids].reset_index()


def build_uploaded_society(key: str, hourly_kwh: pd.DataFrame, mapping: pd.DataFrame, rule: UploadRule = UploadRule(),
                           cleaning: CleaningConfig = CleaningConfig()) -> dict:
    """Clean every meter, keep those passing the rule and sum them per hour (NaN unless all are valid).

    Each building meter column is one building (the mapping's ``building`` text is only a display label).
    Facility meters are cleaned with zero readings allowed (street lights are legitimately off by day) and are
    part of the society total, because the community's demand includes its common services.
    """
    ids = list(hourly_kwh.columns)
    kind = dict(zip(mapping["meter_id"], mapping["kind"], strict=True))
    cleaned, counts = {}, {}
    for c in ids:
        cfg = cleaning if kind[c] == "building" else CleaningConfig(**{**cleaning.to_dict(), "zero_is_invalid": False})
        cleaned[c], counts[c] = clean_meter(hourly_kwh[c], cfg)
    clean_df = pd.DataFrame(cleaned)
    share = clean_df.notna().mean()
    kept = [c for c in ids if share[c] >= rule.min_meter_valid_share]
    excluded = [{"source_id": c, "valid_share": round(float(share[c]), 4), "reason": f"valid hours {share[c]:.1%} below the {rule.min_meter_valid_share:.0%} rule", **counts[c]}
                for c in ids if c not in kept]
    kept_map = mapping[mapping["meter_id"].isin(kept)].set_index("meter_id").loc[kept]
    if len(kept) < rule.min_meters or not (kept_map["kind"] == "building").any():
        raise IngestError(f"Only {len(kept)} meters pass the validity rule (need at least {rule.min_meters}, including one building)")
    kept_df = clean_df[kept]
    total = kept_df.sum(axis=1, min_count=len(kept))
    society_share = float(total.notna().mean())
    if society_share < rule.min_society_valid_share:
        raise IngestError(f"The society total is valid in only {society_share:.1%} of hours (need {rule.min_society_valid_share:.0%}); meters rarely overlap in time")

    codes = {}
    nb = nf = 0
    n_most = max(int((kept_map["kind"] == "building").sum()), int((kept_map["kind"] != "building").sum()), 1)
    width = max(2, len(str(n_most)))
    prefix = key.upper()[:CODE_MAX_CHARS - 2 - width].rstrip("-") or "S"  # "-B" and the number must fit in the column; the prefix is the part that is shortened
    for c in kept:
        if kept_map.loc[c, "kind"] == "building":
            nb += 1
            codes[c] = f"{prefix}-B{nb:0{width}d}"
        else:
            nf += 1
            codes[c] = f"{prefix}-F{nf:0{width}d}"
    meters_df = kept_df.rename(columns=codes)
    meters = pd.DataFrame({
        "code": [codes[c] for c in kept], "source_id": kept, "label": [kept_map.loc[c, "building"] for c in kept], "kind": [kept_map.loc[c, "kind"] for c in kept],
        "facility_category": [kept_map.loc[c, "facility_category"] or None for c in kept], "floor_area_sqm": [kept_map.loc[c, "floor_area_sqm"] for c in kept],
        "valid_share": [round(float(share[c]), 4) for c in kept]})
    return {"key": key, "meters": meters, "meters_df": meters_df, "society_kwh": total.rename("society_kwh"), "n_valid_meters": kept_df.notna().sum(axis=1).rename("n_valid_meters"),
            "excluded": excluded, "society_valid_share": society_share, "rule": rule.to_dict(), "cleaning": cleaning.to_dict(), "cleaning_counts": {codes[c]: counts[c] for c in kept}}
