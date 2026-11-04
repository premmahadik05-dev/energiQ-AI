"""Regenerate every research result from the raw UCI file, in order, with the current interpreter.

    python scripts/reproduce_benchmark.py --input data/raw/uci_household_power/household_power_consumption.txt

Steps (each is also runnable on its own; see docs/05_ml_methodology.md):
  1. run_benchmark   features, expanding-window CV, baselines, Random Forest, XGBoost
  2. run_lstm        LSTM with three seeds (42 is the pre-declared headline run)
  3. evaluate_models test metrics, paired day-block bootstrap, figures
  4. run_explain     TreeSHAP summaries, tariff cost, recommendations
  5. run_anomaly     anomaly detection summary and the synthetic injection check

Results depend on library versions (XGBoost in particular), so every output file records the versions that produced it
(`environment`). Use the interpreter built from requirements.txt to reproduce the published numbers.
On the development machine (2 CPU cores, no GPU) the whole chain takes roughly 25 minutes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(step: str, *args: str) -> None:
    t0 = time.time()
    print(f"\n=== {step} ===", flush=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / f"{step}.py"), *args], cwd=ROOT, check=True)
    print(f"=== {step} finished in {time.time() - t0:.0f} s ===", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path, help="household_power_consumption.txt from the UCI repository")
    ap.add_argument("--skip-lstm", action="store_true", help="skip step 2 (PyTorch is then not needed; the evaluation step needs the saved LSTM files)")
    args = ap.parse_args()
    if not args.input.is_file():
        sys.exit(f"input file not found: {args.input}")
    src = str(args.input)
    run("run_benchmark", "--input", src)
    if not args.skip_lstm:
        run("run_lstm", "--input", src, "--seeds", "42", "43", "44")
    run("evaluate_models")
    run("run_explain", "--input", src)
    run("run_anomaly", "--input", src)
    print("\nDone. Compare the new files under artifacts/reports/ with the committed ones (git diff).")


if __name__ == "__main__":
    main()
