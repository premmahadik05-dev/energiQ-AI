from __future__ import annotations

import shutil
from dataclasses import asdict
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ml_engine.data.ingest import MIN_TRAIN_HOURS, IngestConfig

from ..models import Dataset, Job, ModelVersion, User
from ..schemas import DatasetDetail, DatasetOut, JobOut, ReadingsOut, UploadAccepted
from ..security import current_user_dep, enforce
from ..services import data as data_svc
from .deps import WRITERS, audit, get_session, ip_of, owned_dataset, owned_job, runner_of, settings_of

router = APIRouter(tags=["datasets"])


def _start_ingest(request: Request, db: Session, user: User, ds: Dataset, config: IngestConfig, mode: str) -> Job:
    settings, runner = settings_of(request), runner_of(request)
    job = runner.create(db, user.id, "ingest", ds.id, {"mode": mode})
    runner.submit(job.id, lambda s, ctx: data_svc.ingest_into_dataset(s, ctx, settings, ds.id, config, mode))
    db.refresh(job)
    return job


@router.post("/datasets", response_model=UploadAccepted, status_code=202)
def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=120),
    value_column: str = Form(...),
    unit: str = Form("kW"),
    timestamp_column: str | None = Form(None),
    date_column: str | None = Form(None),
    time_column: str | None = Form(None),
    delimiter: str | None = Form(None),
    dayfirst: bool = Form(False),
    timestamp_format: str | None = Form(None),
    timezone_convention: str = Form("logger_clock"),
    user: User = Depends(WRITERS),
    db: Session = Depends(get_session),
):
    s = settings_of(request)
    enforce(request.app.state.limiter, f"upload:{user.id}", s.upload_per_hour, 3600)
    config = data_svc.build_config(value_column, unit, timestamp_column, date_column, time_column, delimiter, dayfirst,
                                   timestamp_format, timezone_convention)
    ds = Dataset(owner_id=user.id, name=name.strip()[:120], original_filename=data_svc.safe_filename(file.filename),
                 status="processing", config=asdict(config))
    db.add(ds)
    db.flush()
    try:
        ds.sha256, size = data_svc.stream_upload(file, data_svc.stored_path(s, user.id, ds.id), s.max_upload_mb * (1 << 20))
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    audit(db, user.id, "dataset_upload", ip_of(request), "dataset", ds.id, {"bytes": size, "filename": ds.original_filename})
    job = _start_ingest(request, db, user, ds, config, "create")
    db.refresh(ds)
    return UploadAccepted(dataset=DatasetOut.model_validate(ds), job=JobOut.model_validate(job))


@router.post("/datasets/sample", response_model=UploadAccepted, status_code=202)
def load_sample(request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    s = settings_of(request)
    if not s.sample_dataset.is_file():
        raise HTTPException(404, "The bundled sample dataset is not installed on this server")
    config = IngestConfig(value_column="power_kw", unit="kW", timestamp_column="timestamp", delimiter=",",
                          timestamp_format="%Y-%m-%d %H:%M:%S", timezone_convention="logger_clock")
    ds = Dataset(owner_id=user.id, name="UCI household sample (2009, hourly)", original_filename=s.sample_dataset.name,
                 status="processing", config=asdict(config))
    db.add(ds)
    db.flush()
    dest = data_svc.stored_path(s, user.id, ds.id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(s.sample_dataset, dest)
    db.commit()
    audit(db, user.id, "dataset_sample", ip_of(request), "dataset", ds.id)
    job = _start_ingest(request, db, user, ds, config, "create")
    db.refresh(ds)
    return UploadAccepted(dataset=DatasetOut.model_validate(ds), job=JobOut.model_validate(job))


@router.post("/datasets/{dataset_id}/append", response_model=UploadAccepted, status_code=202)
def append_data(dataset_id: int, request: Request, file: UploadFile = File(...), user: User = Depends(WRITERS),
                db: Session = Depends(get_session)):
    """Add newer readings using the column mapping stored with the dataset. Overlapping hours take the new value; gaps in the new file never erase stored readings."""
    s = settings_of(request)
    enforce(request.app.state.limiter, f"upload:{user.id}", s.upload_per_hour, 3600)
    ds = owned_dataset(db, user, dataset_id)
    if ds.status != "ready":
        raise HTTPException(409, "The dataset is not ready")
    config = IngestConfig(**ds.config)
    dest = data_svc.stored_path(s, user.id, ds.id).with_name(f"append_{ds.id}.csv")
    _, size = data_svc.stream_upload(file, dest, s.max_upload_mb * (1 << 20))
    audit(db, user.id, "dataset_append", ip_of(request), "dataset", ds.id, {"bytes": size})
    job = _start_ingest(request, db, user, ds, config, "append")
    db.refresh(ds)
    return UploadAccepted(dataset=DatasetOut.model_validate(ds), job=JobOut.model_validate(job))


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    return db.scalars(select(Dataset).where(Dataset.owner_id == user.id).order_by(Dataset.created_at.desc(), Dataset.id.desc())).all()


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def dataset_detail(dataset_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    return owned_dataset(db, user, dataset_id)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    ds = owned_dataset(db, user, dataset_id)
    s = settings_of(request)
    for mv in db.scalars(select(ModelVersion).where(ModelVersion.dataset_id == ds.id)):
        for mid in mv.horizon_model_ids.values():
            shutil.rmtree(s.models_dir / f"user_{user.id}" / mid, ignore_errors=True)
    data_svc.stored_path(s, user.id, ds.id).unlink(missing_ok=True)
    db.execute(delete(Dataset).where(Dataset.id == ds.id))  # readings, models, anomalies... cascade in the database
    db.commit()
    audit(db, user.id, "dataset_delete", ip_of(request), "dataset", dataset_id, {"name": ds.name})


@router.get("/datasets/{dataset_id}/readings", response_model=ReadingsOut)
def readings(dataset_id: int, start: datetime | None = None, end: datetime | None = None,
             resolution: str = Query("hourly", pattern="^(hourly|daily)$"), limit: int = Query(5000, ge=1, le=20000),
             user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    ds = owned_dataset(db, user, dataset_id)
    if ds.end_ts is None:
        return ReadingsOut(dataset_id=ds.id, resolution=resolution, points=[])
    end = end or ds.end_ts
    start = start or max(ds.start_ts, end - pd.Timedelta(days=14))
    s = data_svc.load_series(db, ds.id, start, end)
    if resolution == "hourly":
        s = s.iloc[-limit:]
        pts = [{"ts": str(t), "kw": None if np.isnan(v) else round(float(v), 4)} for t, v in s.items()]
    else:
        g = s.groupby(s.index.normalize())
        df = pd.DataFrame({"mean_kw": g.mean(), "kwh": g.sum(min_count=1), "valid_hours": g.count()}).iloc[-limit:]
        pts = [{"ts": str(t.date()), "mean_kw": None if np.isnan(r.mean_kw) else round(float(r.mean_kw), 4),
                "kwh": None if np.isnan(r.kwh) else round(float(r.kwh), 3), "valid_hours": int(r.valid_hours)} for t, r in df.iterrows()]
    return ReadingsOut(dataset_id=ds.id, resolution=resolution, points=pts)


@router.get("/datasets/{dataset_id}/profile")
def dataset_profile(dataset_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    """Average daily shape and weekday/weekend shape computed from the stored valid hours."""
    ds = owned_dataset(db, user, dataset_id)
    s = data_svc.load_series(db, ds.id).dropna()
    if s.empty:
        return {"hourly_profile": [], "weekday_vs_weekend": [], "monthly_mean_kw": []}
    wk = s.index.day_of_week >= 5
    hp = s.groupby(s.index.hour).mean()
    wd = s[~wk].groupby(s[~wk].index.hour).mean().reindex(range(24))
    we = s[wk].groupby(s[wk].index.hour).mean().reindex(range(24))
    mo = s.groupby(s.index.to_period("M")).mean()
    r = lambda v: None if pd.isna(v) else round(float(v), 4)  # noqa: E731
    return {"hourly_profile": [{"hour": int(h), "mean_kw": r(v)} for h, v in hp.items()],
            "weekday_vs_weekend": [{"hour": h, "weekday_kw": r(wd[h]), "weekend_kw": r(we[h])} for h in range(24)],
            "monthly_mean_kw": [{"month": str(p), "mean_kw": r(v)} for p, v in mo.items()],
            "valid_hours": int(len(s)), "min_hours_needed_for_forecasting": MIN_TRAIN_HOURS}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    return owned_job(db, user, job_id)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(limit: int = Query(20, ge=1, le=100), dataset_id: int | None = None, user: User = Depends(current_user_dep),
              db: Session = Depends(get_session)):
    q = select(Job).where(Job.owner_id == user.id).order_by(Job.id.desc()).limit(limit)
    if dataset_id is not None:
        q = q.where(Job.dataset_id == dataset_id)
    return db.scalars(q).all()
