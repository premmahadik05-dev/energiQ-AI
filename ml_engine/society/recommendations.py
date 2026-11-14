"""Data-driven recommendations for a society, computed only from observed hourly meter data.

Each recommendation lists the *evidence* (numbers measured from the data), optional *what-if arithmetic*
under an explicit assumption, and *caveats*. What-if figures are scenarios, never predicted savings: the
data cannot tell how much load is actually flexible. Recommendations are independent of anomaly detection.
Nothing here is invented: a rule that does not find its evidence in the data produces no recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ml_engine.optimization.recommendations import _caveats, _hour_ranges, _priority
from ml_engine.optimization.tariff import Tariff, cost_of_series


@dataclass
class SocietyRecConfig:
    window_days: int = 90
    shift_fraction: float = 0.10
    baseload_quantile: float = 0.05
    baseload_share_min_pct: float = 25.0
    peak_share_min_pct: float = 10.0
    peak_concentration_min: float = 1.2
    intensity_ratio_min: float = 1.25  # a building uses >= 25 % more energy per m2 than the median building
    min_valid_hours: int = 24 * 14
    high_forecast_quantile: float = 0.90


def recommend_society(series_kw: pd.Series, tariff: Tariff, buildings: pd.DataFrame | None = None, forecast_kw: pd.Series | None = None,
                      anomaly_events: list[dict] | None = None, cfg: SocietyRecConfig | None = None) -> dict:
    """``buildings``: index = building code; columns ``kwh`` (energy in the window), ``floor_area_sqm``, ``valid_share``."""
    cfg = cfg or SocietyRecConfig()
    s = series_kw.astype("float64")
    end = s.dropna().index.max()
    win = s[s.index > end - pd.Timedelta(days=cfg.window_days)]
    valid = win.dropna()
    if len(valid) < cfg.min_valid_hours:
        return {"recommendations": [], "window": None, "tariff": tariff.to_dict(),
                "message": f"Need at least {cfg.min_valid_hours // 24} days of valid hours in the last {cfg.window_days} days."}
    days = len(valid) / 24.0
    scale30 = 30.0 / days
    cost = cost_of_series(valid, tariff)
    total_kwh, avg_rate = cost["energy_kwh"], cost["avg_cost_per_kwh"] or 0.0
    lo_rate, hi_rate = tariff.cheapest_and_dearest()
    recs: list[dict] = []

    # 1. load shifting out of the dearest tariff hours
    rates = tariff.rates_for(valid.index)
    dear = rates >= hi_rate - 1e-12
    if hi_rate - lo_rate > 1e-9 and dear.any():
        peak_kwh = float(valid[dear].sum())
        share = 100 * peak_kwh / total_kwh
        time_share = 100 * float(dear.mean())
        conc = share / time_share if time_share else 0.0
        if share >= cfg.peak_share_min_pct and conc >= cfg.peak_concentration_min:
            moved = cfg.shift_fraction * peak_kwh * scale30
            saving = moved * (hi_rate - lo_rate)
            hours = sorted(set(valid.index[dear].hour))
            recs.append({
                "id": "shift_peak_load", "category": "load shifting", "priority": _priority(saving / scale30, cost["total_cost"]),
                "title": "Move flexible shared loads out of the most expensive tariff hours",
                "explanation": (f"{share:.0f}% of the society's energy in the last {days:.0f} days was used in the dearest tariff hours "
                                f"({_hour_ranges(hours)}), which are {time_share:.0f}% of all hours. Scheduling flexible shared loads "
                                "(for example laundry rooms, water heating, EV charging or pumping where they exist) outside those hours would reduce cost."),
                "evidence": {"dearest_rate_per_kwh": hi_rate, "cheapest_rate_per_kwh": lo_rate, "peak_energy_share_pct": share,
                             "peak_time_share_pct": time_share, "concentration": conc, "peak_hours": hours, "peak_kwh_in_window": peak_kwh},
                "scenario": {"assumption": f"{cfg.shift_fraction * 100:.0f}% of the dearest-period energy is moved to the cheapest hours",
                             "kwh_moved_per_30d": moved, "saving_per_30d": saving, "currency": tariff.currency},
                "caveats": _caveats(tariff) + ["The meter data does not show which loads are flexible; this is a what-if on total energy only."],
            })

    # 2. always-on base load
    base_kw = float(valid.quantile(cfg.baseload_quantile))
    base_share = 100 * base_kw * len(valid) / total_kwh if total_kwh > 0 else 0.0
    if base_share >= cfg.baseload_share_min_pct:
        recs.append({
            "id": "review_baseload", "category": "always-on load", "priority": "medium",
            "title": "Review what keeps the minimum demand high",
            "explanation": (f"The lowest sustained demand is about {base_kw:,.0f} kW (the {cfg.baseload_quantile * 100:g}th percentile of hourly demand), "
                            f"which is {base_share:.0f}% of all energy used in the last {days:.0f} days. Lighting, ventilation, pumps and standby equipment "
                            "in shared areas are common contributors; the meter data cannot say which are present here."),
            "evidence": {"baseload_kw": base_kw, "baseload_share_pct": base_share, "average_rate_per_kwh": avg_rate},
            "scenario": {"assumption": "each 10% reduction of the minimum demand", "kwh_saved_per_30d": 0.1 * base_kw * 24 * 30,
                         "saving_per_30d": 0.1 * base_kw * 24 * 30 * avg_rate, "currency": tariff.currency},
            "caveats": _caveats(tariff) + ["The base load is a statistical floor of the whole-society reading, not a measurement of individual devices."],
        })

    # 3. evening / daily peak concentration (demand, kW)
    daily = valid.groupby(valid.index.date)
    peak_hours = pd.Series({d: g.idxmax().hour for d, g in daily if len(g) >= 20})
    if len(peak_hours) >= 14:
        top_hour = int(peak_hours.mode().iloc[0])
        freq = 100 * float((peak_hours == top_hour).mean())
        mean_peak = float(daily.max().mean())
        mean_load = float(valid.mean())
        if freq >= 30:
            recs.append({
                "id": "peak_hour_pattern", "category": "peak demand", "priority": "low",
                "title": f"Daily demand peaks most often around {top_hour:02d}:00",
                "explanation": (f"On {freq:.0f}% of days the highest hourly demand falls in the hour starting {top_hour:02d}:00. The average daily peak is "
                                f"{mean_peak:,.0f} kW against an average demand of {mean_load:,.0f} kW (peak-to-average {mean_peak / mean_load:.2f}). "
                                "If the utility charges for peak demand, flattening this peak is where the value is; this tariff model has no demand charge."),
                "evidence": {"most_common_peak_hour": top_hour, "share_of_days_pct": freq, "mean_daily_peak_kw": mean_peak, "mean_demand_kw": mean_load,
                             "days_considered": int(len(peak_hours))},
                "scenario": None, "caveats": ["Hourly averages hide shorter peaks; an instantaneous peak can be higher."],
            })

    # 4. buildings that use clearly more energy per floor area than their peers
    if buildings is not None and len(buildings) >= 4:
        b = buildings.dropna(subset=["kwh", "floor_area_sqm"])
        b = b[(b["floor_area_sqm"] > 0) & (b["valid_share"].fillna(0) >= 0.9)]
        if len(b) >= 4:
            inten = b["kwh"] / b["floor_area_sqm"]
            med = float(inten.median())
            hi = inten[inten >= cfg.intensity_ratio_min * med].sort_values(ascending=False)
            for code, v in hi.head(3).items():
                excess_kwh = float((v - med) * b.loc[code, "floor_area_sqm"])
                recs.append({
                    "id": f"building_intensity_{code}", "category": "building comparison", "priority": "medium",
                    "title": f"{code} uses {v / med:.1f}x the median energy per square metre",
                    "explanation": (f"In the last {days:.0f} days {code} used {v:.1f} kWh per m2 against a median of {med:.1f} kWh per m2 across the society's buildings. "
                                    "Differences in occupancy, equipment or building age can explain part of this; an energy audit of the building is the way to find out."),
                    "evidence": {"building": code, "kwh_per_sqm": float(v), "median_kwh_per_sqm": med, "ratio_to_median": float(v / med),
                                 "energy_above_median_intensity_kwh": excess_kwh, "buildings_compared": int(len(b))},
                    "scenario": {"assumption": "arithmetic comparison only: the building at the median intensity",
                                 "kwh_difference_in_window": excess_kwh, "cost_difference_in_window": excess_kwh * avg_rate, "currency": tariff.currency},
                    "caveats": ["A comparison with peers, not a measured saving; occupancy and use are not in the data."] + _caveats(tariff)[1:],
                })

    # 5. forecast peak awareness
    if forecast_kw is not None and len(forecast_kw.dropna()):
        f = forecast_kw.dropna()
        thr = float(valid.quantile(cfg.high_forecast_quantile))
        t, v = f.idxmax(), float(f.max())
        if v >= thr:
            recs.append({
                "id": "forecast_peak", "category": "peak demand", "priority": "medium",
                "title": "High demand expected in the next 24 hours",
                "explanation": (f"The forecast peaks at {v:,.0f} kW around {t:%a %H:%M}, above {100 * float((valid < v).mean()):.0f}% of the hours in the last {days:.0f} days. "
                                "Postponing flexible shared loads away from that hour lowers the peak."),
                "evidence": {"forecast_peak_kw": v, "forecast_peak_time": str(t), "history_p90_kw": thr},
                "scenario": None, "caveats": ["A model forecast with its own error; see the evaluation page for the measured accuracy at this horizon."],
            })

    # 6. serious anomalies in the last 30 days
    if anomaly_events:
        recent = [e for e in anomaly_events if pd.Timestamp(e["end"]) > end - pd.Timedelta(days=30)]
        serious = [e for e in recent if e.get("severity_level", 0) >= 3]
        if serious:
            top = max(serious, key=lambda e: e.get("excess_ratio") or 0)
            recs.append({
                "id": "review_anomalies", "category": "anomalies", "priority": "high", "title": "Review recent high-severity anomalies",
                "explanation": f"{len(serious)} high-severity event(s) in the last 30 days. Most severe: {top['explanation']}",
                "evidence": {"high_severity_events_30d": len(serious), "total_events_30d": len(recent), "top_event_start": str(top["start_ts"])},
                "scenario": None,
                "caveats": ["An anomaly is an unusual reading relative to the weekly pattern, not a confirmed fault; term breaks and events are flagged too."],
            })

    # 7. data completeness
    last7 = s[s.index > end - pd.Timedelta(days=7)]
    comp = float(last7.notna().mean()) if len(last7) else 0.0
    if comp < 0.9:
        recs.append({"id": "data_gaps", "category": "data quality", "priority": "medium", "title": "Recent meter data has gaps",
                     "explanation": f"Only {comp * 100:.0f}% of the last 7 days have a valid society total (every meter must report). Forecasts and alerts are less reliable until the gaps are fixed.",
                     "evidence": {"last_7_days_completeness_pct": comp * 100}, "scenario": None, "caveats": []})

    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: order[r["priority"]])
    return {"recommendations": recs,
            "window": {"start": str(valid.index.min()), "end": str(valid.index.max()), "valid_hours": int(len(valid)), "days_covered": days},
            "baseline_cost": {k: cost[k] for k in ("energy_kwh", "energy_cost", "total_cost", "currency", "is_demo_tariff")},
            "tariff": tariff.to_dict()}
