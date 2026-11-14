"""Society-level API: overview, consumption, buildings, facilities, forecasts, peaks, anomalies, cost, recommendations, reports.

Societies are shared read-only research data: any signed-in user can read them. Admins import, delete and train; analysts and
admins acknowledge alerts and create reports. ``source_id`` (the dataset's own building identifier) is returned to admins only.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ml_engine.society.serving import explain_from_bundle

from ..models import AnomalyEvent, Building, ForecastResult, Job, Meter, Society, SocietyModel, SocietyReport, User, utcnow
from ..schemas import AnomalyAckIn, BuildingPatch, JobOut, SocietyCostIn, SocietyExplainIn, SocietyRecommendIn, SocietyReportIn
from ..security import current_user_dep, require_roles
from ..services import society as svc
from ..services import society_reports as rep
from .deps import WRITERS, audit, get_session, ip_of, runner_of, settings_of
from .optimize import resolve_tariff

router = APIRouter(tags=["societies"])
ADMIN = require_roles("admin")


def _soc(db: Session, society_id: int) -> Society:
    try:
        return svc.get_society(db, society_id)
    except svc.NotFound:
        raise HTTPException(404, "Society not found") from None


def _admin(user: User) -> bool:
    return user.role == "admin"


def _range(soc: Society, start: datetime | None, end: datetime | None, default_days: int | None = None):
    try:
        return svc.clamp_range(soc, start, end, default_days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _soc_out(soc: Society, db: Session, st=None, detail: bool = False) -> dict:
    model = svc.active_model(db, soc.id)
    n_b = db.scalar(select(func.count(Building.id)).where(Building.society_id == soc.id, Building.is_active.is_(True))) or 0
    area = db.scalar(select(func.sum(Building.floor_area_sqm)).where(Building.society_id == soc.id, Building.is_active.is_(True)))
    out = {"id": soc.id, "key": soc.key, "name": soc.name, "description": soc.description, "timezone": soc.timezone, "start": str(soc.start_ts), "end": str(soc.end_ts),
           "hours": soc.hours, "valid_hours": soc.valid_hours, "buildings": n_b, "floor_area_sqm": area, "has_model": model is not None, "forecast_ready": svc.can_forecast(st, model) if st is not None else None,
           "source_name": soc.source_name, "license": soc.license, "status": soc.status}
    if detail:
        out["source_url"] = soc.source_url
        out["lat"], out["lng"] = soc.lat, soc.lng
        out["data_card"] = soc.meta
        out["model_id"] = model.id if model else None
        out["trained_through"] = str(model.trained_through) if model else None
    return out


# ----------------------------------------------------------------------------- societies
@router.get("/societies")
def list_societies(request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    return [_soc_out(s, db, settings_of(request)) for s in db.scalars(select(Society).order_by(Society.name))]


@router.get("/societies/compare")
def compare_societies(request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    """One row per society with size-independent demand figures and the saved 24 h forecast accuracy, for side-by-side comparison."""
    st = settings_of(request)
    rows = []
    for soc in db.scalars(select(Society).where(Society.status == "ready").order_by(Society.name)):
        base = _soc_out(soc, db, st)
        m = svc.community_metrics(svc.society_frame(db, soc.id)["kwh"], base["floor_area_sqm"])
        if m is None:
            continue
        model = svc.active_model(db, soc.id)
        acc = _acc_summary(model) if model is not None else {}
        a24 = acc.get("24")
        if a24 is not None:
            a24 = {**a24, "mae_pct_of_average": 100 * a24["mae_kw"] / m["avg_kw"] if m["avg_kw"] else None,
                   "gain_vs_baseline_pct": 100 * (1 - a24["mae_kw"] / a24["baseline_mae_kw"]) if a24["baseline_mae_kw"] else None}
        rows.append({**base, **m, "period_start": base["start"], "period_end": base["end"], "accuracy_24h": a24})
    return {"communities": rows,
            "notes": ["Communities differ in size, climate, time zone and years of data, so compare the size-independent figures (energy per m2, load factor, accuracy as a share of average demand) rather than raw kW.",
                      "Energy per m2 per year is the average demand times 8,766 hours divided by the floor area of the active buildings; it needs floor areas and uses valid hours only.",
                      "Accuracy is the held-out test result saved at training time for the 24 h horizon (see Forecasting for the full protocol)."]}


@router.get("/societies/{society_id}")
def society_detail(society_id: int, request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    out = _soc_out(_soc(db, society_id), db, settings_of(request), detail=True)
    card = dict(out["data_card"])
    report = dict(card.get("cleaning_report", {}))
    totals: dict[str, int] = {}
    for counts in report.get("cleaning_counts_per_building", {}).values():
        for k in ("readings", "missing_in_source", "negative", "zero_long_runs", "zero_short", "stuck_sensor", "spike", "valid_out"):
            totals[k] = totals.get(k, 0) + int(counts.get(k, 0))
    card["cleaning_totals"] = totals  # sums over the retained meters; the per-meter breakdown is keyed by the dataset's own identifiers
    card["excluded_count"] = len(card.get("excluded_meters", []))
    if not _admin(user):
        card.pop("excluded_meters", None)  # holds the dataset's own building identifiers
        report.pop("cleaning_counts_per_building", None)
    card["cleaning_report"] = report
    out["data_card"] = card
    return out


@router.delete("/societies/{society_id}", status_code=204)
def delete_society(society_id: int, request: Request, user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    from ..services.society_import import delete_society as _del

    soc = _soc(db, society_id)
    key = soc.key
    _del(db, key)
    audit(db, user.id, "society_delete", ip_of(request), "society", society_id, {"key": key})


# ----------------------------------------------------------------------------- overview
@router.get("/societies/{society_id}/overview")
def overview(society_id: int, request: Request, tariff_id: int | str = "demo", user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    tariff = resolve_tariff(db, user, tariff_id)
    df = svc.society_frame(db, soc.id)
    s = df["kwh"]
    valid = s.dropna()
    if valid.empty:
        raise HTTPException(409, "The society has no valid data")
    as_of = valid.index.max()
    out = {
        "society": _soc_out(soc, db, settings_of(request)), "as_of": str(as_of),
        "as_of_note": "Latest valid hour in the dataset. The data are a historical research record, not a live feed.",
        "latest": {"ts": str(as_of), "demand_kw": float(valid.iloc[-1]), "energy_kwh": float(valid.iloc[-1])},
        "windows": {"last_24h": svc.window_stats(s, as_of, 24), "last_7d": svc.window_stats(s, as_of, 24 * 7), "last_30d": svc.window_stats(s, as_of, 24 * 30)},
        "totals": {"energy_kwh": float(valid.sum()), "avg_kw": float(valid.mean()), "peak_kw": float(valid.max()), "peak_ts": str(valid.idxmax()),
                   "load_factor": float(valid.mean() / valid.max()), "valid_hours": int(len(valid)), "hours": int(len(s))},
        "tariff": {"name": tariff.name, "currency": tariff.currency, "is_demo": tariff.is_demo},
    }
    for key, hours in (("cost_last_24h", 24), ("cost_last_30d", 24 * 30)):
        w = s[s.index > as_of - pd.Timedelta(hours=hours)]
        out[key] = svc.cost_report(w, tariff)["total"] if w.notna().any() else None
    out["forecast"] = None
    model = svc.active_model(db, soc.id)
    if model is not None:
        try:
            fc = svc.live_forecast(db, settings_of(request), soc, model, horizons=list(range(1, 25)))
            out["forecast"] = {"origin": fc["origin"], "trained_through": fc["trained_through"], **svc.forecast_summary(fc["points"], tariff),
                               "note": "Forecast for the 24 hours after the last hour of the dataset, made with models refitted on all data."}
        except (ValueError, FileNotFoundError) as exc:
            out["forecast"] = {"error": str(exc)}
    out["anomalies"] = svc.anomaly_summary(db, soc.id)
    return out


# ----------------------------------------------------------------------------- consumption
@router.get("/societies/{society_id}/consumption")
def consumption(society_id: int, start: datetime | None = None, end: datetime | None = None,
                resolution: str = Query("daily", pattern="^(hourly|daily|weekly|monthly)$"),
                user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    s, e = _range(soc, start, end, 14 if resolution == "hourly" else None)
    if resolution == "hourly" and (e - s) > pd.Timedelta(hours=svc.MAX_HOURLY_POINTS):
        raise HTTPException(422, f"Hourly data is limited to {svc.MAX_HOURLY_POINTS // 24} days per request; choose a shorter range or daily resolution")
    df = svc.society_frame(db, soc.id, s, e)
    agg = svc.aggregate(df["kwh"], resolution)
    return {"society_id": soc.id, "resolution": resolution, "start": str(s), "end": str(e), "unit_energy": "kWh", "unit_demand": "kW",
            "points": svc.to_records(agg)}


# ----------------------------------------------------------------------------- buildings
@router.get("/societies/{society_id}/buildings")
def buildings(society_id: int, start: datetime | None = None, end: datetime | None = None, user: User = Depends(current_user_dep),
              db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    s, e = _range(soc, start, end)
    return {"society_id": soc.id, "start": str(s), "end": str(e), "buildings": svc.building_stats(db, soc, s, e, _admin(user)),
            "note": "Buildings are the dataset's real whole-building meters; no mapping is invented."}


@router.get("/societies/{society_id}/buildings/{building_id}/consumption")
def building_consumption(society_id: int, building_id: int, start: datetime | None = None, end: datetime | None = None,
                         resolution: str = Query("daily", pattern="^(hourly|daily|weekly|monthly)$"), user: User = Depends(current_user_dep),
                         db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    b = db.scalar(select(Building).where(Building.id == building_id, Building.society_id == soc.id))
    if b is None:
        raise HTTPException(404, "Building not found")
    s, e = _range(soc, start, end, 14 if resolution == "hourly" else None)
    if resolution == "hourly" and (e - s) > pd.Timedelta(hours=svc.MAX_HOURLY_POINTS):
        raise HTTPException(422, f"Hourly data is limited to {svc.MAX_HOURLY_POINTS // 24} days per request")
    m = svc.meter_matrix(db, soc.id, s, e, [b.id])
    if m.empty:
        return {"building": b.code, "resolution": resolution, "points": []}
    series = m[b.code].reindex(pd.date_range(s.floor("h"), e.floor("h"), freq="1h"))
    return {"building": b.code, "resolution": resolution, "start": str(s), "end": str(e), "points": svc.to_records(svc.aggregate(series, resolution))}


@router.get("/societies/{society_id}/buildings-monthly")
def buildings_monthly(society_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    """Monthly energy per building (for the stacked comparison chart)."""
    soc = _soc(db, society_id)
    m = svc.meter_matrix(db, soc.id)
    if m.empty:
        return {"months": [], "buildings": []}
    months = m.resample("MS").sum(min_count=1)
    counts = m.resample("MS").count()
    return {"months": [str(t.date()) for t in months.index], "buildings": [
        {"code": c, "energy_kwh": [None if pd.isna(x) else round(float(x), 1) for x in months[c]], "valid_hours": [int(x) for x in counts[c]]} for c in months.columns]}


@router.patch("/societies/{society_id}/buildings/{building_id}")
def patch_building(society_id: int, building_id: int, body: BuildingPatch, request: Request, user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    b = db.scalar(select(Building).where(Building.id == building_id, Building.society_id == soc.id))
    if b is None:
        raise HTTPException(404, "Building not found")
    if body.is_active is not None:
        b.is_active = body.is_active
        for m in db.scalars(select(Meter).where(Meter.building_id == b.id)):
            m.is_active = body.is_active
    db.commit()
    audit(db, user.id, "building_update", ip_of(request), "building", b.id, {"is_active": b.is_active})
    return {"id": b.id, "code": b.code, "is_active": b.is_active}


@router.get("/societies/{society_id}/meters")
def meters(society_id: int, user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    rows = db.execute(select(Meter, Building.code).outerjoin(Building, Building.id == Meter.building_id).where(Meter.society_id == soc.id).order_by(Meter.code)).all()
    return [{"id": m.id, "code": m.code, "building": code, "building_id": m.building_id, "kind": m.kind, "facility_category": m.facility_category, "meter_type": m.meter_type, "unit": m.unit,
             "interval_minutes": m.interval_minutes, "valid_share": m.valid_share, "is_active": m.is_active} for m, code in rows]


# ----------------------------------------------------------------------------- facilities
@router.get("/societies/{society_id}/facilities")
def facilities(society_id: int, start: datetime | None = None, end: datetime | None = None, resolution: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
               user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    out = svc.facilities_overview(db, soc)
    if out["available"]:
        s, e = _range(soc, start, end)
        for c in out["categories"]:
            c["series"] = svc.facility_consumption(db, soc, c["category"], s, e, resolution) if c["measured"] else []
    return out


# ----------------------------------------------------------------------------- peaks
def _peak_evaluation_with_names(model) -> dict | None:
    """The stored daily-peak evaluation plus the names of the two methods it scored.

    Files written before ``model_name`` / ``baseline_name`` existed lost the names (the metrics replaced them), but
    the evaluation was always computed for the 24 h horizon's selected method and best baseline, so the names are read
    from that horizon of the stored cross-validation result. Nothing is recomputed and the stored JSON is not modified.
    """
    if model is None or not model.peaks:
        return None
    out = dict(model.peaks)
    if not out.get("model_name") or not out.get("baseline_name"):
        h24 = (model.evaluation or {}).get("horizons", {}).get("24") or {}
        out.setdefault("model_name", h24.get("best_overall_by_cv"))
        out.setdefault("baseline_name", h24.get("best_baseline_by_cv"))
    return out


@router.get("/societies/{society_id}/peaks")
def peaks(society_id: int, start: datetime | None = None, end: datetime | None = None, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    s, e = _range(soc, start, end)
    df = svc.society_frame(db, soc.id, s, e)
    try:
        out = svc.peak_analysis(df["kwh"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    model = svc.active_model(db, soc.id)
    out["forecast_evaluation"] = _peak_evaluation_with_names(model)
    return out


# ----------------------------------------------------------------------------- models and forecasts
def _acc_summary(model: SocietyModel) -> dict:
    out = {}
    for h, r in model.evaluation.get("horizons", {}).items():
        best, base = r["best_overall_by_cv"], r["best_baseline_by_cv"]
        out[h] = {"model": best, "mae_kw": r["test"][best]["mae"], "rmse_kw": r["test"][best]["rmse"], "mape_pct": r["test"][best]["mape_pct"], "r2": r["test"][best]["r2"],
                  "baseline": base, "baseline_mae_kw": r["test"][base]["mae"]}
    return out


@router.get("/societies/{society_id}/models")
def models(society_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    model = svc.active_model(db, soc.id)
    if model is None:
        return {"model": None, "message": "No model has been trained for this society yet."}
    ev = model.evaluation
    return {"model": {"id": model.id, "trained_through": str(model.trained_through), "created_at": str(model.created_at), "protocol": ev.get("protocol"),
                      "data": ev.get("data"), "versions": ev.get("versions"), "unit": ev.get("unit")},
            "horizons": ev.get("horizons", {}), "deployed": model.bundle.get("horizons", {}), "evaluated_horizons": model.bundle.get("evaluated_horizons", []),
            "note": model.bundle.get("note")}


@router.get("/societies/{society_id}/forecast")
def forecast(society_id: int, request: Request, origin: datetime | None = None, horizons: str | None = None, tariff_id: int | str = "demo",
             user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    model = svc.active_model(db, soc.id)
    if model is None:
        raise HTTPException(409, "No model has been trained for this society yet")
    hs = list(range(1, 25))
    if horizons:
        try:
            hs = sorted({int(x) for x in horizons.split(",")})
        except ValueError:
            raise HTTPException(422, "horizons must be comma-separated integers") from None
        if not hs or any(h < 1 or h > 168 for h in hs):
            raise HTTPException(422, "horizons must be between 1 and 168")
    try:
        res = svc.live_forecast(db, settings_of(request), soc, model, origin, hs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(410, "Model files are not available on this server; retrain the society model") from None
    tariff = resolve_tariff(db, user, tariff_id)
    # the realised values, where the data already contain the forecast hours (a retrospective forecast)
    df = svc.society_frame(db, soc.id)
    for p in res["points"]:
        t = pd.Timestamp(p["ts"])
        p["actual_kw"] = None if t not in df.index or pd.isna(df.loc[t, "kwh"]) else float(df.loc[t, "kwh"])
    return {**res, "summary": svc.forecast_summary(res["points"], tariff), "model_id": model.id,
            "accuracy": _acc_summary(model),
            "note": "Each point is a direct forecast from the origin hour using data up to the origin only. Ranges are empirical 80% bands from out-of-fold residuals."}


@router.get("/societies/{society_id}/backtest")
def backtest(society_id: int, horizon: int = Query(24, ge=1, le=168), start: datetime | None = None, end: datetime | None = None,
             limit: int = Query(2500, ge=1, le=6000), user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    """Held-out test-period forecasts of the selected model against what actually happened (real out-of-sample results)."""
    soc = _soc(db, society_id)
    model = svc.active_model(db, soc.id)
    if model is None:
        raise HTTPException(409, "No model has been trained for this society yet")
    q = select(ForecastResult).where(ForecastResult.society_id == soc.id, ForecastResult.horizon_h == horizon, ForecastResult.model_id == model.id)
    if start is not None:
        q = q.where(ForecastResult.target_ts >= svc.naive_ts(start).to_pydatetime())
    if end is not None:
        q = q.where(ForecastResult.target_ts <= svc.naive_ts(end).to_pydatetime())
    rows = db.scalars(q.order_by(ForecastResult.target_ts).limit(limit)).all()
    if not rows:
        raise HTTPException(404, f"No held-out results stored for horizon {horizon} h (evaluated horizons: {model.bundle.get('evaluated_horizons')})")
    r = model.evaluation["horizons"][str(horizon)]
    return {"horizon": horizon, "model": r["best_overall_by_cv"], "baseline": r["best_baseline_by_cv"],
            "test_period": model.evaluation["protocol"]["test_period"], "metrics": r["test"][r["best_overall_by_cv"]], "baseline_metrics": r["test"][r["best_baseline_by_cv"]],
            "points": [{"origin": str(x.origin), "ts": str(x.target_ts), "actual_kw": x.actual_kw, "predicted_kw": round(x.predicted_kw, 3), "lower_kw": None if x.lower_kw is None else round(x.lower_kw, 3),
                        "upper_kw": None if x.upper_kw is None else round(x.upper_kw, 3), "baseline_kw": x.baseline_kw} for x in rows]}


@router.get("/societies/{society_id}/error-analysis")
def error_analysis(society_id: int, horizon: int = Query(24, ge=1, le=168), user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    """Where the selected model's held-out forecasts go wrong: error by hour of day, error distribution, bias and the worst misses."""
    soc = _soc(db, society_id)
    model = svc.active_model(db, soc.id)
    if model is None:
        raise HTTPException(409, "No model has been trained for this society yet")
    rows = db.scalars(select(ForecastResult).where(ForecastResult.society_id == soc.id, ForecastResult.horizon_h == horizon, ForecastResult.model_id == model.id).order_by(ForecastResult.target_ts)).all()
    if not rows:
        raise HTTPException(404, f"No held-out results stored for horizon {horizon} h (evaluated horizons: {model.bundle.get('evaluated_horizons')})")
    df = pd.DataFrame([{"ts": r.target_ts, "actual": r.actual_kw, "predicted": r.predicted_kw, "lower": r.lower_kw, "upper": r.upper_kw, "baseline": r.baseline_kw} for r in rows])
    try:
        out = svc.error_analysis(df)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    r = model.evaluation["horizons"][str(horizon)]
    return {"horizon": horizon, "model": r["best_overall_by_cv"], "baseline": r["best_baseline_by_cv"], "test_period": model.evaluation["protocol"]["test_period"], **out,
            "note": "Error = predicted minus measured demand. Positive bias means the model over-forecasts on average. Only hours with a valid measured value are counted."}


@router.get("/societies/{society_id}/explain/global")
def explain_global(society_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    model = svc.active_model(db, soc.id)
    if model is None:
        raise HTTPException(409, "No model has been trained for this society yet")
    return {"society_id": soc.id, "model_id": model.id, **model.explanation}


@router.post("/societies/{society_id}/explain/local")
def explain_local(society_id: int, body: SocietyExplainIn, request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    model = svc.active_model(db, soc.id)
    if model is None:
        raise HTTPException(409, "No model has been trained for this society yet")
    if not svc.can_forecast(settings_of(request), model):
        raise HTTPException(410, "The deployment models for this society are not installed on this server")
    df = svc.society_frame(db, soc.id)
    origin = svc.naive_ts(body.origin) if body.origin else df["kwh"].dropna().index.max()
    try:
        return explain_from_bundle(svc.bundle_dir(settings_of(request), model), df["kwh"], df[["airTemperature", "dewTemperature", "windSpeed"]], body.horizon, origin)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(410, "Model files are not available on this server") from None


# ----------------------------------------------------------------------------- anomalies
def _event_out(e: AnomalyEvent, code: str | None, is_admin: bool) -> dict:
    return {"id": e.id, "scope": e.scope, "building": code, "start_ts": str(e.start_ts), "end_ts": str(e.end_ts), "hours": e.hours, "types": e.types,
            "severity": e.severity, "severity_level": e.severity_level, "peak_ts": str(e.peak_ts), "peak_kw": e.peak_kw, "expected_kw": e.expected_kw,
            "excess_ratio": e.excess_ratio, "explanation": e.explanation, "top_contributors": e.top_contributors, "context": e.context,
            "acknowledged": e.acknowledged}


@router.get("/societies/{society_id}/anomalies")
def anomalies(society_id: int, scope: str | None = Query(None, pattern="^(society|building)$"), severity: str | None = Query(None, pattern="^(low|medium|high)$"),
              min_severity: int = Query(1, ge=1, le=3), building_id: int | None = None, acknowledged: bool | None = None, start: datetime | None = None,
              end: datetime | None = None, sort: str = Query("time", pattern="^(time|severity)$"), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
              user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    q = select(AnomalyEvent, Building.code).outerjoin(Building, Building.id == AnomalyEvent.building_id).where(AnomalyEvent.society_id == soc.id,
                                                                                                             AnomalyEvent.severity_level >= min_severity)
    cq = select(func.count(AnomalyEvent.id)).where(AnomalyEvent.society_id == soc.id, AnomalyEvent.severity_level >= min_severity)
    for cond, val in ((AnomalyEvent.scope, scope), (AnomalyEvent.severity, severity), (AnomalyEvent.building_id, building_id), (AnomalyEvent.acknowledged, acknowledged)):
        if val is not None:
            q, cq = q.where(cond == val), cq.where(cond == val)
    if start is not None:
        q, cq = q.where(AnomalyEvent.end_ts >= svc.naive_ts(start).to_pydatetime()), cq.where(AnomalyEvent.end_ts >= svc.naive_ts(start).to_pydatetime())
    if end is not None:
        q, cq = q.where(AnomalyEvent.start_ts <= svc.naive_ts(end).to_pydatetime()), cq.where(AnomalyEvent.start_ts <= svc.naive_ts(end).to_pydatetime())
    order = (AnomalyEvent.severity_level.desc(), AnomalyEvent.start_ts.desc()) if sort == "severity" else (AnomalyEvent.start_ts.desc(),)
    rows = db.execute(q.order_by(*order).limit(limit).offset(offset)).all()
    return {"total": db.scalar(cq) or 0, "summary": svc.anomaly_summary(db, soc.id), "events": [_event_out(e, c, _admin(user)) for e, c in rows],
            "note": "Alerts mark readings that are unusual for that hour of the week. There are no ground-truth fault labels, so no detection accuracy is claimed."}


@router.patch("/societies/{society_id}/anomalies/{event_id}")
def ack_anomaly(society_id: int, event_id: int, body: AnomalyAckIn, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    e = db.scalar(select(AnomalyEvent).where(AnomalyEvent.id == event_id, AnomalyEvent.society_id == soc.id))
    if e is None:
        raise HTTPException(404, "Alert not found")
    e.acknowledged = body.acknowledged
    e.acknowledged_at = utcnow() if body.acknowledged else None
    e.acknowledged_by = user.id if body.acknowledged else None
    db.commit()
    audit(db, user.id, "society_anomaly_ack", ip_of(request), "anomaly_event", e.id, {"acknowledged": body.acknowledged})
    code = db.scalar(select(Building.code).where(Building.id == e.building_id)) if e.building_id else None
    return _event_out(e, code, _admin(user))


# ----------------------------------------------------------------------------- cost and recommendations
@router.post("/societies/{society_id}/cost")
def cost(society_id: int, body: SocietyCostIn, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    tariff = resolve_tariff(db, user, body.tariff_id)
    s, e = _range(soc, body.start, body.end)
    df = svc.society_frame(db, soc.id, s, e)
    try:
        return svc.cost_report(df["kwh"], tariff)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/societies/{society_id}/recommendations")
def recommendations(society_id: int, body: SocietyRecommendIn, request: Request, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    tariff = resolve_tariff(db, user, body.tariff_id)
    return svc.recommendations(db, settings_of(request), soc, tariff)


# ----------------------------------------------------------------------------- reports
def _report_out(r: SocietyReport) -> dict:
    return {"id": r.id, "society_id": r.society_id, "kind": r.kind, "format": r.format, "title": r.title, "period_start": str(r.period_start) if r.period_start else None,
            "period_end": str(r.period_end) if r.period_end else None, "created_at": str(r.created_at), "filename": r.filename, "size_bytes": r.size_bytes}


@router.get("/societies/{society_id}/reports")
def list_reports(society_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    rows = db.scalars(select(SocietyReport).where(SocietyReport.society_id == soc.id).order_by(SocietyReport.id.desc()).limit(50)).all()
    return [_report_out(r) for r in rows]


@router.post("/societies/{society_id}/reports", status_code=201)
def create_report(society_id: int, body: SocietyReportIn, request: Request, user: User = Depends(WRITERS), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    if body.kind == "monthly" and body.format != "pdf":
        raise HTTPException(422, "The monthly report is a PDF; choose a CSV kind for data exports")
    if body.kind != "monthly" and body.format != "csv":
        raise HTTPException(422, f"The {body.kind} report is available as CSV")
    tariff = resolve_tariff(db, user, body.tariff_id)
    end_default = pd.Timestamp(soc.end_ts)
    s, e = _range(soc, body.start, body.end, 31 if body.kind == "monthly" else None)
    if body.kind == "monthly" and body.start is None and body.end is None:  # the calendar month containing the last hour of data
        s = max(pd.Timestamp(soc.start_ts), pd.Timestamp(year=end_default.year, month=end_default.month, day=1))
    df = svc.society_frame(db, soc.id, s, e)
    series = df["kwh"]
    stamp = f"{soc.key}_{body.kind}_{s:%Y%m%d}_{e:%Y%m%d}"
    try:
        if body.kind == "consumption":
            if body.resolution == "hourly" and (e - s) > pd.Timedelta(hours=svc.MAX_HOURLY_POINTS * 3):
                raise ValueError("Hourly exports are limited to 360 days; choose daily resolution for longer ranges")
            content, name, title = rep.csv_consumption(svc.aggregate(series, body.resolution)), f"{stamp}_{body.resolution}.csv", f"Consumption ({body.resolution})"
        elif body.kind == "buildings":
            content, name, title = rep.csv_buildings(svc.building_stats(db, soc, s, e, False)), f"{stamp}.csv", "Building comparison"
        elif body.kind == "cost":
            content, name, title = rep.csv_cost(svc.cost_report(series, tariff)), f"{stamp}.csv", "Cost estimate (not a bill)"
        elif body.kind == "anomalies":
            rows = db.execute(select(AnomalyEvent, Building.code).outerjoin(Building, Building.id == AnomalyEvent.building_id).where(
                AnomalyEvent.society_id == soc.id, AnomalyEvent.end_ts >= s.to_pydatetime(), AnomalyEvent.start_ts <= e.to_pydatetime()).order_by(AnomalyEvent.start_ts)).all()
            content, name, title = rep.csv_anomalies([_event_out(a, c, False) for a, c in rows]), f"{stamp}.csv", "Anomaly alerts"
        elif body.kind == "forecast":
            model = svc.active_model(db, soc.id)
            if model is None:
                raise ValueError("No model has been trained for this society yet")
            rows = db.scalars(select(ForecastResult).where(ForecastResult.society_id == soc.id, ForecastResult.horizon_h == body.horizon, ForecastResult.model_id == model.id,
                                                            ForecastResult.target_ts >= s.to_pydatetime(), ForecastResult.target_ts <= e.to_pydatetime()).order_by(ForecastResult.target_ts)).all()
            if not rows:
                raise ValueError(f"No held-out forecasts stored for {body.horizon} h in that range (test period {model.evaluation['protocol']['test_period']})")
            pts = [{"origin": str(x.origin), "ts": str(x.target_ts), "horizon": x.horizon_h, "actual_kw": x.actual_kw, "predicted_kw": x.predicted_kw, "lower_kw": x.lower_kw,
                    "upper_kw": x.upper_kw, "baseline_kw": x.baseline_kw} for x in rows]
            content, name, title = rep.csv_forecast(pts, "", "backtest"), f"{stamp}_h{body.horizon}.csv", f"Held-out forecasts ({body.horizon} h ahead)"
        else:
            blds = svc.building_stats(db, soc, s, e, False)
            evs = [_event_out(a, c, False) for a, c in db.execute(select(AnomalyEvent, Building.code).outerjoin(Building, Building.id == AnomalyEvent.building_id).where(
                AnomalyEvent.society_id == soc.id, AnomalyEvent.scope == "society", AnomalyEvent.end_ts >= s.to_pydatetime(), AnomalyEvent.start_ts <= e.to_pydatetime()).order_by(
                AnomalyEvent.start_ts)).all()]
            try:
                cost_rep = svc.cost_report(series, tariff)
            except ValueError:
                cost_rep = None
            try:
                pk = svc.peak_analysis(series)
            except ValueError:
                pk = None
            model = svc.active_model(db, soc.id)
            acc = None
            if model is not None:
                acc = {h: {"model": a["model"], "mae": a["mae_kw"], "mape_pct": a["mape_pct"], "r2": a["r2"], "baseline_mae": a["baseline_mae_kw"]}
                       for h, a in _acc_summary(model).items()}
            content = rep.pdf_monthly(soc, (s, e), series, blds, evs, cost_rep, pk, acc, user.full_name or user.email)
            name, title = f"{stamp}.pdf", "Society report"
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = SocietyReport(society_id=soc.id, kind=body.kind, format=body.format, title=title, period_start=s.to_pydatetime(), period_end=e.to_pydatetime(),
                        params=json.loads(body.model_dump_json(exclude={"start", "end"})), created_by=user.id, filename=name, size_bytes=len(content), content=content)
    db.add(row)
    db.commit()
    audit(db, user.id, "society_report", ip_of(request), "society", soc.id, {"kind": body.kind, "format": body.format})
    return _report_out(row)


@router.get("/societies/{society_id}/reports/{report_id}/download")
def download_report(society_id: int, report_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    soc = _soc(db, society_id)
    r = db.scalar(select(SocietyReport).where(SocietyReport.id == report_id, SocietyReport.society_id == soc.id))
    if r is None:
        raise HTTPException(404, "Report not found")
    return Response(r.content, media_type="application/pdf" if r.format == "pdf" else "text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{r.filename}"'})


# ----------------------------------------------------------------------------- admin: import and train
@router.post("/admin/societies/import-bundled", response_model=JobOut, status_code=202)
def import_bundled(request: Request, replace: bool = False, user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    """Load the bundled processed real societies (see scripts/society_prepare.py) that are not yet in the database."""
    from ..services.society_import import import_processed

    st, runner = settings_of(request), runner_of(request)
    index_path = st.society_data_dir / "societies.json"
    if not index_path.is_file():
        raise HTTPException(404, "No processed societies are installed on this server; run scripts/society_prepare.py")
    keys = [e["key"] for e in json.loads(index_path.read_text())["societies"]]
    job = runner.create(db, user.id, "society_import", None, {"keys": keys, "replace": replace})

    def work(s: Session, ctx):
        done, skipped = [], []
        have = set(s.scalars(select(Society.key)))
        for i, k in enumerate(keys):
            ctx.progress(i / len(keys), f"Importing {k}")
            if k in have and not replace:
                skipped.append(k)
                continue
            import_processed(s, k, st.society_data_dir, st.society_dir, replace=replace, log_fn=lambda *a: None)
            done.append(k)
        return {"imported": done, "skipped": skipped}

    runner.submit(job.id, work)
    audit(db, user.id, "society_import", ip_of(request), "society", "bundled", {"replace": replace})
    db.refresh(job)
    return job


MAX_SOCIETY_UPLOAD_MB = 40


def _read_upload(up: UploadFile, limit_mb: int) -> bytes:
    data = up.file.read(limit_mb * (1 << 20) + 1)
    if len(data) > limit_mb * (1 << 20):
        raise HTTPException(413, f"File exceeds the {limit_mb} MB limit")
    if not data:
        raise HTTPException(422, "The file is empty")
    if b"\x00" in data[:65536]:
        raise HTTPException(415, "The file looks binary, not text/CSV")
    if Path(up.filename or "").suffix.lower() not in (".csv", ".txt"):
        raise HTTPException(415, "Only .csv files are accepted")
    return data


@router.post("/admin/societies/upload", response_model=JobOut, status_code=202)
def upload_society(request: Request, name: str = Form(..., min_length=3, max_length=120), unit: str = Form("kwh", pattern="^(kwh|kw)$"), description: str = Form("", max_length=500),
                   file: UploadFile = File(...), mapping: UploadFile | None = File(None), user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    """Add a society from a wide CSV of real meter readings (timestamp + one column per meter) and an optional meter mapping CSV.

    The file is validated now (format errors return 422 immediately); cleaning, aggregation and storing run as a job.
    The upload is real data supplied by the administrator: nothing is generated or filled in.
    """
    from ml_engine.society.ingest import IngestError, UploadRule, build_uploaded_society, read_mapping_csv, read_wide_csv, slugify

    from ..services.society_import import import_built

    runner = runner_of(request)
    try:
        hourly, report = read_wide_csv(_read_upload(file, MAX_SOCIETY_UPLOAD_MB), unit=unit)
        mapping_df = read_mapping_csv(_read_upload(mapping, 2) if mapping is not None else None, list(hourly.columns))
    except IngestError as exc:
        raise HTTPException(422, str(exc)) from exc
    base = slugify(name)
    key, i = base, 1
    while db.scalar(select(Society.id).where(Society.key == key)) is not None:
        i += 1
        key = f"{base}-{i}"[:40]
    busy = db.scalar(select(Job.id).where(Job.kind == "society_upload", Job.status.in_(("queued", "running"))))
    if busy:
        raise HTTPException(409, "Another society upload is still being processed")
    job = runner.create(db, user.id, "society_upload", None, {"key": key, "name": name, "unit": unit, "meters": int(hourly.shape[1])})

    def work(s: Session, ctx):
        ctx.progress(0.1, "Cleaning meters")
        try:
            built = build_uploaded_society(key, hourly, mapping_df, UploadRule())
        except IngestError as exc:
            raise ValueError(str(exc)) from exc
        ctx.progress(0.5, "Storing readings")
        soc = import_built(s, built, name, description, report, mapping is not None, user.id)
        return {"society_id": soc.id, "key": soc.key, "buildings": int((built["meters"]["kind"] == "building").sum()),
                "facility_meters": int((built["meters"]["kind"] == "facility").sum()), "excluded_meters": len(built["excluded"]),
                "valid_hours": soc.valid_hours, "hours": soc.hours}

    runner.submit(job.id, work)
    audit(db, user.id, "society_upload", ip_of(request), "society", key, {"meters": int(hourly.shape[1]), "unit": unit})
    db.refresh(job)
    return job


@router.post("/admin/societies/{society_id}/train", response_model=JobOut, status_code=202)
def train_society(society_id: int, request: Request, user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    """Evaluate (chronological split, expanding-window CV) and deploy forecasters for a stored society, then run anomaly detection."""
    from ml_engine.society.runner import MIN_VALID_HOURS

    from ..services.society_import import train_society as _train

    soc = _soc(db, society_id)
    if soc.valid_hours < MIN_VALID_HOURS:
        raise HTTPException(422, f"Too little data to evaluate: {soc.valid_hours} valid hours, at least {MIN_VALID_HOURS} (about nine months) are needed")
    if db.scalar(select(Job.id).where(Job.kind == "society_train", Job.status.in_(("queued", "running")))):
        raise HTTPException(409, "A society training job is already running")
    st, runner = settings_of(request), runner_of(request)
    job = runner.create(db, user.id, "society_train", None, {"society_id": soc.id})
    runner.submit(job.id, lambda s, ctx: _train(s, ctx, st, soc.id))
    audit(db, user.id, "society_train", ip_of(request), "society", soc.id)
    db.refresh(job)
    return job
