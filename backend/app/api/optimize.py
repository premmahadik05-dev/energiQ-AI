from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ml_engine.optimization.recommendations import cheapest_window, recommend
from ml_engine.optimization.tariff import DEMO_TARIFF, Tariff, TariffError, cost_of_series

from ..models import Anomaly, RecommendationSnapshot, User
from ..models import Tariff as TariffRow
from ..schemas import CostIn, RecommendIn, ScheduleIn, TariffIn
from ..security import current_user_dep
from ..services import ml as ml_svc
from ..services.data import load_series
from .deps import WRITERS, active_or_given_model, audit, get_session, ip_of, owned_dataset, settings_of

router = APIRouter(tags=["optimization"])


def _row_to_tariff(r: TariffRow) -> Tariff:
    try:
        return Tariff(name=r.name, currency=r.currency, weekday_rates=r.weekday_rates, weekend_rates=r.weekend_rates,
                      daily_fixed_charge=r.daily_fixed_charge)
    except TariffError as exc:
        raise HTTPException(422, str(exc)) from exc


def resolve_tariff(db: Session, user: User, tariff_id: int | str) -> Tariff:
    if str(tariff_id) == "demo":
        return DEMO_TARIFF
    try:
        tid = int(tariff_id)
    except ValueError:
        raise HTTPException(422, "tariff_id must be 'demo' or a tariff id") from None
    row = db.scalar(select(TariffRow).where(TariffRow.id == tid, TariffRow.owner_id == user.id))
    if row is None:
        raise HTTPException(404, "Tariff not found")
    return _row_to_tariff(row)


def _tariff_out(t: Tariff, id_: int | str) -> dict:
    d = t.to_dict()
    d["id"] = id_
    return d


@router.get("/tariffs")
def list_tariffs(user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    rows = db.scalars(select(TariffRow).where(TariffRow.owner_id == user.id).order_by(TariffRow.id)).all()
    return [_tariff_out(DEMO_TARIFF, "demo")] + [_tariff_out(_row_to_tariff(r), r.id) for r in rows]


@router.post("/tariffs", status_code=201)
def create_tariff(body: TariffIn, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    try:
        t = Tariff(name=body.name.strip(), currency=body.currency.strip(), weekday_rates=body.weekday_rates,
                   weekend_rates=body.weekend_rates, daily_fixed_charge=body.daily_fixed_charge)
    except TariffError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = TariffRow(owner_id=user.id, name=t.name, currency=t.currency, weekday_rates=t.weekday_rates, weekend_rates=t.weekend_rates,
                    daily_fixed_charge=t.daily_fixed_charge)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already have a tariff with that name") from None
    audit(db, user.id, "tariff_create", ip_of(request), "tariff", row.id)
    return _tariff_out(t, row.id)


@router.delete("/tariffs/{tariff_id}", status_code=204)
def delete_tariff(tariff_id: int, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    row = db.scalar(select(TariffRow).where(TariffRow.id == tariff_id, TariffRow.owner_id == user.id))
    if row is None:
        raise HTTPException(404, "Tariff not found")
    db.delete(row)
    db.commit()
    audit(db, user.id, "tariff_delete", ip_of(request), "tariff", tariff_id)


@router.post("/optimize/cost")
def cost(body: CostIn, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    ds = owned_dataset(db, user, body.dataset_id)
    tariff = resolve_tariff(db, user, body.tariff_id)
    s = load_series(db, ds.id, body.start, body.end)
    if s.dropna().empty:
        raise HTTPException(422, "No valid readings in that range")
    total = cost_of_series(s, tariff)
    monthly = []
    for period, part in s.groupby(s.index.to_period("M")):
        c = cost_of_series(part, tariff)
        monthly.append({"month": str(period), "valid_hours": c["valid_hours"], "energy_kwh": round(c["energy_kwh"], 2),
                        "total_cost": round(c["total_cost"], 2)})
    return {"total": total, "monthly": monthly, "tariff": tariff.to_dict(), "range": [str(s.index.min()), str(s.index.max())]}


def _forecast_series(request: Request, db: Session, user: User, dataset_id: int, model_id: str | None, required: bool = False):
    try:
        mv = active_or_given_model(db, user, dataset_id, model_id)
    except HTTPException:
        if required or model_id:
            raise
        return None
    res = ml_svc.forecast_curve(settings_of(request), mv, load_series(db, dataset_id), None)
    return pd.Series({pd.Timestamp(p["ts"]): p["kw"] for p in res["points"]})


@router.post("/optimize/recommendations")
def recommendations(body: RecommendIn, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    ds = owned_dataset(db, user, body.dataset_id)
    tariff = resolve_tariff(db, user, body.tariff_id)
    end = ds.end_ts
    if end is None:
        raise HTTPException(422, "The dataset has no readings")
    s = load_series(db, ds.id, end - pd.Timedelta(days=130), end)
    fc = _forecast_series(request, db, user, ds.id, body.model_id)
    events = [{"start": str(a.start_ts), "end": str(a.end_ts), "severity_level": a.severity_level, "peak_excess_ratio": a.peak_excess_ratio,
               "explanation": a.explanation} for a in db.scalars(select(Anomaly).where(Anomaly.dataset_id == ds.id, Anomaly.owner_id == user.id))]
    out = recommend(s, tariff, forecast_kw=fc, anomaly_events=events)
    db.add(RecommendationSnapshot(owner_id=user.id, dataset_id=ds.id, tariff_name=tariff.name, payload=out))
    db.commit()
    return out


@router.post("/optimize/schedule")
def schedule(body: ScheduleIn, request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    tariff = resolve_tariff(db, user, body.tariff_id)
    fc, start = None, body.start_after
    if body.dataset_id is not None:
        ds = owned_dataset(db, user, body.dataset_id)
        fc = _forecast_series(request, db, user, ds.id, body.model_id)
        if start is None and ds.end_ts is not None:
            start = ds.end_ts + pd.Timedelta(hours=1)
    start = pd.Timestamp(start) if start is not None else pd.Timestamp.utcnow().tz_localize(None)
    try:
        return cheapest_window(tariff, start, body.duration_h, body.power_kw, forecast_kw=fc,
                               avoid_peak_weight=1.0 if fc is not None else 0.0)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
