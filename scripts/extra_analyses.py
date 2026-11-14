"""Two additional analyses for the research paper, run on the benchmark protocol (nothing here changes any earlier result).

1. Drop-one-group ablation of the XGBoost feature groups: refit without one SHAP group and measure the change in test MAE,
   with a paired day-block bootstrap against the full model. Shows whether the attribution shares of docs/07 agree with what
   actually happens when a group is removed.
2. Empirical coverage of the application's forecast band: the 10th and 90th percentiles of residuals on a chronological
   validation block (2009-07-01 to 2009-12-31), applied to the 2010 test predictions. Also an hour-of-day band and a
   symmetric split-conformal band for comparison. Every choice is fixed in this file before the test rows are looked at.

Reads  data/raw/... (the raw UCI file), artifacts/reports/benchmark/{cv_results.json,predictions_h*.csv}, artifacts/reports/explain/shap_global.json
Writes artifacts/reports/extra/extra_analyses.json

    python scripts/extra_analyses.py --input data/raw/uci_household_power/household_power_consumption.txt

Use the pinned interpreter (requirements.txt): XGBoost results depend on the XGBoost version.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml_engine.data.ingest import UCI_CONFIG, ingest_csv  # noqa: E402
from ml_engine.environment import environment_info  # noqa: E402
from ml_engine.evaluation.metrics import evaluate, paired_block_bootstrap  # noqa: E402
from ml_engine.evaluation.splits import BENCHMARK_PLAN, block_mask  # noqa: E402
from ml_engine.explainability.shap_tree import GROUPS, group_of  # noqa: E402
from ml_engine.features.builder import common_eval_mask, make_supervised  # noqa: E402
from ml_engine.forecasting.models import TreeModel  # noqa: E402
from ml_engine.pipeline import fit_before  # noqa: E402

HORIZONS = (1, 6, 24)
ALPHA = 0.2  # nominal 80 % band: 10th and 90th percentiles
Q_LO, Q_HI = 0.10, 0.90
VAL_START = BENCHMARK_PLAN.val_start
TEST_START, TEST_END = BENCHMARK_PLAN.test_start, BENCHMARK_PLAN.test_end


def interval_score(y, lo, hi, alpha=ALPHA):
    """Gneiting & Raftery (2007) interval score: width plus a penalty proportional to the miss (lower is better)."""
    return (hi - lo) + (2 / alpha) * np.maximum(lo - y, 0) + (2 / alpha) * np.maximum(y - hi, 0)


def day_block_ci(values: np.ndarray, times: pd.DatetimeIndex, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95 % percentile interval of the mean of ``values`` (0/1 hits or scores), resampling whole days."""
    frame = pd.DataFrame({"v": values, "day": times.normalize()}).groupby("day")["v"].agg(["sum", "count"])
    sums, counts = frame["sum"].to_numpy(), frame["count"].to_numpy()
    rng = np.random.default_rng(seed)
    k = len(sums)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, k, k)
        boots[i] = sums[pick].sum() / counts[pick].sum()
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def spearman(a: list[float], b: list[float]) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--bench", type=Path, default=Path("artifacts/reports/benchmark"))
    ap.add_argument("--explain", type=Path, default=Path("artifacts/reports/explain"))
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/reports/extra"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    series = ingest_csv(args.input, UCI_CONFIG).hourly["value_kw"]
    cv = json.loads((args.bench / "cv_results.json").read_text(encoding="utf-8"))
    shap = json.loads((args.explain / "shap_global.json").read_text(encoding="utf-8"))
    out: dict = {"protocol": {"alpha": ALPHA, "val_start": str(VAL_START), "test_start": str(TEST_START), "test_end": str(TEST_END),
                              "seed": args.seed, "note": "settings fixed in the script before test rows were examined"},
                 "reproduction_check": {}, "ablation": {}, "interval": {}, "cv_folds": {}}

    # ---- stability of the CV gain across folds (from the stored cv_results.json) ----
    for h in HORIZONS:
        res = cv["results"][str(h)]
        chosen = res["chosen"]["xgboost"]
        key = f"xgboost#{chosen['index']}"
        base = min(("naive", "seasonal_naive_24", "seasonal_naive_168"), key=lambda b: res["cv"][b]["_summary"]["mean_fold_mae"])
        folds = [f["name"] for f in cv["protocol"]["cv_folds"]]
        rows = [{"fold": f, "xgboost": res["cv"][key][f]["mae"], "baseline": res["cv"][base][f]["mae"]} for f in folds]
        out["cv_folds"][str(h)] = {"baseline": base, "xgboost_key": key, "rows": rows,
                                   "folds_xgboost_better": int(sum(r["xgboost"] < r["baseline"] for r in rows)), "folds": len(rows)}

    for h in HORIZONS:
        sup = make_supervised(series, h)
        evalm = common_eval_mask(sup)
        test_blk = block_mask(sup.target_time, TEST_START, TEST_END)
        scored = test_blk & evalm
        y = sup.y[scored].to_numpy()
        tt = pd.DatetimeIndex(sup.target_time[scored])
        params = cv["results"][str(h)]["chosen"]["xgboost"]["params"]
        stored = pd.read_csv(args.bench / f"predictions_h{h}.csv", index_col="target_time", parse_dates=True)

        # ---- reproduction check: the refit must give the stored benchmark predictions ----
        full = fit_before(sup, "xgboost", params, TEST_START, args.seed)
        p_full = full.predict(sup.X[scored])
        same_rows = stored.index.equals(tt)
        max_diff = float(np.max(np.abs(stored["xgboost"].to_numpy() - p_full))) if same_rows else None
        out["reproduction_check"][str(h)] = {"rows_identical": bool(same_rows), "max_abs_diff_kw": max_diff,
                                             "test_mae": evaluate(y, p_full)["mae"]}
        print(f"[h={h}] reproduction: rows identical={same_rows}, max |diff|={max_diff}", flush=True)
        if not same_rows or max_diff is None or max_diff > 1e-6:
            raise SystemExit(f"h={h}: refit does not reproduce the stored XGBoost predictions; run under the pinned environment")

        # ---- 1. drop-one-group ablation ----
        mae_full = evaluate(y, p_full)["mae"]
        abl: dict = {"full_mae": mae_full, "groups": {}}
        for g in GROUPS:
            keep = [c for c in sup.X.columns if group_of(c) != g]
            dropped = [c for c in sup.X.columns if group_of(c) == g]
            tr = (np.asarray(sup.target_time < TEST_START)) & sup.y.notna().to_numpy()
            m = TreeModel("xgboost", params, seed=args.seed).fit(sup.X.loc[tr, keep], sup.y[tr])
            p_g = m.predict(sup.X.loc[scored, keep])
            b = paired_block_bootstrap(y, p_g, p_full, tt, seed=0)  # positive = ablated model is worse
            abl["groups"][g] = {"dropped_features": dropped, "mae": evaluate(y, p_g)["mae"],
                                "delta_mae": b["mae_diff"], "ci95_low": b["ci95_low"], "ci95_high": b["ci95_high"]}
            print(f"  drop {g}: MAE {abl['groups'][g]['mae']:.4f} (delta {b['mae_diff']:+.4f})", flush=True)
        names = list(GROUPS)
        shares = [shap[str(h)]["group_share_pct"][g] for g in names]
        deltas = [abl["groups"][g]["delta_mae"] for g in names]
        abl["spearman_shap_share_vs_delta_mae"] = spearman(shares, deltas)
        abl["shap_share_pct"] = {g: s for g, s in zip(names, shares)}
        out["ablation"][str(h)] = abl

        # ---- 2. interval coverage ----
        tr_v = (np.asarray(sup.target_time < VAL_START)) & sup.y.notna().to_numpy()
        mv = TreeModel("xgboost", params, seed=args.seed).fit(sup.X[tr_v], sup.y[tr_v])
        val_blk = block_mask(sup.target_time, VAL_START, TEST_START - pd.Timedelta(hours=1)) & evalm
        yv = sup.y[val_blk].to_numpy()
        rv = yv - mv.predict(sup.X[val_blk])
        hv = pd.DatetimeIndex(sup.target_time[val_blk]).hour.to_numpy()
        ht = tt.hour.to_numpy()
        q_lo, q_hi = np.quantile(rv, Q_LO), np.quantile(rv, Q_HI)
        n = len(rv)
        c_q = float(np.quantile(np.abs(rv), min(1.0, math.ceil((n + 1) * (1 - ALPHA)) / n)))
        bands = {
            "horizon_wise": (p_full + q_lo, p_full + q_hi),
            "symmetric_conformal": (p_full - c_q, p_full + c_q),
        }
        lo_h = np.empty_like(p_full)
        hi_h = np.empty_like(p_full)
        for hr in range(24):
            r_h = rv[hv == hr]
            lo_h[ht == hr] = np.quantile(r_h, Q_LO)
            hi_h[ht == hr] = np.quantile(r_h, Q_HI)
        bands["hour_wise"] = (p_full + lo_h, p_full + hi_h)
        itv: dict = {"validation_rows": int(n), "test_rows": int(len(y)), "residual_q10_kw": float(q_lo), "residual_q90_kw": float(q_hi),
                     "conformal_halfwidth_kw": c_q, "bands": {}}
        te_res = y - p_full
        itv["test_residual_q10_kw"] = float(np.quantile(te_res, Q_LO))
        itv["test_residual_q90_kw"] = float(np.quantile(te_res, Q_HI))
        itv["test_mean_residual_kw"] = float(te_res.mean())
        itv["validation_mean_residual_kw"] = float(rv.mean())
        for name, (lo, hi) in bands.items():
            hit = ((y >= lo) & (y <= hi)).astype(float)
            ci = day_block_ci(hit, tt)
            by_hour = {int(hr): float(hit[ht == hr].mean()) for hr in range(24)}
            by_month = {int(mo): float(hit[tt.month.to_numpy() == mo].mean()) for mo in sorted(set(tt.month.tolist()))}
            itv["bands"][name] = {"coverage": float(hit.mean()), "coverage_ci95": list(ci), "mean_width_kw": float(np.mean(hi - lo)),
                                  "mean_interval_score": float(np.mean(interval_score(y, lo, hi))),
                                  "below_rate": float(np.mean(y < lo)), "above_rate": float(np.mean(y > hi)),
                                  "coverage_by_hour": by_hour, "coverage_by_month": by_month,
                                  "min_hour_coverage": float(min(by_hour.values())), "max_hour_coverage": float(max(by_hour.values()))}
            print(f"  band {name}: coverage {hit.mean():.3f} {ci[0]:.3f}-{ci[1]:.3f}, width {np.mean(hi - lo):.3f}", flush=True)
        out["interval"][str(h)] = itv

    # ---- mean hourly load profile (all valid hours), for the data section of the paper ----
    valid = series.dropna()
    wk = np.where(valid.index.day_of_week >= 5, "weekend", "weekday")
    prof = valid.groupby([wk, valid.index.hour]).agg(["mean", "count"])
    out["profile"] = {d: {int(hr): {"mean_kw": float(prof.loc[(d, hr), "mean"]), "hours": int(prof.loc[(d, hr), "count"])}
                          for hr in range(24)} for d in ("weekday", "weekend")}

    out["environment"] = environment_info()
    out["runtime_seconds"] = round(time.time() - t0, 1)
    (args.outdir / "extra_analyses.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
