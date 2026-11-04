"""Rule-based energy-saving recommendations and a flexible-load scheduler.

Everything here is derived from the user's own history, the 24 h forecast, the tariff and the
anomaly events. Recommendations are *separate from anomaly detection*: an anomaly says "this hour
looks unusual", a recommendation says "this habit could cost less".

Dollar/Euro figures are *scenarios under stated assumptions* (for example "if 10% of peak-period
energy moved to the cheapest hours"), never predictions of savings. Each recommendation lists its
evidence, assumptions and caveats. If the tariff is the built-in DEMO tariff the cost caveat says so.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml_engine.optimization.tariff import Tariff, cost_of_series


@dataclass
class RecommendationConfig:
    window_days: int = 90
    shift_fraction: float = 0.10  # what-if: share of dearest-period energy moved to the cheapest hours
    baseload_reduction: float = 0.10  # what-if: reduction of always-on load
    baseload_quantile: float = 0.05
    baseload_share_min_pct: float = 20.0
    peak_share_min_pct: float = 10.0
    peak_concentration_min: float = 1.2  # energy share must exceed the time share by this factor
    high_forecast_quantile: float = 0.90
    min_valid_hours: int = 24 * 14


def _caveats(tariff: Tariff) -> list[str]:
    c = ["Figures are scenario estimates under the stated assumption, not forecasts of savings."]
    if tariff.is_demo:
        c.append("The tariff in use is the built-in DEMO tariff; replace it with your real rates before relying on any cost figure.")
    return c


def _priority(saving_cost: float, period_cost: float) -> str:
    if period_cost <= 0:
        return "low"
    r = saving_cost / period_cost
    return "high" if r >= 0.05 else "medium" if r >= 0.02 else "low"


def recommend(series_kw: pd.Series, tariff: Tariff, forecast_kw: pd.Series | None = None,
              anomaly_events: list[dict] | None = None, cfg: RecommendationConfig | None = None) -> dict:
    cfg = cfg or RecommendationConfig()
    s = series_kw.astype("float64")
    end = s.index.max()
    win = s[s.index > end - pd.Timedelta(days=cfg.window_days)]
    valid = win.dropna()
    if len(valid) < cfg.min_valid_hours:
        return {"recommendations": [], "window": None, "tariff": tariff.to_dict(),
                "message": f"Need at least {cfg.min_valid_hours // 24} days of valid hours in the last {cfg.window_days} days to make recommendations."}
    days_covered = len(valid) / 24.0
    scale30 = 30.0 / days_covered  # convert totals over the window to a 30-day figure
    cost = cost_of_series(valid, tariff)
    total_kwh, avg_rate = cost["energy_kwh"], (cost["avg_cost_per_kwh"] or 0.0)
    lo_rate, hi_rate = tariff.cheapest_and_dearest()
    recs: list[dict] = []

    # --- 1. shift energy out of the dearest-rate hours
    rates = tariff.rates_for(valid.index)
    dear = rates >= hi_rate - 1e-12
    if hi_rate - lo_rate > 1e-9 and dear.any():
        peak_kwh = float(valid[dear].sum())
        share = 100 * peak_kwh / total_kwh if total_kwh > 0 else 0.0
        time_share = 100 * float(dear.mean())
        concentration = share / time_share if time_share > 0 else 0.0
        if share >= cfg.peak_share_min_pct and concentration >= cfg.peak_concentration_min:
            moved = cfg.shift_fraction * peak_kwh * scale30
            saving = moved * (hi_rate - lo_rate)
            hours = sorted(set(valid.index[dear].hour))
            recs.append({
                "id": "shift_peak_load", "category": "load shifting", "priority": _priority(saving / scale30, cost["total_cost"]),
                "title": "Move flexible use out of the most expensive hours",
                "explanation": (f"{share:.0f}% of your energy in the last {days_covered:.0f} days was used in the most expensive tariff hours "
                                f"({_hour_ranges(hours)}), which are only {time_share:.0f}% of the hours. Running dishwashers, washing machines or EV charging outside those hours is the simplest saving."),
                "evidence": {"dearest_rate_per_kwh": hi_rate, "cheapest_rate_per_kwh": lo_rate, "peak_energy_share_pct": share, "peak_time_share_pct": time_share, "concentration": concentration,
                             "peak_hours": hours, "peak_kwh_in_window": peak_kwh},
                "scenario": {"assumption": f"{cfg.shift_fraction * 100:.0f}% of the dearest-period energy is moved to the cheapest hours",
                             "kwh_moved_per_30d": moved, "saving_per_30d": saving, "currency": tariff.currency},
                "caveats": _caveats(tariff) + ["Only flexible loads (laundry, dishwasher, EV charging, water heating) can usually be moved."],
            })

    # --- 2. always-on baseload
    base_kw = float(valid.quantile(cfg.baseload_quantile))
    base_kwh = base_kw * len(valid)
    base_share = 100 * base_kwh / total_kwh if total_kwh > 0 else 0.0
    if base_share >= cfg.baseload_share_min_pct:
        saving_kwh = cfg.baseload_reduction * base_kw * 24 * 30
        saving = saving_kwh * avg_rate
        recs.append({
            "id": "reduce_baseload", "category": "standby / always-on load", "priority": _priority(saving / scale30, cost["total_cost"]),
            "title": "Check always-on devices",
            "explanation": (f"Your lowest sustained demand is about {base_kw:.2f} kW (the {cfg.baseload_quantile * 100:g}th percentile of hourly use), "
                            f"about {base_share:.0f}% of all energy. Fridges and routers account for part of it; old appliances, standby electronics and heating elements are common extras."),
            "evidence": {"baseload_kw": base_kw, "baseload_share_pct": base_share, "average_rate_per_kwh": avg_rate},
            "scenario": {"assumption": f"always-on load is reduced by {cfg.baseload_reduction * 100:.0f}%", "kwh_saved_per_30d": saving_kwh,
                         "saving_per_30d": saving, "currency": tariff.currency},
            "caveats": _caveats(tariff) + ["The 'baseload' is a statistical floor of the whole-house reading, not a measurement of individual devices."],
        })

    # --- 3. forecast peak awareness
    if forecast_kw is not None and len(forecast_kw.dropna()):
        f = forecast_kw.dropna()
        thr = float(valid.quantile(cfg.high_forecast_quantile))
        peak_t = f.idxmax()
        peak_v = float(f.max())
        if peak_v >= thr:
            pct_below = float((valid < peak_v).mean() * 100)
            in_dear = bool(tariff.rates_for(pd.DatetimeIndex([peak_t]))[0] >= hi_rate - 1e-12 and hi_rate > lo_rate)
            recs.append({
                "id": "forecast_peak", "category": "peak demand", "priority": "medium" if in_dear else "low",
                "title": "High demand expected in the next 24 hours",
                "explanation": (f"The forecast peaks at {peak_v:.2f} kW around {peak_t:%a %H:%M}, higher than {pct_below:.0f}% of the hours in your last "
                                f"{days_covered:.0f} days" + (" and inside the most expensive tariff period" if in_dear else "") +
                                ". Staggering heavy appliances around that time lowers the peak."),
                "evidence": {"forecast_peak_kw": peak_v, "forecast_peak_time": str(peak_t), f"history_p{int(cfg.high_forecast_quantile * 100)}_kw": thr,
                             "in_dearest_tariff_period": in_dear},
                "scenario": None,
                "caveats": ["This is a model forecast with its own error; see the model page for the measured accuracy at this horizon."],
            })

    # --- 4. anomaly follow-up
    if anomaly_events:
        recent = [e for e in anomaly_events if pd.Timestamp(e["end"]) > end - pd.Timedelta(days=30)]
        serious = [e for e in recent if e.get("severity_level", 0) >= 3]
        if serious:
            top = max(serious, key=lambda e: e.get("peak_excess_ratio") or 0)
            recs.append({
                "id": "review_anomalies", "category": "anomalies", "priority": "high",
                "title": "Review recent high-severity anomalies",
                "explanation": f"{len(serious)} high-severity anomaly event(s) in the last 30 days. Most severe: {top['explanation']}",
                "evidence": {"high_severity_events_30d": len(serious), "total_events_30d": len(recent), "top_event_start": top["start"]},
                "scenario": None,
                "caveats": ["An anomaly is an unusual reading, not a confirmed fault; unusual-but-legitimate use (guests, holidays) is flagged too."],
            })

    # --- 5. data quality
    last7 = s[s.index > end - pd.Timedelta(days=7)]
    comp = float(last7.notna().mean()) if len(last7) else 0.0
    if comp < 0.9:
        recs.append({
            "id": "data_gaps", "category": "data quality", "priority": "medium", "title": "Recent data has gaps",
            "explanation": f"Only {comp * 100:.0f}% of the last 7 days contain readings. Forecasts and anomaly checks are less reliable until the gaps are filled.",
            "evidence": {"last_7_days_completeness_pct": comp * 100}, "scenario": None, "caveats": [],
        })

    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: order[r["priority"]])
    return {
        "recommendations": recs,
        "window": {"start": str(valid.index.min()), "end": str(valid.index.max()), "valid_hours": int(len(valid)), "days_covered": days_covered},
        "baseline_cost": {k: cost[k] for k in ("energy_kwh", "energy_cost", "total_cost", "currency", "is_demo_tariff")},
        "tariff": tariff.to_dict(),
    }


def _hour_ranges(hours: list[int]) -> str:
    out, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h != prev + 1:
            out.append((start, prev))
            start = h
        prev = h
    out.append((start, prev))
    return ", ".join(f"{a:02d}:00-{b + 1:02d}:00" if a != b else f"{a:02d}:00-{a + 1:02d}:00" for a, b in out)


def cheapest_window(tariff: Tariff, start_after: pd.Timestamp, duration_h: int, power_kw: float,
                    forecast_kw: pd.Series | None = None, horizon_h: int = 24, avoid_peak_weight: float = 0.0) -> dict:
    """Best start time within ``horizon_h`` hours for a flexible load of ``power_kw`` lasting ``duration_h`` h.

    Cost = sum(price_t x power). With ``avoid_peak_weight`` > 0 a small penalty proportional to the
    forecast whole-house demand is added so ties are broken toward quieter hours.
    """
    if duration_h < 1 or duration_h > horizon_h:
        raise ValueError("duration_h must be between 1 and the horizon")
    if power_kw <= 0 or not np.isfinite(power_kw):
        raise ValueError("power_kw must be positive")
    start_after = pd.Timestamp(start_after).ceil("h")
    grid = pd.date_range(start_after, periods=horizon_h, freq="h")
    price = pd.Series(tariff.rates_for(grid), index=grid)
    fc = forecast_kw.reindex(grid) if forecast_kw is not None else None
    rows = []
    for i in range(0, horizon_h - duration_h + 1):
        idx = grid[i: i + duration_h]
        c = float(price.loc[idx].sum() * power_kw)
        penalty = float(fc.loc[idx].fillna(0).sum()) * avoid_peak_weight * 1e-3 if fc is not None and avoid_peak_weight else 0.0
        rows.append((idx[0], c, c + penalty))
    best = min(rows, key=lambda r: (r[2], r[0]))
    now_cost = rows[0][1]
    worst = max(rows, key=lambda r: r[1])
    return {
        "best_start": str(best[0]), "best_end": str(best[0] + pd.Timedelta(hours=duration_h)), "cost": best[1],
        "cost_if_started_first_hour": now_cost, "cost_at_worst_start": worst[1], "worst_start": str(worst[0]),
        "saving_vs_first_hour": now_cost - best[1], "currency": tariff.currency, "is_demo_tariff": tariff.is_demo,
        "energy_kwh": power_kw * duration_h,
    }
