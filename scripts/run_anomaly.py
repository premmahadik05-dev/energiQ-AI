"""Phase 8: run the anomaly detector on the real UCI series, review the events, run the synthetic check.

Outputs in artifacts/reports/anomaly/: anomaly_summary.json, events.csv, injection_check.json,
fig_anomaly_events_by_month.png, fig_anomaly_examples.png.

There are no ground-truth anomaly labels in this dataset. The injection check is synthetic and says
nothing about accuracy on real faults; the event list is meant for human review.

    python scripts/run_anomaly.py --input data/raw/uci_household_power/household_power_consumption.txt
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
from ml_engine.anomaly.detector import AnomalyConfig, detect, injection_check  # noqa: E402
from ml_engine.data.ingest import UCI_CONFIG, ingest_csv  # noqa: E402
from ml_engine.environment import environment_info  # noqa: E402
from ml_engine.evaluation.style import BLUE, INK, ORANGE, setup_style  # noqa: E402

SEV_SHADES = {"low": "#f9c4a8", "medium": "#f08c5c", "high": "#b8431a"}
# Phase 1 findings in the raw data, used here only as a qualitative cross-check
KNOWN = {
    "flat_401min_0.360kW": ("2008-10-06 10:00", "2008-10-06 17:00"),
    "low_use_block_aug_2008": ("2008-08-20", "2008-08-29 23:00"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("artifacts/reports/anomaly"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    setup_style()

    series = ingest_csv(args.input, UCI_CONFIG).hourly["value_kw"]
    cfg = AnomalyConfig()
    res = detect(series, cfg)
    h, ev = res.hourly, pd.DataFrame(res.events)
    ev.to_csv(args.out / "events.csv", index=False)

    cross = {}
    for name, (a, b) in KNOWN.items():
        seg = h.loc[a:b]
        cross[name] = {"window": [a, b], "flagged_hours": int(seg["anomalous"].sum()), "hours": int(len(seg)),
                       "flat_flag_hours": int(seg["flag_flat"].sum()), "drop_flag_hours": int((seg["flag_dev"] & (seg["resid_kw"] < 0)).sum())}

    chk = injection_check(series, cfg, n=60, seed=0)
    (args.out / "injection_check.json").write_text(json.dumps(chk, indent=2), encoding="utf-8")
    top = ev.sort_values(["severity_level", "peak_excess_ratio"], ascending=[False, False]).head(10)
    summary = {"config": res.config, "summary": res.summary, "cross_check_known_phase1_findings": cross,
               "top_events": top[["start", "end", "hours", "types", "severity", "peak_value_kw", "expected_kw", "peak_excess_ratio"]].to_dict("records"),
               "labels": "no ground-truth anomaly labels exist in this dataset; injection check is synthetic"}
    summary["environment"] = environment_info()
    (args.out / "anomaly_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # --- figure 1: events per month by severity (single-hue ordinal ramp)
    ev["month"] = pd.to_datetime(ev["start"]).dt.to_period("M").dt.to_timestamp()
    pivot = ev.groupby(["month", "severity"]).size().unstack(fill_value=0).reindex(columns=["low", "medium", "high"], fill_value=0)
    months = pd.period_range(h.index[0], h.index[-1], freq="M").to_timestamp()
    pivot = pivot.reindex(months, fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 3.8))
    bottom = np.zeros(len(pivot))
    for sev in ("low", "medium", "high"):
        ax.bar(pivot.index, pivot[sev], width=22, bottom=bottom, color=SEV_SHADES[sev], edgecolor="#fcfcfb", linewidth=1.5, label=sev.capitalize())
        bottom += pivot[sev].to_numpy()
    ax.set_ylabel("Anomaly events per month")
    ax.set_title(f"{len(ev)} anomaly events found; flagged hours = {res.summary['flagged_pct_of_valid']:.2f}% of valid hours")
    ax.set_ylim(0, bottom.max() * 1.12)
    ax.legend(title="Severity", loc="lower right", bbox_to_anchor=(1, 1.0), ncols=3)
    fig.savefig(args.out / "fig_anomaly_events_by_month.png", bbox_inches="tight")
    plt.close(fig)

    # --- figure 2: zoom on three events chosen by rule (not by looks)
    picks = []
    spikes = ev[ev["types"].apply(lambda t: "spike" in t)].sort_values("peak_excess_ratio", ascending=False)
    if len(spikes):
        picks.append(("Largest spike (highest ratio to usual range)", pd.Timestamp(spikes.iloc[0]["peak_time"])))
    picks.append(("Longest flat run (identical readings)", None))
    flat = ev[ev["types"].apply(lambda t: "flat_run" in t)].sort_values("hours", ascending=False)
    picks[-1] = (picks[-1][0], pd.Timestamp(flat.iloc[0]["start"]) + pd.Timedelta(hours=int(flat.iloc[0]["hours"]) // 2)) if len(flat) else (picks[-1][0], None)
    drops = ev[ev["types"].apply(lambda t: "drop" in t)].sort_values("hours", ascending=False)
    if len(drops):
        picks.append(("Longest low-use event", pd.Timestamp(drops.iloc[0]["start"]) + pd.Timedelta(hours=int(drops.iloc[0]["hours"]) // 2)))
    picks = [p for p in picks if p[1] is not None]
    fig, axes = plt.subplots(len(picks), 1, figsize=(10, 3.2 * len(picks)))
    axes = np.atleast_1d(axes)
    for ax, (title, centre) in zip(axes, picks):
        span = pd.Timedelta(days=7 if "low-use" in title else 3)
        w = h.loc[centre - span: centre + span]
        ax.plot(w.index, w["value_kw"], color=INK, lw=1.3, label="Actual")
        ax.plot(w.index, w["expected_kw"], color=BLUE, lw=1.3, ls="--", label="Typical for hour of week (median of prior 8 weeks)")
        f = w[w["anomalous"]]
        ax.scatter(f.index, f["value_kw"], s=34, color=ORANGE, edgecolor="#fcfcfb", linewidth=1.2, zorder=3, label="Flagged hour")
        ax.set_title(f"{title}: {centre:%d %b %Y}")
        ax.set_ylabel("kW")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncols=3, fontsize=9)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(args.out / "fig_anomaly_examples.png", bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({"summary": res.summary, "cross_check": cross, "injection": chk}, indent=2, default=str))
    print(top[["start", "hours", "types", "severity", "peak_value_kw", "expected_kw", "peak_excess_ratio"]].to_string())


if __name__ == "__main__":
    main()
