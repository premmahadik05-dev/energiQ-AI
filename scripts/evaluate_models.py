"""Phase 7: merge all model predictions, compute metrics, intervals, breakdowns and figures.

Reads  artifacts/reports/benchmark/{predictions_h*.csv, cv_results.json, lstm_predictions_h*.csv, lstm_results.json}
Writes artifacts/reports/evaluation/{evaluation.json, model_comparison.md, fig_*.png}

Every number is recomputed here from the stored predictions; nothing is typed in.

    python scripts/evaluate_models.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml_engine.environment import environment_info  # noqa: E402
from ml_engine.evaluation.metrics import evaluate, paired_block_bootstrap  # noqa: E402
from ml_engine.evaluation.style import INK, INK2, MODEL_COLORS, MODEL_LABELS, MODEL_ORDER, setup_style  # noqa: E402

HORIZONS = (1, 6, 24)
BASELINES = ("naive", "seasonal_naive_24", "seasonal_naive_168")
ML = ("random_forest", "xgboost", "lstm")
WEEK = ("2010-01-04", "2010-01-10 23:00")  # fixed in advance: first full Mon-Sun week of the test period


def load(bench: Path) -> tuple[dict[int, pd.DataFrame], dict, dict | None]:
    cv = json.loads((bench / "cv_results.json").read_text(encoding="utf-8"))
    lstm_res = json.loads((bench / "lstm_results.json").read_text(encoding="utf-8")) if (bench / "lstm_results.json").is_file() else None
    preds = {}
    for h in HORIZONS:
        df = pd.read_csv(bench / f"predictions_h{h}.csv", index_col="target_time", parse_dates=True)
        lp = bench / f"lstm_predictions_h{h}.csv"
        if lp.is_file():
            lstm_df = pd.read_csv(lp, index_col="target_time", parse_dates=True)
            if not lstm_df.index.equals(df.index) or not np.allclose(lstm_df["y_true"], df["y_true"]):
                raise ValueError(f"h={h}: LSTM and tree predictions are not on identical rows")
            for c in lstm_df.columns:
                if c != "y_true":
                    df[c] = lstm_df[c]
        preds[h] = df
    return preds, cv, lstm_res


def best_cv_baseline(cv: dict, h: int) -> str:
    cvh = cv["results"][str(h)]["cv"]
    return min(BASELINES, key=lambda b: cvh[b]["_summary"]["mean_fold_mae"])


def models_in(df: pd.DataFrame) -> list[str]:
    return [m for m in MODEL_ORDER if m in df.columns]


def savefig(fig, out: Path, name: str) -> str:
    fig.savefig(out / name, bbox_inches="tight")
    plt.close(fig)
    return name


def fig_mae_by_horizon(summary: dict, base_name: dict, out: Path) -> str:
    fig, ax = plt.subplots(figsize=(9, 4.4))
    models = [m for m in MODEL_ORDER if m in summary[HORIZONS[0]]]
    width = 0.8 / len(models)
    for i, m in enumerate(models):
        xs = np.arange(len(HORIZONS)) + (i - (len(models) - 1) / 2) * width
        ax.bar(xs, [summary[h][m]["mae"] for h in HORIZONS], width=width * 0.92, color=MODEL_COLORS[m], label=MODEL_LABELS[m],
               edgecolor="#fcfcfb", linewidth=1.5)
    ax.set_xticks(range(len(HORIZONS)), [f"{h} h ahead" for h in HORIZONS])
    ax.set_ylabel("Test MAE (kW), lower is better")
    ax.set_title("Test MAE by horizon: every learned model beats every baseline")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", ncols=3, fontsize=8, bbox_to_anchor=(0, 1.0))
    ax.set_ylim(0, max(summary[h][m]["mae"] for h in HORIZONS for m in models) * 1.3)
    return savefig(fig, out, "fig_mae_by_horizon.png")


def fig_week(preds: dict, base_name: dict, out: Path) -> str:
    fig, axes = plt.subplots(3, 1, figsize=(10, 8.2), sharex=True)
    for ax, h in zip(axes, HORIZONS):
        w = preds[h].loc[WEEK[0]:WEEK[1]]
        ax.plot(w.index, w["y_true"], color=MODEL_COLORS["actual"], lw=1.8, label="Actual")
        for m in (base_name[h], "xgboost", "lstm"):
            if m in w:
                ax.plot(w.index, w[m], color=MODEL_COLORS[m], lw=1.4, ls="--" if m in BASELINES else "-",
                        label=MODEL_LABELS[m] + (" (best baseline by CV)" if m in BASELINES else ""))
        ax.set_title(f"{h} h ahead")
        ax.set_ylabel("kW")
        ax.legend(loc="upper left", ncols=4, fontsize=8)
    axes[-1].set_xlabel("Target time, first full week of the test period (Mon 4 Jan - Sun 10 Jan 2010; window fixed in advance)")
    fig.autofmt_xdate()
    return savefig(fig, out, "fig_actual_vs_predicted_week.png")


def fig_breakdown(preds: dict, base_name: dict, by: str, out: Path) -> tuple[str, dict]:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    table: dict = {}
    for ax, h in zip(axes, HORIZONS):
        df = preds[h]
        key = df.index.hour if by == "hour" else df.index.month
        table[h] = {}
        for m in [base_name[h], "random_forest", "xgboost", "lstm"]:
            if m not in df:
                continue
            e = (df[m] - df["y_true"]).abs().groupby(key).mean()
            table[h][m] = {int(k): float(v) for k, v in e.items()}
            ax.plot(e.index, e.values, marker="o" if by == "month" else None, ms=5, lw=2,
                    ls="--" if m in BASELINES else "-", color=MODEL_COLORS[m], label=MODEL_LABELS[m])
        ax.set_title(f"{h} h ahead")
        ax.set_xlabel("Hour of day (target)" if by == "hour" else "Month of 2010 (target)")
        if by == "hour":
            ax.set_xticks(range(0, 24, 3))
        else:
            ax.set_xticks(sorted(set(df.index.month)))
    axes[0].set_ylabel("MAE (kW)")
    axes[0].legend(loc="upper left", fontsize=8)
    return savefig(fig, out, f"fig_error_by_{by}.png"), table


def fig_residuals(preds: dict, out: Path) -> tuple[str, dict]:
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    stats: dict = {}
    for ax, h in zip(axes, HORIZONS):
        df = preds[h]
        stats[h] = {}
        for m in ML:
            if m not in df:
                continue
            r = df[m] - df["y_true"]
            stats[h][m] = {"mean_error_kw": float(r.mean()), "median_error_kw": float(r.median()),
                           "p05_kw": float(r.quantile(0.05)), "p95_kw": float(r.quantile(0.95))}
            ax.hist(r.clip(-3, 3), bins=60, range=(-3, 3), histtype="step", lw=2, density=True,
                    color=MODEL_COLORS[m], label=f"{MODEL_LABELS[m]} (bias {r.mean():+.3f} kW)")
        ax.axvline(0, color=INK2, lw=1)
        ax.set_title(f"{h} h ahead")
        ax.set_xlabel("Prediction - actual (kW), clipped to +/-3")
        ax.legend(loc="upper right", fontsize=8)
    axes[0].set_ylabel("Density")
    return savefig(fig, out, "fig_residuals.png"), stats


def fig_scatter(preds: dict, out: Path) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, h in zip(axes, HORIZONS):
        df = preds[h]
        hb = ax.hexbin(df["y_true"], df["xgboost"], gridsize=40, bins="log", cmap="Blues", mincnt=1, extent=(0, 6, 0, 6))
        ax.plot([0, 6], [0, 6], color=INK, lw=1)
        ax.set_xlim(0, 6)
        ax.set_ylim(0, 6)
        ax.set_title(f"XGBoost, {h} h ahead")
        ax.set_xlabel("Actual (kW)")
        ax.grid(False)
        fig.colorbar(hb, ax=ax, label="hours (log)", shrink=0.8)
    axes[0].set_ylabel("Predicted (kW)")
    return savefig(fig, out, "fig_actual_vs_predicted_scatter.png")


def fmt(v, d=3):
    return "-" if v is None else f"{v:.{d}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=Path, default=Path("artifacts/reports/benchmark"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/reports/evaluation"))
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    setup_style()

    preds, cv, lstm_res = load(args.bench)
    base_name = {h: best_cv_baseline(cv, h) for h in HORIZONS}
    result: dict = {"protocol": cv["protocol"], "best_cv_baseline": {str(h): base_name[h] for h in HORIZONS}, "horizons": {}}
    summary: dict = {}

    for h in HORIZONS:
        df = preds[h]
        ms = models_in(df)
        met = {m: evaluate(df["y_true"], df[m]) for m in ms}
        # the stored tree metrics from the pipeline must equal what is recomputed here
        for m in ms:
            if m in cv["results"][str(h)]["test"]:
                stored = cv["results"][str(h)]["test"][m]["mae"]
                assert abs(stored - met[m]["mae"]) < 1e-9, f"metric mismatch for {m} h={h}"
        summary[h] = met
        base = base_name[h]
        boot = {}
        for m in ms:
            if m != base:
                boot[m] = paired_block_bootstrap(df["y_true"], df[m], df[base], df.index, n_boot=args.boot, seed=h)
        hind = min(BASELINES, key=lambda b: met[b]["mae"])
        boot_hind = {}
        if hind != base:
            for m in ms:
                if m not in BASELINES:
                    boot_hind[m] = paired_block_bootstrap(df["y_true"], df[m], df[hind], df.index, n_boot=args.boot, seed=h)
        pair = {"xgboost_vs_random_forest": paired_block_bootstrap(df["y_true"], df["xgboost"], df["random_forest"], df.index, args.boot, h)}
        if "lstm" in df:
            pair["lstm_vs_xgboost"] = paired_block_bootstrap(df["y_true"], df["lstm"], df["xgboost"], df.index, args.boot, h)
        result["horizons"][str(h)] = {
            "n_rows_scored": int(len(df)), "counts": cv["results"][str(h)]["counts"], "metrics": met,
            "mean_actual_kw": float(df["y_true"].mean()),
            "hindsight_best_baseline": hind, "bootstrap_mae_diff_vs_hindsight_best_baseline": boot_hind,
            "bootstrap_mae_diff_vs_best_cv_baseline": boot, "pairwise_mae_diff": pair,
            "chosen_params": {k: v["params"] for k, v in cv["results"][str(h)]["chosen"].items()},
            "cv_mean_fold_mae": {k: v["_summary"]["mean_fold_mae"] for k, v in cv["results"][str(h)]["cv"].items()},
        }

    figs = [fig_mae_by_horizon(summary, base_name, args.out), fig_week(preds, base_name, args.out)]
    name, by_hour = fig_breakdown(preds, base_name, "hour", args.out)
    figs.append(name)
    name, by_month = fig_breakdown(preds, base_name, "month", args.out)
    figs.append(name)
    name, resid = fig_residuals(preds, args.out)
    figs.append(name)
    figs.append(fig_scatter(preds, args.out))
    for h in HORIZONS:
        result["horizons"][str(h)]["mae_by_hour"] = by_hour[h]
        result["horizons"][str(h)]["mae_by_month"] = by_month[h]
        result["horizons"][str(h)]["residuals"] = resid[h]
    if lstm_res:
        result["lstm_seed_robustness"] = {
            seed: {f"h{h}": r["test"][f"h{h}"]["mae"] for h in HORIZONS} | {"best_epochs": r["best_epochs"]}
            for seed, r in lstm_res["seeds"].items()}
        result["lstm_headline_seed"] = lstm_res["protocol"]["headline_seed"]
    result["figures"] = figs
    result["environment"] = environment_info()
    (args.out / "evaluation.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    # ---------------- markdown report ----------------
    L = ["# Model comparison (test period, scored once)", "",
         f"Test period: {cv['protocol']['test_period'][0][:10]} to {cv['protocol']['test_period'][1][:10]}. "
         "All models are scored on exactly the same rows per horizon. Units: kW (hourly mean Global_active_power). "
         "Lower is better for MAE, RMSE, MAPE and sMAPE; higher for R2.", ""]
    for h in HORIZONS:
        r = result["horizons"][str(h)]
        L += [f"## {h} h ahead  (n = {r['n_rows_scored']} hours scored; {r['counts']['test_rows_excluded']} of "
              f"{r['counts']['test_target_hours']} test hours excluded for a missing target or missing inputs)", "",
              "| Model | MAE | RMSE | MAPE % | sMAPE % | R2 |", "|---|---|---|---|---|---|"]
        for m, v in r["metrics"].items():
            tag = " (best baseline by CV)" if m == base_name[h] else ""
            L.append(f"| {MODEL_LABELS[m]}{tag} | {fmt(v['mae'], 4)} | {fmt(v['rmse'], 4)} | {fmt(v['mape_pct'], 1)} | {fmt(v['smape_pct'], 1)} | {fmt(v['r2'], 3)} |")
        L += ["", f"Mean actual load in these rows: {r['mean_actual_kw']:.3f} kW. MAPE excludes hours with actual < 0.05 kW ({r['metrics']['naive']['mape_excluded']} hours).", "",
              f"Paired day-block bootstrap, MAE(model) - MAE({MODEL_LABELS[base_name[h]]}), 95% CI (negative = model better):", ""]
        for m, b in r["bootstrap_mae_diff_vs_best_cv_baseline"].items():
            L.append(f"- {MODEL_LABELS[m]}: {b['mae_diff']:+.4f} kW  [{b['ci95_low']:+.4f}, {b['ci95_high']:+.4f}]  ({b['days']} days)")
        if r["bootstrap_mae_diff_vs_hindsight_best_baseline"]:
            L += ["", f"Same comparison against the strongest baseline *in hindsight* on the test rows ({MODEL_LABELS[r['hindsight_best_baseline']]}), a stricter reference than the CV-chosen one:", ""]
            for m, b in r["bootstrap_mae_diff_vs_hindsight_best_baseline"].items():
                L.append(f"- {MODEL_LABELS[m]}: {b['mae_diff']:+.4f} kW  [{b['ci95_low']:+.4f}, {b['ci95_high']:+.4f}]")
            L.append("")
            L.append("Pairwise comparisons between learned models:")
            L.append("")
        for k, b in r["pairwise_mae_diff"].items():
            a, c = k.split("_vs_")
            L.append(f"- {MODEL_LABELS[a]} vs {MODEL_LABELS[c]}: {b['mae_diff']:+.4f} kW  [{b['ci95_low']:+.4f}, {b['ci95_high']:+.4f}]")
        L.append("")
    if lstm_res:
        L += ["## LSTM seed robustness (test MAE, kW)", "",
              f"Headline run = seed {result['lstm_headline_seed']}, fixed before looking at test scores. Other seeds are shown for stability only.", "",
              "| Seed | best epochs | h=1 | h=6 | h=24 |", "|---|---|---|---|---|"]
        for s, v in result["lstm_seed_robustness"].items():
            L.append(f"| {s} | {v['best_epochs']} | {v['h1']:.4f} | {v['h6']:.4f} | {v['h24']:.4f} |")
        L.append("")
    L += ["## Figures", ""] + [f"- `{f}`" for f in figs]
    (args.out / "model_comparison.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:60]))


if __name__ == "__main__":
    main()
