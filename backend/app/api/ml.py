from __future__ import annotations

import csv
import io
import json
import re
import shutil

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ml_engine.data.ingest import MIN_TRAIN_HOURS

from ..models import Forecast, Job, ModelVersion, User
from ..schemas import ForecastIn, ForecastOut, JobOut, LocalExplainIn, ModelOut, TrainIn
from ..security import current_user_dep
from ..services import ml as ml_svc
from ..services.data import load_series
from .deps import WRITERS, active_or_given_model, audit, get_session, ip_of, owned_dataset, owned_model, runner_of, settings_of

router = APIRouter(tags=["models and forecasts"])


# ----------------------------------------------------------------------------- training and models
@router.post("/datasets/{dataset_id}/train", response_model=JobOut, status_code=202)
def train(dataset_id: int, request: Request, body: TrainIn | None = None, user: User = Depends(WRITERS),
          db: Session = Depends(get_session)):
    body = body or TrainIn()
    ds = owned_dataset(db, user, dataset_id)
    if ds.status != "ready":
        raise HTTPException(409, "The dataset is not ready")
    if ds.valid_hours < MIN_TRAIN_HOURS:
        raise HTTPException(422, f"Insufficient training history: {ds.valid_hours} valid hours, at least {MIN_TRAIN_HOURS} (4 weeks) are required")
    busy = db.scalar(select(Job.id).where(Job.dataset_id == ds.id, Job.kind == "train", Job.status.in_(("queued", "running"))))
    if busy:
        raise HTTPException(409, "A training job is already running for this dataset")
    settings, runner = settings_of(request), runner_of(request)
    job = runner.create(db, user.id, "train", ds.id, {"activate": body.activate})
    runner.submit(job.id, lambda s, ctx: ml_svc.train_bundle(s, ctx, settings, ds.id, body.activate))
    audit(db, user.id, "train_start", ip_of(request), "dataset", ds.id)
    db.refresh(job)
    return job


@router.get("/models", response_model=list[ModelOut])
def list_models(dataset_id: int | None = None, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    q = select(ModelVersion).where(ModelVersion.owner_id == user.id).order_by(ModelVersion.created_at.desc())
    if dataset_id is not None:
        q = q.where(ModelVersion.dataset_id == dataset_id)
    return db.scalars(q).all()


@router.get("/models/{model_id}", response_model=ModelOut)
def get_model(model_id: str, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    return owned_model(db, user, model_id)


@router.post("/models/{model_id}/activate", response_model=ModelOut)
def activate(model_id: str, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    mv = owned_model(db, user, model_id)
    db.execute(update(ModelVersion).where(ModelVersion.dataset_id == mv.dataset_id).values(is_active=False))
    mv.is_active = True
    db.commit()
    audit(db, user.id, "model_activate", ip_of(request), "model", mv.id)
    return mv


@router.delete("/models/{model_id}", status_code=204)
def delete_model(model_id: str, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    mv = owned_model(db, user, model_id)
    s = settings_of(request)
    for mid in mv.horizon_model_ids.values():
        shutil.rmtree(s.models_dir / f"user_{user.id}" / mid, ignore_errors=True)
    db.delete(mv)
    db.commit()
    audit(db, user.id, "model_delete", ip_of(request), "model", model_id)


@router.get("/models/{model_id}/monitoring")
def monitoring(model_id: str, recent_days: int = Query(28, ge=7, le=180), user: User = Depends(current_user_dep),
               db: Session = Depends(get_session)):
    return ml_svc.model_monitoring(db, owned_model(db, user, model_id), recent_days)


# ----------------------------------------------------------------------------- forecasts
@router.post("/forecasts", response_model=ForecastOut, status_code=201)
def create_forecast(body: ForecastIn, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    ds = owned_dataset(db, user, body.dataset_id)
    if ds.status != "ready":
        raise HTTPException(409, "The dataset is not ready")
    mv = active_or_given_model(db, user, ds.id, body.model_id)
    series = load_series(db, ds.id)
    try:
        res = ml_svc.forecast_curve(settings_of(request), mv, series, pd.Timestamp(body.origin) if body.origin else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(410, "Model files are no longer available; retrain the model") from exc
    fc = Forecast(owner_id=user.id, dataset_id=ds.id, model_id=mv.id, origin=res["origin"].to_pydatetime(), points=res["points"],
                  origin_value_missing=res["origin_value_missing"])
    db.add(fc)
    db.commit()
    db.refresh(fc)
    audit(db, user.id, "forecast_create", ip_of(request), "forecast", fc.id)
    return fc


@router.get("/forecasts", response_model=list[ForecastOut])
def list_forecasts(dataset_id: int | None = None, limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user_dep),
                   db: Session = Depends(get_session)):
    q = select(Forecast).where(Forecast.owner_id == user.id).order_by(Forecast.id.desc()).limit(limit)
    if dataset_id is not None:
        q = q.where(Forecast.dataset_id == dataset_id)
    return db.scalars(q).all()


def _owned_forecast(db: Session, user: User, fid: int) -> Forecast:
    fc = db.scalar(select(Forecast).where(Forecast.id == fid, Forecast.owner_id == user.id))
    if fc is None:
        raise HTTPException(404, "Forecast not found")
    return fc


@router.get("/forecasts/{forecast_id}", response_model=ForecastOut)
def get_forecast(forecast_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    return _owned_forecast(db, user, forecast_id)


@router.get("/forecasts/{forecast_id}/export.csv")
def export_forecast(forecast_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    fc = _owned_forecast(db, user, forecast_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["origin", "target_time", "horizon_h", "forecast_kw", "lower_kw", "upper_kw"])
    for p in fc.points:  # numeric/time fields only: no user-supplied text, so no spreadsheet-formula injection
        w.writerow([fc.origin.isoformat(sep=" "), p["ts"], p["horizon"], round(p["kw"], 4), round(p["lower_kw"], 4), round(p["upper_kw"], 4)])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="forecast_{fc.id}.csv"'})


# ----------------------------------------------------------------------------- explainability
@router.post("/explain/local")
def explain_local(body: LocalExplainIn, request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    mv = owned_model(db, user, body.model_id)
    series = load_series(db, mv.dataset_id)
    try:
        return ml_svc.explain_local(settings_of(request), mv, series, body.horizon, pd.Timestamp(body.origin) if body.origin else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/explain/global")
def explain_global(model_id: str, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    mv = owned_model(db, user, model_id)
    return {"model_id": mv.id, "basis": "mean |SHAP| on the hold-out period, per evaluated horizon", "horizons": mv.explanation}


# ----------------------------------------------------------------------------- offline benchmark (UCI) reports
_FIG = re.compile(r"^fig_[a-z0-9_]+\.png$")
_REPORT_DIRS = ("evaluation", "anomaly", "explain", "eda")


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("/benchmark")
def benchmark(request: Request, user: User = Depends(current_user_dep)):
    """Reproducible offline results on the UCI household data (see docs and scripts/)."""
    root = settings_of(request).reports_dir
    figs = {d: sorted(p.name for p in (root / d).glob("fig_*.png")) for d in _REPORT_DIRS if (root / d).is_dir()}
    return {
        "dataset": "UCI Individual household electric power consumption (Hebrail & Berard, 2006), CC BY 4.0",
        "evaluation": _read_json(root / "evaluation" / "evaluation.json"),
        "anomaly": _read_json(root / "anomaly" / "anomaly_summary.json"),
        "anomaly_injection_check": _read_json(root / "anomaly" / "injection_check.json"),
        "shap": _read_json(root / "explain" / "shap_global.json"),
        "figures": figs,
    }


@router.get("/benchmark/figures/{group}/{name}")
def benchmark_figure(group: str, name: str, request: Request, user: User = Depends(current_user_dep)):
    if group not in _REPORT_DIRS or not _FIG.match(name):
        raise HTTPException(404, "Figure not found")
    path = settings_of(request).reports_dir / group / name
    if not path.is_file():
        raise HTTPException(404, "Figure not found")
    return FileResponse(path, media_type="image/png")
