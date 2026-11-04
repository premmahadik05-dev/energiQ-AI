"""Phase 4-5 benchmark: baselines, Random Forest, XGBoost on the UCI household data.

Selection uses the 8 expanding-window folds in 2008-2009; the 2010 test period is
scored once after refitting on everything before it.

    python scripts/run_benchmark.py --input data/raw/uci_household_power/household_power_consumption.txt
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml_engine.data.ingest import UCI_CONFIG, ingest_csv  # noqa: E402
from ml_engine.environment import environment_info  # noqa: E402
from ml_engine.evaluation.splits import BENCHMARK_PLAN  # noqa: E402
from ml_engine.forecasting.registry import series_hash  # noqa: E402
from ml_engine.pipeline import ExperimentConfig, run_experiment  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/reports/benchmark"))
    ap.add_argument("--models-dir", type=Path, default=Path("artifacts/models"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    ing = ingest_csv(args.input, UCI_CONFIG)
    series = ing.hourly["value_kw"]
    print(f"ingested: {ing.report['valid_hours']} valid hours, quality {ing.report['quality']['score']}", flush=True)
    cfg = ExperimentConfig(plan=BENCHMARK_PLAN, seed=args.seed, models_dir=args.models_dir,
                           log=lambda m: print(m, flush=True))
    results, preds = run_experiment(series, cfg)
    for h, df in preds.items():
        df.to_csv(args.outdir / f"predictions_h{h}.csv")
    out = {
        "protocol": {
            "target": "hourly mean Global_active_power (kW), hours with >= 45 valid minutes",
            "cv_folds": [{"name": f.name, "test_start": str(f.test_start), "test_end": str(f.test_end)} for f in BENCHMARK_PLAN.folds],
            "test_period": [str(BENCHMARK_PLAN.test_start), str(BENCHMARK_PLAN.test_end)],
            "seed": args.seed,
            "data_hash": series_hash(series),
        },
        "results": results,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out["environment"] = environment_info()
    (args.outdir / "cv_results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
