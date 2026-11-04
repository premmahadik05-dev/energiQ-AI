from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ml_engine.anomaly.detector import AnomalyConfig

from ..models import Anomaly, AnomalyRun, Job, User, utcnow
from ..schemas import AnomalyOut, AnomalyRunIn, JobOut
from ..security import current_user_dep
from ..services import ml as ml_svc
from .deps import WRITERS, audit, get_session, ip_of, owned_dataset, runner_of

router = APIRouter(tags=["anomalies"])


class AckIn(BaseModel):
    acknowledged: bool = True


@router.post("/datasets/{dataset_id}/anomalies/run", response_model=JobOut, status_code=202)
def run_detection(dataset_id: int, request: Request, body: AnomalyRunIn | None = None, user: User = Depends(WRITERS),
                  db: Session = Depends(get_session)):
    body = body or AnomalyRunIn()
    ds = owned_dataset(db, user, dataset_id)
    need = 24 * 7 * (AnomalyConfig().min_baseline_weeks + 8)
    if ds.status != "ready" or ds.valid_hours < need:
        raise HTTPException(422, f"Insufficient history for anomaly detection: need at least {need // 24} days of valid hours")
    if db.scalar(select(Job.id).where(Job.dataset_id == ds.id, Job.kind == "anomaly", Job.status.in_(("queued", "running")))):
        raise HTTPException(409, "Anomaly detection is already running for this dataset")
    runner = runner_of(request)
    job = runner.create(db, user.id, "anomaly", ds.id, {"sensitivity": body.sensitivity})

    def fn(s, ctx):
        res = ml_svc.run_anomaly_job(s, ctx, ds.id, body.sensitivity)
        ml_svc.delete_old_runs(s, ds.id, res["run_id"])  # only the latest run per dataset is kept
        return res

    runner.submit(job.id, fn)
    audit(db, user.id, "anomaly_run", ip_of(request), "dataset", ds.id, {"sensitivity": body.sensitivity})
    db.refresh(job)
    return job


@router.get("/anomalies")
def list_anomalies(dataset_id: int, severity: str | None = Query(None, pattern="^(low|medium|high)$"),
                   acknowledged: bool | None = None, sort: str = Query("severity", pattern="^(severity|time)$"),
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                   user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    owned_dataset(db, user, dataset_id)
    cond = [Anomaly.dataset_id == dataset_id, Anomaly.owner_id == user.id]
    if severity:
        cond.append(Anomaly.severity == severity)
    if acknowledged is not None:
        cond.append(Anomaly.acknowledged.is_(acknowledged))
    total = db.scalar(select(func.count()).select_from(Anomaly).where(*cond))
    order = (Anomaly.severity_level.desc(), Anomaly.peak_excess_ratio.desc().nulls_last()) if sort == "severity" else (Anomaly.start_ts.desc(),)
    rows = db.scalars(select(Anomaly).where(*cond).order_by(*order).limit(limit).offset(offset)).all()
    return {"total": total, "items": [AnomalyOut.model_validate(r) for r in rows]}


@router.get("/anomalies/summary")
def anomaly_summary(dataset_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    owned_dataset(db, user, dataset_id)
    run = db.scalar(select(AnomalyRun).where(AnomalyRun.dataset_id == dataset_id, AnomalyRun.owner_id == user.id).order_by(AnomalyRun.id.desc()))
    if run is None:
        return {"run": None}
    by_sev = dict(db.execute(select(Anomaly.severity, func.count()).where(Anomaly.run_id == run.id).group_by(Anomaly.severity)).all())
    open_n = db.scalar(select(func.count()).select_from(Anomaly).where(Anomaly.run_id == run.id, Anomaly.acknowledged.is_(False)))
    return {"run": {"id": run.id, "created_at": run.created_at, "sensitivity": run.sensitivity, "config": run.config},
            "summary": run.summary, "by_severity": by_sev, "unacknowledged": open_n,
            "note": "Unsupervised detection. No ground-truth anomaly labels exist, so no accuracy figure is claimed; the alert rate is set by the sensitivity."}


@router.patch("/anomalies/{anomaly_id}", response_model=AnomalyOut)
def acknowledge(anomaly_id: int, body: AckIn, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    a = db.scalar(select(Anomaly).where(Anomaly.id == anomaly_id, Anomaly.owner_id == user.id))
    if a is None:
        raise HTTPException(404, "Anomaly not found")
    a.acknowledged = body.acknowledged
    a.acknowledged_at = utcnow() if body.acknowledged else None
    db.commit()
    audit(db, user.id, "anomaly_ack", ip_of(request), "anomaly", a.id, {"acknowledged": body.acknowledged})
    return a
