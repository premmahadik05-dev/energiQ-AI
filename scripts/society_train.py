"""Train and evaluate the society-level forecasters on the real processed data.

    python scripts/society_train.py                    # evaluate every society (about 3-5 minutes each on 2 CPUs)
    python scripts/society_train.py --societies fox    # one society
    python scripts/society_train.py --deploy           # also refit and save the deployment bundle
    python scripts/society_train.py --peaks-only       # recompute peak_evaluation.json from saved predictions

Writes, per society, to artifacts/society/<key>/:
    evaluation.json          protocol, per-horizon CV results, chosen parameters, test metrics for every model
    predictions_h<h>.csv.gz  held-out test predictions of every model (actual vs predicted)
    shap_global.json         mean |SHAP| of the CV-selected model on the test rows, per horizon
    peak_evaluation.json     how well the 24 h forecast finds each test day's peak
and (with --deploy) models/ and bundle.json: the models used by the API for live forecasts.
The protocol lives in ml_engine/society/runner.py and is shared with the API's train job.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_engine.society.experiment import HORIZONS  # noqa: E402
from ml_engine.society.runner import peak_evaluation, train  # noqa: E402


def load_society(processed: Path, key: str) -> tuple[pd.Series, pd.DataFrame]:
    d = pd.read_csv(processed / key / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    return d["society_kwh"].rename("demand_kw"), d[["airTemperature", "dewTemperature", "windSpeed"]]


def peaks_only(out_root: Path, key: str) -> None:
    ev = json.loads((out_root / key / "evaluation.json").read_text())["horizons"]["24"]
    preds = pd.read_csv(out_root / key / "predictions_h24.csv.gz", parse_dates=["target_time"], index_col="target_time")
    res = peak_evaluation(preds, ev["best_overall_by_cv"], ev["best_baseline_by_cv"])
    (out_root / key / "peak_evaluation.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"  [{key}] peak days={res['days']} model MAE {res['model']['peak_mae_kw']:.1f} kW vs baseline {res['baseline']['peak_mae_kw']:.1f} kW", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processed", type=Path, default=ROOT / "data/society/processed")
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/society")
    ap.add_argument("--societies", nargs="*")
    ap.add_argument("--horizons", type=int, nargs="*", default=list(HORIZONS))
    ap.add_argument("--deploy", action="store_true", help="after evaluating, refit and save the deployment bundle")
    ap.add_argument("--peaks-only", action="store_true", help="only recompute peak_evaluation.json from saved predictions")
    a = ap.parse_args()
    index = json.loads((a.processed / "societies.json").read_text())["societies"]
    keys = a.societies or [s["key"] for s in index]
    for key in keys:
        print(f"== {key}", flush=True)
        if a.peaks_only:
            peaks_only(a.out, key)
            continue
        series, weather = load_society(a.processed, key)
        train(key, series, weather, a.out / key, tuple(a.horizons), deploy=a.deploy, log=lambda m, k=key: print(f"  [{k}] {m}", flush=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
