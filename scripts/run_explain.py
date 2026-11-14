"""Phase 9: SHAP explanations of the saved XGBoost models, plus tariff-based recommendations on real data.

Outputs in artifacts/reports/explain/: shap_global.json, shap_local_example.json, recommendations.json,
fig_shap_global.png, fig_shap_groups.png, fig_shap_local.png.

    python scripts/run_explain.py --input data/raw/uci_household_power/household_power_consumption.txt
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
from ml_engine.anomaly.detector import detect  # noqa: E402
from ml_engine.data.ingest import UCI_CONFIG, ingest_csv  # noqa: E402
from ml_engine.environment import environment_info  # noqa: E402
from ml_engine.evaluation.splits import BENCHMARK_PLAN, block_mask  # noqa: E402
from ml_engine.evaluation.style import BLUE, INK2, ORANGE, setup_style  # noqa: E402
from ml_engine.explainability.shap_tree import GROUPS, contributions, explain_rows, global_importance, narrative  # noqa: E402
from ml_engine.features.builder import common_eval_mask, make_supervised  # noqa: E402
from ml_engine.forecasting.registry import load_tree_model  # noqa: E402
from ml_engine.optimization.recommendations import recommend  # noqa: E402
from ml_engine.optimization.tariff import DEMO_TARIFF  # noqa: E402

HORIZONS = (1, 6, 24)
LOCAL_ORIGIN = {1: "2010-01-04 18:00", 6: "2010-01-04 18:00", 24: "2010-01-04 18:00"}  # first Monday 18:00 of the test period (fixed in advance)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--bench", type=Path, default=Path("artifacts/reports/benchmark"))
    ap.add_argument("--models-dir", type=Path, default=Path("artifacts/models"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/reports/explain"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    setup_style()

    series = ingest_csv(args.input, UCI_CONFIG).hourly["value_kw"]
    cv = json.loads((args.bench / "cv_results.json").read_text(encoding="utf-8"))
    plan = BENCHMARK_PLAN

    glob: dict = {}
    imps: dict[int, pd.DataFrame] = {}
    local: dict = {}
    for h in HORIZONS:
        mid = cv["results"][str(h)]["chosen"]["xgboost"]["model_id"]
        model, meta = load_tree_model(args.models_dir, mid)
        sup = make_supervised(series, h)
        rows = block_mask(sup.target_time, plan.test_start, plan.test_end) & common_eval_mask(sup)
        X = sup.X[rows]
        contrib, bias = contributions(model, X)
        recon = contrib.sum(axis=1).to_numpy() + bias
        add_err = float(np.abs(recon - model.predict(X)).max())
        imp = global_importance(model, X, max_rows=len(X))
        imps[h] = imp
        grp = imp.groupby("group")["share_pct"].sum().sort_values(ascending=False)
        glob[str(h)] = {"model_id": mid, "rows_explained": int(len(X)), "max_additivity_error_kw": add_err,
                        "top_features": imp.head(10)[["feature", "label", "group", "mean_abs_shap_kw", "share_pct"]].to_dict("records"),
                        "group_share_pct": grp.to_dict()}
        origin = pd.Timestamp(LOCAL_ORIGIN[h])
        xr = sup.X.loc[[origin]]
        exp = explain_rows(model, xr)[0]
        exp["narrative"] = narrative(exp, h)
        exp["actual_kw"] = None if pd.isna(sup.y.loc[origin]) else float(sup.y.loc[origin])
        local[str(h)] = exp
        print(f"h={h}: {len(X)} rows, additivity max err {add_err:.2e} kW; top: " + ", ".join(imp['feature'].head(4)))
    glob["environment"] = environment_info()
    (args.out / "shap_global.json").write_text(json.dumps(glob, indent=2), encoding="utf-8")
    (args.out / "shap_local_example.json").write_text(json.dumps(local, indent=2), encoding="utf-8")

    # --- figure: top features per horizon
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), sharex=False)
    for ax, h in zip(axes, HORIZONS):
        top = imps[h].head(8).iloc[::-1]
        ax.barh(range(len(top)), top["mean_abs_shap_kw"], color=BLUE, height=0.62)
        ax.set_yticks(range(len(top)), top["label"])
        ax.set_title(f"{h} h ahead")
        ax.set_xlabel("Mean |SHAP| (kW)")
        ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(args.out / "fig_shap_global.png", bbox_inches="tight")
    plt.close(fig)

    # --- figure: share by feature group (annotated heatmap, one sequential hue)
    order = list(GROUPS)
    mat = np.array([[glob[str(h)]["group_share_pct"].get(g, 0.0) for h in HORIZONS] for g in order])
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    ax.imshow(mat, cmap="Blues", vmin=0, vmax=max(60, mat.max()), aspect="auto")
    ax.set_xticks(range(3), [f"{h} h ahead" for h in HORIZONS])
    ax.set_yticks(range(len(order)), order)
    ax.grid(False)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat[i, j]:.0f}%", ha="center", va="center", color="#0b0b0b" if mat[i, j] < 38 else "#ffffff", fontsize=10)
    ax.set_title("Share of the model's attention by kind of information")
    fig.savefig(args.out / "fig_shap_groups.png", bbox_inches="tight")
    plt.close(fig)

    # --- figure: local explanation for the fixed example origin
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, h in zip(axes, HORIZONS):
        d = local[str(h)]["drivers"][:6][::-1]
        ax.barh(range(len(d)), [x["contribution_kw"] for x in d], color=[ORANGE if x["contribution_kw"] > 0 else BLUE for x in d], height=0.6)
        ax.set_yticks(range(len(d)), [x["label"] for x in d])
        ax.axvline(0, color=INK2, lw=1)
        e = local[str(h)]
        ax.set_title(f"{h} h ahead\nforecast {e['prediction_kw']:.2f} kW (base {e['base_value_kw']:.2f})")
        ax.set_xlabel("Contribution (kW): orange raises, blue lowers")
        ax.grid(axis="y", visible=False)
    fig.suptitle("Why the forecast made on Mon 4 Jan 2010 18:00 looks the way it does", x=0.01, ha="left", fontsize=11, fontweight="bold", color="#0b0b0b")
    fig.tight_layout()
    fig.savefig(args.out / "fig_shap_local.png", bbox_inches="tight")
    plt.close(fig)

    # --- recommendations on the last 90 days of real data (DEMO tariff)
    events = detect(series).events
    rec = recommend(series, DEMO_TARIFF, anomaly_events=events)
    (args.out / "recommendations.json").write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    for r in rec["recommendations"]:
        print(f"[{r['priority']}] {r['title']}: {r['explanation'][:160]}")


if __name__ == "__main__":
    main()
