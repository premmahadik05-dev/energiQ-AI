"""Training, forecasting, explanation, anomaly detection and monitoring on top of ml_engine."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ml_engine.anomaly.detector import AnomalyConfig, detect
from ml_engine.data.ingest import MIN_TRAIN_HOURS, RECOMMENDED_SPAN_DAYS
from ml_engine.evaluation.metrics import evaluate
from ml_engine.evaluation.splits import block_mask, fractional_plan
from ml_engine.explainability.shap_tree import explain_rows, global_importance, narrative
from ml_engine.features.builder import common_eval_mask, make_features, make_supervised, regularize
from ml_engine.forecasting.models import XGB_GRID, baselines
from ml_engine.forecasting.registry import load_tree_model, save_tree_model, series_hash
from ml_engine.pipeline import fit_before

from ..config import Settings
from ..models import Anomaly, AnomalyRun, Dataset, Forecast, ModelVersion, utcnow
from .core import JobContext, notify
from .data import load_series

BUNDLE_HORIZONS = tuple(range(1, 25))
EVAL_HORIZONS = (1, 6, 24)
XGB_PARAMS = XGB_GRID[0]  # fixed, untuned configuration so training finishes in minutes on a laptop
SENSITIVITY = {"low": 0.999, "medium": 0.995, "high": 0.99}


def models_root(settings: Settings, owner_id: int) -> Path:
    return settings.models_dir / f"user_{owner_id}"


@lru_cache(maxsize=512)
def _load_cached(root: str, model_id: str):
    return load_tree_model(Path(root), model_id)  # artifacts are immutable once written


# ----------------------------------------------------------------------------- training
def train_bundle(db: Session, ctx: JobContext, settings: Settings, dataset_id: int, activate: bool = True) -> dict:
    ds = db.get(Dataset, dataset_id)
    series = regularize(load_series(db, dataset_id))
    valid = series.dropna()
    if len(valid) < MIN_TRAIN_HOURS:
        raise ValueError(f"Insufficient training history: {len(valid)} valid hours, at least {MIN_TRAIN_HOURS} (4 weeks) are required")
    plan = fractional_plan(valid.index)
    ctx.progress(0.02, "Evaluating on a chronological hold-out")

    horizons_eval: dict[str, dict] = {}
    shap_summary: dict[str, dict] = {}
    for i, h in enumerate(EVAL_HORIZONS):
        sup = make_supervised(series, h)
        test_rows = block_mask(sup.target_time, plan.test_start, plan.test_end) & common_eval_mask(sup)
        if int(test_rows.sum()) < 24:
            raise ValueError("Too few valid hours in the hold-out period to evaluate a model; upload a longer or more complete series")
        model = fit_before(sup, "xgboost", XGB_PARAMS, plan.test_start, seed=42)
        y = sup.y[test_rows].to_numpy()
        pred = model.predict(sup.X[test_rows])
        metrics = {"xgboost": evaluate(y, pred)}
        for b in baselines():
            metrics[b.name] = evaluate(y, b.predict(sup.X[test_rows]))
        best_base = min((b.name for b in baselines()), key=lambda n: metrics[n]["mae"])
        q10, q90 = residual_band(y, pred)
        horizons_eval[str(h)] = {
            "metrics": metrics, "rows_scored": int(test_rows.sum()), "best_baseline": best_base,
            "mae_improvement_vs_best_baseline_pct": float(100 * (1 - metrics["xgboost"]["mae"] / metrics[best_base]["mae"])),
            "residual_q10_kw": q10, "residual_q90_kw": q90,
        }
        imp = global_importance(model, sup.X[test_rows], max_rows=3000)
        shap_summary[str(h)] = {
            "top_features": imp.head(10)[["feature", "label", "group", "mean_abs_shap_kw", "share_pct"]].to_dict("records"),
            "group_share_pct": imp.groupby("group")["share_pct"].sum().sort_values(ascending=False).to_dict(),
        }
        ctx.progress(0.02 + 0.2 * (i + 1) / len(EVAL_HORIZONS), f"Evaluated {h} h ahead")

    evaluation = {
        "protocol": "Chronological split by target time: models are fitted on rows whose target is before the hold-out start and scored once on the hold-out; the deployed models are then refitted on all data.",
        "holdout_start": str(plan.test_start), "holdout_end": str(plan.test_end),
        "horizons": horizons_eval, "xgboost_params": XGB_PARAMS, "seed": 42,
        "caveat": None if (valid.index.max() - valid.index.min()).days >= RECOMMENDED_SPAN_DAYS else "The data covers less than one year: yearly seasonality cannot be learned or evaluated.",
    }

    root = models_root(settings, ds.owner_id)
    data_hash = series_hash(series)
    cutoff = series.index.max() + pd.Timedelta(hours=1)
    horizon_ids: dict[str, str] = {}
    train_rows = 0
    for k, h in enumerate(BUNDLE_HORIZONS):
        sup = make_supervised(series, h)
        model = fit_before(sup, "xgboost", XGB_PARAMS, cutoff, seed=42)
        meta = {"horizon": h, "data_hash": data_hash, "dataset_id": dataset_id, "owner_id": ds.owner_id,
                "train_target_before": str(cutoff), "unit": "kW"}
        horizon_ids[str(h)] = save_tree_model(root, model, meta)
        if h == 1:
            train_rows = int((sup.y.notna() & pd.Series(sup.target_time < cutoff, index=sup.y.index)).sum())
        ctx.progress(0.25 + 0.73 * (k + 1) / len(BUNDLE_HORIZONS), f"Training final model for {h} h ahead")

    bundle_id = f"bundle_{ds.owner_id}_{dataset_id}_{utcnow().strftime('%Y%m%dT%H%M%S%f')}"
    if activate:
        db.execute(update(ModelVersion).where(ModelVersion.dataset_id == dataset_id).values(is_active=False))
    mv = ModelVersion(id=bundle_id, owner_id=ds.owner_id, dataset_id=dataset_id, family="xgboost", is_active=activate,
                      horizon_model_ids=horizon_ids, train_rows=train_rows, train_end=series.index.max().to_pydatetime(),
                      data_hash=data_hash, evaluation=evaluation, explanation=shap_summary)
    db.add(mv)
    db.commit()
    notify(db, ds.owner_id, "model", f"Forecast model trained on '{ds.name}'", f"/models/{bundle_id}")
    return {"model_id": bundle_id, "active": activate, "holdout_mae_kw": {h: v["metrics"]["xgboost"]["mae"] for h, v in horizons_eval.items()}}


# ----------------------------------------------------------------------------- forecasting
def residual_band(y, pred) -> tuple[float, float]:
    """10th and 90th percentile of (actual - predicted), in kW.

    The forecast range is ``prediction + q10 .. prediction + q90``. The residual MUST be defined as actual minus
    predicted for that to be the right way round: household load has occasional large upward spikes, so the upper
    side of the band has to be wider than the lower one.
    """
    resid = np.asarray(y, dtype=float) - np.asarray(pred, dtype=float)
    return float(np.quantile(resid, 0.1)), float(np.quantile(resid, 0.9))


def _interp_band(ev: dict, h: int) -> tuple[float, float]:
    hs = sorted(int(k) for k in ev["horizons"])
    q10 = [ev["horizons"][str(k)]["residual_q10_kw"] for k in hs]
    q90 = [ev["horizons"][str(k)]["residual_q90_kw"] for k in hs]
    return float(np.interp(h, hs, q10)), float(np.interp(h, hs, q90))


def _tail(series: pd.Series, origin: pd.Timestamp) -> pd.Series:
    s = regularize(series)
    if origin not in s.index:
        raise ValueError("origin is outside the dataset's time range")
    return s[s.index <= origin].iloc[-24 * 21:]  # covers the 168 h windows and every lag


def forecast_curve(settings: Settings, mv: ModelVersion, series: pd.Series, origin: pd.Timestamp | None) -> dict:
    s = regularize(series)
    origin = pd.Timestamp(origin).floor("h") if origin is not None else s.index.max()
    tail = _tail(s, origin)
    root = str(models_root(settings, mv.owner_id))
    points = []
    missing = bool(np.isnan(tail.iloc[-1]))
    for h in BUNDLE_HORIZONS:
        model, _ = _load_cached(root, mv.horizon_model_ids[str(h)])
        row = make_features(tail, h).loc[[origin]]
        pred = float(model.predict(row)[0])
        lo, hi = _interp_band(mv.evaluation, h)
        points.append({"horizon": h, "ts": str(origin + pd.Timedelta(hours=h)), "kw": max(pred, 0.0),
                       "lower_kw": max(pred + lo, 0.0), "upper_kw": max(pred + hi, 0.0)})
    return {"origin": origin, "points": points, "origin_value_missing": missing}


def explain_local(settings: Settings, mv: ModelVersion, series: pd.Series, horizon: int, origin: pd.Timestamp | None) -> dict:
    if str(horizon) not in mv.horizon_model_ids:
        raise ValueError("horizon must be between 1 and 24")
    s = regularize(series)
    origin = pd.Timestamp(origin).floor("h") if origin is not None else s.index.max()
    tail = _tail(s, origin)
    model, _ = _load_cached(str(models_root(settings, mv.owner_id)), mv.horizon_model_ids[str(horizon)])
    exp = explain_rows(model, make_features(tail, horizon).loc[[origin]])[0]
    exp["narrative"] = narrative(exp, horizon)
    exp["target_time"] = str(origin + pd.Timedelta(hours=horizon))
    return exp


# ----------------------------------------------------------------------------- anomalies
def run_anomaly_job(db: Session, ctx: JobContext, dataset_id: int, sensitivity: str) -> dict:
    ds = db.get(Dataset, dataset_id)
    series = load_series(db, dataset_id)
    cfg = AnomalyConfig(alert_quantile=SENSITIVITY[sensitivity])
    ctx.progress(0.1, "Detecting anomalies")
    res = detect(series, cfg)
    run = AnomalyRun(owner_id=ds.owner_id, dataset_id=dataset_id, sensitivity=sensitivity, config=res.config, summary=res.summary)
    db.add(run)
    db.flush()
    for e in res.events:
        db.add(Anomaly(run_id=run.id, owner_id=ds.owner_id, dataset_id=dataset_id, start_ts=pd.Timestamp(e["start"]).to_pydatetime(),
                       end_ts=pd.Timestamp(e["end"]).to_pydatetime(), hours=e["hours"], types=e["types"], severity=e["severity"],
                       severity_level=e["severity_level"], peak_ts=pd.Timestamp(e["peak_time"]).to_pydatetime(),
                       peak_value_kw=e["peak_value_kw"], expected_kw=e["expected_kw"], peak_excess_ratio=e["peak_excess_ratio"],
                       explanation=e["explanation"]))
    db.commit()
    high = sum(1 for e in res.events if e["severity_level"] >= 3)
    notify(db, ds.owner_id, "anomaly", f"{len(res.events)} anomaly events found in '{ds.name}' ({high} high severity)", f"/anomalies?dataset={dataset_id}")
    return {"run_id": run.id, "events": len(res.events), "high_severity": high, "flagged_pct": res.summary["flagged_pct_of_valid"]}


def delete_old_runs(db: Session, dataset_id: int, keep_run_id: int) -> None:
    db.execute(delete(AnomalyRun).where(AnomalyRun.dataset_id == dataset_id, AnomalyRun.id != keep_run_id))
    db.commit()


# ----------------------------------------------------------------------------- monitoring
def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population stability index with reference-quantile bins; 0.1 / 0.25 are the usual cut-offs."""
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(reference, edges)[0] / len(reference)
    c = np.histogram(current, edges)[0] / len(current)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def model_monitoring(db: Session, mv: ModelVersion, recent_days: int = 28) -> dict:
    series = load_series(db, mv.dataset_id)
    valid = series.dropna()
    out: dict = {"model_id": mv.id, "trained_through": str(mv.train_end), "data_through": str(series.index.max()) if len(series) else None}
    train_end = pd.Timestamp(mv.train_end)
    ref = valid[valid.index <= train_end]
    cur = valid[valid.index > valid.index.max() - pd.Timedelta(days=recent_days)]
    if len(ref) >= 24 * 14 and len(cur) >= 24 * 3:
        # drift is only meaningful when new data arrived after training; otherwise recent == tail of training data
        new_data = bool((valid.index > train_end).any())
        p = psi(ref.to_numpy(), cur.to_numpy())
        ks = sps.ks_2samp(ref.to_numpy(), cur.to_numpy())
        out["drift"] = {"psi": p, "ks_statistic": float(ks.statistic), "ks_pvalue": float(ks.pvalue),
                        "reference_hours": int(len(ref)), "recent_hours": int(len(cur)), "recent_days": recent_days,
                        "new_data_since_training": new_data,
                        "mean_ratio_recent_to_reference": float(cur.mean() / ref.mean()) if ref.mean() > 0 else None,
                        "status": "stable" if p < 0.1 else "moderate shift" if p < 0.25 else "significant shift"}
    else:
        out["drift"] = {"status": "not enough data", "new_data_since_training": False}

    fcs = db.scalars(select(Forecast).where(Forecast.model_id == mv.id).order_by(Forecast.created_at.desc()).limit(50)).all()
    errs: list[float] = []
    for f in fcs:
        for p_ in f.points:
            ts = pd.Timestamp(p_["ts"])
            if ts in series.index and not np.isnan(series.loc[ts]):
                errs.append(abs(p_["kw"] - float(series.loc[ts])))
    hold = [v["metrics"]["xgboost"]["mae"] for v in mv.evaluation.get("horizons", {}).values()]
    hold_mae = float(np.mean(hold)) if hold else None
    realized = float(np.mean(errs)) if errs else None
    ratio = realized / hold_mae if realized is not None and hold_mae else None
    out["realized_performance"] = {
        "forecasts_checked": len(fcs), "points_scored": len(errs), "realized_mae_kw": realized,
        "holdout_mae_kw_mean_over_1_6_24h": hold_mae, "ratio_realized_to_holdout": ratio,
        "status": "no realised data yet" if ratio is None else "within expectation" if ratio <= 1.25 else "degraded - consider retraining",
        "note": "Realised error mixes all 24 horizons while the hold-out figure averages 1, 6 and 24 h, so treat the ratio as a rough alarm, not a precise score.",
    }
    out["retrain_recommended"] = bool(out["drift"].get("status") == "significant shift" or out["realized_performance"]["status"].startswith("degraded"))
    return out
