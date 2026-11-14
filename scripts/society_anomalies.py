"""Detect anomalies for every society (society total plus each building) and save them.

    python scripts/society_anomalies.py [--societies fox rat] [--sensitivity medium]

Writes artifacts/society/<key>/anomalies.json. Alert counts depend on the sensitivity parameter; there are
no ground-truth labels, so no accuracy is claimed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_engine.society.anomalies import detect_society  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processed", type=Path, default=ROOT / "data/society/processed")
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/society")
    ap.add_argument("--societies", nargs="*")
    ap.add_argument("--sensitivity", default="medium", choices=["low", "medium", "high"])
    a = ap.parse_args()
    index = json.loads((a.processed / "societies.json").read_text())["societies"]
    for key in a.societies or [s["key"] for s in index]:
        soc = pd.read_csv(a.processed / key / "society_hourly.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
        meters = pd.read_csv(a.processed / key / "meters_hourly_kwh.csv.gz", parse_dates=["timestamp"], index_col="timestamp")
        res = detect_society(soc["society_kwh"], meters, soc.get("airTemperature"), a.sensitivity)
        (a.out / key).mkdir(parents=True, exist_ok=True)
        (a.out / key / "anomalies.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
        s = res["society_summary"]
        print(f"{key}: society events {s['events']} ({s['events_by_severity']}), "
              f"building events {sum(1 for e in res['events'] if e['scope'] == 'building')}, society flagged {s['flagged_pct_of_valid']:.2f}% of valid hours", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
