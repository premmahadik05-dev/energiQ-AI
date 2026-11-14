"""Dataset upload handling, ingestion into the database and series loading."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ml_engine.data.ingest import IngestConfig, IngestError, ingest_csv

from ..config import Settings
from ..models import Dataset, Reading, utcnow
from .core import JobContext

ALLOWED_EXT = {".csv", ".txt", ".tsv"}
ALLOWED_UNITS = {"kw", "w", "mw", "kwh", "wh", "mwh"}
ALLOWED_DELIMS = {",", ";", "\t", "|"}
ALLOWED_TZ = {"logger_clock", "utc", "local_with_dst"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ \-()]+")


def safe_filename(name: str | None) -> str:
    base = Path((name or "upload").replace("\\", "/")).name
    return (_SAFE_NAME.sub("_", base)[:120]) or "upload"


def build_config(value_column: str, unit: str, timestamp_column: str | None, date_column: str | None,
                 time_column: str | None, delimiter: str | None, dayfirst: bool, timestamp_format: str | None,
                 timezone_convention: str) -> IngestConfig:
    def clean(v: str | None, label: str, maxlen: int = 100) -> str | None:
        if v is None or v.strip() == "":
            return None
        if len(v) > maxlen or any(ord(c) < 32 for c in v):
            raise HTTPException(422, f"Invalid {label}")
        return v.strip()

    value_column = clean(value_column, "value column")
    if not value_column:
        raise HTTPException(422, "value_column is required")
    if unit.strip().lower() not in ALLOWED_UNITS:
        raise HTTPException(422, "unit must be one of kW, W, MW, kWh, Wh, MWh")
    if delimiter in ("\\t", "tab"):
        delimiter = "\t"
    if delimiter not in (None, "") and delimiter not in ALLOWED_DELIMS:
        raise HTTPException(422, "delimiter must be one of , ; tab |")
    if timezone_convention not in ALLOWED_TZ:
        raise HTTPException(422, f"timezone_convention must be one of {sorted(ALLOWED_TZ)}")
    ts, d, t = clean(timestamp_column, "timestamp column"), clean(date_column, "date column"), clean(time_column, "time column")
    if not ts and not (d and t):
        raise HTTPException(422, "Provide timestamp_column, or both date_column and time_column")
    fmt = clean(timestamp_format, "timestamp format", 60)
    return IngestConfig(value_column=value_column, unit=unit.strip(), timestamp_column=ts, date_column=d, time_column=t,
                        delimiter=delimiter or None, dayfirst=dayfirst, timestamp_format=fmt,
                        timezone_convention=timezone_convention)


def stored_path(settings: Settings, owner_id: int, dataset_id: int) -> Path:
    return settings.upload_dir / f"user_{owner_id}" / f"dataset_{dataset_id}.csv"


def stream_upload(upload: UploadFile, dest: Path, max_bytes: int) -> tuple[str, int]:
    """Write the upload to disk with a size cap, reject binary content, return (sha256, size)."""
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Only {', '.join(sorted(ALLOWED_EXT))} files are accepted")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(f".{uuid.uuid4().hex}.part")
    h, size, first = hashlib.sha256(), 0, True
    try:
        with tmp.open("wb") as fh:
            while True:
                chunk = upload.file.read(1 << 20)
                if not chunk:
                    break
                if first:
                    first = False
                    if b"\x00" in chunk[:65536]:
                        raise HTTPException(415, "The file looks binary, not text/CSV")
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"File exceeds the {max_bytes // (1 << 20)} MB limit")
                h.update(chunk)
                fh.write(chunk)
        if size == 0:
            raise HTTPException(422, "The file is empty")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return h.hexdigest(), size


def _row_dicts(dataset_id: int, hourly: pd.DataFrame) -> list[dict]:
    vals = hourly["value_kw"].to_numpy(dtype="float64")
    vf = hourly["valid_fraction"].to_numpy(dtype="float64")
    return [{"dataset_id": dataset_id, "ts": ts.to_pydatetime(), "value_kw": None if np.isnan(v) else float(v),
             "valid_fraction": None if np.isnan(f) else float(f)}
            for ts, v, f in zip(hourly.index, vals, vf)]


def refresh_stats(db: Session, dataset: Dataset) -> None:
    total, valid, first, last = db.execute(
        select(func.count(Reading.ts), func.count(Reading.value_kw), func.min(Reading.ts), func.max(Reading.ts))
        .where(Reading.dataset_id == dataset.id)).one()
    dataset.hours, dataset.valid_hours, dataset.start_ts, dataset.end_ts = int(total), int(valid), first, last


def ingest_into_dataset(db: Session, ctx: JobContext, settings: Settings, dataset_id: int, config: IngestConfig,
                        mode: str = "create") -> dict:
    ds = db.get(Dataset, dataset_id)
    path = stored_path(settings, ds.owner_id, dataset_id) if mode == "create" else stored_path(settings, ds.owner_id, dataset_id).with_name(f"append_{dataset_id}.csv")
    try:
        ctx.progress(0.1, "Reading and validating the file")
        res = ingest_csv(path, config)
    except IngestError as exc:
        if mode == "create":
            ds.status, ds.error = "failed", str(exc)[:1000]
            db.commit()
        raise
    finally:
        if mode == "append":
            path.unlink(missing_ok=True)
    ctx.progress(0.6, "Saving hourly readings")
    rows = _row_dicts(dataset_id, res.hourly)
    lo, hi = res.hourly.index.min().to_pydatetime(), res.hourly.index.max().to_pydatetime()
    if mode == "create":
        db.execute(delete(Reading).where(Reading.dataset_id == dataset_id))
    else:
        # Append: a new reading replaces an old one for the same hour, but a gap in the new file must never erase an
        # existing valid reading. Hours the new file has no value for are only added if the hour is not stored yet.
        existing = {r[0] for r in db.execute(select(Reading.ts).where(Reading.dataset_id == dataset_id, Reading.ts >= lo, Reading.ts <= hi))}
        replace = [r["ts"] for r in rows if r["value_kw"] is not None and r["ts"] in existing]
        for i in range(0, len(replace), 5000):
            db.execute(delete(Reading).where(Reading.dataset_id == dataset_id, Reading.ts.in_(replace[i:i + 5000])))
        replaced = set(replace)
        rows = [r for r in rows if r["ts"] not in existing or r["ts"] in replaced]
    for i in range(0, len(rows), 5000):
        db.execute(insert(Reading), rows[i:i + 5000])
    db.flush()
    refresh_stats(db, ds)
    if mode == "create":
        ds.report, ds.quality_score, ds.status, ds.error = res.report, res.report["quality"]["score"], "ready", None
    else:
        rep = dict(ds.report or {})
        rep["appends"] = [*rep.get("appends", []), {"at": utcnow().isoformat(timespec="seconds"), "rows_read": res.report["rows_read"],
                                                     "range": [res.report["first_timestamp"], res.report["last_timestamp"]],
                                                     "quality_score": res.report["quality"]["score"], "warnings": res.report["warnings"]}][-20:]
        ds.report = rep
    ds.updated_at = utcnow()
    db.commit()
    return {"dataset_id": dataset_id, "hours": ds.hours, "valid_hours": ds.valid_hours, "quality_score": res.report["quality"]["score"],
            "suitable_for_forecasting": res.report["suitable_for_forecasting"], "warnings": res.report["warnings"]}


def load_series(db: Session, dataset_id: int, start: datetime | None = None, end: datetime | None = None) -> pd.Series:
    stmt = select(Reading.ts, Reading.value_kw).where(Reading.dataset_id == dataset_id).order_by(Reading.ts)
    if start is not None:
        stmt = stmt.where(Reading.ts >= start)
    if end is not None:
        stmt = stmt.where(Reading.ts <= end)
    rows = db.execute(stmt).all()
    if not rows:
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="timestamp"), name="value_kw")
    idx = pd.DatetimeIndex([r[0] for r in rows], name="timestamp")
    return pd.Series([np.nan if r[1] is None else r[1] for r in rows], index=idx, name="value_kw", dtype="float64")
