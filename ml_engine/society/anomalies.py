"""Anomaly detection for a society: the community total and every building meter.

Re-uses the household detector (``ml_engine.anomaly.detector``: weekly-baseline deviation band, Isolation
Forest, stuck-meter run rule) with thresholds scaled to the size of each series. For every event on the
society total the buildings are ranked by how much more they used than their own expected value during the
event, so an alert says *where* the unusual load came from. Missing hours are data gaps, never anomalies.

There are no ground-truth anomaly labels in BDG2, so no detection accuracy is claimed: the alert rate is
set by the quantile parameter. The explanation text is built from the measured values only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml_engine.anomaly.detector import AnomalyConfig, detect, deviation_stats
from ml_engine.features.builder import regularize

SEVERITY_LEVEL = {"low": 1, "medium": 2, "high": 3}


def scaled_config(series: pd.Series, sensitivity: str = "medium", building: bool = False) -> AnomalyConfig:
    """Detector parameters in kW scaled to the typical level of ``series`` (a design choice, not a tuned value)."""
    q = {"low": 0.999, "medium": 0.995, "high": 0.99}[sensitivity]
    level = float(series[series > 0].median())
    return AnomalyConfig(alert_quantile=q, baseline_weeks=4, min_baseline_weeks=2,
                         min_abs_dev_kw=(0.08 if building else 0.04) * level, scale_floor_kw=0.005 * level,
                         flat_min_hours=6 if building else 4)


def _contributors(events: list[dict], meters: pd.DataFrame, cfg_by_building: dict[str, AnomalyConfig]) -> None:
    """Attach the buildings that exceeded their own expected load during each society event."""
    expected = {}
    for b in meters.columns:
        s = regularize(meters[b])
        expected[b] = deviation_stats(s, cfg_by_building[b])["expected_kw"]
    for e in events:
        a, z = pd.Timestamp(e["start"]), pd.Timestamp(e["end"])
        rows = []
        for b in meters.columns:
            act = meters[b].loc[a:z]
            exp = expected[b].loc[a:z]
            ok = act.notna() & exp.notna()
            if ok.sum() == 0:
                continue
            rows.append((b, float((act[ok] - exp[ok]).sum()), float(act[ok].sum())))
        if not rows:
            e["top_contributors"] = []
            continue
        total = sum(abs(v) for _, v, _ in rows) or 1.0
        direction = -1.0 if "drop" in e["types"] and "spike" not in e["types"] else 1.0
        rows.sort(key=lambda r: -direction * r[1])
        e["top_contributors"] = [{"building": b, "deviation_kwh": round(v, 1), "share_of_total_deviation_pct": round(100 * abs(v) / total, 1)}
                                 for b, v, _ in rows[:3] if direction * v > 0]
        if e["top_contributors"]:
            c = e["top_contributors"][0]
            word = "above" if direction > 0 else "below"
            e["explanation"] += (f" Largest contributor: {c['building']}, {abs(c['deviation_kwh']):.0f} kWh {word} its own expected load "
                                 f"over the event ({c['share_of_total_deviation_pct']:.0f}% of the summed building deviations).")


def detect_society(total_kw: pd.Series, meters: pd.DataFrame, weather_temp: pd.Series | None = None, sensitivity: str = "medium") -> dict:
    """Run the detector on the society total and on each building meter."""
    total_cfg = scaled_config(total_kw, sensitivity)
    res = detect(total_kw, total_cfg)
    b_cfg = {b: scaled_config(meters[b], sensitivity, building=True) for b in meters.columns}
    events = [{**e, "scope": "society", "building": None} for e in res.events]
    _contributors(events, meters, b_cfg)
    if weather_temp is not None:
        for e in events:
            t = pd.Timestamp(e["peak_time"])
            if t in weather_temp.index and not np.isnan(weather_temp.loc[t]):
                e["context"] = {"outdoor_temperature_c": float(weather_temp.loc[t])}
    building_summary: dict[str, dict] = {}
    for b in meters.columns:
        try:
            r = detect(meters[b], b_cfg[b])
        except ValueError as exc:  # too little valid history for this meter
            building_summary[b] = {"error": str(exc)}
            continue
        building_summary[b] = {"events": len(r.events), "flagged_pct_of_valid": round(r.summary["flagged_pct_of_valid"], 3),
                               "events_by_severity": r.summary["events_by_severity"]}
        events += [{**e, "scope": "building", "building": b} for e in r.events]
    return {"sensitivity": sensitivity, "society_config": res.config, "society_summary": res.summary, "building_summary": building_summary,
            "events": events}
