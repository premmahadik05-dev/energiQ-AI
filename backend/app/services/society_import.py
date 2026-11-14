"""Load a processed society (and its trained bundle, evaluation and anomalies) into the database.

The same function is used by ``scripts/society_import.py`` and by the admin "import bundled societies" job,
so what is tested through the API is exactly what the command line loads.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..models import (
    AnomalyEvent,
    Building,
    ConsumptionRecord,
    ForecastResult,
    Meter,
    Society,
    SocietyHourly,
    SocietyModel,
    SocietyReport,
    utcnow,
)

log = logging.getLogger("energiq")
CHUNK = 50_000


def _none(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)) and not np.isfinite(v):
        return None
    return v.item() if isinstance(v, np.generic) else v


def json_safe(obj):
    """A copy of ``obj`` that is valid JSON: NaN and infinity become ``None`` and numpy scalars become Python numbers.

    The BDG2 metadata has no coordinates for the Eagle site, so its cleaning report contains ``NaN``. Python's ``json`` accepts
    that and SQLite stores it as text, but PostgreSQL's ``json`` type (and every strict JSON parser) rejects it, so every value
    written to a JSON column goes through this function.
    """
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _chunks(rows: list[dict]):
    for i in range(0, len(rows), CHUNK):
        yield rows[i:i + CHUNK]


def delete_society(db: Session, key: str) -> bool:
    s = db.scalar(select(Society).where(Society.key == key))
    if s is None:
        return False
    # explicit deletes keep this fast and independent of whether the engine enforces foreign keys
    meter_ids = [m for (m,) in db.execute(select(Meter.id).where(Meter.society_id == s.id))]
    for i in range(0, len(meter_ids), 500):
        db.execute(delete(ConsumptionRecord).where(ConsumptionRecord.meter_id.in_(meter_ids[i:i + 500])))
    for model in (SocietyHourly, ForecastResult, AnomalyEvent, SocietyModel, SocietyReport, Meter, Building):
        db.execute(delete(model).where(model.society_id == s.id))
    db.delete(s)
    db.commit()
    return True


def import_processed(db: Session, key: str, data_dir: Path, society_dir: Path, replace: bool = False, log_fn=log.info) -> dict:
    folder = Path(data_dir) / key
    if not (folder / "society_hourly.csv.gz").is_file():
        raise FileNotFoundError(f"No processed data for society '{key}' in {data_dir}")
    if db.scalar(select(Society.id).where(Society.key == key)) is not None:
        if not replace:
            raise ValueError(f"Society '{key}' already exists")
        delete_society(db, key)

    index = json.loads((Path(data_dir) / "societies.json").read_text())
    entry = next((e for e in index["societies"] if e["key"] == key), None)
    if entry is None:
        raise FileNotFoundError(f"'{key}' is not listed in societies.json")
    report = json.loads((folder / "cleaning_report.json").read_text())
    soc_df = pd.read_csv(folder / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    meters_df = pd.read_csv(folder / "meters_hourly_kwh.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    b_df = pd.read_csv(folder / "buildings.csv")
    src = index["source"]

    soc = Society(
        key=key, name=entry["name"],
        description=(f"{len(b_df)} real residential-use buildings of {src['name']} site '{entry['bdg2_site']}', summed per hour. "
                     "A research-based representative community, not a registered housing society."),
        source_name=src["name"], source_url=src["official_url"], license=src["license"], timezone=entry["timezone"],
        lat=_none(report.get("lat")), lng=_none(report.get("lng")), start_ts=pd.Timestamp(soc_df.index[0]).to_pydatetime(), end_ts=pd.Timestamp(soc_df.index[-1]).to_pydatetime(),
        hours=int(len(soc_df)), valid_hours=int(soc_df["society_kwh"].notna().sum()), status="ready",
        meta=json_safe({"source": src, "downloaded_at": index.get("downloaded_at"), "files": index.get("files"), "rule": index.get("rule"), "cleaning": index.get("cleaning"),
                        "cleaning_report": report,
                        "excluded_meters": pd.read_csv(folder / "excluded_meters.csv").to_dict("records") if (folder / "excluded_meters.csv").stat().st_size > 5 else []}))
    db.add(soc)
    db.flush()

    code_to_building: dict[str, Building] = {}
    code_to_meter: dict[str, Meter] = {}
    for r in b_df.itertuples(index=False):
        b = Building(society_id=soc.id, code=r.code, source_id=str(r.source_id), sub_use=str(r.sub_use) if pd.notna(r.sub_use) else "",
                     floor_area_sqm=_none(r.floor_area_sqm), year_built=int(r.year_built) if pd.notna(r.year_built) else None,
                     floors=int(r.floors) if pd.notna(r.floors) else None, valid_share=_none(r.valid_share))
        db.add(b)
        code_to_building[r.code] = b
    db.flush()
    for code, b in code_to_building.items():
        m = Meter(society_id=soc.id, building_id=b.id, code=code, kind="building", valid_share=b.valid_share)
        db.add(m)
        code_to_meter[code] = m
    db.flush()

    n_rec = 0
    for code, m in code_to_meter.items():
        col = meters_df[code]
        rows = [{"meter_id": m.id, "ts": t.to_pydatetime(), "kwh": _none(v)} for t, v in zip(col.index, col.to_numpy(), strict=True)]
        for ch in _chunks(rows):
            db.execute(insert(ConsumptionRecord), ch)
        n_rec += len(rows)
    rows = [{"society_id": soc.id, "ts": t.to_pydatetime(), "kwh": _none(r.society_kwh), "n_valid_meters": int(r.n_valid_meters),
             "air_temp_c": _none(r.airTemperature), "dew_temp_c": _none(r.dewTemperature), "wind_ms": _none(r.windSpeed)}
            for t, r in zip(soc_df.index, soc_df.itertuples(index=False), strict=True)]
    for ch in _chunks(rows):
        db.execute(insert(SocietyHourly), ch)
    db.commit()

    out = {"society": key, "society_id": soc.id, "buildings": len(code_to_building), "consumption_records": n_rec, "hourly_rows": len(rows)}
    art = Path(society_dir) / key
    if (art / "evaluation.json").is_file():
        out["model"] = import_model(db, soc, key, art)
    if (art / "anomalies.json").is_file():
        out["anomaly_events"] = import_anomalies(db, soc, art / "anomalies.json")
    log_fn("imported society %s: %s", key, out)
    return out


def import_model(db: Session, soc: Society, key: str, art: Path) -> dict:
    bundle = json.loads((art / "bundle.json").read_text()) if (art / "bundle.json").is_file() else {}  # evaluation can be loaded without the deployed models
    ev = json.loads((art / "evaluation.json").read_text())
    shap = json.loads((art / "shap_global.json").read_text()) if (art / "shap_global.json").is_file() else {}
    peaks = json.loads((art / "peak_evaluation.json").read_text()) if (art / "peak_evaluation.json").is_file() else {}
    trained_through = pd.Timestamp(bundle["trained_through"] if bundle else ev["data"]["last"])
    model_id = f"society_{key}_{trained_through:%Y%m%d%H}"
    db.execute(delete(SocietyModel).where(SocietyModel.society_id == soc.id))
    mv = SocietyModel(id=model_id, society_id=soc.id, is_active=True, artifact_key=key, bundle=json_safe(bundle), evaluation=json_safe(ev), explanation=json_safe(shap), peaks=json_safe(peaks),
                      trained_through=trained_through.to_pydatetime(), created_at=utcnow())
    db.add(mv)
    db.flush()
    n = 0
    for h_str, r in ev["horizons"].items():
        h = int(h_str)
        f = art / f"predictions_h{h}.csv.gz"
        if not f.is_file():
            continue
        pdf = pd.read_csv(f, parse_dates=["target_time"], index_col="target_time")
        best = r["best_overall_by_cv"]
        if r["best_overall_is_baseline"]:
            band = r["chosen_baselines"][best]
            lo, hi = band["residual_q10"], band["residual_q90"]
        else:
            lo, hi = r["chosen"][best]["residual_q10"], r["chosen"][best]["residual_q90"]
        base = r["best_baseline_by_cv"]
        rows = []
        for t, row in pdf.iterrows():
            origin = t - pd.Timedelta(hours=h)
            p = float(row[best])
            rows.append({"society_id": soc.id, "model_id": model_id, "horizon_h": h, "origin": origin.to_pydatetime(), "target_ts": t.to_pydatetime(),
                         "actual_kw": _none(row["y_true"]), "predicted_kw": p, "lower_kw": max(p + lo, 0.0), "upper_kw": max(p + hi, 0.0),
                         "baseline_kw": _none(row[base])})
        for ch in _chunks(rows):
            db.execute(insert(ForecastResult), ch)
        n += len(rows)
    db.commit()
    return {"model_id": model_id, "backtest_rows": n}


def import_anomalies(db: Session, soc: Society, path: Path) -> int:
    return import_anomalies_data(db, soc, json.loads(path.read_text()))


def import_anomalies_data(db: Session, soc: Society, data: dict) -> int:
    ids = {b.code: b.id for b in db.scalars(select(Building).where(Building.society_id == soc.id))}
    db.execute(delete(AnomalyEvent).where(AnomalyEvent.society_id == soc.id))
    rows = []
    for e in data["events"]:
        bid = ids.get(e["building"]) if e["scope"] == "building" else None
        if e["scope"] == "building" and bid is None:
            continue
        rows.append({"society_id": soc.id, "building_id": bid, "scope": e["scope"], "start_ts": pd.Timestamp(e["start"]).to_pydatetime(),
                     "end_ts": pd.Timestamp(e["end"]).to_pydatetime(), "hours": e["hours"], "types": json_safe(e["types"]), "severity": e["severity"],
                     "severity_level": e["severity_level"], "peak_ts": pd.Timestamp(e["peak_time"]).to_pydatetime(), "peak_kw": e.get("peak_value_kw"),
                     "expected_kw": e.get("expected_kw"), "excess_ratio": e.get("peak_excess_ratio"), "explanation": e["explanation"],
                     "top_contributors": json_safe(e.get("top_contributors", [])), "context": json_safe(e.get("context", {})), "acknowledged": False})
    for ch in _chunks(rows):
        db.execute(insert(AnomalyEvent), ch)
    db.commit()
    return len(rows)


# ----------------------------------------------------------------------------- admin uploads
def import_built(db: Session, built: dict, name: str, description: str, upload_report: dict, mapping_given: bool, created_by: int | None = None) -> Society:
    """Store a society built by ``ml_engine.society.ingest.build_uploaded_society`` (real, admin-supplied meter data)."""
    key = built["key"]
    if db.scalar(select(Society.id).where(Society.key == key)) is not None:
        raise ValueError(f"A society with the key '{key}' already exists")
    meters_df: pd.DataFrame = built["meters_df"]
    total: pd.Series = built["society_kwh"]
    mt: pd.DataFrame = built["meters"]
    n_fac = int((mt["kind"] == "facility").sum())
    soc = Society(
        key=key, name=name[:160], description=description or f"{len(mt) - n_fac} buildings and {n_fac} facility meters uploaded by an administrator.",
        source_name="Administrator upload", source_url="", license="As supplied by the uploader", timezone="as uploaded (local clock time)",
        start_ts=pd.Timestamp(total.index[0]).to_pydatetime(), end_ts=pd.Timestamp(total.index[-1]).to_pydatetime(), hours=int(len(total)),
        valid_hours=int(total.notna().sum()), status="ready",
        meta=json_safe({"source": {"name": "Administrator upload", "kind": "upload"}, "uploaded_by": created_by, "upload": upload_report, "mapping_supplied": mapping_given,
                        "rule": built["rule"], "cleaning": built["cleaning"], "excluded_meters": built["excluded"],
                        "cleaning_report": {"society_valid_share": built["society_valid_share"], "cleaning_counts_per_building": built["cleaning_counts"],
                                            "kept_meters": int(len(mt)), "excluded_meters": int(len(built["excluded"])), "facility_meters": n_fac,
                                            "aggregation": "society kWh = sum of all retained meters at each hour; missing unless every retained meter is valid; nothing is filled"}}))
    db.add(soc)
    db.flush()
    meter_rows: dict[str, Meter] = {}
    for r in mt.itertuples(index=False):
        b = None
        if r.kind == "building":
            b = Building(society_id=soc.id, code=r.code, source_id=str(r.source_id), sub_use="", floor_area_sqm=_none(r.floor_area_sqm), valid_share=_none(r.valid_share))
            db.add(b)
            db.flush()
        m = Meter(society_id=soc.id, building_id=b.id if b else None, code=r.code, kind=r.kind, facility_category=r.facility_category if r.kind == "facility" else None,
                  valid_share=_none(r.valid_share))
        db.add(m)
        meter_rows[r.code] = m
    db.flush()
    for code, m in meter_rows.items():
        col = meters_df[code]
        rows = [{"meter_id": m.id, "ts": t.to_pydatetime(), "kwh": _none(v)} for t, v in zip(col.index, col.to_numpy(), strict=True)]
        for ch in _chunks(rows):
            db.execute(insert(ConsumptionRecord), ch)
    rows = [{"society_id": soc.id, "ts": t.to_pydatetime(), "kwh": _none(v), "n_valid_meters": int(n), "air_temp_c": None, "dew_temp_c": None, "wind_ms": None}
            for t, v, n in zip(total.index, total.to_numpy(), built["n_valid_meters"].to_numpy(), strict=True)]
    for ch in _chunks(rows):
        db.execute(insert(SocietyHourly), ch)
    db.commit()
    return soc


def detect_and_store_anomalies(db: Session, soc: Society, sensitivity: str = "medium") -> int:
    """Run the society anomaly detector on the stored data and replace the society's alerts."""
    from ml_engine.society.anomalies import detect_society

    from . import society as svc

    df = svc.society_frame(db, soc.id)
    m = svc.meter_matrix(db, soc.id)
    if m.empty or df["kwh"].notna().sum() < 24 * 28:
        return import_anomalies_data(db, soc, {"events": []})
    res = detect_society(df["kwh"], m, df["airTemperature"] if df["airTemperature"].notna().any() else None, sensitivity)
    return import_anomalies_data(db, soc, res)


def train_society(db: Session, ctx, settings, society_id: int) -> dict:
    """Job body: evaluate + deploy models for a stored society, then load the results and the alerts."""
    from ml_engine.society.experiment import HORIZONS
    from ml_engine.society.runner import train

    from . import society as svc

    soc = db.get(Society, society_id)
    if soc is None:
        raise ValueError("Society not found")
    df = svc.society_frame(db, soc.id)
    series = df["kwh"].rename("demand_kw")
    weather = df[["airTemperature", "dewTemperature", "windSpeed"]]
    out_dir = Path(settings.society_dir) / soc.key
    steps = [0]

    def log_fn(msg: str) -> None:
        steps[0] += 1
        ctx.progress(min(0.9, 0.05 + steps[0] * 0.025), str(msg)[:200])

    ctx.progress(0.02, "Evaluating models on a chronological split")
    train(soc.key, series, weather, out_dir, HORIZONS, deploy=True, log=log_fn)
    ctx.progress(0.92, "Loading results")
    res = import_model(db, soc, soc.key, out_dir)
    ctx.progress(0.96, "Detecting anomalies")
    n = detect_and_store_anomalies(db, soc)
    return {"society_id": soc.id, "model_id": res["model_id"], "backtest_rows": res["backtest_rows"], "anomaly_events": n}
