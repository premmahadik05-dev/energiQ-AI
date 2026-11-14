"""Society-level data access and analytics on top of the database.

All figures are computed from the stored cleaned meter data. Energy is kWh (sum of hourly kWh), demand is kW
(hourly mean, numerically the hourly kWh). Missing hours are never filled: a sum over a period covers the valid
hours only and the response says how many hours that is out of how many were expected.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ml_engine.optimization.tariff import Tariff, cost_of_series
from ml_engine.society.recommendations import recommend_society
from ml_engine.society.serving import forecast_from_bundle

from ..config import Settings
from ..models import AnomalyEvent, Building, ConsumptionRecord, Meter, Society, SocietyHourly, SocietyModel

RESOLUTIONS = ("hourly", "daily", "weekly", "monthly")
FACILITY_CATEGORIES = {"lift": "Lifts", "pump": "Water pumps", "streetlight": "Street / compound lighting", "clubhouse": "Clubhouse and amenities"}
MAX_HOURLY_POINTS = 24 * 120


class NotFound(LookupError):
    pass


def get_society(db: Session, society_id: int) -> Society:
    s = db.get(Society, society_id)
    if s is None:
        raise NotFound("Society not found")
    return s


def naive_ts(v) -> pd.Timestamp:
    """User-supplied time as a naive wall-clock timestamp (the data are stored in the site's local clock time; a UTC offset is dropped, not converted)."""
    t = pd.Timestamp(v)
    return t.tz_localize(None) if t.tzinfo is not None else t


def _ts(v) -> pd.Timestamp | None:
    return None if v is None else naive_ts(v)


# ----------------------------------------------------------------------------- loading
def society_frame(db: Session, society_id: int, start=None, end=None) -> pd.DataFrame:
    """Hourly society total (kwh = kW) and weather on a complete hourly grid; missing hours are NaN."""
    q = select(SocietyHourly.ts, SocietyHourly.kwh, SocietyHourly.n_valid_meters, SocietyHourly.air_temp_c,
               SocietyHourly.dew_temp_c, SocietyHourly.wind_ms).where(SocietyHourly.society_id == society_id).order_by(SocietyHourly.ts)
    if start is not None:
        q = q.where(SocietyHourly.ts >= naive_ts(start).to_pydatetime())
    if end is not None:
        q = q.where(SocietyHourly.ts <= naive_ts(end).to_pydatetime())
    rows = db.execute(q).all()
    if not rows:
        return pd.DataFrame(columns=["kwh", "n_valid", "airTemperature", "dewTemperature", "windSpeed"], index=pd.DatetimeIndex([], name="ts"))
    df = pd.DataFrame(rows, columns=["ts", "kwh", "n_valid", "airTemperature", "dewTemperature", "windSpeed"]).set_index("ts")
    df.index = pd.DatetimeIndex(df.index, name="ts")
    full = pd.date_range(df.index.min(), df.index.max(), freq="1h")
    return df.astype("float64").reindex(full).rename_axis("ts")


def meter_matrix(db: Session, society_id: int, start=None, end=None, building_ids: list[int] | None = None) -> pd.DataFrame:
    """Hourly kWh per building meter (columns = building code)."""
    q = (select(ConsumptionRecord.ts, Building.code, ConsumptionRecord.kwh)
         .join(Meter, Meter.id == ConsumptionRecord.meter_id).join(Building, Building.id == Meter.building_id)
         .where(Meter.society_id == society_id, Meter.kind == "building", Building.is_active.is_(True), Meter.is_active.is_(True)))
    if building_ids:
        q = q.where(Building.id.in_(building_ids))
    if start is not None:
        q = q.where(ConsumptionRecord.ts >= naive_ts(start).to_pydatetime())
    if end is not None:
        q = q.where(ConsumptionRecord.ts <= naive_ts(end).to_pydatetime())
    rows = db.execute(q).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ts", "code", "kwh"])
    m = df.pivot(index="ts", columns="code", values="kwh").sort_index()
    m.index = pd.DatetimeIndex(m.index, name="ts")
    return m.astype("float64")


def clamp_range(soc: Society, start, end, default_days: int | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    lo, hi = _ts(soc.start_ts), _ts(soc.end_ts)
    e = min(naive_ts(end), hi) if end is not None else hi
    s = max(naive_ts(start), lo) if start is not None else (max(lo, e - pd.Timedelta(days=default_days)) if default_days else lo)
    if s > e:
        raise ValueError("start must not be after end")
    return s, e


# ----------------------------------------------------------------------------- aggregation
_FREQ = {"daily": "D", "weekly": "W-MON", "monthly": "MS"}


def aggregate(s: pd.Series, resolution: str) -> pd.DataFrame:
    """Energy (kWh, valid hours only), mean/peak demand (kW) and coverage per period."""
    if resolution == "hourly":
        out = pd.DataFrame({"energy_kwh": s, "avg_kw": s, "peak_kw": s, "valid_hours": s.notna().astype(int), "expected_hours": 1})
    else:
        kw = {"label": "left", "closed": "left"}
        r = s.resample(_FREQ[resolution], **kw)
        out = pd.DataFrame({"energy_kwh": r.sum(min_count=1), "avg_kw": r.mean(), "peak_kw": r.max(),
                            "valid_hours": r.count(), "expected_hours": r.size()})
    out["complete"] = out["valid_hours"] == out["expected_hours"]
    return out


def to_records(df: pd.DataFrame, round_to: int = 3) -> list[dict]:
    rows = []
    for ts, r in df.iterrows():
        d = {"ts": str(ts)}
        for k, v in r.items():
            if isinstance(v, (bool, np.bool_)):
                d[k] = bool(v)
            elif v is None or (isinstance(v, float) and np.isnan(v)):
                d[k] = None
            elif isinstance(v, (int, np.integer)):
                d[k] = int(v)
            else:
                d[k] = round(float(v), round_to)
        rows.append(d)
    return rows


def window_stats(s: pd.Series, end: pd.Timestamp, hours: int) -> dict:
    w = s[(s.index > end - pd.Timedelta(hours=hours)) & (s.index <= end)]
    prev = s[(s.index > end - pd.Timedelta(hours=2 * hours)) & (s.index <= end - pd.Timedelta(hours=hours))]
    v, pv = w.dropna(), prev.dropna()
    energy = float(v.sum()) if len(v) else None
    change = None
    if len(v) and len(pv) and len(v) == len(pv) == hours and pv.sum() > 0:  # only compare two complete windows
        change = float(100 * (v.sum() / pv.sum() - 1))
    return {"hours": hours, "energy_kwh": energy, "avg_kw": float(v.mean()) if len(v) else None, "peak_kw": float(v.max()) if len(v) else None,
            "valid_hours": int(len(v)), "change_vs_previous_pct": change}


# ----------------------------------------------------------------------------- models and forecasts
def active_model(db: Session, society_id: int) -> SocietyModel | None:
    return db.scalar(select(SocietyModel).where(SocietyModel.society_id == society_id, SocietyModel.is_active.is_(True))
                     .order_by(SocietyModel.created_at.desc()))


def bundle_dir(settings: Settings, model: SocietyModel) -> Path:
    return settings.society_dir / model.artifact_key


def can_forecast(settings: Settings, model: SocietyModel | None) -> bool:
    """True when the deployment models of ``model`` are installed on this server (evaluation results can exist without them)."""
    return model is not None and bool(model.bundle) and (bundle_dir(settings, model) / "bundle.json").is_file()


def live_forecast(db: Session, settings: Settings, soc: Society, model: SocietyModel, origin=None, horizons: list[int] | None = None) -> dict:
    if not can_forecast(settings, model):
        raise FileNotFoundError("The deployment models for this society are not installed on this server")
    df = society_frame(db, soc.id)
    if df.empty:
        raise ValueError("The society has no data")
    series = df["kwh"].rename("demand_kw")
    weather = df[["airTemperature", "dewTemperature", "windSpeed"]]
    last_valid = series.dropna().index.max()
    res = forecast_from_bundle(bundle_dir(settings, model), series, weather, naive_ts(origin) if origin is not None else last_valid, horizons)
    for p in res["points"]:
        p["ts"] = str(p["ts"])
    res["origin"] = str(res["origin"])
    return res


def forecast_summary(points: list[dict], tariff: Tariff | None) -> dict:
    hourly = [p for p in points if p["horizon"] <= 24]
    out: dict = {}
    if len(hourly) == 24:
        kw = np.array([p["kw"] for p in hourly])
        lo = np.array([p["lower_kw"] for p in hourly])
        hi = np.array([p["upper_kw"] for p in hourly])
        i = int(kw.argmax())
        out = {"next_24h_energy_kwh": float(kw.sum()), "next_24h_energy_range_kwh": [float(lo.sum()), float(hi.sum())],
               "peak_kw": float(kw[i]), "peak_range_kw": [float(lo[i]), float(hi[i])], "peak_time": hourly[i]["ts"],
               "range_note": "Per-hour empirical 80% ranges; the summed range adds the hourly ranges, so it is wider than a range for the total would be."}
        if tariff is not None:
            idx = pd.DatetimeIndex([pd.Timestamp(p["ts"]) for p in hourly])
            rates = tariff.rates_for(idx)
            out["next_24h_energy_cost"] = float((kw * rates).sum() + tariff.daily_fixed_charge)
            out["currency"] = tariff.currency
    return out


# ----------------------------------------------------------------------------- cost
def cost_report(s: pd.Series, tariff: Tariff) -> dict:
    v = s.dropna()
    if v.empty:
        raise ValueError("No valid readings in that range")
    total = cost_of_series(s, tariff)
    rates = pd.Series(tariff.rates_for(v.index), index=v.index)
    cost_h = v * rates
    daily = pd.DataFrame({"energy_kwh": v.resample("D").sum(), "energy_cost": cost_h.resample("D").sum(), "valid_hours": v.resample("D").count()})
    daily = daily[daily["valid_hours"] > 0]
    daily["total_cost"] = daily["energy_cost"] + tariff.daily_fixed_charge * daily["valid_hours"] / 24.0
    monthly = pd.DataFrame({"energy_kwh": v.resample("MS").sum(), "energy_cost": cost_h.resample("MS").sum(), "valid_hours": v.resample("MS").count()})
    monthly = monthly[monthly["valid_hours"] > 0]
    monthly["total_cost"] = monthly["energy_cost"] + tariff.daily_fixed_charge * monthly["valid_hours"] / 24.0
    lo, hi = tariff.cheapest_and_dearest()
    dear = rates >= hi - 1e-12
    peak_split = None
    if hi - lo > 1e-9 and dear.any():
        peak_split = {"dearest_rate_per_kwh": hi, "dearest_hours": sorted({int(h) for h in v.index[dear].hour}),
                      "energy_share_pct": float(100 * v[dear].sum() / v.sum()), "cost_share_pct": float(100 * cost_h[dear].sum() / cost_h.sum()),
                      "time_share_pct": float(100 * dear.mean())}
    last30 = daily.tail(30)
    projected = None
    if len(last30) >= 14:
        projected = {"basis_days": int(len(last30)), "avg_daily_cost": float(last30["total_cost"].mean()),
                     "projected_30_day_cost": float(last30["total_cost"].mean() * 30),
                     "assumption": "the average of the last valid days repeats for the next 30 days; weather, occupancy and tariff changes are not modelled"}
    return {"total": total, "daily": to_records(daily, 2), "monthly": to_records(monthly, 2), "peak_split": peak_split, "projected": projected,
            "tariff": tariff.to_dict(), "range": [str(v.index.min()), str(v.index.max())],
            "disclaimer": "Estimate from measured kWh and the tariff you entered. It is not a utility bill: taxes, demand charges, tiers and fees are not modelled."}


def load_duration(v: pd.Series, points: int = 101) -> list[dict]:
    """Load-duration curve: for each share of the valid hours, the demand that was met or exceeded for that share of the time."""
    v = v.dropna()
    if v.empty:
        return []
    pct = np.linspace(0, 100, points)
    return [{"percent_of_time": round(float(p), 2), "kw": float(v.quantile(1 - p / 100))} for p in pct]


def demand_distribution(v: pd.Series, bins: int = 20) -> list[dict]:
    """Histogram of hourly demand: how many valid hours fell in each equal-width kW band."""
    v = v.dropna()
    if v.empty:
        return []
    counts, edges = np.histogram(v.to_numpy(), bins=bins)
    return [{"from_kw": float(edges[i]), "to_kw": float(edges[i + 1]), "hours": int(counts[i])} for i in range(len(counts))]


HOURS_PER_YEAR = 8766  # 365.25 days


def community_metrics(s: pd.Series, floor_area_sqm: float | None) -> dict | None:
    """Size-independent and absolute demand figures of one society, from its valid hours only."""
    v = s.dropna()
    if v.empty:
        return None
    avg, peak = float(v.mean()), float(v.max())
    area = float(floor_area_sqm) if floor_area_sqm else None
    return {"valid_hours": int(len(v)), "energy_kwh": float(v.sum()), "avg_kw": avg, "peak_kw": peak, "load_factor": avg / peak if peak > 0 else None,
            "kwh_per_sqm_year": avg * HOURS_PER_YEAR / area if area else None, "avg_w_per_sqm": avg * 1000 / area if area else None,
            "peak_w_per_sqm": peak * 1000 / area if area else None}


def error_analysis(df: pd.DataFrame, bins: int = 24) -> dict:
    """Where does a held-out forecast go wrong? ``df`` has columns ts, actual, predicted, lower, upper, baseline (kW); only rows with a measured actual count."""
    d = df.dropna(subset=["actual", "predicted"]).copy()
    if d.empty:
        raise ValueError("No held-out hours with a measured value")
    d["err"] = d["predicted"] - d["actual"]
    d["abs"] = d["err"].abs()
    d["hour"] = pd.DatetimeIndex(d["ts"]).hour
    base = d.dropna(subset=["baseline"])
    by_hour = []
    for h in range(24):
        g = d[d["hour"] == h]
        if g.empty:
            continue
        gb = base[base["hour"] == h] if len(base) else base
        by_hour.append({"hour": h, "n": int(len(g)), "mae_kw": float(g["abs"].mean()), "bias_kw": float(g["err"].mean()),
                        "baseline_mae_kw": float((gb["baseline"] - gb["actual"]).abs().mean()) if len(gb) else None})
    limit = float(np.ceil(max(d["abs"].quantile(0.99), 1.0)))
    counts, edges = np.histogram(d["err"].clip(-limit, limit).to_numpy(), bins=bins, range=(-limit, limit))
    covered = d.dropna(subset=["lower", "upper"])
    worst = d.nlargest(5, "abs")
    return {
        "hours": int(len(d)), "bias_kw": float(d["err"].mean()), "mae_kw": float(d["abs"].mean()), "rmse_kw": float(np.sqrt((d["err"] ** 2).mean())),
        "baseline_mae_kw": float((base["baseline"] - base["actual"]).abs().mean()) if len(base) else None,
        "abs_error_percentiles_kw": {"p50": float(d["abs"].quantile(0.5)), "p90": float(d["abs"].quantile(0.9)), "p95": float(d["abs"].quantile(0.95)), "p99": float(d["abs"].quantile(0.99))},
        "interval_coverage_pct": float(100 * ((covered["actual"] >= covered["lower"]) & (covered["actual"] <= covered["upper"])).mean()) if len(covered) else None,
        "by_hour": by_hour,
        "histogram": [{"from_kw": float(edges[i]), "to_kw": float(edges[i + 1]), "hours": int(counts[i])} for i in range(len(counts))],
        "histogram_note": f"Errors beyond +/-{limit:.0f} kW (about the largest 1% of absolute errors) are shown in the outermost bars.",
        "worst": [{"ts": str(r.ts), "actual_kw": float(r.actual), "predicted_kw": float(r.predicted), "error_kw": float(r.err)} for r in worst.itertuples()],
    }


# ----------------------------------------------------------------------------- peaks
def peak_analysis(s: pd.Series) -> dict:
    v = s.dropna()
    if len(v) < 24 * 14:
        raise ValueError("At least 14 days of valid hours are needed for peak analysis")
    hod = v.groupby(v.index.hour)
    weekend = v.index.day_of_week >= 5
    profile = [{"hour": int(h), "mean_kw": float(g.mean()), "p05_kw": float(g.quantile(0.05)), "p95_kw": float(g.quantile(0.95)),
                "weekday_mean_kw": float(v[(~weekend) & (v.index.hour == h)].mean()),
                "weekend_mean_kw": float(v[weekend & (v.index.hour == h)].mean())} for h, g in hod]
    daily = v.groupby(v.index.normalize())
    full_days = daily.size()[daily.size() >= 20].index
    peaks = pd.DataFrame({"peak_kw": daily.max(), "peak_hour": daily.apply(lambda g: g.idxmax().hour)}).loc[full_days]
    hist = peaks["peak_hour"].value_counts().sort_index()
    top = v.nlargest(10)
    peak = float(v.max())
    monthly = v.groupby(v.index.to_period("M"))
    return {
        "profile": profile,
        "peak_hour_histogram": [{"hour": int(h), "days": int(hist.get(h, 0))} for h in range(24)],
        "top_hours": [{"ts": str(t), "kw": float(x)} for t, x in top.items()],
        "overall": {"mean_kw": float(v.mean()), "peak_kw": peak, "load_factor": float(v.mean() / peak), "p95_kw": float(v.quantile(0.95)),
                    "p99_kw": float(v.quantile(0.99)), "peak_to_average": float(peak / v.mean()), "days": int(len(full_days))},
        "monthly": [{"month": str(p), "mean_kw": float(g.mean()), "peak_kw": float(g.max()), "load_factor": float(g.mean() / g.max())} for p, g in monthly],
        "load_duration": load_duration(v),
        "distribution": demand_distribution(v),
        "note": "Peak demand here is the highest hourly average kW; an instantaneous peak inside an hour can be higher.",
    }


# ----------------------------------------------------------------------------- buildings and facilities
def building_stats(db: Session, soc: Society, start, end, is_admin: bool) -> list[dict]:
    m = meter_matrix(db, soc.id, start, end)
    blds = db.scalars(select(Building).where(Building.society_id == soc.id, Building.is_active.is_(True)).order_by(Building.code)).all()
    total = float(m.sum().sum()) if not m.empty else 0.0
    out = []
    for b in blds:
        col = m[b.code] if b.code in m.columns else pd.Series(dtype="float64")
        v = col.dropna()
        energy = float(v.sum()) if len(v) else None
        out.append({"id": b.id, "code": b.code, "sub_use": b.sub_use,
                    "floor_area_sqm": b.floor_area_sqm, "year_built": b.year_built, "floors": b.floors, "valid_share_overall": b.valid_share,
                    "energy_kwh": energy, "share_pct": 100 * energy / total if energy is not None and total > 0 else None,
                    "kwh_per_sqm": energy / b.floor_area_sqm if energy is not None and b.floor_area_sqm else None,
                    "avg_kw": float(v.mean()) if len(v) else None, "peak_kw": float(v.max()) if len(v) else None,
                    "valid_hours": int(len(v)), "expected_hours": int(len(col)), **({"source_id": b.source_id} if is_admin else {})})
    return out


def facilities_overview(db: Session, soc: Society) -> dict:
    meters = db.scalars(select(Meter).where(Meter.society_id == soc.id, Meter.kind == "facility", Meter.is_active.is_(True))).all()
    cats = []
    for key, label in FACILITY_CATEGORIES.items():
        ms = [m for m in meters if m.facility_category == key]
        cats.append({"category": key, "label": label, "measured": bool(ms), "meters": [m.code for m in ms],
                     "status": "measured" if ms else "not measured in this dataset"})
    other = [m for m in meters if m.facility_category not in FACILITY_CATEGORIES]
    if other:
        cats.append({"category": "other", "label": "Other common-area meters", "measured": True, "meters": [m.code for m in other], "status": "measured"})
    available = bool(meters)
    return {"available": available, "categories": cats,
            "message": None if available else ("This dataset has whole-building electricity meters only. Lifts, pumps, street lighting and the clubhouse are not "
                                               "metered separately, so no facility figures are shown. They appear here when an admin uploads facility meters.")}


def facility_consumption(db: Session, soc: Society, category: str, start, end, resolution: str) -> list[dict]:
    q = (select(ConsumptionRecord.ts, func.sum(ConsumptionRecord.kwh)).join(Meter, Meter.id == ConsumptionRecord.meter_id)
         .where(Meter.society_id == soc.id, Meter.kind == "facility", Meter.facility_category == category)
         .group_by(ConsumptionRecord.ts).order_by(ConsumptionRecord.ts))
    if start is not None:
        q = q.where(ConsumptionRecord.ts >= naive_ts(start).to_pydatetime())
    if end is not None:
        q = q.where(ConsumptionRecord.ts <= naive_ts(end).to_pydatetime())
    rows = db.execute(q).all()
    if not rows:
        return []
    s = pd.Series({pd.Timestamp(t): v for t, v in rows}, dtype="float64")
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="1h"))
    return to_records(aggregate(s, resolution))


# ----------------------------------------------------------------------------- anomalies
def anomaly_summary(db: Session, society_id: int) -> dict:
    rows = db.execute(select(AnomalyEvent.scope, AnomalyEvent.severity, AnomalyEvent.acknowledged, func.count()).where(AnomalyEvent.society_id == society_id)
                      .group_by(AnomalyEvent.scope, AnomalyEvent.severity, AnomalyEvent.acknowledged)).all()
    out = {"society": {"low": 0, "medium": 0, "high": 0}, "building": {"low": 0, "medium": 0, "high": 0}, "open": 0, "total": 0}
    for scope, sev, ack, n in rows:
        out[scope][sev] += n
        out["total"] += n
        if not ack:
            out["open"] += n
    return out


# ----------------------------------------------------------------------------- recommendations
def recommendations(db: Session, settings: Settings, soc: Society, tariff: Tariff) -> dict:
    df = society_frame(db, soc.id)
    series = df["kwh"]
    end = series.dropna().index.max()
    start = end - pd.Timedelta(days=90)
    b = pd.DataFrame(building_stats(db, soc, start, end, False)).set_index("code") if db.scalar(select(func.count(Building.id)).where(Building.society_id == soc.id)) else None
    if b is not None and not b.empty:
        b = b.rename(columns={"energy_kwh": "kwh", "valid_share_overall": "valid_share"})[["kwh", "floor_area_sqm", "valid_share"]]
    fc = None
    model = active_model(db, soc.id)
    if model is not None:
        try:
            pts = live_forecast(db, settings, soc, model, horizons=list(range(1, 25)))["points"]
            fc = pd.Series({pd.Timestamp(p["ts"]): p["kw"] for p in pts})
        except (ValueError, FileNotFoundError):
            fc = None
    ev = [{"start": e.start_ts, "end": e.end_ts, "severity_level": e.severity_level, "excess_ratio": e.excess_ratio, "explanation": e.explanation,
           "start_ts": e.start_ts}
          for e in db.scalars(select(AnomalyEvent).where(AnomalyEvent.society_id == soc.id, AnomalyEvent.scope == "society", AnomalyEvent.end_ts > (end - pd.Timedelta(days=45)).to_pydatetime()))]
    return recommend_society(series, tariff, b, fc, ev)
