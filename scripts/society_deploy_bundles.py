"""Install the live-forecast models (deployment bundles) for the bundled communities WITHOUT re-running the evaluation.

    python scripts/society_deploy_bundles.py                   # every bundled community that has no bundle yet
    python scripts/society_deploy_bundles.py --societies bull  # one community
    python scripts/society_deploy_bundles.py --force           # rebuild bundles that already exist

Why this exists: ``society_train.py --deploy`` repeats the whole evaluation (minutes per community) and rewrites
``evaluation.json`` and the prediction files. The evaluation of the delivered communities is already saved and is
the published result, so this script only does the last step of the protocol: it reads the saved
``evaluation.json`` of each community, takes the configuration that cross-validation selected for every horizon
and refits it on all valid history (``ml_engine.society.deploy.build_bundle``). It writes ``models/`` and
``bundle.json`` next to the evaluation and never touches ``evaluation.json``, ``predictions_h*.csv.gz``,
``shap_global.json``, ``peak_evaluation.json`` or ``anomalies.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_engine.society.deploy import build_bundle  # noqa: E402

PROCESSED = ROOT / "data" / "society" / "processed"
ARTIFACTS = ROOT / "artifacts" / "society"


def load_society(key: str) -> tuple[pd.Series, pd.DataFrame]:
    d = pd.read_csv(PROCESSED / key / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
    return d["society_kwh"].rename("demand_kw"), d[["airTemperature", "dewTemperature", "windSpeed"]]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--societies", nargs="*", help="community keys (default: all bundled communities)")
    ap.add_argument("--force", action="store_true", help="rebuild a bundle that already exists")
    args = ap.parse_args()

    index = json.loads((PROCESSED / "societies.json").read_text())["societies"]
    keys = args.societies or [e["key"] for e in index]
    status = 0
    for key in keys:
        out = ARTIFACTS / key
        if not (out / "evaluation.json").is_file():
            print(f"[{key}] no evaluation.json in {out}; run scripts/society_train.py first", file=sys.stderr)
            status = 1
            continue
        if (out / "bundle.json").is_file() and not args.force:
            print(f"[{key}] bundle already installed - skipped (use --force to rebuild)")
            continue
        guarded = [out / "evaluation.json", *sorted(out.glob("predictions_h*.csv.gz"))]
        before = {p.name: digest(p) for p in guarded}
        series, weather = load_society(key)
        t0 = time.time()
        print(f"[{key}] fitting the deployment models on {int(series.notna().sum()):,} valid hours ...", flush=True)
        build_bundle(key, series, weather, out, log=lambda m, k=key: print(f"[{k}]   {m}", flush=True))
        changed = [p.name for p in guarded if digest(p) != before[p.name]]
        if changed:  # cannot happen by construction; fail loudly rather than publish altered results
            print(f"[{key}] ERROR: evaluation files changed: {changed}", file=sys.stderr)
            return 2
        print(f"[{key}] done in {time.time() - t0:.0f} s; evaluation files unchanged", flush=True)
    return status


if __name__ == "__main__":
    sys.exit(main())
