"""Phase 6: train and score the LSTM on the UCI benchmark with the same protocol as the tree models.

* Early stopping on a validation block (2009-07-01 .. 2009-12-31), network trained on targets before it.
* Refit on all targets before the 2010 test period for exactly the number of epochs chosen on validation.
* Scored once on the same rows (common_eval_mask) as every other model.
* The first seed is the pre-declared headline run; other seeds are reported as robustness, never picked by test score.

    python scripts/run_lstm.py --input data/raw/uci_household_power/household_power_consumption.txt --seeds 42 43 44
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml_engine.data.ingest import UCI_CONFIG, ingest_csv  # noqa: E402
from ml_engine.environment import environment_info  # noqa: E402
from ml_engine.evaluation.metrics import evaluate  # noqa: E402
from ml_engine.evaluation.splits import BENCHMARK_PLAN, block_mask  # noqa: E402
from ml_engine.features.builder import common_eval_mask, make_supervised  # noqa: E402
from ml_engine.forecasting.lstm import HORIZONS, LSTMConfig, LSTMForecaster  # noqa: E402
from ml_engine.forecasting.registry import new_model_id, series_hash  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/reports/benchmark"))
    ap.add_argument("--models-dir", type=Path, default=Path("artifacts/models"))
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--max-epochs", type=int, default=12)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    series = ingest_csv(args.input, UCI_CONFIG).hourly["value_kw"]
    plan = BENCHMARK_PLAN
    data_hash = series_hash(series)

    # Test rows are rebuilt independently of the tree benchmark with the same code path,
    # so every model is scored on identical (target_time, y_true) rows.
    test_rows = {}
    for h in HORIZONS:
        sup = make_supervised(series, h)
        scored = block_mask(sup.target_time, plan.test_start, plan.test_end) & common_eval_mask(sup)
        test_rows[h] = pd.Series(sup.y[scored].to_numpy(), index=sup.target_time[scored], name="y_true")

    val_range = (plan.val_start, plan.test_start)
    out: dict = {"protocol": {"validation": [str(val_range[0]), str(val_range[1])],
                              "test": [str(plan.test_start), str(plan.test_end)],
                              "headline_seed": args.seeds[0], "data_hash": data_hash}, "seeds": {}}
    preds = {h: test_rows[h].to_frame() for h in HORIZONS}

    for seed in args.seeds:
        cfg = LSTMConfig(seed=seed, threads=args.threads, max_epochs=args.max_epochs)
        ts = time.time()
        sel = LSTMForecaster(cfg)
        info = sel.fit(series, plan.val_start, val_range=val_range, log=lambda r, seed=seed: print(f"  [seed {seed}] select {r}", flush=True))
        best_epochs = info["best_epoch"]
        print(f"[seed {seed}] validation: best epoch {best_epochs}/{len(info['history'])}, "
              f"val MAE (kW) {info['history'][best_epochs - 1]['val_mae_kw']} ({time.time() - ts:.0f}s)", flush=True)
        final = LSTMForecaster(cfg)
        final_info = final.fit(series, plan.test_start, epochs=best_epochs, log=lambda r, seed=seed: print(f"  [seed {seed}] refit epoch {r['epoch']} loss {r['train_loss']:.4f}", flush=True))
        grid = final.predict(series)
        res = {"best_epochs": best_epochs, "selection_history": info["history"],
               "train_windows_selection": info["train_windows"], "train_windows_final": final_info["train_windows"],
               "test": {}}
        for h in HORIZONS:
            origins = test_rows[h].index - pd.Timedelta(hours=h)
            p = grid[f"h{h}"].reindex(origins).to_numpy()
            if np.isnan(p).any():
                raise RuntimeError(f"LSTM has no prediction for some test origins at h={h}")
            col = "lstm" if seed == args.seeds[0] else f"lstm_seed{seed}"
            preds[h][col] = p
            res["test"][f"h{h}"] = evaluate(test_rows[h].to_numpy(), p)
        if seed == args.seeds[0]:
            mid = new_model_id("lstm", 0).replace("_h0_", "_multi_")
            final.save(args.models_dir / mid, {
                "model_id": mid, "data_hash": data_hash, "train_target_before": str(plan.test_start),
                "selection_validation": [str(v) for v in val_range], "test_metrics": res["test"], "unit": "kW",
            })
            res["model_id"] = mid
        out["seeds"][str(seed)] = res
        print(f"[seed {seed}] test MAE (kW): " + " | ".join(f"h{h}: {res['test'][f'h{h}']['mae']:.4f}" for h in HORIZONS)
              + f" ({time.time() - ts:.0f}s)", flush=True)

    for h in HORIZONS:
        preds[h].to_csv(args.outdir / f"lstm_predictions_h{h}.csv", index_label="target_time")
    out["runtime_seconds"] = round(time.time() - t0, 1)
    out["environment"] = environment_info()
    (args.outdir / "lstm_results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
