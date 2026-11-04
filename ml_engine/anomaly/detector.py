"""Unsupervised anomaly detection on an hourly load series (kW).

Three independent detectors, combined by an explicit, documented rule:

1. Deviation rule. ``expected`` is the median of the same hour of the week over the previous
   ``baseline_weeks`` weeks. The residual (actual - expected) is compared with the empirical
   ``alert_quantile`` / ``1 - alert_quantile`` quantiles of residuals at the same hour of day over the
   previous ``scale_weeks`` weeks. An hour is flagged when it falls outside that band *and* deviates by
   at least ``min_abs_dev_kw`` (a practical-significance guard so tiny night-time deviations do not
   alert). Only earlier data is used, so the rule is causal. Household load is bursty and heavy-tailed,
   so empirical quantiles are used instead of a Gaussian-style z cut-off (a MAD z-score at 3.5 flagged
   12% of the benchmark hours in testing; see docs/08_anomaly_detection.md).
2. Isolation Forest on pointwise features, fitted on the first ``fit_frac`` of the valid history;
   its score threshold is the ``if_quantile`` quantile of scores in that fit window.
3. Flat-run rule: ``flat_min_hours`` or more consecutive identical readings (stuck meter, repeated or
   imputed values). Hourly means of real readings essentially never repeat exactly.

An hour is anomalous when the deviation rule fires, or the flat-run rule fires, or Isolation Forest
fires *and* |z| >= ``if_needs_z``. Consecutive anomalous hours are merged into events with a severity
level and a plain-language explanation. Missing hours are data gaps, not anomalies: never scored.

There are no real anomaly labels in the UCI dataset. The expected alert rate is set by the alert
quantile and is a design parameter, not an accuracy figure. The injection check below is
synthetic and says nothing about accuracy on real faults.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ml_engine.features.builder import regularize

SEVERITY = {0: "none", 1: "low", 2: "medium", 3: "high"}


@dataclass
class AnomalyConfig:
    baseline_weeks: int = 8
    min_baseline_weeks: int = 4
    scale_weeks: int = 26
    min_scale_days: int = 56
    alert_quantile: float = 0.995
    min_abs_dev_kw: float = 0.5
    scale_floor_kw: float = 0.05
    flat_min_hours: int = 4
    fit_frac: float = 0.6
    if_quantile: float = 0.995
    if_needs_z: float = 2.5
    if_trees: int = 150
    merge_gap_hours: int = 1
    seed: int = 42


@dataclass
class AnomalyResult:
    hourly: pd.DataFrame
    events: list[dict]
    summary: dict
    config: dict


# --------------------------------------------------------------------------- detectors
def deviation_stats(s: pd.Series, cfg: AnomalyConfig) -> pd.DataFrame:
    """Causal expected value, residual, adaptive band, robust z and exceedance ratio."""
    how = pd.Series(s.index.day_of_week * 24 + s.index.hour, index=s.index)
    expected = s.groupby(how).transform(
        lambda g: g.shift(1).rolling(cfg.baseline_weeks, min_periods=cfg.min_baseline_weeks).median())
    r = s - expected
    window = cfg.scale_weeks * 7
    gr = r.groupby(s.index.hour)

    def q(p: float) -> pd.Series:
        return gr.transform(lambda g: g.shift(1).rolling(window, min_periods=cfg.min_scale_days).quantile(p))

    q_hi, q_lo, q_mid, q25, q75 = q(cfg.alert_quantile), q(1 - cfg.alert_quantile), q(0.5), q(0.25), q(0.75)
    scale = np.maximum((q75 - q25) / 1.349, cfg.scale_floor_kw)
    z = (r - q_mid) / scale
    up = (r - q_mid) / np.maximum(q_hi - q_mid, cfg.scale_floor_kw)
    down = (q_mid - r) / np.maximum(q_mid - q_lo, cfg.scale_floor_kw)
    excess = np.where(r >= q_mid, up, down)  # 1.0 = exactly at the band edge
    return pd.DataFrame({"expected_kw": expected, "resid_kw": r, "q_hi": q_hi, "q_lo": q_lo, "z": z,
                         "excess_ratio": pd.Series(excess, index=s.index).where(q_hi.notna())})


def flat_runs(s: pd.Series, min_hours: int) -> pd.Series:
    """True for hours that belong to a run of >= min_hours identical consecutive readings."""
    v = s.to_numpy(dtype="float64")
    same = np.zeros(len(v), dtype=bool)
    same[1:] = (np.abs(np.diff(v)) < 1e-9) & ~np.isnan(v[1:]) & ~np.isnan(v[:-1])
    out = np.zeros(len(v), dtype=bool)
    i = 0
    while i < len(v):
        if i + 1 < len(v) and same[i + 1]:
            j = i + 1
            while j + 1 < len(v) and same[j + 1]:
                j += 1
            if j - i + 1 >= min_hours:
                out[i: j + 1] = True
            i = j + 1
        else:
            i += 1
    return pd.Series(out, index=s.index)


def _if_features(s: pd.Series, dev: pd.DataFrame) -> pd.DataFrame:
    prev24 = s.shift(1).rolling(24, min_periods=12).mean()
    return pd.DataFrame({
        "value": s,
        "diff1": s.diff(),
        "ratio_prev24": s / prev24.clip(lower=0.05),
        "resid": dev["resid_kw"],
        "hour_sin": np.sin(2 * np.pi * s.index.hour / 24),
        "hour_cos": np.cos(2 * np.pi * s.index.hour / 24),
        "weekend": (s.index.day_of_week >= 5).astype(float),
    }, index=s.index)


def _severity_from_excess(e: np.ndarray) -> np.ndarray:
    return np.where(e >= 2.5, 3, np.where(e >= 1.5, 2, 1))


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    out = np.zeros(len(mask), dtype=int)
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            out[i: j + 1] = j - i + 1
            i = j + 1
        else:
            i += 1
    return out


# --------------------------------------------------------------------------- main API
def detect(series: pd.Series, cfg: AnomalyConfig | None = None) -> AnomalyResult:
    cfg = cfg or AnomalyConfig()
    s = regularize(series.astype("float64"))
    valid = s.notna()
    need = 24 * 7 * (cfg.min_baseline_weeks + 8)
    if valid.sum() < need:
        raise ValueError(f"Insufficient history for anomaly detection: need at least {need // 24} days of valid hours")
    dev = deviation_stats(s, cfg)
    feats = _if_features(s, dev)

    valid_idx = np.flatnonzero(valid.to_numpy())
    n_fit = max(int(len(valid_idx) * cfg.fit_frac), 24 * 14)
    fit_rows = valid_idx[:n_fit]
    fit_end = s.index[fit_rows[-1]]
    X = feats.fillna(feats.iloc[fit_rows].median())
    forest = IsolationForest(n_estimators=cfg.if_trees, random_state=cfg.seed, n_jobs=1)
    forest.fit(X.iloc[fit_rows])
    raw_score = -forest.score_samples(X)  # higher = more anomalous
    if_thr = float(np.quantile(raw_score[fit_rows], cfg.if_quantile))
    if_score = pd.Series(np.where(valid, raw_score, np.nan), index=s.index)

    r = dev["resid_kw"]
    flag_dev = valid & ((r > dev["q_hi"]) & (r >= cfg.min_abs_dev_kw) | (r < dev["q_lo"]) & (r <= -cfg.min_abs_dev_kw))
    flag_if = valid & (if_score >= if_thr)
    flag_flat = valid & flat_runs(s, cfg.flat_min_hours)
    flag_if_only = flag_if & ~flag_dev & (dev["z"].abs() >= cfg.if_needs_z)
    anomalous = flag_dev | flag_flat | flag_if_only

    excess = dev["excess_ratio"].fillna(0).to_numpy()
    sev = np.where(flag_dev, _severity_from_excess(excess), 0)
    sev = np.where(flag_if & flag_dev, np.minimum(sev + 1, 3), sev)
    sev = np.where(flag_if_only, 1, sev)
    run_len = _run_lengths(flag_flat.to_numpy())
    sev = np.where(flag_flat, np.maximum(sev, np.where(run_len >= 24, 3, 2)), sev)

    hourly = pd.DataFrame({
        "value_kw": s, "expected_kw": dev["expected_kw"], "resid_kw": r, "z": dev["z"],
        "excess_ratio": dev["excess_ratio"], "if_score": if_score,
        "flag_dev": flag_dev, "flag_if": flag_if, "flag_flat": flag_flat, "anomalous": anomalous,
        "severity": sev.astype(int),
    })
    events = _events(hourly, cfg)
    summary = {
        "hours_total": int(len(s)), "hours_valid": int(valid.sum()), "hours_flagged": int(anomalous.sum()),
        "flagged_pct_of_valid": float(100 * anomalous.sum() / max(valid.sum(), 1)),
        "hours_with_baseline": int(dev["q_hi"].notna().sum()),
        "hours_flagged_by": {"deviation": int(flag_dev.sum()), "flat_run": int(flag_flat.sum()),
                             "isolation_forest_only_with_z": int(flag_if_only.sum()),
                             "isolation_forest_any": int(flag_if.sum())},
        "events": len(events),
        "events_by_severity": {SEVERITY[k]: int(sum(e["severity_level"] == k for e in events)) for k in (1, 2, 3)},
        "events_by_type": {t: int(sum(t in e["types"] for e in events)) for t in ("spike", "drop", "flat_run", "unusual_pattern")},
        "isolation_forest": {"fit_end": str(fit_end), "fit_rows": int(len(fit_rows)), "score_threshold": if_thr,
                             "note": "hours up to fit_end are in-sample for Isolation Forest"},
    }
    return AnomalyResult(hourly=hourly, events=events, summary=summary, config=asdict(cfg))


def _events(h: pd.DataFrame, cfg: AnomalyConfig) -> list[dict]:
    flagged = np.flatnonzero(h["anomalous"].to_numpy())
    if flagged.size == 0:
        return []
    groups, start, prev = [], flagged[0], flagged[0]
    for i in flagged[1:]:
        if i - prev > cfg.merge_gap_hours + 1:
            groups.append((start, prev))
            start = i
        prev = i
    groups.append((start, prev))
    events = []
    for k, (a, b) in enumerate(groups, 1):
        seg = h.iloc[a: b + 1]
        fl = seg[seg["anomalous"]]
        dv = fl[fl["flag_dev"]]
        types = []
        if fl["flag_flat"].any():
            types.append("flat_run")
        if (dv["resid_kw"] > 0).any():
            types.append("spike")
        if (dv["resid_kw"] < 0).any():
            types.append("drop")
        if not types:
            types.append("unusual_pattern")
        score = fl["excess_ratio"].fillna(0)
        peak = score.idxmax() if score.max() > 0 else fl.index[0]
        row = h.loc[peak]
        level = int(fl["severity"].max())
        events.append({
            "id": k, "start": str(seg.index[0]), "end": str(seg.index[-1]), "hours": int(len(seg)),
            "flagged_hours": int(len(fl)), "types": types, "severity": SEVERITY[level], "severity_level": level,
            "peak_time": str(peak), "peak_value_kw": _f(row["value_kw"]), "expected_kw": _f(row["expected_kw"]),
            "peak_z": _f(row["z"]), "peak_excess_ratio": _f(row["excess_ratio"]), "max_if_score": _f(fl["if_score"].max()),
            "explanation": _explain(types, peak, row, int(len(seg)), int(fl["flag_flat"].sum()), cfg),
        })
    return events


def _f(v) -> float | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def _explain(types: list[str], peak: pd.Timestamp, row: pd.Series, hours: int, flat_hours: int, cfg: AnomalyConfig) -> str:
    when = peak.strftime("%a %Y-%m-%d %H:%M")
    exp = row["expected_kw"]
    ref = f"typical {exp:.2f} kW for this hour of the week" if not np.isnan(exp) else "no weekly baseline yet"
    ex = row["excess_ratio"]
    band = (f", {ex:.1f}x the edge of the usual range for this hour (the {cfg.alert_quantile * 100:g}th-percentile deviation of the last {cfg.scale_weeks} weeks)"
            if ex == ex else "")
    parts = []
    if "flat_run" in types:
        parts.append(f"{flat_hours} consecutive hours with an identical reading of {row['value_kw']:.3f} kW (possible stuck meter or repeated/imputed data)")
    if "spike" in types:
        parts.append(f"unusually high use around {when}: {row['value_kw']:.2f} kW vs {ref}{band}")
    if "drop" in types:
        parts.append(f"unusually low use around {when}: {row['value_kw']:.2f} kW vs {ref}{band}")
    if types == ["unusual_pattern"]:
        parts.append(f"unusual combination of level and change around {when}: {row['value_kw']:.2f} kW vs {ref}")
    return "; ".join(parts) + f". Event spans {hours} h."


# --------------------------------------------------------------------------- synthetic check
def inject_synthetic(series: pd.Series, n: int, kind: str = "spike", magnitude: float = 3.0, seed: int = 0,
                     min_gap_hours: int = 48, eligible: pd.DatetimeIndex | None = None) -> tuple[pd.Series, pd.DatetimeIndex]:
    """Inject ``n`` synthetic faults. kind: spike (x magnitude + 1 kW), drop (to 5%), flat (8 identical hours)."""
    rng = np.random.default_rng(seed)
    s = regularize(series.astype("float64")).copy()
    ok = np.flatnonzero(s.notna().to_numpy())
    if eligible is not None:
        ok = np.intersect1d(ok, s.index.get_indexer(eligible))
    ok = ok[ok < len(s) - 10]
    chosen: list[int] = []
    for i in rng.permutation(ok):
        if all(abs(i - c) >= min_gap_hours for c in chosen):
            chosen.append(int(i))
        if len(chosen) == n:
            break
    marked: list[pd.Timestamp] = []
    for i in chosen:
        if kind == "spike":
            s.iloc[i] = s.iloc[i] * magnitude + 1.0
            marked.append(s.index[i])
        elif kind == "drop":
            s.iloc[i] = s.iloc[i] * 0.05
            marked.append(s.index[i])
        elif kind == "flat":
            s.iloc[i: i + 8] = s.iloc[i]
            marked.extend(s.index[i: i + 8])
        else:
            raise ValueError(f"unknown kind {kind}")
    return s, pd.DatetimeIndex(sorted(set(marked)))


def injection_check(series: pd.Series, cfg: AnomalyConfig | None = None, n: int = 40, seed: int = 0) -> dict:
    """SYNTHETIC check: recall on injected faults and flag rate on untouched hours (not real accuracy).

    Injection is restricted to hours where the clean detector has a baseline. Recall is also reported
    for injected hours whose expected load is at least 1 kW, because a *drop* from a 0.3 kW night-time
    baseline is physically too small to be detectable.
    """
    cfg = cfg or AnomalyConfig()
    clean = detect(series, cfg)
    eligible = clean.hourly.index[clean.hourly["excess_ratio"].notna()]
    out: dict = {"synthetic": True, "n_injected_per_kind": n, "clean_flag_rate_pct": float(100 * clean.hourly["anomalous"].mean()), "kinds": {}}
    for label, kind, mag in (("spike_x3", "spike", 3.0), ("spike_x1.6", "spike", 1.6), ("drop_to_5pct", "drop", 0.0), ("flat_8h", "flat", 0.0)):
        mod, marked = inject_synthetic(series, n, kind, mag or 3.0, seed=seed, eligible=eligible)
        res = detect(mod, cfg).hourly["anomalous"]
        if kind == "flat":
            starts = marked[::8]
            rec = float(np.mean([res.iloc[res.index.get_loc(t): res.index.get_loc(t) + 8].any() for t in starts]))
            big = rec
        else:
            rec = float(res.reindex(marked).mean())
            exp = clean.hourly["expected_kw"].reindex(marked)
            sel = marked[(exp >= 1.0).to_numpy()]
            big = float(res.reindex(sel).mean()) if len(sel) else float("nan")
        untouched = res.drop(marked, errors="ignore")
        out["kinds"][label] = {"injected": int(len(marked) // (8 if kind == "flat" else 1)), "recall_on_injected": rec,
                               "recall_when_expected_ge_1kw": big, "flag_rate_untouched_pct": float(100 * untouched.mean())}
    return out
